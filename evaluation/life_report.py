"""Readable synthetic evaluation report, with separate automatic and semantic review."""

import argparse
import html
import json
from collections import Counter
from pathlib import Path

from evaluation.life_diagnostics import digest, summarize, write_json

STAGES = {
    "extraction",
    "query_interpretation",
    "retrieval",
    "relationship",
    "answer",
    "unconfirmed",
}


def load(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def signature(entry):
    response = entry.get("response", {})
    sources = {r["id"]: entry["source_ids"][r["record_id"]] for r in response.get("results", [])}
    return (
        response.get("status"),
        sorted(
            (item["text"], tuple(sorted(sources.get(cid, "unknown") for cid in item["citations"])))
            for item in response.get("items", [])
        ),
    )


def apply_reviews(entries, reviews):
    by_id = {e["run_id"]: e for e in entries}
    if len({r["run_id"] for r in reviews}) != len(reviews):
        raise ValueError("Duplicate semantic reviews")
    for review in reviews:
        if review["run_id"] not in by_id or review["verdict"] not in {
            "correct",
            "incorrect",
            "unclear",
        }:
            raise ValueError("Invalid semantic review")
        if (
            review["failure_stage"] not in STAGES
            or not review["reviewer"]
            or not review["rationale"]
        ):
            raise ValueError("Review needs attribution, evidence and a valid failure stage")
        entry = by_id[review["run_id"]]
        assessment = entry.setdefault("assessment", {})
        assessment.update(
            semantic_correct={"correct": True, "incorrect": False, "unclear": None}[
                review["verdict"]
            ],
            semantic_review=review,
            failure_stage=review["failure_stage"],
        )


def report(dataset, directory):
    dataset = dataset or directory / "dataset.json"
    manifest = load(directory / "manifest.json", {})
    if not manifest.get("synthetic_only") or digest(dataset) != manifest.get("dataset_sha256"):
        raise ValueError("REPORT_DATASET_VERSION_MISMATCH")
    data = json.loads(dataset.read_text(encoding="utf-8"))
    entries = load(directory / "questions.json", [])
    apply_reviews(entries, load(directory / "semantic_reviews.json", []))
    summary = summarize(data, entries)
    summary["report_code_sha256"] = digest(Path(__file__))
    summary["semantic_review_count"] = sum(
        isinstance(e.get("assessment", {}).get("semantic_review"), dict) for e in entries
    )
    summary["semantic_verdicts"] = dict(
        Counter(
            e["assessment"]["semantic_review"]["verdict"]
            for e in entries
            if isinstance(e.get("assessment", {}).get("semantic_review"), dict)
        )
    )
    summary["review_sampling_note"] = (
        "직접 검토한 사례는 오류 신호를 중심으로 선택했으므로 전체 정확도로 환산하지 않습니다."
    )
    extraction = load(directory / "extractions.json", {})
    summary["extraction"] = dict(
        expected=300,
        executed=len(extraction),
        statuses=dict(Counter(r["status"] for r in extraction.values())),
        missing=[r["id"] for r in data["records"] if r["id"] not in extraction],
    )
    lifecycle = load(directory / "lifecycle.json", [])
    summary["lifecycle"] = dict(
        expected_events=40,
        executed_events=len(lifecycle),
        missing=[
            e["id"] for e in data["events"] if e["id"] not in {r["event_id"] for r in lifecycle}
        ],
        dismissal_not_exercised=[r["event_id"] for r in lifecycle if not r["dismissed_count"]],
    )
    paired = {e["run_id"]: e for e in entries}
    summary["order_comparisons"] = []
    summary["order_comparison_note"] = (
        "재생 DB의 UUID도 새로 생성됩니다. 결과 차이는 순서만의 인과 효과로 단정하지 않고 안정성 신호로 검토합니다."
    )
    summary["growth_comparisons"] = []
    for case in data["questions"]:
        if not case["repeat_at_snapshots"]:
            continue
        for before, after in ((30, 100), (100, 300)):
            first = paired.get(f"forward-{before}-{case['id']}")
            last = paired.get(f"forward-{after}-{case['id']}")
            if first and last:
                summary["growth_comparisons"].append(
                    dict(
                        question_id=case["id"],
                        before=before,
                        after=after,
                        expected_support_changed=first["expected"]["available_support"]
                        != last["expected"]["available_support"],
                        same_answer_and_sources=signature(first) == signature(last),
                        semantic_invariance="requires_review",
                    )
                )
    for e in entries:
        if e["variant"] != "reverse":
            continue
        forward = paired.get("forward-300-" + e["id"])
        if forward:
            summary["order_comparisons"].append(
                dict(
                    question_id=e["id"],
                    same_answer_and_sources=signature(e) == signature(forward),
                    semantic_invariance="requires_review",
                )
            )
    summary["complete_execution"] = (
        not summary["missing"]
        and not summary["duplicates"]
        and not summary["unexpected"]
        and not summary["extraction"]["missing"]
        and not summary["lifecycle"]["missing"]
    )
    write_json(directory / "review_summary.json", summary)

    def escape(value):
        return html.escape(str(value))

    cards = []
    for entry in entries:
        response = entry.get("response", {})
        expected = entry["expected"]
        answers = "\n".join(item["text"] for item in response.get("items", []))
        facts = "\n".join(f["quote"] for f in expected["supporting_facts"])
        signal = entry.get("assessment", {}).get("signal", entry.get("error_type", "unknown"))
        detail = dict(
            assessment=entry.get("assessment"),
            understood=entry.get("understood"),
            query_plan=response.get("query_plan"),
            results=response.get("results"),
            items=response.get("items"),
            elapsed_seconds=entry["elapsed_seconds"],
        )
        cards.append(
            f"<details><summary>{escape(entry['run_id'])} · {escape(signal)} · {escape(entry['question'])}</summary>"
            f"<p>기대 상태: {escape(expected['mode'])} / 응답 상태: {escape(response.get('status'))}</p>"
            f"<h3>기대 근거</h3><pre>{escape(facts or '판단 보류 또는 단서 확인 필요')}</pre>"
            f"<h3>실제 답변</h3><pre>{escape(answers or '답변 없음')}</pre>"
            f"<h3>검색·답변 진단</h3><pre>{escape(json.dumps(detail, ensure_ascii=False, indent=2))}</pre></details>"
        )
    body = """<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>누적 생활 기록 평가</title><style>body{max-width:1100px;margin:32px auto;padding:0 20px;font-family:system-ui;line-height:1.6;color:#172b35;background:#f7f9fa}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#edf1f3;padding:12px}details{background:white;padding:14px;margin:10px 0;border:1px solid #ccd6dc;border-radius:8px}summary{cursor:pointer}input{width:95%;padding:12px;font:inherit}h3{margin-bottom:0}</style>
<h1>누적 생활 기록 평가</h1><p>가상 데이터 전용. 자동 근거 검사는 답변의 의미 정확도가 아닙니다. 미실행·검토 대기는 통과로 계산하지 않습니다.</p>
"""
    body += f"<p>추출 {len(extraction)}/300 · 질문 {summary['executed']}/{summary['planned']} · 수명주기 {len(lifecycle)}/40 사건</p>"
    body += f"<details><summary>분류별 집계와 미실행 목록</summary><pre>{escape(json.dumps(summary, ensure_ascii=False, indent=2))}</pre></details>"
    notes = load(Path(__file__).resolve().parents[1] / "data/life_evaluation_notes.json", {})
    body += f"<details><summary>발견한 문제와 다음 개선 지점</summary><pre>{escape(json.dumps(notes, ensure_ascii=False, indent=2))}</pre></details>"
    body += '<label for="filter">질문·결과 검색</label><input id="filter" placeholder="예: E01, missing_expected_evidence, direct">'
    body += '<p><a href="questions.json">전체 질문 실행 기록 JSON</a> · <a href="extractions.json">추출 결과 JSON</a></p>'
    body += "".join(cards)
    body += """<script>document.getElementById('filter').addEventListener('input',e=>{const q=e.target.value.toLowerCase();document.querySelectorAll('details').forEach(d=>d.hidden=!d.textContent.toLowerCase().includes(q))});</script></html>"""
    (directory / "report.html").write_text(body, encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, help="Defaults to the immutable run snapshot")
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    result = report(args.dataset, args.run_dir)
    print(
        json.dumps(
            {
                "executed": result["executed"],
                "planned": result["planned"],
                "complete_execution": result["complete_execution"],
            }
        )
    )


if __name__ == "__main__":
    main()
