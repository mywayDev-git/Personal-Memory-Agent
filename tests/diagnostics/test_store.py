"""Observe real SQLite reads without changing SQL, transactions, or return values."""

import json
import sqlite3
from contextlib import closing, contextmanager

import numpy as np
import pytest
from conftest import memory

from pma import diagnostics as d


@pytest.fixture
def stored_rows(store, settings):
    for index in range(3):
        text = f"PRIVATE 합성 기록 {index}"
        store.create(text, None)
        job = store.claim()
        store.publish(job, [memory(text)], np.array([[1, 0, 0]]), settings.embedding_key, {})
    return store.snapshot(settings.embedding_key)[1]


def seed_links(store, rows):
    with store.connect(True) as db:
        for index in (1, 2):
            db.execute(
                "INSERT INTO memory_links VALUES (?,?,?,?,?)",
                (
                    f"private-link-{index}",
                    rows[0]["id"],
                    rows[index]["id"],
                    f"synthetic-signature-{index}",
                    json.dumps({"kind": "synthetic"}),
                ),
            )


@pytest.fixture
def sql_calls(monkeypatch):
    original = sqlite3.connect
    calls = []

    def connect(*args, **kwargs):
        calls.append("CONNECT")
        db = original(*args, **kwargs)
        db.set_trace_callback(calls.append)
        return db

    monkeypatch.setattr(sqlite3, "connect", connect)
    return calls


def test_snapshot_sql_result_order_and_private_fields(
    store, settings, stored_rows, sql_calls, tmp_path
):
    expected = store.snapshot(settings.embedding_key)
    expected_sql = sql_calls[:]
    sql_calls.clear()
    path = tmp_path / "snapshot.jsonl"
    with d.start_trace(enabled=True, path=path) as trace:
        actual = store.snapshot(settings.embedding_key)
    assert actual == expected
    assert sql_calls == expected_sql
    (event,) = trace.events
    assert event["stage"] == "snapshot"
    assert event["input_count"] is None  # Full DB population is not observed by this query.
    assert event["output_count"] == 3
    assert event["duration_ms"] >= 0
    assert [c["memory_ref"] for c in event["candidates"]] == [
        trace.memory_ref(r["id"]) for r in actual[1]
    ]
    assert [c["record_ref"] for c in event["candidates"]] == [
        trace.record_ref(r["record_id"]) for r in actual[1]
    ]
    assert all(
        c["has_fact"] and c["has_embedding"] and c["has_record"] for c in event["candidates"]
    )
    raw = path.read_text("utf-8")
    assert "PRIVATE" not in raw and "vector" not in raw
    assert all(r["id"] not in raw and r["record_id"] not in raw for r in stored_rows)


@pytest.mark.parametrize("missing", ["fact", "embedding", "record"])
def test_snapshot_reports_only_observable_absences(store, settings, stored_rows, missing):
    victim = stored_rows[0]
    # Deliberately construct a dangling record FK using a separate fixture-only connection.
    # Production code keeps foreign_keys ON and must not add a diagnostic repair/query.
    with closing(sqlite3.connect(store.path)) as db:
        if missing == "record":
            db.execute("DELETE FROM records WHERE id=?", (victim["record_id"],))
        else:
            table = "facts" if missing == "fact" else "embeddings"
            db.execute(f"DELETE FROM {table} WHERE memory_id=?", (victim["id"],))
        db.commit()
    with d.start_trace(enabled=True) as trace:
        _, rows = store.snapshot(settings.embedding_key)
    (event,) = trace.events
    assert event["unobserved_reason"] == "not_observed"
    assert event["output_count"] == len(rows)
    if missing == "fact":
        candidate = next(
            c for c in event["candidates"] if c["memory_ref"] == trace.memory_ref(victim["id"])
        )
        assert candidate["has_fact"] is False
        assert candidate["has_embedding"] is True
    else:
        assert len(rows) == 2
        assert victim["id"] not in [r["id"] for r in rows]
        assert all("reason" not in c for c in event["candidates"])


