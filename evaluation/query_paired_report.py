"""Read-only analysis of saved paired trials; writes derived reports, never calls models."""

import argparse
import csv
import hashlib
import html
import json
from collections import Counter
from pathlib import Path
from statistics import median

from evaluation.query_paired import ARMS, LABELS


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def percentile(values, fraction):
    values = sorted(values)
    return values[min(len(values) - 1, int((len(values) - 1) * fraction))] if values else None


def summarize(entries, expected_count):
    complete = [e for e in entries if e.get("status") == "complete" and set(e["arms"]) == set(ARMS)]
    scored = [e for e in complete if not e["excluded"]]
    result = dict(
        expected_cases=expected_count,
        saved_cases=len(entries),
        complete_cases=len(complete),
        scored_cases=len(scored),
        excluded_cases=[e["case"] for e in complete if e["excluded"]],
        failed_cases=[e["case"] for e in entries if e not in complete],
        missing_cases=expected_count - len(entries),
        analysis_attempted=len(complete),
        analysis_valid=sum(e["analysis"]["status"] == "ok" for e in complete),
        analysis_fallback_reasons=dict(
            Counter(
                e["analysis"].get("reason", "unknown")
                for e in complete
                if e["analysis"]["status"] != "ok"
            )
        ),
        arms=[],
        pairs=[],
    )
    elapsed = [e["analysis_seconds"] for e in complete]
    result["analysis_median_seconds"] = median(elapsed) if elapsed else None
    result["analysis_p95_seconds"] = percentile(elapsed, 0.95)
    result["answer_errors"] = [
        dict(case=e["case"], arm=label, error=t)
        for e in complete
        for label, arm in e["arms"].items()
        for t in arm.get("answer_trace", [])
        if t["stage"] == "error"
    ]
    result["answer_reuse_count"] = sum(
        "answer_reused_from" in arm for e in complete for arm in e["arms"].values()
    )
    result["answer_results_available"] = sum(
        "response" in arm for e in complete for arm in e["arms"].values()
    )
    result["answer_not_run"] = len(complete) * len(ARMS) - result["answer_results_available"]
    result["model_calls"] = sum(len(e.get("calls", [])) for e in entries)
    result["call_errors"] = sum(c["status"] != "ok" for e in entries for c in e.get("calls", []))
    result["vector_counts"] = [
        dict(
            case=e["case"],
            single=len(
                e["frozen_memories"] and [m for group in e["frozen_memories"] for m in group]
            ),
            multi=e["vector_count"],
            multi_bytes=e["vector_bytes"],
        )
        for e in complete
    ]
    for split in ["all", "regression", "development", "holdout"]:
        values = [e for e in scored if split == "all" or e["split"] == split]
        if not values:
            continue
        for label in ARMS:
            arms = [e["arms"][label] for e in values]
            search = [a["search_with_analysis_seconds"] for a in arms]
            effective = [
                a["search_with_analysis_seconds"] + a["answer_seconds"]
                for a in arms
                if "response" in a and "answer_seconds" in a
            ]
            result["arms"].append(
                dict(
                    split=split,
                    arm=label,
                    cases=len(arms),
                    candidate_all=sum(a["metrics"]["candidates"]["all_required"] for a in arms),
                    selected_all=sum(a["metrics"]["selected"]["all_required"] for a in arms),
                    delivered_all=sum(a["metrics"]["delivered"]["all_required"] for a in arms),
                    mean_selected_precision=sum(a["metrics"]["selected"]["precision"] for a in arms)
                    / len(arms),
                    search_analysis_median_seconds=median(search),
                    search_analysis_p95_seconds=percentile(search, 0.95),
                    effective_answer_median_seconds=median(effective) if effective else None,
                    effective_answer_timed_count=len(effective),
                    answer_statuses=dict(
                        Counter(a.get("response", {}).get("status", "not_run") for a in arms)
                    ),
                )
            )
        for method in "VMGH":

            def metric(e, enabled, stage):
                return e["arms"][f"{method}{enabled}"]["metrics"][stage]["all_required"]

            for stage in ("candidates", "selected", "delivered"):
                gains = [
                    e["case"] for e in values if metric(e, 1, stage) and not metric(e, 0, stage)
                ]
                harms = [
                    e["case"] for e in values if metric(e, 0, stage) and not metric(e, 1, stage)
                ]
                result["pairs"].append(
                    dict(
                        split=split,
                        method=method,
                        stage=stage,
                        gains=gains,
                        harms=harms,
                        unchanged=len(values) - len(gains) - len(harms),
                    )
                )
    return result


