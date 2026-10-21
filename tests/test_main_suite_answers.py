"""Offline authored-answer checks. No actual model calls or main evaluation."""

import json
from contextlib import nullcontext

from evaluation.main_suite import catalog, grading, runner, runtime
from evaluation.main_suite.answer_comparison import compare_answer, normalized
from evaluation.repository import Repository
from tests.test_main_suite import config, observation, product_case


def test_every_catalogue_case_has_a_real_question_and_reference():
    cases = catalog.read("scenarios.json")
    assert cases and all(c["adapter"] != "review" for c in cases)
    migrated = [c for c in cases if c.get("automated_from_review")]
    assert sum(len(c.get("source_case_ids", [c["id"]])) for c in migrated) > 1000
    assert all(c["question"] and c["expected_answer"] and c["steps"] for c in migrated)
    assert all(c["steps"][-1]["action"] in {"chat", "input_contract"} and c["steps"][-1]["question"] == c["question"] for c in migrated)
    assert all(c["coverage_gaps"] for c in migrated if c["variables"][0].startswith("UI-"))
    assert all(not c["model_accuracy_sample"] for c in migrated if c.get("catalog_only"))
    assert all(c["expected_answer"] for c in cases)
    catalog.validate()


def test_exact_comparison_preserves_critical_differences():
    case = {"accepted_answers": ["정확도는 0.89입니다."], "required_facts": ["0.89"], "forbidden_facts": ["0.95"]}
    assert compare_answer(case, "정확도는 0.89입니다.  ")["exact_match"]
    for answer in ("정확도는 089입니다.", "정확도는 0.95입니다.", "정확도는 0.89가 아닙니다.", "정확도는 0.89입니다. 사실은 0.95입니다."):
        assert not compare_answer(case, answer)["exact_match"]
    assert normalized("src/search/router.py") != normalized("src/search/routerpy")
    assert normalized("C++") != normalized("C")
    assert normalized("1 2") != normalized("12")
    assert compare_answer(case, "") ["status"] == "NO_ANSWER"


def test_fact_presence_does_not_certify_a_contradiction():
    case = product_case()
    case.update(expected_answer="정확도는 0.89입니다.", accepted_answers=["정확도는 0.89입니다."])
    result = grading.grade(case, observation("정확도는 0.89가 아니라 0.81입니다."))
    assert result["verdict"] == "PENDING_REVIEW"
    assert result["evaluation"]["answer_comparison"]["required_facts"][0]["status"] == "MATCH"
    assert result["evaluation"]["answer_correct"] is None
    assert grading.grade(case, observation())["verdict"] == "PASS"
    case["coverage_gaps"] = ["모바일 화면의 실제 배치는 미검증"]
    assert grading.grade(case, observation())["verdict"] == "PENDING_REVIEW"
    case["gold_groups"]["extra"] = [{"record_id": "missing", "version": 1, "start": 0, "end": 1, "quote": "x"}]
    assert grading.grade(case, observation())["verdict"] == "FAIL"


def test_runner_persists_reference_actual_and_comparison_without_changing_prior_runs(tmp_path):
    case = product_case()
    case.update(expected_answer="정확도는 0.89입니다.", accepted_answers=["정확도는 0.89입니다."])
    jobs = runner.trials([case], 1, 42)
    _, rows = runner.run_candidate(tmp_path / "good", config(), jobs, nullcontext(None), execute_fn=lambda *a, **k: observation())
    manifest = runner.read_rows(tmp_path / "good/cases.jsonl")
    assert manifest[0]["actual_answer"] == "정확도는 0.89입니다."
    assert rows[0]["evaluation"]["answer_comparison"]["exact_match"]
    repo = Repository(tmp_path / "good/evaluation.db")
    run_id = json.loads((tmp_path / "good/manifest.json").read_text("utf-8"))["run_id"]
    dataset_id = repo.get_run(run_id)["dataset_id"]
    assert repo.cases(dataset_id)[0].expected_answer == case["expected_answer"]
    def failed(*args, **kwargs):
        raise TimeoutError("synthetic secret must not appear in UI")
    _, errors = runner.run_candidate(tmp_path / "error", config(), jobs, nullcontext(None), execute_fn=failed)
    assert errors[0]["verdict"] == "ERROR"
    assert "TimeoutError" in errors[0]["actual_answer"]
    assert "synthetic secret" not in errors[0]["actual_answer"]
    assert errors[0]["evaluation"]["answer_comparison"]["status"] == "EXECUTION_ERROR"


def test_catalogue_diagnostics_are_excluded_from_model_metrics():
    result = grading.summary([{"verdict": "PASS", "family": "coverage", "evaluation": {
        "answer_correct": True, "model_accuracy_sample": False}}], 1)
    assert result["metrics"]["answer_correct"]["denominator"] == 0
    assert result["metrics"]["grounded_answer_success_rate"]["denominator"] == 0
    assert result["families"] == {}


def test_input_rejection_uses_the_real_product_without_any_models(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "LocalModels", lambda *a: (_ for _ in ()).throw(AssertionError("model must not be loaded")))
    cases = {c["id"]: c for c in catalog.read("scenarios.json")}
    for index, name in enumerate(("IN-08.normal", "IN-49.normal", "IN-70.normal", "QU-36.normal", "QU-37.normal")):
        case = cases[name]
        result = runtime.execute(case, None, tmp_path / str(index))
        assert result["probe"]["passed"]
        assert result["probe"]["no_records_created"]
        assert result["probe"]["model_accuracy_sample"] is False
    # U+FFFD is valid text; do not invent a product encoding rejection contract.
    result = runtime.execute(cases["IN-72.normal"], None, tmp_path / "broken")
    assert result["probe"]["passed"] is True


def test_exact_reference_cannot_override_an_independent_failure():
    case = product_case()
    case["accepted_answers"] = ["정확도는 0.89입니다."]
    assert grading.grade(case, observation(), semantic={"correct": False, "supported": True})["verdict"] == "FAIL"
