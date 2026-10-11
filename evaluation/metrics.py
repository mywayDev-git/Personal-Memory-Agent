from __future__ import annotations

from collections import Counter
from statistics import mean
from typing import Any


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
            "evidence_valid_rate": 0.0,
            "avg_latency_seconds": None,
            "error_types": {},
            "finish_reasons": {},
        }

    completed_records = [
        record for record in records
        if not record.get("error")
    ]

    valid_count = sum(
        record.get("valid") is True
        for record in records
    )
    schema_valid_count = sum(
        record.get("schema_valid") is True
        for record in records
    )
    evidence_valid_count = sum(
        record.get("evidence_valid") is True
        for record in records
    )

    latencies = [
        float(record["latency_seconds"])
        for record in records
        if isinstance(record.get("latency_seconds"), (int, float))
    ]

    error_types = Counter()
    finish_reasons = Counter()

    for record in records:
        error = record.get("error")
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
        "evidence_valid_rate": evidence_valid_count / total,
        "avg_latency_seconds": (
            mean(latencies) if latencies else None
        ),
        "error_types": dict(error_types),
        "finish_reasons": dict(finish_reasons),
    }