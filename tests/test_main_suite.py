"""Offline harness checks only. No real model or main evaluation may run here."""

import json
from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi import FastAPI

from evaluation.comparison import compare, compare_models
from evaluation.main_suite import catalog, grading, runner, runtime
from evaluation.repository import Repository
from evaluation.schema import Case, Dataset, Result
from pma.evaluation_api import install
from pma.settings import AppSettings


def product_case():
    return {"id": "example.normal", "family": "example", "split": "development", "variant": "normal",
            "adapter": "product", "priority": "P0", "variables": ["EV-02"], "question": "정확도는?",
            "expected_behavior": "answer", "required_facts": ["0.89"], "forbidden_facts": ["0.95"],
            "records": [{"id": "target", "text": "정확도 0.89", "version": 1, "owner": "user-a"}],
            "steps": [{"action": "chat", "question": "정확도는?"}],
            "gold_groups": {"value": [{"record_id": "target", "version": 1,
                "start": 0, "end": 8, "quote": "정확도 0.89"}]}}


def observation(text="정확도는 0.89입니다."):
    return {"response": {"status": "answered", "items": [{"text": text, "citations": ["memory"]}],
                          "citation_details": [{"record_id": "actual", "memory_id": "memory",
                              "start": 0, "end": 8, "quote": "정확도 0.89"}]},
            "sources": {"actual": {"logical_id": "target", "text": "정확도 0.89", "version": 1, "state": "active"}},
            "retrieved": ["target"], "retrieval_observed": True, "events": [], "latency_ms": 3}


def config():
    return {"candidate": "baseline--baseline", "profile": "core", "snapshot": "fixed",
            "grading_version": catalog.VERSION, "commit": "fixed", "environment": {}, "gates": None}


def test_catalog_source_coverage_and_holdout():
    result = catalog.validate()
    assert result["variables"] == 489
    cases = catalog.read("scenarios.json")
    core = runner.select_cases("core")
    represented = {vid for case in core for vid in case["variables"]}
    assert all(v["variable_id"] in represented for v in catalog.read("catalog.json") if v["priority"] == "P0")
    assert not {c["family"] for c in core if not c.get("catalog_only")} & {
        c["family"] for c in cases if c["split"] == "final"}
    assert any(c["adapter"] == "product" for c in runner.select_cases("final"))


def test_static_default_does_not_read_models_or_start_servers(monkeypatch, capsys):
    monkeypatch.setattr(runner, "servers", lambda *a, **k: pytest.fail("server started"))
    monkeypatch.setattr(runner, "model_specs", lambda *a: pytest.fail("models opened"))
    assert runner.main([]) == 0
    assert json.loads(capsys.readouterr().out)["executed"] is False


def test_presence_of_expected_number_is_not_proof_of_truth():
    result = grading.grade(product_case(), observation("정확도는 0.89가 아니라 0.81입니다."))
    assert result["verdict"] == "PENDING_REVIEW"
    assert result["evaluation"]["answer_correct"] is None


@pytest.mark.parametrize("change", ["missing_source", "wrong_quote", "deleted", "wrong_version", "wrong_location"])
def test_invalid_citations_cannot_pass(change):
    obs = observation()
    ref = obs["response"]["citation_details"][0]
    if change == "missing_source":
        obs["sources"] = {}
    elif change == "wrong_quote":
        ref["quote"] = "정확도 0.95"
    elif change == "deleted":
        obs["sources"]["actual"]["state"] = "trash"
    elif change == "wrong_version":
        ref["version"] = 2
    else:
        ref["start"] = 1
    result = grading.grade(product_case(), obs, semantic={"correct": True, "supported": True})
    assert result["verdict"] == "FAIL"
    assert result["error_type"] == "F-CITATION"


def test_independent_review_and_required_groups():
    case = product_case()
    assert grading.grade(case, observation(), semantic={"correct": True, "supported": True})["verdict"] == "PASS"
    case["gold_groups"]["reason"] = [{"record_id": "another", "version": 1, "start": 0, "end": 1, "quote": "x"}]
    assert grading.grade(case, observation(), semantic={"correct": True, "supported": True})["verdict"] == "FAIL"


