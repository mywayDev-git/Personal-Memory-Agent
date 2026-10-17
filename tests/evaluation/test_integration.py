import json
import sqlite3
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from evaluation.adapters import adapt
from evaluation.comparison import compare
from evaluation.diagnostics import diagnose
from evaluation.metrics import dashboard_metrics
from evaluation.repository import Repository
from evaluation.runner import execute
from evaluation.schema import Case, Dataset, Result
from evaluation.trace import TraceCollector
from pma.service import Service
from pma.web import create_app


def dataset():
    return Dataset(
        id="integration",
        name="Integration",
        version="1",
        cases=[
            Case(
                id="one",
                question="who?",
                expected_answer="answer",
                gold_groups={"g": ["m1"]},
                metadata={"grading_method": "exact_match"},
            ),
            Case(
                id="two",
                question="no evidence",
                answerability="unanswerable",
                expected_behavior="abstain",
            ),
        ],
    )


class ServiceStub:
    diagnostic_sink = None

    def answer(self, question, today=None):
        if question == "no evidence":
            raise RuntimeError("private message")
        self.diagnostic_sink({"stage": "retrieval_merge", "candidates": [{"id": "m1", "rank": 1}]})
        self.diagnostic_sink({"stage": "evidence", "ids": ["m1"]})
        return {"status": "answered", "items": [{"text": "answer", "citations": ["m1"]}]}


def test_runner_persistence_and_progress(tmp_path):
    repo = Repository(tmp_path / "eval.db")
    service = ServiceStub()
    rid = execute(repo, dataset(), service, {"grading_version": "v1"})
    assert service.diagnostic_sink is None
    assert repo.get_run(rid)["status"] == "completed"
    summary = repo.get_run_summary(rid)
    assert summary["case_counts"]["recorded"] == 2
    assert summary["case_counts"]["error"] == 1
    assert summary["progress"]["case_id"] == "two"
    assert summary["progress"]["stage"] == "case_completed"
    assert summary["metrics"]["answer_accuracy"]["value"] == 1
    assert repo.get_case_trace(rid, "one")["stages"][0]["candidates"][0]["id"] == "m1"
    assert "private message" not in json.dumps(repo.get_case_result(rid, "two"))
    another = execute(repo, dataset(), service, {"grading_version": "v1"})
    assert another != rid


def test_api_detail_filters_compare(settings, models):
    settings = replace(settings, evaluation_enabled=True, evaluation_details=True)
    repo = Repository(settings.data_dir / "evaluation" / "evaluation.db")
    rid = execute(repo, dataset(), ServiceStub(), {"grading_version": "v1"})
    app = create_app(settings, models, run_worker=False)
    with TestClient(app, base_url=settings.origin) as client:
        client.headers["Origin"] = settings.origin
        client.post("/api/v1/session", json={"token": app.state.bootstrap_token})
        root = f"/api/eval/runs/{rid}"
        assert client.get(root + "/cases?verdict=error").json()["total"] == 1
        assert client.get(root + "/cases?q=who").json()["total"] == 1
        assert client.get(root + "/cases?q=' OR 1=1 --").json()["total"] == 0
        assert client.get(root + "/cases?offset=100").json()["items"] == []
        assert client.get(root + "/cases/one").json()["actual_answer"] == "answer"
        assert client.get(root + "/cases/one/trace").json()["trace_status"] == "partial"
        assert client.get(root + "/cases/missing/trace").status_code == 404
        assert client.get(root + "/failures").json()["items"][0]["count"] == 1
        assert client.get(root + "/scenarios").json()["items"][0]["total"] == 2
        assert (
            client.get(
                f"/api/eval/compare?left_run_id={rid}&right_run_id={rid}&strict=1"
            ).status_code
            == 409
        )
        assert client.get("/api/eval/compare").status_code == 400
        for page in ("", "/cases", "/cases/one", "/scenarios", "/compare", "/regression"):
            assert client.get("/evaluation" + page).status_code == 200


def test_comparison_regressions(tmp_path):
    repo = Repository(tmp_path / "eval.db")
    repo.create_dataset(dataset())
    config = dict(
        snapshot="same", model="same", embedding="same", grading_version="v1", retrieval={}
    )
    left, right = [repo.create_run("integration", config=config) for _ in range(2)]
    for rid, verdict in [(left, "pass"), (right, "fail")]:
        repo.save_case_result(
            rid,
            Result(
                case_id="one", verdict=verdict, evaluation={"answer_correct": verdict == "pass"}
            ),
        )
        repo.save_case_result(rid, Result(case_id="two", verdict="pending_review"))
        repo.update_run_status(rid, "completed")
    value = compare(repo, left, right)
    assert value["comparable"]
    assert value["new_failures"] == ["one"]
    assert value["excluded"] == ["two"]
    assert value["metric_deltas"]["answer_accuracy"] == -100


