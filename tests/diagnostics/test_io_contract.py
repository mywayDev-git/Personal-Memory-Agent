"""Real SQLite and HTTP parity, with fake models only."""

import json
from contextlib import contextmanager
from dataclasses import replace

import numpy as np
import pytest
from conftest import FakeModels, memory
from fastapi.testclient import TestClient

from pma.service import Service
from pma.web import create_app

from .test_trace_contract import diagnostics


def test_real_store_sql_and_results_identical_on_off(
    store, settings, models, monkeypatch, tmp_path
):
    store.create("담당자를 정했다.", None)
    Service(store, models, settings).run_one()
    statements = []
    connect = store.connect

    @contextmanager
    def counted(write=False):
        with connect(write) as db:
            db.set_trace_callback(statements.append)
            yield db

    monkeypatch.setattr(store, "connect", counted)
    path = tmp_path / "sql.jsonl"
    off = replace(settings, diagnostics=False, diagnostics_path=path)
    on = replace(settings, diagnostics=True, diagnostics_path=path)
    expected = Service(store, models, off).answer("질문", today="2026-10-17")
    expected_sql = statements[:]
    statements.clear()
    assert not path.exists()
    actual = Service(store, models, on).answer("질문", today="2026-10-17")
    assert actual == expected
    assert statements == expected_sql  # Includes every SQL statement, not only method calls.
    assert path.exists()


@pytest.mark.parametrize("question", ["질문", "그때 질문"])
def test_http_response_schema_and_status_on_off(settings, tmp_path, question):
    path = tmp_path / "http.jsonl"
    responses = []
    for enabled in (False, True):
        configured = replace(settings, diagnostics=enabled, diagnostics_path=path)
        app = create_app(configured, FakeModels(), run_worker=False)
        with TestClient(app, base_url=configured.origin) as client:
            client.headers["Origin"] = configured.origin
            session = client.post("/api/v1/session", json={"token": app.state.bootstrap_token})
            client.headers["X-CSRF-Token"] = session.json()["csrf"]
            if not enabled:
                client.post("/api/v1/records", json={"text": "담당자를 정했다."})
                app.state.service.run_one()
            response = client.post(
                "/api/v1/answers", json={"question": question, "today": "2026-10-17"}
            )
            responses.append((response.status_code, response.json()))
        if not enabled:
            assert not path.exists()
    assert responses[0] == responses[1]
    assert responses[0][0] == 200
    assert "trace_id" not in responses[1][1]
    events = [json.loads(line) for line in path.read_text("utf-8").splitlines()]
    final = [e for e in events if e["stage"] == "final_decision"]
    assert len(final) == 1


def test_snapshot_missing_fact_and_unobserved_embedding(store, settings):
    d = diagnostics()
    store.create("합성 기록", None)
    job = store.claim()
    store.publish(job, [memory("합성 기록")], np.array([[1, 0, 0]]), settings.embedding_key, {})
    with store.connect(True) as db:
        db.execute("DELETE FROM facts")
    with d.start_trace(enabled=True) as trace:
        _, rows = store.snapshot(settings.embedding_key)
    assert len(rows) == 1 and rows[0]["fact"] is None
    snapshot = next(e for e in trace.events if e["stage"] == "snapshot")
    candidate = snapshot["candidates"][0]
    assert candidate["memory_ref"] == trace.memory_ref(rows[0]["id"])
    assert candidate["has_fact"] is False
    assert candidate["has_embedding"] is True
    assert candidate["record_ref"]
    with store.connect(True) as db:
        db.execute("DELETE FROM embeddings")
    with d.start_trace(enabled=True) as trace:
        assert store.snapshot(settings.embedding_key)[1] == []
    snapshot = next(e for e in trace.events if e["stage"] == "snapshot")
    assert snapshot["output_count"] == 0
    # The INNER JOIN cannot observe why other rows are absent; do not invent a reason.
    assert snapshot["unobserved_reason"] == "not_observed"
