from evaluation.query_paired import ARMS
from evaluation.query_paired_report import summarize


def result(case, excluded=False, valid=True):
    return dict(
        case=case,
        status="complete",
        excluded=excluded,
        split="holdout",
        analysis=dict(status="ok" if valid else "fallback", reason="analysis_relation"),
        analysis_seconds=2,
        frozen_memories=[[]],
        vector_count=0,
        vector_bytes=0,
        arms={
            label: dict(
                metrics={
                    stage: dict(all_required=False, precision=0)
                    for stage in ("candidates", "selected", "delivered")
                },
                search_with_analysis_seconds=2.1 if label[1] == "1" else 0.1,
                response=dict(status="insufficient_evidence"),
                answer_trace=[],
            )
            for label in ARMS
        },
    )


def test_report_keeps_failed_missing_excluded_and_fallback_distinct():
    included = result("one", valid=False)
    excluded = result("excluded", excluded=True)
    failed = dict(case="failure", status="failed", arms={})
    report = summarize([included, excluded, failed], 4)
    assert report["complete_cases"] == 2
    assert report["scored_cases"] == 1
    assert report["failed_cases"] == ["failure"]
    assert report["missing_cases"] == 1
    assert report["analysis_valid"] == 1
    assert report["analysis_fallback_reasons"] == {"analysis_relation": 1}
    assert all(a["cases"] == 1 for a in report["arms"])


def test_context_gain_is_not_counted_as_selection_gain():
    entry = result("context-only")
    entry["arms"]["V1"]["metrics"]["delivered"]["all_required"] = True
    entry["arms"]["V1"]["answer_trace"] = [dict(stage="error", error="Timeout")]
    report = summarize([entry], 1)
    selected = next(
        p
        for p in report["pairs"]
        if p["split"] == "all" and p["method"] == "V" and p["stage"] == "selected"
    )
    delivered = next(
        p
        for p in report["pairs"]
        if p["split"] == "all" and p["method"] == "V" and p["stage"] == "delivered"
    )
    assert selected["gains"] == []
    assert delivered["gains"] == ["context-only"]
    assert len(report["answer_errors"]) == 1
