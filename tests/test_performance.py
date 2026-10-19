import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest
import requests

from pma.chat.router import RetrievalRouter, RoutingMode
from pma.errors import AppError
from pma.service import Service


def test_foreground_runs_before_next_background_call():
    service = Service(None, None, SimpleNamespace(llm=SimpleNamespace(timeout=2)))
    order = []
    service.gate.acquire()

    def call(name, background):
        with service.model_slot(wait=2, background=background):
            order.append(name)

    foreground = threading.Thread(target=call, args=("foreground", False))
    foreground.start()
    deadline = time.monotonic() + 1
    while not service.foreground_waiters and time.monotonic() < deadline:
        time.sleep(0.001)
    assert service.foreground_waiters == 1
    background = threading.Thread(target=call, args=("background", True))
    background.start()
    with service.slot_condition:
        service.gate.release()
        service.slot_condition.notify_all()
    foreground.join(3)
    background.join(3)
    assert order == ["foreground", "background"]


@pytest.mark.parametrize("error_type", [requests.ConnectionError, requests.ReadTimeout])
def test_embedding_retry_reuses_extraction(monkeypatch, error_type):
    calls = []
    job = dict(id="job", record_id="record", text="private", reference_time="2026-10-19")
    published = []

    def publish(*args):
        assert service.gate.locked()
        published.append(args)

    def rebuild():
        assert service.gate.locked()

    store = SimpleNamespace(
        rebuild_facts=rebuild, claim=lambda: job,
        publish=publish,
        fail=lambda *args: (_ for _ in ()).throw(AssertionError(args)),
    )

    def extract(*args):
        calls.append("extract")
        return {"memories": [{"content": "private"}]}, {}

    def embed(texts):
        calls.append("embed")
        if calls.count("embed") == 1:
            raise error_type()
        return np.array([[1, 0]], dtype=np.float32)

    monkeypatch.setattr("pma.service.extract_record", extract)
    service = Service(store, SimpleNamespace(embed=embed), SimpleNamespace(
        llm=SimpleNamespace(timeout=2), embedding_dimensions=2, embedding_key="test"))
    assert service.run_one()
    assert calls == ["extract", "embed", "embed"]
    assert len(published) == 1
    assert not service.gate.locked()


def test_extraction_read_timeout_is_not_repeated(monkeypatch):
    calls = []
    failures = []
    job = dict(id="job", record_id="record", text="synthetic", reference_time="2026-10-19")

    def extract(*args):
        calls.append("extract")
        raise requests.ReadTimeout()

    store = SimpleNamespace(rebuild_facts=lambda: None, claim=lambda: job,
                            fail=lambda *args: failures.append(args))
    monkeypatch.setattr("pma.service.extract_record", extract)
    service = Service(store, SimpleNamespace(), SimpleNamespace(
        llm=SimpleNamespace(timeout=2), embedding_dimensions=2, embedding_key="test"))
    assert service.run_one()
    assert calls == ["extract"]
    assert failures[0][1] == "MODEL_TIMEOUT"
    assert failures[0][2]["processing"]["performance"].get("retries", 0) == 0
    assert not service.gate.locked()


def test_wait_cancellation_removes_foreground_priority():
    service = Service(None, None, SimpleNamespace(llm=SimpleNamespace(timeout=2)))
    service.gate.acquire()
    with pytest.raises(AppError, match="CANCELLED"):
        with service.model_slot(cancelled=lambda: True):
            raise AssertionError("cancelled request acquired model")
    assert service.foreground_waiters == 0
    service.gate.release()
    with service.background_model_slot():
        assert service.gate.locked()


def test_background_wait_outlives_model_http_timeout_and_can_stop():
    service = Service(None, None, SimpleNamespace(llm=SimpleNamespace(timeout=0.01)))
    service.gate.acquire()
    finished = threading.Event()
    errors = []

    def background():
        try:
            with service.background_model_slot():
                finished.set()
        except AppError as exc:
            errors.append(exc.code)

    worker = threading.Thread(target=background)
    worker.start()
    assert not finished.wait(0.05)
    assert worker.is_alive()
    service.stop_event.set()
    worker.join(1)
    service.gate.release()
    assert errors == ["CANCELLED"]


def test_foreground_deadline_does_not_leak_waiter_or_release_owners_lock():
    service = Service(None, None, SimpleNamespace(llm=SimpleNamespace(timeout=0.01)))
    service.gate.acquire()
    with pytest.raises(AppError, match="MODEL_BUSY"):
        with service.model_slot():
            raise AssertionError("owner lock was bypassed")
    assert service.foreground_waiters == 0
    assert service.gate.locked()
    service.gate.release()


def test_first_explicit_memory_turn_does_not_classify_but_followups_still_do():
    calls = []

    def classify():
        calls.append(True)
        return {"mode": "memory", "query": "resolved question"}

    router = RetrievalRouter()
    route = router.decide("standalone question", force_memory=True, classify=classify)
    assert route.mode == RoutingMode.MEMORY_REQUIRED
    assert route.query == "standalone question"
    assert calls == []
    followup = router.decide("ambiguous question", history=[{}], force_memory=True,
                            classify=classify)
    assert followup.query == "resolved question"
    assert calls == [True]
    assert router.decide("question", memory_enabled=False, force_memory=True).mode == RoutingMode.CHAT_ONLY
