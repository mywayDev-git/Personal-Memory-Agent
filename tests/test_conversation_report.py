from copy import deepcopy

import pytest

from evaluation.conversation_cases import cases
from evaluation.conversation_report import compare, retrieval_metrics, summarize


def sample(passed=True, seconds=1):
    return {
        "id": "fixture",
        "passed": passed,
        "elapsed_seconds": seconds,
        "expected": {"expected_search": True, "records": [{"id": "r", "text": "가상 기록"}]},
        "evidence_ids": ["other", "r", "r"],
        "response": {
            "citation_details": [
                {"memory_id": "m", "record_id": "r", "quote": "가상 기록", "start": 0, "end": 5}
            ]
        },
        "checks": {"exact_citations": True},
    }


def test_metrics_deduplicate_records_and_keep_failure_latency():
    result = retrieval_metrics(sample())
    assert result["recall_at_8"] == 1 and result["reciprocal_rank"] == 0.5
    assert 0 < result["ndcg_at_8"] < 1
    report = summarize({"cases": [sample(), {**sample(False, 9), "id": "failed"}]})
    assert report["fixture_pass_rate"] == 0.5
    assert report["latency_including_failures"]["p50"] == 5
    assert report["successful_latency_p50"] == 1


def test_comparison_rejects_changed_or_missing_fixture():
    report = {"dataset_sha256": "same", "scoring_version": 2, "cases": [sample()]}
    assert compare(report, deepcopy(report))["after"]["fixture_passed"] == 1
    for changed, error in [
        ({**report, "dataset_sha256": "different"}, "DATASET_MISMATCH"),
        ({**report, "cases": []}, "INCOMPLETE_PAIR"),
    ]:
        with pytest.raises(ValueError, match=error):
            compare(report, changed)


def test_recommendation_is_not_misgraded_as_past_completion():
    import re

    pattern = cases()[0]["forbidden_claims"][0]
    assert not re.search(pattern, "Part 2를 완료하는 것이 좋겠어요.")
    assert re.search(pattern, "Part 2를 완료했습니다.")


def test_unreviewed_personal_narrative_cannot_pass_without_citations():
    row = sample()
    row["response"] = {
        "status": "insufficient_evidence",
        "validation": "rejected",
        "items": [{"text": "그럴듯한 개인 사실", "citations": []}],
    }
    assert summarize({"cases": [row]})["fixture_passed"] == 0
