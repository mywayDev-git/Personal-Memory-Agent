"""RED tests: the diagnostics API below is a proposed implementation contract.

Imports happen inside tests so a missing module does not hide baseline results.
No skips or xfails: these requirements must fail until implemented.
"""

import asyncio
import importlib
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from pma.settings import AppSettings

from .helpers import row, run


def diagnostics():
    return importlib.import_module("pma.diagnostics")


def test_schema_sequence_pseudonyms_and_memory_only_mapping(tmp_path):
    d = diagnostics()
    path = tmp_path / "trace.jsonl"
    with d.start_trace(enabled=True, path=path) as trace:
        first = trace.memory_ref("private-memory-id")
        assert first == trace.memory_ref("private-memory-id")
        assert first != trace.memory_ref("another-private-id")
        d.record_event(
            d.Stage.STRUCTURE_FILTER,
            input_count=2,
            output_count=1,
            candidates=[dict(memory_ref=first, status="included")],
        )
        d.record_event(
            d.Stage.EVIDENCE_SELECTION,
            input_count=1,
            output_count=1,
            candidates=[dict(memory_ref=first, status="selected", rank=1, score=0.25)],
        )
        assert trace.memory_ref("private-memory-id") == first
    events = [json.loads(line) for line in path.read_text("utf-8").splitlines()]
    assert len(events) >= 2
    assert [e["event_sequence"] for e in events] == list(range(1, len(events) + 1))
    assert {e["trace_id"] for e in events} == {trace.trace_id}
    assert all(e["schema_version"] == "pma.search_trace.v1" for e in events)
    assert all(e["elapsed_ms"] >= 0 and "status" in e for e in events)
    assert "private-memory-id" not in path.read_text("utf-8")
    assert "another-private-id" not in path.read_text("utf-8")
    assert d.current_trace() is None


def test_off_and_no_path_never_write(tmp_path):
    d = diagnostics()
    path = tmp_path / "off.jsonl"
    with d.start_trace(enabled=False, path=path):
        d.record_event(d.Stage.FINAL_DECISION, status="answer")
    assert not path.exists()
    with d.start_trace(enabled=True) as trace:
        d.record_event(d.Stage.FINAL_DECISION, status="answer")
    assert trace.events
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "private_key",
    ["question", "text", "content", "actor", "place", "prompt", "response", "embedding", "vector"],
)
def test_default_events_reject_private_payloads(tmp_path, private_key):
    d = diagnostics()
    path = tmp_path / "safe.jsonl"
    with d.start_trace(enabled=True, path=path):
        d.record_event(d.Stage.QUERY_UNDERSTANDING, **{private_key: "PRIVATE_SENTINEL"})
    assert "PRIVATE_SENTINEL" not in path.read_text("utf-8")


def test_nested_private_data_and_nonserializable_values_cannot_escape(tmp_path):
    d = diagnostics()
    path = tmp_path / "safe.jsonl"
    with d.start_trace(enabled=True, path=path) as trace:
        d.record_event(
            d.Stage.VECTOR_RETRIEVAL,
            candidates=[
                dict(
                    memory_ref=trace.memory_ref("secret-id"),
                    score=float("nan"),
                    content="NESTED_SECRET",
                    vector=[0.125, 0.875],
                )
            ],
            unexpected=object(),
        )
    text = path.read_text("utf-8") if path.exists() else ""
    assert "NESTED_SECRET" not in text and "secret-id" not in text
    assert "0.875" not in text and "NaN" not in text


def test_unwritable_path_does_not_mask_original_exception(tmp_path):
    d = diagnostics()
    with pytest.raises(ValueError, match="ORIGINAL"):
        with d.start_trace(enabled=True, path=tmp_path):  # directory cannot be a JSONL file
            d.record_event(d.Stage.FINAL_DECISION, status="error")
            raise ValueError("ORIGINAL")
    assert d.current_trace() is None