def test_trace_regression_and_sink_failure(store, models, settings):
    import numpy as np
    from conftest import memory

    store.create("담당자를 정했다.", "2026-10-17T00:00:00+09:00")
    store.publish(
        store.claim(),
        [memory()],
        np.asarray([[1, 0, 0]], dtype=np.float32),
        settings.embedding_key,
        {},
    )
    service = Service(store, models, settings)
    expected = service.answer("기억이 있나요?", today="2026-10-17")
    trace = TraceCollector()
    service.diagnostic_sink = trace
    assert service.answer("기억이 있나요?", today="2026-10-17") == expected
    assert any(e["stage"] == "retrieval_merge" for e in trace.events)

    def fail(event):
        raise RuntimeError("diagnostic disk failure")

    service.diagnostic_sink = fail
    assert service.answer("기억이 있나요?", today="2026-10-17") == expected


def test_metrics_unknown_and_alternatives():
    c = Case(id="x", question="x", gold_groups={"a": ["1", "2"], "b": ["3"]})
    r = Result(
        case_id="x",
        verdict="pending_review",
        evaluation={"answer_correct": None, "retrieval_complete": True, "retrieved_ids": ["2"]},
        claims=[{"support_status": "uncertain"}],
    )
    m = dashboard_metrics([c], [r])
    assert m["answer_accuracy"]["value"] is None
    assert m["evidence_recall_at_20"]["value"] == 0.5
    assert m["complete_evidence_recall"]["value"] == 0
    assert m["unsupported_claim_rate"]["value"] is None
    assert m["p95_latency_ms"]["value"] is None
    r.evaluation["retrieval_complete"] = False
    assert dashboard_metrics([c], [r])["evidence_recall_at_20"]["value"] is None


def test_diagnosis_requires_observation():
    case = dataset().cases[0]
    events = [
        {"stage": "retrieval_merge", "candidates": [{"id": "m1"}]},
        {"stage": "evidence", "ids": []},
    ]
    assert diagnose(case, events, {}, "answer")["error_type"] == "evidence_selection_miss"
    assert diagnose(case, events[1:], {}, "answer")["error_type"] == "unknown"
    assert diagnose(case, [], {}, "clarify")["error_type"] == "unnecessary_clarification"
    assert (
        diagnose(case, [], {"answer_correct": False, "final_evidence_complete": True}, "answer")[
            "error_type"
        ]
        == "answer_generation_error"
    )


def test_schema_and_legacy():
    with pytest.raises(ValueError):
        Dataset(id="d", name="d", version="1", cases=[dataset().cases[0]] * 2)
    with pytest.raises(ValueError):
        Result(case_id="x", verdict="pass", latency_ms=float("nan"))
    with pytest.raises(ValueError):
        Result(case_id="x", verdict="pass", evaluation={"answer_correct": "true"})
    assert adapt({"case_id": "x", "status": "PASS_EXISTING"}).verdict == "pending_review"


def test_immutable_dataset_and_cross_run_lookup(tmp_path):
    repo = Repository(tmp_path / "eval.db")
    data = dataset()
    repo.create_dataset(data)
    data.cases[0].question = "changed"
    with pytest.raises(ValueError):
        repo.create_dataset(data)
    a = repo.create_run(data.id)
    b = repo.create_run(data.id)
    repo.save_case_result(a, Result(case_id="one", verdict="pass"))
    with pytest.raises(KeyError):
        repo.get_case_result(b, "one")
    with pytest.raises(sqlite3.IntegrityError):
        repo.create_run("missing")


def test_memory_database_is_never_migrated(store):
    with store.connect() as db:
        before = db.execute("SELECT sql FROM sqlite_master ORDER BY name").fetchall()
    with pytest.raises(ValueError, match="separate"):
        Repository(store.path)
    with store.connect() as db:
        assert db.execute("SELECT sql FROM sqlite_master ORDER BY name").fetchall() == before


def test_snapshot_reference_contract():
    with pytest.raises(ValueError):
        Case(id="x", question="y", metadata={"reference_time": "2026-10-17T00:00:00"})
    c = Case(
        id="x",
        question="y",
        metadata={"required_evidence_groups": [{"group_id": "g", "memory_ids": ["m1"]}]},
    )
    assert c.gold_groups == {"g": ["m1"]}


def test_legacy_dataset_conversion(tmp_path):
    from evaluation.adapters import load_dataset

    path = tmp_path / "cases.json"
    path.write_text(
        json.dumps(
            [
                {
                    "case_id": "old",
                    "question": "q",
                    "expected_facts": ["a"],
                    "records": [{"text": "private source"}],
                }
            ]
        ),
        encoding="utf-8",
    )
    data = load_dataset(path)
    assert data.cases[0].metadata["legacy_import_only"]
    assert "private source" not in data.model_dump_json()
