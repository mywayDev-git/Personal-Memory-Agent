"""Instrument the real batching method without HTTP calls or prompt changes."""

from copy import deepcopy

import pytest
import requests

from pma.models import LocalModels

from .helpers import row
from .test_trace_contract import diagnostics


@pytest.mark.parametrize("count", [0, 1, 4, 5, 10])
def test_selection_batches_preserve_payload_calls_and_output(settings, monkeypatch, count):
    d = diagnostics()
    gateway = LocalModels(settings)
    calls = []

    def structured(*args, **kwargs):
        calls.append(deepcopy((args, kwargs)))
        return {"ids": args[2]["properties"]["ids"]["items"]["enum"]}

    monkeypatch.setattr(gateway, "structured", structured)
    monkeypatch.setattr(gateway, "compact_evidence", lambda rows: [{"id": r["id"]} for r in rows])
    evidence = [row(i) for i in range(count)]
    expected = gateway.select("PRIVATE QUESTION", evidence)
    expected_calls = deepcopy(calls)
    calls.clear()
    with d.start_trace(enabled=True) as trace:
        actual = gateway.select("PRIVATE QUESTION", evidence)
    assert actual == expected
    assert calls == expected_calls
    batches = [e for e in trace.events if e["stage"] == "evidence_selection_batch"]
    assert len(batches) == (count + 3) // 4
    assert [e["input_count"] for e in batches] == [min(4, count - i) for i in range(0, count, 4)]
    for batch, offset in zip(batches, range(0, count, 4), strict=True):
        assert [c["memory_ref"] for c in batch["candidates"] if c["status"] == "selected"] == [
            trace.memory_ref(f"memory-{i:02d}") for i in range(offset, min(offset + 4, count))
        ]
    assert "PRIVATE QUESTION" not in str(trace.events)


@pytest.mark.parametrize(
    "error", [ValueError("PRIVATE PARSE ERROR"), requests.Timeout("PRIVATE TIMEOUT")]
)
def test_batch_errors_are_observed_without_retry_or_masking(settings, monkeypatch, error):
    d = diagnostics()
    gateway = LocalModels(settings)
    calls = []

    def fail(*args, **kwargs):
        calls.append(1)
        raise error

    monkeypatch.setattr(gateway, "structured", fail)
    monkeypatch.setattr(gateway, "compact_evidence", lambda rows: [])
    with d.start_trace(enabled=True) as trace:
        with pytest.raises(type(error)) as caught:
            gateway.select("PRIVATE QUESTION", [row()])
    assert caught.value is error
    assert calls == [1]
    batches = [e for e in trace.events if e["stage"] == "evidence_selection_batch"]
    assert len(batches) == 1 and batches[0]["status"] == "error"
    assert "PRIVATE" not in str(trace.events)


@pytest.mark.parametrize(
    "raw,valid,parsed",
    [
        ('{"ids":["memory-00"]}', True, True),
        ('{"ids":[]}', True, True),
        ('{"ids":["memory-00","memory-00"]}', False, True),
        ('{"ids":["PRIVATE-unknown"]}', False, True),
        ("PRIVATE broken JSON", False, False),
    ],
)
def test_real_structured_transport_and_schema_unchanged(settings, monkeypatch, raw, valid, parsed):
    import pma.models as module

    gateway = LocalModels(settings)
    calls = []
    monkeypatch.setattr(gateway, "budget", lambda *a, **k: None)

    def chat(session, *args, **kwargs):
        calls.append(deepcopy((args, kwargs)))
        return raw, None, None

    monkeypatch.setattr(module, "chat", chat)

    def run():
        try:
            return gateway.select("PRIVATE", [row()])
        except Exception as error:
            return type(error), str(error)

    expected = run()
    original_calls = deepcopy(calls)
    calls.clear()
    with diagnostics().start_trace(enabled=True) as trace:
        assert run() == expected
    assert calls == original_calls and len(calls) == 1
    event = next(e for e in trace.events if e["stage"] == "evidence_selection_batch")
    assert event["status"] == ("completed" if valid else "error")
    assert event["parse_succeeded"] is parsed
    assert event["model_called"] is True
    assert "PRIVATE" not in str(trace.events)


@pytest.mark.parametrize(
    "method,stage,result",
    [
        (
            "understand",
            "model_understanding",
            {"intent": "recall", "date_from": None, "date_to": None},
        ),
        (
            "answer",
            "model_answer",
            {"status": "answered", "items": [{"text": "PRIVATE", "citations": ["memory-00"]}]},
        ),
    ],
)
def test_other_model_boundaries(settings, monkeypatch, method, stage, result):
    gateway = LocalModels(settings)
    monkeypatch.setattr(gateway, "structured", lambda *a, **k: result)
    args = ("2026-10-17",) if method == "understand" else ([row()],)
    with diagnostics().start_trace(enabled=True) as trace:
        assert getattr(gateway, method)("PRIVATE", *args) is result
    event = next(e for e in trace.events if e["stage"] == stage)
    assert event["status"] == "completed"
    assert "PRIVATE" not in str(trace.events)


def test_collector_failure_does_not_change_model_return(settings, monkeypatch):
    gateway = LocalModels(settings)
    selected = ["memory-00"]
    monkeypatch.setattr(gateway, "structured", lambda *a, **k: {"ids": selected})
    with diagnostics().start_trace(enabled=True) as trace:
        monkeypatch.setattr(trace, "memory_ref", lambda *a: 1 / 0)
        assert gateway.select("PRIVATE", [row()]) is selected
    assert trace.recording_failed