@pytest.mark.parametrize("selection", ["all", "subset", "empty", "record", "generator"])
def test_links_targets_returned_ids_and_sql_unchanged(
    store, settings, stored_rows, sql_calls, selection
):
    seed_links(store, stored_rows)
    ids = [r["id"] for r in stored_rows]

    def arguments():
        if selection == "record":
            return {"record_id": stored_rows[0]["record_id"]}
        if selection == "all":
            return {}
        if selection == "generator":
            return {"memory_ids": iter(ids)}
        return {"memory_ids": set(ids[:2]) if selection == "subset" else set()}

    sql_calls.clear()
    expected = store.links(**arguments())
    expected_sql = sql_calls[:]
    sql_calls.clear()
    with d.start_trace(enabled=True) as trace:
        actual = store.links(**arguments())
    assert actual == expected
    assert sql_calls == expected_sql
    (event,) = trace.events
    assert event["stage"] == "relation_lookup"
    assert event["output_count"] == len(actual)
    assert event["relation_refs"] == [trace.relation_ref(r["id"]) for r in actual]
    assert event["duration_ms"] >= 0
    if selection == "empty":
        assert sql_calls == []
        assert event["executed"] is False and event["input_count"] == 0
    elif selection in {"subset", "generator"}:
        selected = ids[:2] if selection == "subset" else ids
        assert event["input_count"] == len(selected)
        assert event["evidence_refs"] == [trace.memory_ref(mid) for mid in sorted(selected)]
    else:
        assert event["input_count"] is None
        assert event["evidence_refs"] is None
    if selection == "record":
        assert event["record_refs"] == [trace.record_ref(stored_rows[0]["record_id"])]
    for relation in actual:
        observed = [
            c
            for c in event["candidates"]
            if c["relation_ref"] == trace.relation_ref(relation["id"])
        ]
        assert [c["memory_ref"] for c in observed] == [
            trace.memory_ref(mid) for mid in relation["citations"]
        ]
    serialized = json.dumps(trace.events)
    assert "PRIVATE" not in serialized and "private-link" not in serialized
    assert all(r["id"] not in serialized and r["record_id"] not in serialized for r in stored_rows)


def test_links_no_matching_relations_are_observed_as_zero(store, stored_rows):
    ids = {r["id"] for r in stored_rows}
    with d.start_trace(enabled=True) as trace:
        assert store.links(memory_ids=ids) == []
    (event,) = trace.events
    assert event["executed"] is True
    assert event["input_count"] == 3 and event["output_count"] == 0
    assert event["relation_refs"] == []


@pytest.mark.parametrize("operation", ["snapshot", "links"])
def test_off_avoids_candidate_preparation(store, settings, stored_rows, monkeypatch, operation):
    def forbidden(*args, **kwargs):
        raise AssertionError("diagnostics OFF must not prepare refs")

    monkeypatch.setattr(d.SearchTrace, "memory_ref", forbidden)
    with d.start_trace(enabled=False):
        if operation == "snapshot":
            assert len(store.snapshot(settings.embedding_key)[1]) == 3
        else:
            assert store.links(memory_ids={stored_rows[0]["id"]}) == []


@pytest.mark.parametrize("operation", ["snapshot", "links"])
def test_observation_failures_do_not_change_results(
    store, settings, stored_rows, monkeypatch, operation
):
    call = (
        (lambda: store.snapshot(settings.embedding_key)) if operation == "snapshot" else store.links
    )
    expected = call()

    def fail(*args, **kwargs):
        raise RuntimeError("PRIVATE diagnostic failure")

    with d.start_trace(enabled=True) as trace:
        monkeypatch.setattr(trace, "record_event", fail)
        assert call() == expected
    assert d.current_trace() is None


@pytest.mark.parametrize("operation", ["snapshot", "links"])
def test_database_errors_are_never_masked(store, settings, monkeypatch, operation):
    original = sqlite3.OperationalError("PRIVATE DB ERROR")

    def fail(*args, **kwargs):
        raise original

    monkeypatch.setattr(store, "connect", fail)
    with d.start_trace(enabled=True) as trace:
        with pytest.raises(sqlite3.OperationalError) as caught:
            if operation == "snapshot":
                store.snapshot(settings.embedding_key)
            else:
                store.links()
    assert caught.value is original
    assert "PRIVATE" not in str(trace.events)
    assert d.current_trace() is None


@pytest.mark.parametrize("operation", ["snapshot", "links"])
def test_event_preparation_happens_after_transaction_close(
    store, settings, stored_rows, monkeypatch, operation
):
    connect = store.connect
    active = False
    observed = []

    @contextmanager
    def watched(write=False):
        nonlocal active
        with connect(write) as db:
            active = True
            yield db
        active = False

    monkeypatch.setattr(store, "connect", watched)
    with d.start_trace(enabled=True) as trace:
        original = trace.record_event

        def record(*args, **kwargs):
            observed.append(active)
            return original(*args, **kwargs)

        monkeypatch.setattr(trace, "record_event", record)
        if operation == "snapshot":
            store.snapshot(settings.embedding_key)
        else:
            store.links()
    assert observed == [False]


def test_ref_preparation_error_cannot_break_snapshot(store, settings, stored_rows, monkeypatch):
    expected = store.snapshot(settings.embedding_key)
    with d.start_trace(enabled=True) as trace:

        def fail(*args):
            raise RuntimeError("PRIVATE")

        monkeypatch.setattr(trace, "memory_ref", fail)
        assert store.snapshot(settings.embedding_key) == expected
    assert trace.recording_failed
    assert trace.events[-1]["stage"] == "trace_summary"
    assert "PRIVATE" not in json.dumps(trace.events)
