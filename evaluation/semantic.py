"""Deterministic expectation checks, explicitly not a semantic correctness score."""

from collections import Counter


def check_expected(expected, result):
    if result is None:
        return {"status": "not_evaluated", "checks": {}, "human_review_required": True}
    memories = result["memories"]
    checks = {}
    if "min_memory_count" in expected:
        checks["min_memory_count"] = len(memories) >= expected["min_memory_count"]
    if "max_memory_count" in expected:
        checks["max_memory_count"] = len(memories) <= expected["max_memory_count"]
    if "memory_types_any_order" in expected:
        checks["memory_types_any_order"] = Counter(m["memory_type"] for m in memories) == Counter(
            expected["memory_types_any_order"]
        )
    return {
        "status": "fail" if False in checks.values() else "partial" if checks else "not_evaluated",
        "checks": checks,
        "human_review_required": True,
        "unautomated_expectations": [k for k in expected if k not in checks],
    }