def test_context_restored_after_nested_scope_and_exception():
    d = diagnostics()
    with d.start_trace(enabled=True) as outer:
        with pytest.raises(RuntimeError):
            with d.start_trace(enabled=True) as inner:
                assert d.current_trace() is inner
                raise RuntimeError("synthetic")
        assert d.current_trace() is outer
    assert d.current_trace() is None


def test_async_requests_are_isolated():
    d = diagnostics()

    async def request(index):
        with d.start_trace(enabled=True) as trace:
            await asyncio.sleep(0)
            assert d.current_trace() is trace
            d.record_event(d.Stage.STRUCTURE_FILTER, input_count=index, output_count=index)
            await asyncio.sleep(0)
        return trace

    async def main():
        return await asyncio.gather(*(request(i) for i in range(6)))

    traces = asyncio.run(main())
    assert len({t.trace_id for t in traces}) == 6
    for index, trace in enumerate(traces):
        events = [e for e in trace.events if e["stage"] == "structure_filter"]
        assert [e["input_count"] for e in events] == [index]
    assert d.current_trace() is None


def test_threaded_requests_share_jsonl_without_mixing_events(tmp_path):
    d = diagnostics()
    path = tmp_path / "parallel.jsonl"

    def request(index):
        with d.start_trace(enabled=True, path=path) as trace:
            for _ in range(5):
                d.record_event(d.Stage.STRUCTURE_FILTER, input_count=index, output_count=index)
        assert d.current_trace() is None
        return trace.trace_id, index

    with ThreadPoolExecutor(max_workers=4) as pool:
        requests = dict(pool.map(request, range(8)))
    events = [json.loads(line) for line in path.read_text("utf-8").splitlines()]
    assert len(requests) == 8
    for trace_id, index in requests.items():
        selected = [
            e for e in events if e["trace_id"] == trace_id and e["stage"] == "structure_filter"
        ]
        assert len(selected) == 5
        assert all(e["input_count"] == index for e in selected)


@pytest.mark.parametrize(
    "value,expected", [(None, False), ("0", False), ("1", True), ("invalid", False)]
)
def test_settings_opt_in_preserves_all_existing_values(monkeypatch, value, expected):
    monkeypatch.delenv("PMA_DIAGNOSTICS", raising=False)
    monkeypatch.delenv("PMA_DIAGNOSTICS_PATH", raising=False)
    baseline = AppSettings.from_env()
    if value is not None:
        monkeypatch.setenv("PMA_DIAGNOSTICS", value)
    configured = AppSettings.from_env()
    assert configured.diagnostics is expected
    assert not configured.diagnostics_path
    for name in AppSettings.__dataclass_fields__:
        if name not in {"diagnostics", "diagnostics_path"}:
            assert getattr(configured, name) == getattr(baseline, name)


@pytest.mark.parametrize(
    "question,options",
    [
        ("synthetic", {}),
        ("그때 synthetic", {}),
        ("synthetic", {"selected": []}),
        ("synthetic", {"verified": False}),
        ("synthetic", {"error": "understand"}),
    ],
)
def test_service_on_off_full_output_and_calls_identical(settings, tmp_path, question, options):
    path = tmp_path / "service.jsonl"
    off = replace(settings, diagnostics=False, diagnostics_path=path)
    on = replace(settings, diagnostics=True, diagnostics_path=path)
    rows = [row(i) for i in range(30)]
    expected = run(off, rows, question=question, **options)
    assert not path.exists()
    assert run(on, rows, question=question, **options) == expected
    events = [json.loads(line) for line in path.read_text("utf-8").splitlines()]
    assert len({e["trace_id"] for e in events}) == 1
    assert events[-1]["stage"] == "final_decision"
    assert events[-1]["status"] == (
        "clarification"
        if "그때" in question
        else "answer"
        if expected[0]["status"] == "answered"
        else "abstention"
    )
    # Clarification currently happens AFTER retrieval; never report it as unexecuted.
    assert any(e["stage"] == "vector_retrieval" for e in events)
    serialized = path.read_text("utf-8")
    for private in ("synthetic", "memory-00", "record-00", "합성 답변", "그때"):
        assert private not in serialized


