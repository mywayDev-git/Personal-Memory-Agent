"""Read-only reporting of source-reviewed retrieval experiments; never calls a model."""

import argparse
import csv
import hashlib
import html
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from evaluation.query_tree import coverage, digest
from pma.grounding import claims_supported

LABELS = {
    "A": "기존 검색",
    "B": "의미 제외·LLM 선택 제거",
    "C": "B + 질문 분해",
    "D": "C + 주제 트리",
    "E": "C + 원문 검색",
    "F": "D + 원문·문맥 확장",
}
JUDGMENTS = {"correct", "wrong", "appropriate_abstention", "excessive_abstention", "needs_review"}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def mechanism(arm):
    """Observed terminal stage, not an inferred causal explanation."""
    trace = arm.get("answer_trace", [])
    if arm.get("response", {}).get("status") == "answered":
        return "answered"
    if not arm["selected"]:
        return "retrieval_empty"
    error = next((t for t in trace if t["stage"] == "error"), None)
    if error:
        return "answer_error:" + error["error"]
    draft = next((t["response"] for t in trace if t["stage"] == "draft"), None)
    if draft and draft.get("status") == "insufficient_evidence":
        return "generation_abstention"
    if any(t["stage"] == "verify" and not t["supported"] for t in trace):
        guard_passed = claims_supported(draft["items"], arm["selected"])
        return "model_verification_rejection" if guard_passed else "code_attribute_rejection"
    return "unclassified"


def context_only_support(arm, gold):
    """Whether required source spans are present only through cited surrounding context."""
    if not gold or not arm["response"]["items"]:
        return False
    ids = {key for item in arm["response"]["items"] for key in item["citations"]}
    cited = [n for n in arm["selected"] if n["id"] in ids]
    direct = [
        dict(
            n,
            spans=[
                dict(record=n["record_no"], start=e["start"], end=e["end"]) for e in n["evidence"]
            ],
        )
        for n in cited
    ]
    return coverage(cited, gold)["all_required"] and not coverage(direct, gold)["all_required"]


