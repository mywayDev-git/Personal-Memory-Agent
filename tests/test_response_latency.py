import json
from types import SimpleNamespace

import pytest

from pma.chat.engine import ChatEngine
from pma.chat.store import ChatStore
from pma.service import Service
from pma.settings import AppSettings
from pma.store import Store
from scripts.memory_agent import performance
from scripts.memory_agent.llm_client import post_json, request_budget
from scripts.memory_agent.performance import count, measure, profile_request


def test_nested_times_are_exclusive_and_live_snapshot_does_not_mutate(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(performance.time, "perf_counter", lambda: now[0])
    with profile_request() as profile:
        with measure("parent"):
            now[0] = 2.0
            with measure("child"):
                now[0] = 5.0
                live = profile.snapshot()
                assert sum(s["exclusive_seconds"] for s in live["stages"].values()) == 5
                assert profile.stages == {}
            now[0] = 7.0
        count("search_iterations")
    result = profile.snapshot()
    assert result["stages"]["parent"]["inclusive_seconds"] == 7
    assert result["stages"]["parent"]["exclusive_seconds"] == 4
    assert result["stages"]["child"]["exclusive_seconds"] == 3
    assert result["counts"] == {"search_iterations": 1}
    with profile_request() as other:
        assert other.snapshot()["counts"] == {}


def test_failure_measurement_never_includes_exception_or_request_text():
    with profile_request() as profile:
        with pytest.raises(ValueError):
            with measure("generation"):
                raise ValueError("PRIVATE SOURCE")
    result = profile.snapshot("failed")
    assert result["stages"]["generation"]["failures"] == 1
    assert "PRIVATE" not in json.dumps(result)


def test_transport_usage_is_allowlisted():
    payload = {"usage": {"prompt_tokens": 12, "completion_tokens": 3,
                         "total_tokens": 15, "private": "SECRET"}, "text": "SECRET"}
    session = SimpleNamespace(post=lambda *a, **k: SimpleNamespace(status_code=200, json=lambda: payload))
    with request_budget(10) as budget:
        assert post_json(session, "http://127.0.0.1:1234/v1/chat/completions", {}, 10) == payload
    assert budget.calls[0]["usage"] == {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15}
    assert "SECRET" not in json.dumps(budget.calls)


def test_failed_request_persists_profile_without_source_text(tmp_path):
    settings = AppSettings(data_dir=tmp_path)
    models = SimpleNamespace(count_tokens=lambda _: 1,
                             structured=lambda *a, **k: (_ for _ in ()).throw(ValueError("SECRET")))
    engine = ChatEngine(Service(Store(tmp_path / "synthetic.db"), models, settings))
    sid = engine.store.create_empty()["id"]
    with pytest.raises(ValueError):
        engine.message(sid, "failed", "안녕")
    message = engine.store.get(sid)["messages"][-1]
    assert message["snapshot"]["performance"]["profile"]["outcome"] == "failed"
    assert "SECRET" not in json.dumps(message["snapshot"])
    # Retry uses the existing message and must be able to write a fresh snapshot.
    mid, _ = engine.store.begin(sid, "failed", "안녕")
    engine.store.fail(mid, "MODEL_FAILED", performance={"profile": {"outcome": "failed"}})
    assert ChatStore(engine.service.store).get(sid)["messages"][-1]["state"] == "failed"