def test_stage_candidates_scores_limits_and_citations(settings):
    d = diagnostics()
    with d.start_trace(enabled=True) as trace:
        response, _, _ = run(settings, [row(i) for i in range(30)])
    stages = {e["stage"]: e for e in trace.events}
    for stage in (
        "structure_filter",
        "vector_retrieval",
        "keyword_retrieval",
        "rank_fusion",
        "evidence_selection",
        "relation_lookup",
        "answer_validation",
        "final_decision",
    ):
        assert stage in stages
    assert stages["structure_filter"]["input_count"] == 30
    for stage in ("vector_retrieval", "keyword_retrieval"):
        candidates = stages[stage]["candidates"]
        assert stages[stage]["output_count"] == len(candidates) == 20
        assert [c["rank"] for c in candidates] == list(range(1, 21))
        assert [c["memory_ref"] for c in candidates] == [
            trace.memory_ref(f"memory-{i:02d}") for i in range(20)
        ]
        assert [c["score"] for c in candidates] == [1.0] * 20
    merged = stages["rank_fusion"]["candidates"]
    assert [c["score"] for c in merged] == [2 / (60 + rank) for rank in range(1, 21)]
    for candidate in merged:
        assert set(candidate["score_components"]) == {"vector", "keyword", "role", "structure"}
        assert sum(candidate["score_components"].values()) == candidate["score"]
    selected = stages["evidence_selection"]["candidates"]
    assert [c["memory_ref"] for c in selected if c["status"] == "selected"] == [
        trace.memory_ref(r["id"]) for r in response["results"]
    ]
    assert len([c for c in selected if c.get("reason") == "evidence_limit"]) == 12
    assert stages["final_decision"]["citation_refs"] == [trace.memory_ref("memory-00")]


@pytest.mark.parametrize("error", ["select", "answer"])
def test_service_error_finishes_trace_and_keeps_exception(settings, tmp_path, error):
    d = diagnostics()
    path = tmp_path / "errors.jsonl"
    enabled = replace(settings, diagnostics=True, diagnostics_path=path)
    with pytest.raises(ValueError):
        run(enabled, [row()], error=error)
    events = [json.loads(line) for line in path.read_text("utf-8").splitlines()]
    assert events[-1]["stage"] == "final_decision"
    assert events[-1]["status"] == "error"
    assert d.current_trace() is None


def test_service_logging_failure_does_not_change_answer(settings, tmp_path):
    rows = [row()]
    expected = run(settings, rows)
    # No new directories or model calls may be needed to recover from logging failure.
    enabled = replace(settings, diagnostics=True, diagnostics_path=tmp_path)
    assert run(enabled, rows) == expected


def test_explicit_path_does_not_enable_diagnostics(monkeypatch, tmp_path):
    path = tmp_path / "explicit.jsonl"
    monkeypatch.setenv("PMA_DIAGNOSTICS", "0")
    monkeypatch.setenv("PMA_DIAGNOSTICS_PATH", str(path))
    configured = AppSettings.from_env()
    assert configured.diagnostics is False
    assert str(configured.diagnostics_path) == str(path)
    assert not path.exists()


def test_sequential_requests_and_empty_candidates(settings, tmp_path):
    d = diagnostics()
    path = tmp_path / "sequential.jsonl"
    configured = replace(settings, diagnostics=True, diagnostics_path=path)
    for _ in range(2):
        response, calls, _ = run(configured, [])
        assert response["status"] == "insufficient_evidence"
        assert [c[0] for c in calls] == ["understand"]
        assert d.current_trace() is None
    events = [json.loads(line) for line in path.read_text("utf-8").splitlines()]
    assert len({e["trace_id"] for e in events}) == 2
    assert len([e for e in events if e["stage"] == "final_decision"]) == 2
    assert not any(
        e["stage"] == "vector_retrieval" and e["status"] != "not_executed" for e in events
    )