def build(run, strict=False):
    manifest = read(run / "manifest.json")
    drift = [
        name
        for name, sha in manifest["files"].items()
        if not Path(name).exists() or hashlib.sha256(Path(name).read_bytes()).hexdigest() != sha
    ]
    if drift:
        raise ValueError(f"Frozen inputs changed: {drift}")
    reviews = read(run / "reviews.json") if (run / "reviews.json").exists() else []
    reviewed = {}
    for review in reviews:
        key = (review["case"], review["scale"], review["condition"])
        if key in reviewed or review["judgment"] not in JUDGMENTS or not review.get("reason"):
            raise ValueError(f"Invalid or duplicate review: {key}")
        reviewed[key] = review
    rows, groups, details, completed = [], defaultdict(list), [], set()
    for path in sorted((run / "results").glob("*.json")):
        case = read(path)
        if case["status"] != "complete":
            if strict:
                raise ValueError(f"Failed execution: {path}")
            continue
        completed.add((case["case"], case["scale"]))
        for label in "ABCDEF":
            arm = case["arms"][label]
            key = (case["case"], case["scale"], label)
            review = reviewed.get(key)
            if review and review["response_hash"] != digest(arm["response"]):
                raise ValueError(f"Review does not match response: {key}")
            # A reasoned unresolved judgment is a completed review, never a success.
            if strict and not review:
                raise ValueError(f"Unreviewed response: {key}")
            calls = [
                c for c in case["calls"] if c["stage"] in {f"search-{label}", f"answer-{label}"}
            ]
            row = dict(
                case=case["case"],
                scale=case["scale"],
                condition=label,
                question=case["question"],
                expected=case["expected"],
                judgment=review["judgment"] if review else "needs_review",
                reason=review["reason"] if review else "미검토",
                error_kind=review.get("error_kind") if review else None,
                irrelevant_details=bool(review and review.get("irrelevant_details")),
                citation_context_only=bool(review and review.get("citation_context_only"))
                or context_only_support(arm, case.get("gold")),
                mechanism=mechanism(arm),
                required_spans_delivered=arm["metrics"]["delivered"]["all_required"],
                answer="\n".join(i["text"] for i in arm["response"]["items"]),
                generation_calls=sum(c["endpoint"] == "completions" for c in calls),
                prompt_tokens=sum(c.get("prompt_tokens") or 0 for c in calls),
                completion_tokens=sum(c.get("completion_tokens") or 0 for c in calls),
                seconds=arm["total_seconds"],
            )
            rows.append(row)
            groups[(case["scale"], label)].append(row)
        details.append(case)
    if strict:
        expected = {
            c["id"] for c in read(Path("data/query_tree_cases.json")) if c["split"] == "holdout"
        }
        if {c for c, scale in completed if scale == 0} != expected:
            raise ValueError("Not all 24 held-out cases were executed")
        if set(reviewed) != {(r["case"], r["scale"], r["condition"]) for r in rows}:
            raise ValueError("Extraneous or missing reviews")
    summaries = []
    for (scale, label), values in sorted(groups.items()):
        counts = Counter(r["judgment"] for r in values)
        summaries.append(
            dict(
                scale=scale,
                condition=label,
                cases=len(values),
                **{k: counts[k] for k in sorted(JUDGMENTS)},
                acceptable=counts["correct"] + counts["appropriate_abstention"],
                incomplete_answers=sum(r["error_kind"] == "incomplete_answer" for r in values),
                factual_or_citation_errors=sum(
                    r["judgment"] == "wrong" and r["error_kind"] != "incomplete_answer"
                    for r in values
                ),
                irrelevant_answer_count=sum(r["irrelevant_details"] for r in values),
                context_only_citation_count=sum(r["citation_context_only"] for r in values),
                required_spans_delivered=sum(r["required_spans_delivered"] for r in values),
                generation_calls=sum(r["generation_calls"] for r in values),
                prompt_tokens=sum(r["prompt_tokens"] for r in values),
                completion_tokens=sum(r["completion_tokens"] for r in values),
                median_seconds=float(np.median([r["seconds"] for r in values])),
                p95_seconds=float(np.percentile([r["seconds"] for r in values], 95)),
            )
        )
    shared = [
        c for d in details for c in d["calls"] if not c["stage"].startswith(("search-", "answer-"))
    ]
    metadata = dict(
        strict_review_complete=strict,
        cases=len(details),
        answers=len(rows),
        summaries=summaries,
        shared_generation_calls=sum(c["endpoint"] == "completions" for c in shared),
        shared_prompt_tokens=sum(c.get("prompt_tokens") or 0 for c in shared),
        shared_completion_tokens=sum(c.get("completion_tokens") or 0 for c in shared),
        analysis_fallback=sum(d["analysis"]["status"] != "ok" for d in details),
        limitations=[
            "보조자의 원문 대조이며 독립 평가자 합의가 아님",
            "개발과 병렬인 합성 문장 및 어색한 조사 포함",
            "기존 LLM 답변·검증 공통 경로; 운영 코드 생성 답변 포함 종단 평가 아님",
            "단일 실행이며 반복 안정성은 별도",
        ],
    )
    (run / "answer-audit.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if rows:
        with (run / "answer-audit.csv").open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    table = "".join(
        "<tr>"
        + "".join(
            f"<td>{html.escape(str(s[k]))}</td>"
            for k in [
                "scale",
                "condition",
                "cases",
                "correct",
                "appropriate_abstention",
                "factual_or_citation_errors",
                "incomplete_answers",
                "excessive_abstention",
                "needs_review",
                "required_spans_delivered",
            ]
        )
        + "</tr>"
        for s in summaries
    )
    content = "".join(
        f"<details><summary>{html.escape(r['case'])} · {r['condition']} · {r['judgment']}</summary><p><b>질문:</b> {html.escape(r['question'])}</p><p><b>정답 조건:</b> {html.escape(r['expected'])}</p><p><b>최종 답변:</b> {html.escape(r['answer'] or '(보류)')}</p><p><b>판정:</b> {html.escape(r['reason'])}</p><p>관측된 종료 단계: {r['mechanism']} / 필수 원문 구간 전달: {r['required_spans_delivered']}</p></details>"
        for r in rows
    )
    page = (
        """<!doctype html><html lang="ko"><meta charset="utf-8"><title>보류 평가·최종 답변 검증</title><style>body{font:16px/1.7 system-ui;max-width:1200px;margin:32px auto;padding:16px}table{border-collapse:collapse;width:100%}td,th{padding:8px;border-bottom:1px solid #ccd}details{background:#f3f6fa;margin:10px 0;padding:12px}pre{white-space:pre-wrap}</style><h1>보류 평가·최종 답변 검증</h1><p>답변 원문과 인용 근거를 별도 대조한 결과입니다. 모델 검증 통과를 정답으로 세지 않았습니다. 보조자의 검토이며 독립 평가자 합의가 아닙니다.</p><p>A 기존 검색 · B 별도 혼합 검색 · C 질문 분해 · D 주제 트리 · E 원문 검색 · F 원문·문맥 확장</p><table><tr><th>방해 기록</th><th>조건</th><th>사례</th><th>정답</th><th>적절한 보류</th><th>오답</th><th>과도한 보류</th><th>미검토</th><th>필수 근거 전달</th></tr>"""
        + table
        + "</table><p>필수 근거 전달은 정답률이 아닙니다. 원문 구간이 있어도 요약 오류·잘못된 답변·검증 거절이 발생할 수 있습니다.</p>"
        + content
        + "<h2>비용·한계</h2><p>조건별 시간은 검색·답변·검증을 포함합니다. 공유 질문 분석·구축은 별도입니다. 임베딩 캐시가 있는 측정입니다.</p><pre>"
        + html.escape(json.dumps(metadata, ensure_ascii=False, indent=2))
        + "</pre><p><a href='answer-audit.csv'>답변 판정 CSV</a> · <a href='report.html'>검색·비용·원문 상세 진단</a> · <a href='review-protocol.json'>사전 판정 기준</a></p></html>"
    )
    page = page.replace("<th>오답</th>", "<th>사실·근거 오류</th><th>미완답</th>")
    state = (
        "고정 평가 24개 사례와 모든 최종 응답의 검토 완료"
        if strict
        else "진행 중인 중간 집계 · 최종 결과 아님"
    )
    page = page.replace("<h1>", f"<p><b>{state}</b></p><h1>", 1)
    (run / "answer-audit.html").write_text(page, encoding="utf-8")
    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    if not args.tag.replace("-", "").replace("_", "").isalnum():
        parser.error("Invalid tag")
    print(
        json.dumps(build(Path("output/query-tree-v1") / args.tag, args.strict), ensure_ascii=False)
    )
