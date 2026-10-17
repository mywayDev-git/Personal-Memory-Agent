from evaluation.query_paired import ARMS
from evaluation.query_paired_selective import changed_pairs


def result():
    return dict(
        arms={
            label: dict(
                metrics={stage: dict(hits=[True, False]) for stage in ("selected", "delivered")},
                selected=[dict(id=label)],
            )
            for label in ARMS
        }
    )


def test_rank_or_irrelevant_evidence_change_requests_answers_but_legacy_does_not():
    assert changed_pairs(result()) == list("VMGH")
    assert changed_pairs(result(), "gold") == []


def test_changing_which_required_fact_was_found_counts_even_at_equal_recall():
    entry = result()
    entry["arms"]["V1"]["metrics"]["selected"]["hits"] = [False, True]
    assert changed_pairs(entry, "gold") == ["V"]


def test_context_recovery_and_regression_both_select_the_pair():
    entry = result()
    entry["arms"]["G1"]["metrics"]["delivered"]["hits"] = [True, True]
    entry["arms"]["M1"]["metrics"]["selected"]["hits"] = [False, False]
    assert changed_pairs(entry, "gold") == ["M", "G"]


def test_same_order_with_changed_time_or_source_context_is_selected():
    entry = result()
    for arm in entry["arms"].values():
        arm["selected"] = [dict(id="V0")]
    assert changed_pairs(entry) == []
    entry["arms"]["V1"]["selected"] = [dict(id="V0", source_text="정정된 날짜")]
    assert changed_pairs(entry) == ["V"]


def test_method_change_without_decomposition_change_also_compares_baseline():
    entry = result()
    for arm in entry["arms"].values():
        arm["selected"] = [dict(id="same")]
    entry["arms"]["G0"]["selected"] = [dict(id="graph")]
    entry["arms"]["G1"]["selected"] = [dict(id="graph")]
    assert changed_pairs(entry) == ["V", "G"]
    assert changed_pairs(entry, "gold") == []
