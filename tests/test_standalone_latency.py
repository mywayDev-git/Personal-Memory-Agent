import json
from types import SimpleNamespace

import pytest

from pma.errors import AppError
from pma.service import Service
from scripts.memory_agent.llm_client import RequestDeadlineExceeded, request_budget, token_count
from scripts.memory_agent.performance import profile_request


def fixture_service(*, enabled=True, sink=None):
    calls = []
    session = SimpleNamespace(post=lambda *a, **kw: (
        calls.append(kw) or SimpleNamespace(status_code=200, json=lambda: {"tokens": [1, 2, 3]})))
    service = Service(None, None, SimpleNamespace(
        diagnostics=enabled, request_token_cache=enabled, llm=SimpleNamespace(timeout=17)), diagnostic_sink=sink)

    def search(question, *a, **kw):
        for _ in range(2):
            token_count(session, "http://127.0.0.1:1234/tokenize", question, 17,
                        add_special=False, cache=True, identity="fixed-model")
        return 1, {"status": "ok", "results": [], "synthetic_private_field": "SECRET"}
    service._search = search
    return service, calls, search


def test_standalone_search_profiles_safe_metrics_and_never_reuses_across_requests():
    service, calls, _ = fixture_service()
    first = service.search("SECRET QUESTION")
    assert len(calls) == 1 and calls[0]["timeout"] == 17
    metrics = first["performance"]
    assert metrics["profile"]["counts"]["token_cache_hits"] == 1
    assert metrics["profile"]["stages"]["model_wait"]["calls"] == 1
    assert "SECRET" not in json.dumps(metrics)
    service.search("SECRET QUESTION")
    assert len(calls) == 2
    service.search("CHANGED QUESTION AND EVIDENCE")
    assert len(calls) == 3


@pytest.mark.parametrize("error,outcome", [
    (AppError("CANCELLED", "SECRET", 409), "cancelled"),
    (RequestDeadlineExceeded("SECRET"), "failed"),
    (ValueError("SECRET"), "failed"),
])
def test_standalone_failure_and_cancellation_drop_request_cache(error, outcome):
    events = []
    service, calls, search = fixture_service(sink=events.append)
    def fail(question, *a, **kw):
        search(question, *a, **kw)
        raise error
    service._search = fail
    with pytest.raises(type(error)):
        service.search("SECRET QUESTION")
    metrics = next(row["performance"] for row in events if row["stage"] == "request_performance")
    assert metrics["profile"]["outcome"] == outcome
    assert "SECRET" not in json.dumps(metrics)
    service._search = search
    service.search("SECRET QUESTION")
    assert len(calls) == 2


def test_nested_search_reuses_the_callers_profile_and_deadline():
    service, calls, _ = fixture_service()
    with profile_request() as profile, request_budget(.5) as budget:
        result = service.search("SECRET QUESTION")
        assert "performance" not in result
        assert profile.snapshot()["counts"]["token_cache_hits"] == 1
        assert len(budget.calls) == 1
        assert 0 < calls[0]["timeout"] <= .5


def test_plain_legacy_search_keeps_existing_response_and_per_call_timeout():
    service, calls, _ = fixture_service(enabled=False)
    result = service.search("SECRET QUESTION")
    assert result == {"status": "ok", "results": [], "synthetic_private_field": "SECRET"}
    assert len(calls) == 2 and all(c["timeout"] == 17 for c in calls)


def test_explicit_search_preserves_optional_performance_in_existing_metadata(tmp_path):
    from pma.chat.engine import ChatEngine
    from pma.settings import AppSettings
    from pma.store import Store

    settings = AppSettings(data_dir=tmp_path)
    store = Store(tmp_path / "synthetic.db")
    service = Service(store, SimpleNamespace(), settings)
    performance = {"profile": {"elapsed_seconds": .1}, "model_http_calls": []}
    service.search = lambda *a, **kw: {"status": "ok", "results": [], "filters": {}, "performance": performance}
    result = ChatEngine(service).search("synthetic")
    with store.connect() as db:
        metadata = json.loads(db.execute("SELECT payload FROM chat_searches WHERE id=?", (result["search_id"],)).fetchone()[0])
    assert metadata["performance"] == performance
