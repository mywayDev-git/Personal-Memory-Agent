from threading import RLock
from types import SimpleNamespace

from pma.chat.engine import ChatEngine


def test_live_timings_accumulate_without_mutating_completed_phases(monkeypatch):
    engine = ChatEngine.__new__(ChatEngine)
    engine.progress_lock = RLock()
    engine.progress = {("session", "request"): "searching"}
    engine.progress_times = {("session", "request"): {
        "started": 10, "since": 12, "durations": {"resolving_context": 2, "searching": 1}}}
    engine.store = SimpleNamespace(request_state=lambda *_: {"state": "running"})
    monkeypatch.setattr("pma.chat.engine.time.monotonic", lambda: 15)
    result = engine.request_status("session", "request")
    assert result["phase"] == "searching"
    assert result["elapsed_seconds"] == 5
    assert result["phase_seconds"] == 3
    assert result["phase_timings"] == {"resolving_context": 2, "searching": 4}
    assert engine.progress_times["session", "request"]["durations"]["searching"] == 1
    assert engine.timing("other", "request") == {}