def test_unobserved_retrieval_is_unknown():
    obs = observation()
    obs["retrieval_observed"] = False
    result = grading.grade(product_case(), obs)
    assert result["evaluation"]["recall_at_20"] is None


def test_group_recall_deduplicates_equivalent_sources():
    groups = {"fact": [{"record_id": "a"}, {"record_id": "b"}], "reason": [{"record_id": "c"}]}
    result = grading.evidence_metrics(groups, ["a", "a", "unrelated", "c"])
    assert result["recall_at_8"] == 1
    assert result["complete_evidence_recall"] is True
    assert result["mrr"] == 1


def test_errors_and_pending_are_never_silent_success():
    rows = [{"verdict": verdict, "family": str(i), "evaluation": {}, "expected_behavior": "answer"}
            for i, verdict in enumerate(("PASS", "ERROR", "PENDING_REVIEW", "UNSUPPORTED"))]
    result = grading.summary(rows, 5)
    assert result["metrics"]["overall_success_rate"]["value"] == .25
    assert result["not_run"] == 1
    assert result["metrics"]["answer_correct"]["value"] is None
    assert result["complete"] is False


def test_isolation_rejects_personal_and_non_suite_paths(tmp_path, monkeypatch):
    with pytest.raises(ValueError):
        runtime.checked_root(tmp_path / "memory.db")
    root = Path(__file__).resolve().parents[1] / ".local/main-suite/test-path-only"
    assert runtime.checked_root(root) == root.resolve()
    monkeypatch.setenv("PMA_DATA_DIR", str(root))
    with pytest.raises(ValueError, match="PERSONAL"):
        runtime.checked_root(root)


def test_resume_does_not_rerun_completed_failures_or_pending(tmp_path):
    jobs = runner.trials([product_case()], 2, 42)
    called = []
    def fake(case, settings, directory, **kwargs):
        called.append(directory)
        return observation()
    result, first = runner.run_candidate(tmp_path, config(), jobs, nullcontext(None), execute_fn=fake)
    before = (tmp_path / "cases.jsonl").read_bytes()
    runner.run_candidate(tmp_path, config(), jobs, nullcontext(None), execute_fn=fake, resume=True)
    assert len(called) == 2
    assert (tmp_path / "cases.jsonl").read_bytes() == before
    assert result["counts"]["PENDING_REVIEW"] == 2
    with pytest.raises(ValueError, match="IDENTICAL"):
        runner.run_candidate(tmp_path, {**config(), "snapshot": "changed"}, jobs, nullcontext(None), resume=True)


def test_cancel_preserves_completed_attempts_and_resumes(tmp_path):
    jobs = runner.trials([product_case()], 2, 42)
    called = []
    def cancel_second(case, settings, directory, **kwargs):
        called.append(directory)
        if len(called) == 2:
            raise KeyboardInterrupt()
        return observation()
    with pytest.raises(KeyboardInterrupt):
        runner.run_candidate(tmp_path, config(), jobs, nullcontext(None), execute_fn=cancel_second)
    manifest = json.loads((tmp_path / "manifest.json").read_text("utf-8"))
    assert Repository(tmp_path / "evaluation.db").get_run(manifest["run_id"])["status"] == "cancelled"
    assert len(runner.read_rows(tmp_path / "cases.jsonl")) == 1
    _, rows = runner.run_candidate(tmp_path, config(), jobs, nullcontext(None), execute_fn=lambda *a, **k: observation(), resume=True)
    assert len(rows) == 2


def test_review_is_hash_bound_and_does_not_rewrite_raw_results(tmp_path):
    jobs = runner.trials([product_case()], 1, 42)
    _, rows = runner.run_candidate(tmp_path, config(), jobs, nullcontext(None), execute_fn=lambda *a, **k: observation())
    original = (tmp_path / "cases.jsonl").read_bytes()
    (tmp_path / "evidence.txt").write_text("원문과 답변 전체 사실을 수동 대조함", "utf-8")
    review = {"trial_id": rows[0]["trial_id"], "observation_hash": rows[0]["observation_hash"],
              "reviewer": "synthetic tester", "reason": "전체 주장과 근거 일치 확인", "evidence": ["evidence.txt"],
              "verdict": "PASS", "evaluation": {"answer_correct": True, "claims_supported": True}}
    path = tmp_path / "review.json"
    path.write_text(json.dumps([review]), "utf-8")
    result = runner.import_reviews(tmp_path, path)
    assert result["counts"] == {"PASS": 1}
    assert (tmp_path / "cases.jsonl").read_bytes() == original
    with pytest.raises(ValueError, match="PENDING"):
        runner.import_reviews(tmp_path, path)


