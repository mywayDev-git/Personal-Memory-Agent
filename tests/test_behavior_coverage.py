"""Full-variable binding and isolated contract execution; never a main run."""

import json
from pathlib import Path

import pytest

from evaluation.main_suite import catalog, runtime
from evaluation.main_suite.behavior_contracts import contracts, validate_contracts
from evaluation.main_suite.contract_runner import checks_passed, execute_contract_tests


def test_all_365_previous_gaps_have_real_executable_companions():
    values = validate_contracts()
    variables = catalog.read("catalog.json")
    cases = {c["id"]: c for c in catalog.read("scenarios.json")}
    previous = {v["variable_id"] for v in variables if any(cases[c].get("coverage_gaps") and
                not cases[c].get("catalog_only") for c in v["cases"])}
    assert len(values) == 365 and set(values) == previous
    for variable in variables:
        assert variable["automation_status"] == "SCENARIO_CONTRACT"
        if variable["variable_id"] not in values:
            continue
        linked = [cases[c] for c in variable["cases"] if cases[c]["adapter"] == "contract_tests"]
        assert linked and all(c["behavior_contract"] == values[variable["variable_id"]] for c in linked)
        assert all(c["model_accuracy_sample"] is False for c in linked)
        assert {variant for c in linked for variant in c["variable_variants"][variable["variable_id"]]} == {"normal", "boundary"}
    catalog.validate()


def test_behavior_adapter_runs_actual_checks_without_a_model(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "LocalModels", lambda *a: pytest.fail("real model loaded"))
    case = next(c for c in catalog.read("scenarios.json") if c["id"] == "behavior.IN-01.normal")
    result = runtime.execute(case, None, tmp_path / "contract")
    assert result["probe"]["passed"]
    assert len(result["probe"]["checks"]) == 1
    assert all(c["outcome"] == "passed" for c in result["probe"]["checks"])
    assert result["probe"]["model_accuracy_sample"] is False
    report = json.loads(Path(result["probe"]["report"]).read_text("utf-8"))
    assert len(report["checks"]) == 1 and report["exit_code"] == 0


def test_unsupported_feature_is_tested_but_never_reported_as_implemented(tmp_path):
    result = execute_contract_tests(contracts()["IN-08"], tmp_path / "unsupported")
    assert result["probe"]["passed"] and result["probe"]["unsupported"]
    assert len(result["probe"]["checks"]) == 1
    assert result["probe"]["support_reference"] == "docs/behavior_test_coverage.md"


def test_arbitrary_test_path_or_code_is_rejected_before_process_start(tmp_path):
    invalid = {**contracts()["IN-01"], "tests": ["../../private.py::test_x"]}
    with pytest.raises(ValueError, match="UNREGISTERED"):
        execute_contract_tests(invalid, tmp_path / "invalid")
    assert not (tmp_path / "invalid").exists()


def test_large_corpus_checks_stay_out_of_core_and_final():
    for profile in ("core", "compare", "final"):
        cases = catalog.select_cases(profile)
        assert all(not (c["adapter"] == "contract_tests" and c["variables"][0].startswith("PF-")
                        and 3 <= int(c["variables"][0].split("-")[1]) <= 11) for c in cases)
    assert any(c["id"] == "behavior.PF-06.normal" for c in catalog.select_cases("extended"))


def test_completed_proof_cannot_contain_skipped_or_failed_checks():
    assert checks_passed(0, [{"outcome":"passed"}])
    assert not checks_passed(0, [])
    assert not checks_passed(0, [{"outcome":"skipped"}])
    assert not checks_passed(0, [{"outcome":"failed"}])
    assert not checks_passed(1, [{"outcome":"passed"}])


def test_answer_scope_does_not_certify_the_separate_functional_contract():
    from evaluation.main_suite.grading import grade, summary
    from tests.test_main_suite import observation, product_case
    case = product_case()
    case.update(accepted_answers=["정확도는 0.89입니다."], coverage_gaps=["별도 화면 검사"], behavior_case_ids=["behavior.UI-01.normal"])
    result = grade(case, observation())
    assert result["verdict"] == "PASS"
    assert result["evaluation"]["coverage_complete"] is False
    rows = [{**result, "adapter":"product", "family":"answer"},
            {"verdict":"FAIL", "trial_id":"ui", "adapter":"contract_tests", "family":"ui", "evaluation":{}}]
    assert summary(rows, 2)["functional_failures"] == ["ui"]
