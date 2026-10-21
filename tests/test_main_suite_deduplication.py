"""Offline coverage and execution equivalence checks; never call a model."""

from copy import deepcopy

from evaluation.main_suite import catalog, runner
from evaluation.main_suite.deduplication import consolidate, execution_key
from tests.test_main_suite import product_case


def test_duplicates_merge_variables_without_repeating_the_execution():
    first = product_case()
    second = deepcopy(first)
    second.update(id="other.boundary", family="other", variables=["EX-01"], variant="boundary")
    first["coverage_gaps"] = ["first gap"]
    second["coverage_gaps"] = ["second gap"]
    variables = [{"variable_id": "EV-02", "cases": [first["id"]]},
                 {"variable_id": "EX-01", "cases": [second["id"]]}]
    merged = consolidate([first, second], variables)
    assert len(merged) == 1
    assert merged[0]["variables"] == ["EV-02", "EX-01"]
    assert merged[0]["variable_variants"] == {"EV-02": ["normal"], "EX-01": ["boundary"]}
    assert merged[0]["coverage_gaps"] == ["first gap", "second gap"]
    assert merged[0]["source_case_ids"] == [first["id"], second["id"]]
    assert all(v["cases"] == [first["id"]] for v in variables)
    assert first["variables"] == ["EV-02"], "never mutate the authored source fixture"


def test_same_question_with_different_conditions_never_merges():
    original = product_case()
    variants = []
    for index, field in enumerate(("records", "steps", "required_facts", "expected_behavior", "split", "corpus_size")):
        case = deepcopy(original)
        case["id"] = f"different-{index}"
        if field == "records":
            case[field][0]["text"] = "different synthetic source"
        elif field == "steps":
            case[field].insert(0, {"action": "delete", "record": "target"})
        else:
            case[field] = {"required_facts": ["0.95"], "expected_behavior": "abstain", "split": "final", "corpus_size": 1000}[field]
        variants.append(case)
    assert len(consolidate([original, *variants], [])) == len(variants) + 1


def test_real_inventory_is_unique_and_retains_all_variable_links():
    cases = catalog.read("scenarios.json")
    variables = catalog.read("catalog.json")
    assert len(cases) == len({execution_key(c) for c in cases})
    assert len(cases) < sum(len(c["source_case_ids"]) for c in cases)
    assert {v["variable_id"] for v in variables} == {vid for c in cases for vid in c["variables"]}
    assert catalog.validate()["variables"] == 489


def test_removed_id_remains_a_valid_explicit_case_alias(monkeypatch, capsys):
    monkeypatch.setattr(runner, "servers", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not start models")))
    case = next(c for c in catalog.select_cases("core") if len(c["source_case_ids"]) > 1)
    assert runner.main(["--case", case["source_case_ids"][-1]]) == 0
    assert '"executed": false' in capsys.readouterr().out
