"""Denominator-aware CSV/HTML reports, including missing and failed executions."""

import argparse
import csv
import html
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from .kiwi_scoring import apply_reviews, prf


def read_entries(directory):
    entries = []
    for path in sorted((directory / "completed").glob("*.json")):
        entries.append(json.loads(path.read_text(encoding="utf-8")))
    return entries


def average(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def report(directory, reviews=None):
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    entries = read_entries(directory)
    expected_ids = {j["run_id"] for j in manifest["schedule"]}
    if len({e["run_id"] for e in entries}) != len(entries) or any(
        e["run_id"] not in expected_ids for e in entries
    ):
        raise ValueError("UNKNOWN_OR_DUPLICATE_RESULT")
    if reviews:
        apply_reviews(entries, json.loads(reviews.read_text(encoding="utf-8")))
    by_id = {e["run_id"]: e for e in entries}
    groups = defaultdict(list)
    for job in manifest["schedule"]:
        e = by_id.get(job["run_id"], {**job, "status": "not_executed", "answers": []})
        groups[(job["arm"], job["category"], job["phase"])].append(e)
        groups[(job["arm"], "ALL", job["phase"])].append(e)
    summary = []
    for (arm, category, phase), rows in sorted(groups.items()):
        times = sorted(r["seconds"] for r in rows if "seconds" in r)
        assessments = [a["assessment"] for r in rows for a in r.get("answers", [])]
        reviewed = [a for a in assessments if a.get("semantic_verdict")]
        fields = [f for r in rows for f in r.get("extraction_assessment", {}).get("fields", [])]
        event_checks = [
            r["extraction_assessment"]["event_lower_bound"]
            for r in rows
            if r.get("extraction_assessment")
        ]
        relation_checks = [
            r["extraction_assessment"]["relation_specified_checks"]
            for r in rows
            if r.get("extraction_assessment") and arm != "L"
        ]
        question_checks = [
            r["extraction_assessment"]["clarification_checks"]
            for r in rows
            if r.get("extraction_assessment") and arm != "L"
        ]

        def aggregate(checks):
            return prf(
                sum(c["tp"] for c in checks),
                sum(c["predicted"] for c in checks),
                sum(c["expected"] for c in checks),
            )

        event_metric = aggregate(event_checks)
        relation_metric = aggregate(relation_checks)
        question_metric = aggregate(question_checks)
        summary.append(
            dict(
                arm=arm,
                category=category,
                phase=phase,
                planned=len(rows),
                completed=sum(r["status"] == "complete" for r in rows),
                failed=sum(r["status"] == "failed" for r in rows),
                not_executed=sum(r["status"] == "not_executed" for r in rows),
                expected_answers=sum(r.get("question_count", 3) for r in rows),
                executed_answers=len(assessments),
                reviewed_answers=len(reviewed),
                semantic_accuracy=average(
                    [
                        a["semantic_verdict"] in {"correct", "appropriate_abstention"}
                        for a in reviewed
                    ]
                ),
                evidence_recall=average([a["evidence_recall"] for a in assessments]),
                appropriate_abstention=average([a["appropriate_abstention"] for a in assessments]),
                field_checks=len(fields),
                field_accuracy=average([f["correct"] for f in fields]),
                wrong_resolution=sum(f["wrong_resolution"] for f in fields),
                unnecessary_abstention=sum(f["unnecessary_abstention"] for f in fields),
                aligned_events=sum(c["tp"] for c in event_checks),
                predicted_events=sum(c["predicted"] for c in event_checks),
                expected_events=sum(c["expected"] for c in event_checks),
                event_precision_lower_bound=event_metric["precision"],
                event_recall_lower_bound=event_metric["recall"],
                event_f1_lower_bound=event_metric["f1"] if event_checks else None,
                relation_precision_partial=relation_metric["precision"],
                relation_recall_partial=relation_metric["recall"],
                relation_f1_partial=relation_metric["f1"] if relation_checks else None,
                clarification_precision=question_metric["precision"],
                clarification_recall=question_metric["recall"],
                alignment_review_count=sum(
                    len(r.get("extraction_assessment", {}).get("review_queue", [])) for r in rows
                ),
                failure_stages=json.dumps(
                    dict(Counter(r.get("failure_stage") for r in rows if r["status"] == "failed"))
                ),
                seconds_median=statistics.median(times) if times else None,
                seconds_p95=times[max(0, (95 * len(times) + 99) // 100 - 1)] if times else None,
                http_calls=sum(len(r.get("calls", [])) for r in rows),
                generation_calls=sum(
                    c["endpoint"] == "completions" for r in rows for c in r.get("calls", [])
                ),
                total_tokens_known=sum(
                    c["total_tokens"] or 0 for r in rows for c in r.get("calls", [])
                ),
                token_usage_missing=sum(
                    c["total_tokens"] is None
                    for r in rows
                    for c in r.get("calls", [])
                    if c["endpoint"] != "tokenize"
                ),
                kiwi_seconds=sum(r.get("kiwi_seconds", 0) for r in rows),
                ungrounded_times_removed=sum(
                    len(r.get("extraction", {}).get("validation_issues", [])) for r in rows
                ),
            )
        )
    with (directory / "summary.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary[0]) if summary else ["arm"])
        writer.writeheader()
        writer.writerows(summary)
    comparisons = []
    for with_kiwi, without in [("C", "A"), ("D", "B"), ("G", "E"), ("H", "F")]:
        matching = {r["arm"]: r for r in summary if r["category"] == "ALL" and r["phase"] == "main"}
        if with_kiwi in matching and without in matching:
            a, b = matching[with_kiwi], matching[without]
            comparisons.append(
                dict(
                    pair=f"{with_kiwi}-{without}",
                    field_accuracy_delta=a["field_accuracy"] - b["field_accuracy"]
                    if a["field_accuracy"] is not None and b["field_accuracy"] is not None
                    else None,
                    decision="보류: 전체 실행·의미 검토·누락/보류 변화 확인 필요",
                )
            )
    stability = []
    repeated = defaultdict(list)
    for e in entries:
        if e["phase"] in {"main", "repeat1", "repeat2"} and e["status"] == "complete":
            repeated[(e["arm"], e["case"])].append(e)
    for (arm, case), rows in repeated.items():
        if len(rows) > 1:
            signatures = {
                json.dumps(
                    dict(
                        extraction=r.get("extraction"),
                        answers=[a["response"] for a in r["answers"]],
                    ),
                    ensure_ascii=False,
                    sort_keys=True,
                )
                for r in rows
            }
            stability.append(
                dict(arm=arm, case=case, executions=len(rows), variants=len(signatures))
            )
    review_queue = [
        dict(
            run_id=r["run_id"],
            result_hash=r.get("result_hash"),
            question=i,
            reviewer="",
            rationale="",
            verdict=None,
            source_case=r["case"],
            response=a["response"],
        )
        for r in entries
        for i, a in enumerate(r.get("answers", []))
        if a["assessment"].get("review_required", True)
    ]
    payload = dict(
        summary=summary,
        kiwi_comparisons=comparisons,
        stability=stability,
        complete_execution=len(entries) == len(manifest["schedule"]),
        semantic_review_complete=not review_queue
        and len(entries) == len(manifest["schedule"])
        and all(e["status"] == "complete" for e in entries),
        recommendation="보류: 지표와 원문 검토 후 판단. 자동 문자열 통과를 의미 정답으로 간주하지 않음.",
    )
    for name, data in [("report.json", payload), ("review_queue.json", review_queue)]:
        (directory / name).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    title = "Kiwi + LLM 비교 실험"
    rows_html = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(v))}</td>" for v in row.values()) + "</tr>"
        for row in summary
    )
    details = "".join(
        f"<details><summary>{html.escape(r['run_id'])}: {r['status']}</summary>"
        f"<pre>{html.escape(json.dumps(r, ensure_ascii=False, indent=2))}</pre></details>"
        for r in entries
    )
    (directory / "report.html").write_text(
        f"<!doctype html><html lang='ko'><meta charset='utf-8'><title>{title}</title>"
        "<style>body{font:14px sans-serif;margin:24px}table{border-collapse:collapse}"
        "td,th{border:1px solid #ccc;padding:6px}pre{white-space:pre-wrap}section{overflow:auto}</style>"
        f"<h1>{title}</h1><p>{html.escape(payload['recommendation'])}</p>"
        f"<p>계획 {len(manifest['schedule'])} / 결과 {len(entries)} / 의미 검토 대기 {len(review_queue)}</p>"
        "<section><table><tr>"
        + "".join(f"<th>{k}</th>" for k in summary[0] if summary)
        + "</tr>"
        + rows_html
        + "</table></section>"
        + details
        + "</html>",
        encoding="utf-8",
    )
    return payload


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("directory", type=Path)
    p.add_argument("--reviews", type=Path)
    a = p.parse_args()
    result = report(a.directory, a.reviews)
    print(
        json.dumps(
            {k: result[k] for k in ("complete_execution", "semantic_review_complete")},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
