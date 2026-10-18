"""Additional safety contracts for the standalone trace collector."""

import json

import pytest

from .test_trace_contract import diagnostics


def test_refs_are_request_local_and_namespaced():
    d = diagnostics()
    with d.start_trace(enabled=True) as first:
        refs = [
            first.memory_ref("same-id"),
            first.record_ref("same-id"),
            first.relation_ref("same-id"),
        ]
        assert len(set(refs)) == 3
    with d.start_trace(enabled=True) as second:
        assert second.memory_ref("same-id") not in refs
    assert first.memory_ref("same-id") == refs[0]


def test_untrusted_values_cannot_hide_in_allowed_keys(tmp_path):
    d = diagnostics()
    path = tmp_path / "trace.jsonl"
    with d.start_trace(enabled=True, path=path) as trace:
        d.record_event(
            d.Stage.STRUCTURE_FILTER,
            status="PRIVATE_STATUS",
            reason="PRIVATE_REASON",
            input_count="PRIVATE_COUNT",
            citation_refs=["PRIVATE_ID"],
            candidates=[
                dict(
                    memory_ref="PRIVATE_ID",
                    status="PRIVATE_STATUS",
                    record_ref="PRIVATE_RECORD",
                    reason="PRIVATE_REASON",
                    score_components={"vector": "PRIVATE_SCORE"},
                )
            ],
        )
        d.record_event("PRIVATE_STAGE", status="completed")
        d.record_event(
            d.Stage.STRUCTURE_FILTER,
            candidates=[dict(memory_ref=trace.memory_ref("raw"), status="included")],
        )
    assert "PRIVATE" not in path.read_text("utf-8")
    assert len(trace.events) == 2
    assert trace.events[0]["status"] == "unknown"


def test_event_copy_cannot_mutate_persisted_data(tmp_path):
    d = diagnostics()
    path = tmp_path / "trace.jsonl"
    with d.start_trace(enabled=True, path=path) as trace:
        candidates = [dict(memory_ref=trace.memory_ref("raw"), status="selected")]
        d.record_event(d.Stage.EVIDENCE_SELECTION, candidates=candidates)
        candidates[0]["content"] = "PRIVATE_INPUT"
        trace.events[0]["content"] = "PRIVATE_OUTPUT"
    assert "PRIVATE" not in path.read_text("utf-8")


def test_off_does_not_construct_trace_or_touch_payload(monkeypatch, tmp_path):
    d = diagnostics()

    def forbidden(*args, **kwargs):
        raise AssertionError("off must not instantiate SearchTrace")

    monkeypatch.setattr(d, "SearchTrace", forbidden)
    with d.start_trace(enabled=False, path=tmp_path / "off.jsonl"):
        assert d.current_trace() is None
        d.record_candidates(d.Stage.STRUCTURE_FILTER, object())
        d.record_event(d.Stage.FINAL_DECISION, unexpected=object())
    assert list(tmp_path.iterdir()) == []


def test_disabled_nested_scope_does_not_leak_to_outer():
    d = diagnostics()
    with d.start_trace(enabled=True) as outer:
        with d.start_trace(enabled=False):
            d.record_event(d.Stage.FINAL_DECISION, status="answer")
            assert d.current_trace() is None
        assert d.current_trace() is outer
        assert not outer.events


@pytest.mark.parametrize("operation", ["record_event", "write_jsonl"])
def test_internal_errors_are_fail_open(monkeypatch, operation, tmp_path):
    d = diagnostics()

    def fail(*args, **kwargs):
        raise OSError("PRIVATE FAILURE")

    with d.start_trace(enabled=True, path=tmp_path / "trace.jsonl") as trace:
        monkeypatch.setattr(trace, operation, fail)
        d.record_event(d.Stage.FINAL_DECISION, status="answer")
    assert d.current_trace() is None