def test_model_comparison_does_not_relax_regression_or_allow_prompt_changes(tmp_path):
    repo = Repository(tmp_path / "evaluation.db")
    repo.create_dataset(Dataset(id="test", name="test", version="1", cases=[Case(id="one", question="q")]))
    base = {"snapshot": "s", "model": {"model": "a", "sha256": "a"}, "embedding": {"sha256": "e"},
            "grading_version": "main-suite-v1", "retrieval": {}, "server_sha256": "server", "seed": 42, "profile": "compare"}
    ids = []
    for c in (base, {**base, "model": {"model": "b", "sha256": "b"}}, {**base, "snapshot": "changed"}):
        rid = repo.create_run("test", config=c)
        repo.save_case_result(rid, Result(case_id="one", verdict="pass"))
        repo.update_run_status(rid, "completed")
        ids.append(rid)
    assert not compare(repo, *ids[:2])["comparable"]
    assert compare_models(repo, *ids[:2])["comparable"]
    assert not compare_models(repo, ids[0], ids[2])["comparable"]


def test_read_only_plan_and_details_mask_without_any_execution(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "main", lambda *a: pytest.fail("suite executed"))
    settings = replace(AppSettings(), data_dir=tmp_path, evaluation_enabled=True, evaluation_details=False)
    app = FastAPI()
    install(app, settings, Path(__file__).resolve().parents[1] / "pma/static")
    installed = []
    for r in app.routes:
        installed.extend(r.original_router.routes if hasattr(r, "original_router") else [r])
    routes = {r.path: r for r in installed if hasattr(r, "path")}
    # Exercise the installed handlers without starting an application's worker.
    assert len(routes["/api/eval/plan"].endpoint()["variables"]) == 489
    assert routes["/api/eval/plan"].methods == {"GET"}
    assert routes["/evaluation"].endpoint().path.name == "evaluation.html"
    assert not (tmp_path / "memory.db").exists()


def test_no_gate_or_unresolved_result_means_no_recommendation():
    s = grading.summary([], 1)
    s["candidate"] = "baseline"
    assert runner.ranking([s], None)["recommended"] is None
    gates = {"minimums": {"answer_correct": 0}}
    assert runner.ranking([s], gates)["recommended"] is None


def test_trials_are_reproducible_and_each_repeat_is_distinct():
    cases = [product_case()]
    assert runner.trials(cases, 5, 42) == runner.trials(cases, 5, 42)
    assert len({j["id"] for j in runner.trials(cases, 5, 42)}) == 5


def test_internal_owner_and_import_adapters_use_real_isolated_store(tmp_path):
    from pma.store import Store
    store = Store(tmp_path / "synthetic.db", clock=lambda: runtime.NOW)
    assert runtime.owner_probe(store)["passed"]
    case = next(c for c in catalog.read("scenarios.json") if c["adapter"] == "import_probe" and c["variant"] == "boundary")
    assert runtime.import_probe(store, case)["passed"]


def test_additional_model_requires_hash_and_bad_hash_is_rejected(tmp_path):
    path = tmp_path / "synthetic.gguf"
    path.write_bytes(b"not a real model")
    spec = {"path": str(path), "sha256": None, "context": 16384, "threads": 0, "gpu_layers": 0}
    manifest = {"generation": {"other": spec}, "embedding": {"baseline": spec}}
    with pytest.raises(ValueError, match="PINNED"):
        runtime.model_specs(manifest)
    spec["sha256"] = "wrong"
    with pytest.raises(ValueError, match="HASH_MISMATCH"):
        runtime.model_specs(manifest)


