from __future__ import annotations

from collections import Counter
from statistics import mean
from typing import Any


def dashboard_metrics(cases, results):
    """Independent answer/evidence grades, with explicit eligible denominators."""
    import math

    by_id = {r.case_id: r for r in results}
    pairs = [(c, by_id[c.id]) for c in cases if c.id in by_id]
    eligible = [(c, r) for c, r in pairs if r.verdict in {"pass", "fail", "pending_review"}]
    metrics = {}

    def ratio(name, values):
        values = [v for v in values if v is not None]
        metrics[name] = dict(
            numerator=sum(values),
            denominator=len(values),
            value=sum(values) / len(values) if values else None,
            details={"grading_version": "dashboard-v1"},
        )

    answers = [
        (c, r)
        for c, r in eligible
        if c.answerability == "answerable" and r.evaluation.get("answer_correct") is not None
    ]
    ratio("answer_accuracy", [r.evaluation["answer_correct"] for c, r in answers])
    evidence = []
    complete = []
    for c, r in eligible:
        if c.gold_groups and r.evaluation.get("retrieval_complete") is True:
            retrieved = set(r.evaluation.get("retrieved_ids", [])[:20])
            groups = [bool(retrieved.intersection(ids)) for ids in c.gold_groups.values()]
            evidence.extend(groups)
            complete.append(all(groups))
    ratio("evidence_recall_at_20", evidence)
    ratio("complete_evidence_recall", complete)
    ratio(
        "grounded_answer_success_rate",
        [
            r.evaluation["answer_correct"] and r.evaluation["final_evidence_complete"]
            for c, r in answers
            if r.evaluation.get("final_evidence_complete") is not None
        ],
    )
    ratio(
        "unsupported_claim_rate",
        [
            c["support_status"] == "unsupported"
            for _, r in eligible
            for c in r.claims
            if c["support_status"] in {"supported", "unsupported"}
        ],
    )
    ratio(
        "unnecessary_clarification_rate",
        [
            r.response_behavior == "clarify"
            for c, r in eligible
            if c.expected_behavior == "answer" and r.response_behavior is not None
        ],
    )
    ratio(
        "necessary_clarification_recall",
        [
            r.response_behavior == "clarify"
            for c, r in eligible
            if c.expected_behavior == "clarify" and r.response_behavior is not None
        ],
    )
    ratio(
        "answer_abstention_accuracy",
        [
            r.response_behavior == "abstain"
            for c, r in eligible
            if c.expected_behavior == "abstain" and r.response_behavior is not None
        ],
    )
    for kind in ("temporal", "relation"):
        ratio(
            kind + "_accuracy",
            [r.evaluation["answer_correct"] for c, r in answers if kind in c.question_type],
        )
    latencies = sorted(r.latency_ms for _, r in pairs if r.latency_ms is not None)
    metrics["p95_latency_ms"] = dict(
        numerator=None,
        denominator=None,
        value=latencies[math.ceil(0.95 * len(latencies)) - 1] if latencies else None,
        details={"sample_count": len(latencies), "method": "nearest_rank"},
    )
    for metric in metrics.values():
        metric["status"] = "not_applicable" if metric["value"] is None else "available"
        metric["details"]["missing_cases"] = len(cases) - len(pairs)
    return metrics


def calculate_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    """평가 결과 레코드 목록에서 집계 지표를 계산한다."""
    total = len(records)

    if total == 0:
        return {
            "total": 0,
            "completed": 0,
            "valid_count": 0,
            "invalid_count": 0,
            "valid_rate": 0.0,
            "schema_valid_rate": 0.0,
            "schema_valid_count": 0,
            "evidence_valid_count": 0,
            "evidence_valid_rate": 0.0,
            "avg_latency_seconds": None,
            "error_types": {},
            "finish_reasons": {},
        }

    completed_records = [record for record in records if not record.get("error")]

    valid_count = sum(record.get("valid") is True for record in records)
    schema_valid_count = sum(
        record.get("final_schema_valid", record.get("schema_valid")) is True for record in records
    )
    evidence_valid_count = sum(record.get("evidence_valid") is True for record in records)

    latencies = [
        float(record["latency_seconds"])
        for record in records
        if isinstance(record.get("latency_seconds"), (int, float))
        and not isinstance(record.get("latency_seconds"), bool)
        and record["latency_seconds"] >= 0
    ]

    error_types = Counter()
    finish_reasons = Counter()

    for record in records:
        error = record.get("failure_stage") or record.get("error")
        if error:
            error_types[str(error)] += 1

        finish_reason = record.get("finish_reason")
        if finish_reason:
            finish_reasons[str(finish_reason)] += 1

    return {
        "total": total,
        "completed": len(completed_records),
        "valid_count": valid_count,
        "invalid_count": total - valid_count,
        "valid_rate": valid_count / total,
        "schema_valid_rate": schema_valid_count / total,
        "schema_valid_count": schema_valid_count,
        "evidence_valid_count": evidence_valid_count,
        "evidence_valid_rate": evidence_valid_count / total,
        "avg_latency_seconds": (mean(latencies) if latencies else None),
        "error_types": dict(error_types),
        "finish_reasons": dict(finish_reasons),
    }