def test_initialization_failure_does_not_mask_caller_error(monkeypatch):
    d = diagnostics()

    def fail(*args, **kwargs):
        raise OSError("PRIVATE FAILURE")

    monkeypatch.setattr(d, "SearchTrace", fail)
    with pytest.raises(ValueError, match="original"):
        with d.start_trace(enabled=True):
            raise ValueError("original")
    assert d.current_trace() is None


def test_explicit_flush_and_finish_are_idempotent(tmp_path):
    d = diagnostics()
    path = tmp_path / "trace.jsonl"
    with d.start_trace(enabled=True, path=path) as trace:
        d.record_candidates(
            d.Stage.VECTOR_RETRIEVAL, [dict(memory_ref=trace.memory_ref("raw"), rank=1, score=1.0)]
        )
        assert trace.write_jsonl() is True
        assert trace.write_jsonl() is True
        d.record_event(d.Stage.FINAL_DECISION, status="answer")
    trace.finish_trace()
    assert len(path.read_text("utf-8").splitlines()) == 2
    assert [e["event_sequence"] for e in trace.events] == [1, 2]


def test_not_executed_counts_cannot_be_zero():
    d = diagnostics()
    with d.start_trace(enabled=True) as trace:
        d.record_event(
            d.Stage.VECTOR_RETRIEVAL, status="not_executed", input_count=0, output_count=0
        )
    assert trace.events[0]["input_count"] is None
    assert trace.events[0]["output_count"] is None


def test_bounded_events_report_truncation():
    d = diagnostics()
    trace = d.SearchTrace(max_events=2)
    for _ in range(3):
        trace.record_event(d.Stage.STRUCTURE_FILTER, input_count=1)
    assert len(trace.events) == 2
    assert trace.truncated is True
    assert trace.events[-1]["truncated"] is True


def test_finite_scores_and_timing_are_preserved(tmp_path):
    d = diagnostics()
    path = tmp_path / "trace.jsonl"
    with d.start_trace(enabled=True, path=path) as trace:
        ref = trace.memory_ref("raw")
        d.record_event(
            d.Stage.RANK_FUSION,
            elapsed_ms=2.4,
            duration_ms=0.4,
            candidates=[
                dict(
                    memory_ref=ref,
                    rank=1,
                    score=-0.25,
                    score_components=dict(vector=0.1, keyword=0.2, role=0, structure=0),
                )
            ],
        )
    event = json.loads(path.read_text("utf-8"))
    assert event["elapsed_ms"] == 2.4 and event["duration_ms"] == 0.4
    assert event["candidates"][0]["score"] == -0.25


def test_truncation_after_flush_is_visible_on_disk(tmp_path):
    d = diagnostics()
    path = tmp_path / "bounded.jsonl"
    trace = d.SearchTrace(path=path, max_events=1)
    trace.record_event(d.Stage.STRUCTURE_FILTER, input_count=1)
    trace.write_jsonl()
    trace.record_event(d.Stage.FINAL_DECISION, status="answer")
    trace.finish_trace()
    events = [json.loads(line) for line in path.read_text("utf-8").splitlines()]
    assert events[-1]["stage"] == "trace_summary"
    assert events[-1]["truncated"] is True
    assert [e["event_sequence"] for e in events] == [1, 2]


def test_empty_buffer_overflow_is_not_silently_lost(tmp_path):
    d = diagnostics()
    path = tmp_path / "bounded.jsonl"
    trace = d.SearchTrace(path=path, max_bytes=1024)
    trace.record_event(
        d.Stage.STRUCTURE_FILTER,
        candidates=[
            dict(memory_ref=trace.memory_ref(str(i)), status="included") for i in range(20)
        ],
    )
    trace.finish_trace()
    assert json.loads(path.read_text("utf-8"))["truncated"] is True


def test_other_trace_refs_are_not_accepted():
    d = diagnostics()
    with d.start_trace(enabled=True) as first:
        ref = first.memory_ref("raw")
    with d.start_trace(enabled=True) as second:
        d.record_candidates(d.Stage.STRUCTURE_FILTER, [dict(memory_ref=ref)])
    assert second.events[0]["candidates"] == []