def report(out, expected_count=118):
    entries = []
    for path in sorted((out / "results").glob("*.json")):
        entry = load(path)
        overlay_path = out / "selective_answers" / path.name
        if overlay_path.exists():
            overlay = load(overlay_path)
            if overlay["result_sha256"] != hashlib.sha256(path.read_bytes()).hexdigest():
                raise ValueError("SELECTIVE_ANSWER_SOURCE_CHANGED")
            for label, value in overlay["arms"].items():
                arm = entry["arms"][label]
                if "response" not in arm:
                    arm.update(
                        response=value["response"],
                        answer_trace=value["answer_trace"],
                        answer_seconds=value["seconds"],
                    )
                arm["selective_answer"] = True
            entry["calls"].extend(overlay["calls"])
        entries.append(entry)
    summary = summarize(entries, expected_count)
    (out / "paired-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (out / "paired-comparison.csv").open("w", encoding="utf-8-sig", newline="") as f:
        if summary["arms"]:
            writer = csv.DictWriter(f, fieldnames=list(summary["arms"][0]))
            writer.writeheader()
            writer.writerows(summary["arms"])

    def esc(x):
        return html.escape(str(x))

    page = [
        "<!doctype html><html lang='ko'><meta charset='utf-8'><title>전체 질문 분해 비교</title>",
        "<style>body{font:16px/1.6 system-ui;max-width:1200px;margin:32px auto;padding:16px}"
        "table{border-collapse:collapse;width:100%;margin:20px 0}td,th{border:1px solid #ccc;padding:8px;text-align:left}"
        "pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f5f7;padding:14px}summary{cursor:pointer}</style>",
        "<h1>전체 질문 분해: 4개 검색 방식 × 적용·미적용</h1>",
        f"<p>완료 {summary['complete_cases']}/{expected_count}질문. 채점 {summary['scored_cases']}질문, "
        f"제외 {esc(summary['excluded_cases'])}. 전체 질문에 분해를 시도했으며 형식 검증 통과 "
        f"{summary['analysis_valid']}건. 형식 통과는 의미 정확도가 아닙니다.</p>",
        "<p>0 = 분해 미적용, 1 = 모든 질문에 분해 시도. 실패하면 원래 질문으로 검색하며 전체 집계에 포함합니다. "
        "각 조건은 같은 추출 기억·원문·질문과 동일한 답변 모델, 최대 8개 기억·6000토큰 근거 예산을 사용합니다.</p>",
        "<p>V: 문장 벡터·키워드. M: 기억 내용·역할을 유지한 사실 표현·근거별 벡터의 최대 유사도. "
        "G: 벡터 없는 규칙 기반 시작점 선택 및 인물·대상 공유 그래프의 최대 2단계 확장. "
        "H: M과 G의 순위 결합. G는 완전한 의미 그래프 매칭 구현이 아니며 공유 이름은 동일 인물의 확정이 아닙니다.</p>",
        "<p>필수 근거 전체 포함은 검색 지표이며 답변 정확도가 아닙니다. 전달 단계에는 기존 답변기의 주변 문맥도 포함되어 "
        "선택 단계보다 수치가 높을 수 있습니다. 분해 비용은 1 조건에만 더합니다. "
        "벡터는 공통 캐시를 사용하며 준비 비용은 별도입니다. 동일 답변 입력은 출처를 남겨 공유하므로 "
        "반복 생성의 안정성을 측정한 실험이 아닙니다. 답변 오류와 미검토 답변을 성공으로 계산하지 않습니다.</p>",
    ]
    if (out / "resume-imports.json").exists():
        page.append(
            "<p><strong>사용자 선택에 따라 전체 질문은 검색 비교하고, 선택/전달 단계의 필수 근거 회수 상태가 "
            "분해 전후 달라진 쌍만 추가 답변 비교했습니다.</strong> 이미 완료된 답변은 보존했습니다. "
            f"답변 결과 {summary['answer_results_available']}조건, 미실행 {summary['answer_not_run']}조건. "
            "순위나 불필요 근거만 달라진 경우는 추가 답변 대상에서 제외했습니다. "
            "따라서 전체 답변 정확도나 조건별 답변 성공률로 해석할 수 없습니다.</p>"
        )
    for split in ("all", "regression", "development", "holdout"):
        page.append(
            f"<h2>{esc(split)}</h2><table><tr><th>조건</th><th>질문 수</th><th>후보 전체 근거</th>"
            "<th>선택 전체 근거</th><th>전달 전체 근거</th><th>검색+분해 중앙값(초)</th></tr>"
        )
        for row in summary["arms"]:
            if row["split"] == split:
                values = [
                    LABELS[row["arm"][0]] + " " + row["arm"],
                    row["cases"],
                    row["candidate_all"],
                    row["selected_all"],
                    row["delivered_all"],
                    round(row["search_analysis_median_seconds"], 3),
                ]
                page.append("<tr>" + "".join(f"<td>{esc(v)}</td>" for v in values) + "</tr>")
        page.append("</table>")
    page.append(
        "<h2>분해로 개선·악화된 질문</h2><pre>"
        + esc(json.dumps(summary["pairs"], ensure_ascii=False, indent=2))
        + "</pre>"
    )
    page.append(
        "<h2>분해 실패·답변 오류</h2><pre>"
        + esc(
            json.dumps(
                {
                    k: summary[k]
                    for k in (
                        "analysis_fallback_reasons",
                        "analysis_median_seconds",
                        "answer_errors",
                        "failed_cases",
                        "missing_cases",
                    )
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        + "</pre>"
    )
    notes_path = out / "manual-notes.json"
    if notes_path.exists():
        notes = load(notes_path)
        verified = [
            n
            for n in notes["observations"]
            if n.get("result_sha256")
            == hashlib.sha256((out / "results" / (n["case"] + "--0.json")).read_bytes()).hexdigest()
        ]
        page.append(
            "<h2>일부 사례의 원문 대조 관찰</h2><p>"
            + esc(notes["scope"])
            + "</p><pre>"
            + esc(json.dumps(verified, ensure_ascii=False, indent=2))
            + "</pre>"
        )
    imports_path = out / "frozen-imports.json"
    if imports_path.exists():
        page.append(
            "<details><summary>동결 추출 재사용 출처·준비 비용 제한</summary><pre>"
            + esc(json.dumps(load(imports_path), ensure_ascii=False, indent=2))
            + "</pre></details>"
        )
    selection_path = out / "answer-selection.json"
    if selection_path.exists():
        page.append(
            "<details><summary>추가 답변 비교 대상과 선정 규칙</summary><pre>"
            + esc(json.dumps(load(selection_path), ensure_ascii=False, indent=2))
            + "</pre></details>"
        )
    review_path = out / "selective-review.json"
    if review_path.exists():
        review = load(review_path)
        for row in review["cases"]:
            source = out / "selective_answers" / (row["case"] + "--0.json")
            if hashlib.sha256(source.read_bytes()).hexdigest() != row["answer_sha256"]:
                raise ValueError("REVIEWED_ANSWER_CHANGED")
        page.append(
            "<h2>선별한 6개 질문의 원문 대조</h2><p>"
            + esc(review["scope"])
            + "</p><pre>"
            + esc(json.dumps(review["cases"], ensure_ascii=False, indent=2))
            + "</pre>"
        )
    for entry in entries:
        detail = dict(
            question=entry["question"],
            expected=entry.get("expected"),
            records=entry.get("records"),
            analysis=entry.get("analysis"),
            arms={
                k: dict(
                    response=a.get("response"),
                    trace=a.get("answer_trace"),
                    queries=a.get("trace", {}).get("queries"),
                    metrics=a["metrics"],
                    reused_from=a.get("answer_reused_from"),
                )
                for k, a in entry["arms"].items()
            },
        )
        page.append(
            f"<details><summary>{esc(entry['case'])} — {esc(entry['question'])}</summary><pre>"
            + esc(json.dumps(detail, ensure_ascii=False, indent=2))
            + "</pre></details>"
        )
    page.append("</html>")
    (out / "paired-report.html").write_text("".join(page), encoding="utf-8")
    print(
        json.dumps(
            {k: v for k, v in summary.items() if k not in {"vector_counts", "pairs"}},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--expected-count", type=int, default=118)
    args = parser.parse_args()
    report(args.run_dir, args.expected_count)