def test_publish_is_idempotent_and_rejects_memory_database(tmp_path):
    candidate = tmp_path / "candidate"
    runner.run_candidate(candidate, config(), runner.trials([product_case()], 1, 42), nullcontext(None),
                         execute_fn=lambda *a, **k: observation())
    dest = tmp_path / "dashboard/evaluation/evaluation.db"
    runner.publish_run(candidate, dest)
    runner.publish_run(candidate, dest)
    assert Repository(dest).list_runs()["total"] == 1
    with pytest.raises(ValueError, match="DESTINATION"):
        runner.publish_run(candidate, tmp_path / "memory.db")


def test_item_cannot_cite_an_id_missing_from_details():
    obs = observation()
    obs["response"]["items"][0]["citations"].append("invented")
    assert grading.grade(product_case(), obs)["error_type"] == "F-CITATION"


def test_memory_id_must_belong_to_the_cited_revision():
    obs = observation()
    obs["memory_sources"] = {"memory": {"record_id": "actual", "version": 2, "revision_id": "new"}}
    assert grading.grade(product_case(), obs)["error_type"] == "F-CITATION"


def test_deleted_secret_output_is_counted_as_exposure():
    case = product_case()
    case["forbidden_facts"] = ["SYNTH-DELETE-872"]
    result = grading.grade(case, observation("정확도 0.89. 삭제된 값 SYNTH-DELETE-872"))
    assert result["verdict"] == "FAIL"
    assert result["evaluation"]["deleted_exposures"] == 1


def test_negative_mention_does_not_prove_an_incorrect_claim():
    result = grading.grade(product_case(), observation("0.95가 아니라 0.89입니다."))
    assert result["verdict"] == "PENDING_REVIEW"


def test_live_mirror_records_cancelled_run_and_completed_case(tmp_path):
    candidate = tmp_path / "candidate"
    destination = tmp_path / "dashboard/evaluation/evaluation.db"
    jobs = runner.trials([product_case()], 2, 42)
    count = 0
    def fake(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 2:
            raise KeyboardInterrupt()
        return observation()
    with pytest.raises(KeyboardInterrupt):
        runner.run_candidate(candidate, config(), jobs, nullcontext(None), execute_fn=fake, dashboard=destination)
    repo = Repository(destination)
    run = repo.list_runs()["items"][0]
    assert run["status"] == "cancelled"
    assert len(repo.results(run["id"])) == 1


def test_partial_run_never_receives_official_recommendation():
    metrics = {key: {"value": 1} for key in ("answer_correct", "grounded_answer_success_rate", "complete_evidence_recall")}
    value = {"candidate": "candidate", "metrics": metrics, "complete": True, "counts": {"PASS": 1},
             "security_exposures": 0, "deleted_exposures": 0, "invalid_citations": 0, "partial_selection": True}
    gates = {"minimums": {"answer_correct": .9}}
    assert runner.ranking([value], gates)["recommended"] is None


def test_changed_review_evidence_invalidates_previous_adjudication(tmp_path):
    _, rows = runner.run_candidate(tmp_path, config(), runner.trials([product_case()], 1, 42),
                                   nullcontext(None), execute_fn=lambda *a, **k: observation())
    evidence = tmp_path / "evidence.txt"
    evidence.write_text("verified", "utf-8")
    path = tmp_path / "reviews.json"
    path.write_text(json.dumps([{"trial_id": rows[0]["trial_id"], "observation_hash": rows[0]["observation_hash"],
        "reviewer": "tester", "reason": "verified", "evidence": ["evidence.txt"], "verdict": "PASS",
        "evaluation": {"answer_correct": True, "claims_supported": True}}]), "utf-8")
    runner.import_reviews(tmp_path, path)
    evidence.write_text("changed", "utf-8")
    with pytest.raises(ValueError, match="EVIDENCE_CHANGED"):
        runner.apply_reviews(tmp_path, runner.read_rows(tmp_path / "cases.jsonl"))


def test_bootstrap_does_not_treat_repeats_as_independent_families():
    a = {"families": {"one": [{"answer_correct": 1}] * 100}}
    b = {"families": {"one": [{"answer_correct": 0}] * 100}}
    assert runner.paired_interval(a, b, "answer_correct") is None


def test_core_refuses_a_case_that_only_belongs_to_extended(monkeypatch):
    monkeypatch.setattr(runner, "servers", lambda *a, **k: pytest.fail("server started"))
    with pytest.raises(ValueError, match="CASE_NOT"):
        runner.main(["--case", "EXT-records-100"])
