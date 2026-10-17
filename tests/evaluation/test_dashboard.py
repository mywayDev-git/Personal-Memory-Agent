from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from evaluation.comparison import compare
from evaluation.metrics import dashboard_metrics
from evaluation.repository import Repository
from evaluation.schema import Case, Dataset, Result
from evaluation.trace import TraceCollector
from pma.web import create_app


def seed(path):
    repo = Repository(path)
    dataset = Dataset(
        id="d1",
        name="test",
        version="1",
        cases=[
            Case(
                id="c1",
                question="who?",
                expected_answer="Kim",
                gold_groups={"a": ["m1", "m2"], "b": ["m3"]},
            )
        ],
    )
    repo.create_dataset(dataset)
    run = repo.create_run(
        "d1",
        config={
            "snapshot": "s",
            "model": "m",
            "embedding": "e",
            "grading_version": "v1",
            "retrieval": {},
        },
    )
    return repo, run, dataset


def test_repository_and_metrics(tmp_path):
    repo, run, dataset = seed(tmp_path / "eval.db")
    Repository(repo.path)
    result = Result(
        case_id="c1",
        verdict="fail",
        response_behavior="answer",
        evaluation={
            "answer_correct": True,
            "retrieved_ids": ["m2", "m3"],
            "retrieval_complete": True,
            "final_evidence_complete": False,
        },
        latency_ms=100,
    )
    repo.save_case_result(run, result)
    repo.save_case_result(run, result)
    assert repo.list_case_results(run)["total"] == 1
    metrics = dashboard_metrics(dataset.cases, [result])
    assert metrics["answer_accuracy"]["value"] == 1
    assert metrics["complete_evidence_recall"]["value"] == 1
    assert metrics["grounded_answer_success_rate"]["value"] == 0
    assert metrics["unsupported_claim_rate"]["value"] is None
    repo.replace_run_metrics(run, metrics)
    assert repo.get_run_summary(run)["case_counts"]["recorded"] == 1
    with pytest.raises(Exception):
        repo.save_case_result(run, Result(case_id="missing", verdict="error"))


def test_trace_redaction_and_limit():
    trace = TraceCollector(max_bytes=600)
    trace({"stage": "question", "question": "secret", "plan": {"raw": "secret"}})
    trace(
        {
            "stage": "retrieval_merge",
            "candidates": [{"id": "m1", "score": 0.8, "content": "secret"}],
        }
    )
    assert "secret" not in str(trace.events)
    for _ in range(100):
        trace({"stage": "evidence", "ids": ["m1"]})
    assert trace.truncated
    assert trace.bytes_used <= 600


def test_comparison_requires_conditions(tmp_path):
    repo, left, _ = seed(tmp_path / "eval.db")
    right = repo.create_run("d1", config={})
    assert compare(repo, left, right)["comparable"] is False


def test_api_access_and_empty(settings, models):
    enabled = replace(settings, evaluation_enabled=True)
    app = create_app(enabled, models, run_worker=False)
    with TestClient(app, base_url=settings.origin) as client:
        assert client.get("/api/eval/runs").status_code == 401
        client.headers["Origin"] = settings.origin
        client.post("/api/v1/session", json={"token": app.state.bootstrap_token})
        assert client.get("/api/eval/runs").json()["total"] == 0
        assert client.get("/api/eval/runs?limit=0").status_code == 400
        assert client.get("/api/eval/runs/missing").status_code == 404
        assert client.get("/evaluation").status_code == 200
        repo, run, _ = seed(settings.data_dir / "evaluation" / "evaluation.db")
        repo.save_case_result(
            run, Result(case_id="c1", verdict="pending_review", actual_answer="private")
        )
        detail = client.get(f"/api/eval/runs/{run}/cases/c1").json()
        assert detail["actual_answer"] is None
        assert client.get(f"/api/eval/runs/{run}/cases/c1/trace").status_code == 403


def test_default_disabled(client, settings):
    assert client.get("/api/eval/runs").status_code == 404
    assert not (settings.data_dir / "evaluation").exists()
