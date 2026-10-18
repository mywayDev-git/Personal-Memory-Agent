import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
import requests
from conftest import FakeModels
from fastapi.testclient import TestClient

from pma.diagnostics import current_trace
from pma.web import create_app


def test_web_lifecycle_errors_parallel_and_cleanup(settings, tmp_path):
    path = tmp_path / "http.jsonl"
    config = replace(settings, diagnostics=True, diagnostics_path=path)
    app = create_app(config, FakeModels(), run_worker=False)
    with TestClient(app, base_url=config.origin) as client:
        client.headers["Origin"] = config.origin
        assert client.post("/api/v1/answers", json={"question": "PRIVATE"}).status_code == 401
        session = client.post("/api/v1/session", json={"token": app.state.bootstrap_token})
        client.headers["X-CSRF-Token"] = session.json()["csrf"]
        assert client.post("/api/v1/answers", json={"question": ""}).status_code == 422
        with ThreadPoolExecutor(max_workers=3) as pool:
            responses = list(
                pool.map(
                    lambda i: client.post("/api/v1/answers", json={"question": f"PRIVATE {i}"}),
                    range(3),
                )
            )
        assert all(r.status_code == 200 and "trace_id" not in r.json() for r in responses)
    events = [json.loads(line) for line in path.read_text("utf-8").splitlines()]
    http = [e for e in events if e["stage"] == "http_request"]
    assert sorted(e["http_status"] for e in http) == [200, 200, 200, 401, 422]
    assert len({e["trace_id"] for e in http}) == 5
    assert {e["trace_id"] for e in events} == {e["trace_id"] for e in http}
    assert current_trace() is None and "PRIVATE" not in str(events)


def test_web_storage_failure_is_not_http_failure(settings, tmp_path):
    config = replace(
        settings, diagnostics=True, diagnostics_path=tmp_path / "missing" / "trace.jsonl"
    )
    app = create_app(config, FakeModels(), run_worker=False)
    with TestClient(app, base_url=config.origin) as client:
        client.headers["Origin"] = config.origin
        session = client.post("/api/v1/session", json={"token": app.state.bootstrap_token})
        client.headers["X-CSRF-Token"] = session.json()["csrf"]
        assert client.post("/api/v1/answers", json={"question": "질문"}).status_code == 200
    assert not config.diagnostics_path.exists()


@pytest.mark.parametrize(
    "error,status",
    [
        (ValueError("PRIVATE"), 503),
        (requests.Timeout("PRIVATE"), 504),
        (RuntimeError("PRIVATE"), 500),
    ],
)
def test_model_errors_finish_request_trace(settings, tmp_path, error, status):
    path = tmp_path / "errors.jsonl"
    config = replace(settings, diagnostics=True, diagnostics_path=path)
    models = FakeModels()
    app = create_app(config, models, run_worker=False)
    with TestClient(app, base_url=config.origin) as client:
        client.headers["Origin"] = config.origin
        session = client.post("/api/v1/session", json={"token": app.state.bootstrap_token})
        client.headers["X-CSRF-Token"] = session.json()["csrf"]
        client.post("/api/v1/records", json={"text": "담당자를 정했다."})
        app.state.service.run_one()
        original = models.embed

        def fail(texts):
            raise error

        models.embed = fail
        assert client.post("/api/v1/answers", json={"question": "PRIVATE"}).status_code == status
        models.embed = original
        assert client.post("/api/v1/answers", json={"question": "질문"}).status_code == 200
    events = [json.loads(line) for line in path.read_text("utf-8").splitlines()]
    requests_done = [e for e in events if e["stage"] == "http_request"]
    assert [e["http_status"] for e in requests_done] == [status, 200]
    assert len({e["trace_id"] for e in requests_done}) == 2
    assert current_trace() is None and "PRIVATE" not in str(events)