@pytest.mark.parametrize("policy", [False, True])
def test_answer_repair_and_verification_calls_preserved(settings, monkeypatch, policy):
    from dataclasses import replace

    gateway = LocalModels(replace(settings, answer_validation=policy))
    calls = []

    def structured(*args, **kwargs):
        calls.append(deepcopy((args, kwargs)))
        properties = args[2]["properties"]
        if "verdict" in properties:
            return {"reason": "PRIVATE", "verdict": "supported_answer"}
        if "abstention" in properties:
            return {
                "items": [],
                "fulfillment": "missing",
                "abstention": "appropriate",
                "reason": "PRIVATE",
            }
        return {"status": "insufficient_evidence", "items": []}

    monkeypatch.setattr(gateway, "structured", structured)

    def run():
        answer = gateway.answer("PRIVATE", [row()])
        repaired = gateway.answer("PRIVATE", [row()], feedback={"PRIVATE": "PRIVATE"})
        return answer, repaired, gateway.verify("PRIVATE", [row()], [])

    expected = run()
    original_calls = deepcopy(calls)
    calls.clear()
    with diagnostics().start_trace(enabled=True) as trace:
        assert run() == expected
    assert calls == original_calls and len(calls) == 3
    generated = [e for e in trace.events if e["stage"] == "model_answer"]
    assert [e["regenerated"] for e in generated] == [False, True]
    assert next(e for e in trace.events if e["stage"] == "model_verify")["supported"]
    assert "PRIVATE" not in str(trace.events)


def test_service_does_not_mislabel_model_limit(settings, monkeypatch):
    from pma.service import Service

    from .helpers import Models, SnapshotStore

    gateway = LocalModels(settings)
    fake = Models()
    monkeypatch.setattr(gateway, "embed", fake.embed)
    monkeypatch.setattr(gateway, "understand", fake.understand)
    monkeypatch.setattr(
        gateway, "structured", lambda *a, **k: {"ids": a[2]["properties"]["ids"]["items"]["enum"]}
    )
    service = Service(SnapshotStore([row(i) for i in range(10)]), gateway, settings)
    with diagnostics().start_trace(enabled=True) as trace:
        service.search("synthetic", today="2026-10-17")
    merge = next(e for e in trace.events if e["stage"] == "evidence_selection_merge")
    summary = next(e for e in trace.events if e["stage"] == "evidence_selection")
    dropped = {c["memory_ref"] for c in merge["candidates"] if c.get("reason") == "evidence_limit"}
    assert len(dropped) == 2
    assert all(
        c["reason"] == "evidence_limit" for c in summary["candidates"] if c["memory_ref"] in dropped
    )


@pytest.mark.parametrize(
    "method,args,stage",
    [
        ("understand", ("2026-10-17",), "model_understanding"),
        ("answer", ([row()],), "model_answer"),
        ("review", ([row()], {"status": "insufficient_evidence", "items": []}), "model_review"),
        ("verify", ([row()], []), "model_verify"),
    ],
)
def test_model_errors_preserve_exception(settings, monkeypatch, method, args, stage):
    gateway = LocalModels(settings)
    error = requests.Timeout("PRIVATE")
    calls = []

    def fail(*a, **k):
        calls.append(1)
        raise error

    monkeypatch.setattr(gateway, "structured", fail)
    with diagnostics().start_trace(enabled=True) as trace:
        with pytest.raises(requests.Timeout) as caught:
            getattr(gateway, method)("PRIVATE", *args)
    assert caught.value is error and calls == [1]
    assert next(e for e in trace.events if e["stage"] == stage)["status"] == "error"
    assert "PRIVATE" not in str(trace.events)


def test_merge_records_limit_separately(settings, monkeypatch):
    gateway = LocalModels(settings)
    monkeypatch.setattr(
        gateway, "structured", lambda *a, **k: {"ids": a[2]["properties"]["ids"]["items"]["enum"]}
    )
    with diagnostics().start_trace(enabled=True) as trace:
        result = gateway.select("PRIVATE", [row(i) for i in range(10)])
    merge = next(e for e in trace.events if e["stage"] == "evidence_selection_merge")
    assert merge["model_selected_refs"] == [trace.memory_ref(row(i)["id"]) for i in range(10)]
    assert merge["evidence_refs"] == [trace.memory_ref(i) for i in result]
    assert [
        c["memory_ref"] for c in merge["candidates"] if c.get("reason") == "evidence_limit"
    ] == [trace.memory_ref(row(i)["id"]) for i in (8, 9)]


@pytest.mark.parametrize(
    "selected", [[], ["memory-01"], ["memory-00", "memory-00"], ["PRIVATE-unknown"]]
)
def test_injected_selection_is_never_repaired(settings, monkeypatch, selected):
    gateway = LocalModels(settings)
    monkeypatch.setattr(gateway, "structured", lambda *a, **k: {"ids": selected})
    with diagnostics().start_trace(enabled=True) as trace:
        assert gateway.select("PRIVATE", [row(0), row(1)]) is selected
    batch = next(e for e in trace.events if e["stage"] == "evidence_selection_batch")
    assert batch["model_selected_refs"] == [trace.memory_ref(i) for i in selected]
    assert "PRIVATE" not in str(trace.events)
