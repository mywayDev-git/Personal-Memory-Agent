"""Reasons describe existing branches; tests must not introduce new filters."""

import pytest

from pma.service import Service

from .helpers import Models, SnapshotStore, row
from .test_trace_contract import diagnostics

FILTER_CASES = [
    ("missing", "synthetic", {}, None, "fact_missing"),
    (
        "relation",
        "달린 기록",
        {"relation": "visit", "distance_m": ["5000"]},
        None,
        "relation_mismatch",
    ),
    ("person", "내가 달린 기록", {"relation": "run", "actor": "민수"}, None, "person_mismatch"),
    (
        "quantity",
        "4km 미만 달린 기록",
        {"relation": "run", "distance_m": ["5000"]},
        None,
        "quantity_mismatch",
    ),
    ("state", "달린 기록", {"relation": "run", "state": "planned"}, None, "status_mismatch"),
    ("place", "서울숲에서 뭐 했지", {}, None, "place_mismatch"),
    ("unknown_time", "synthetic", {}, {"date_from": "2026-10-01", "date_to": None}, "time_unknown"),
    ("time", "synthetic", {}, {"date_from": "2026-10-04", "date_to": None}, "time_mismatch"),
    ("activity", "뭐 했지", {"state": "desire"}, None, "activity_state"),
    ("preference", "선호가 바뀌었어", {}, None, "preference_change"),
    # Multiple mismatches: relationship is tested before actor/state/quantity/time.
    (
        "first",
        "내가 4km 미만 달린 기록",
        {"relation": "visit", "actor": "민수", "state": "planned", "distance_m": ["5000"]},
        {"date_from": "2026-10-04", "date_to": None},
        "relation_mismatch",
    ),
]


@pytest.mark.parametrize("scenario,question,changes,filters,reason", FILTER_CASES)
def test_first_actual_exclusion_reason(settings, scenario, question, changes, filters, reason):
    d = diagnostics()
    item = row(**changes)
    if scenario == "missing":
        item["fact"] = None
    if scenario == "unknown_time":
        item["fact"]["event_time"] = dict(start=None, end=None, certainty="uncertain")
    with d.start_trace(enabled=True) as trace:
        result = Service(SnapshotStore([item]), Models(), settings).search(
            question, filters, today="2026-10-17"
        )
    assert result["results"] == []
    events = [e for e in trace.events if e["stage"] == "structure_filter"]
    candidates = [c for e in events for c in e.get("candidates", []) if c["status"] == "excluded"]
    assert [(c["memory_ref"], c["reason"]) for c in candidates] == [
        (trace.memory_ref(item["id"]), reason)
    ]
    assert reason in {r.value for r in d.Reason}
    assert not any(
        e["stage"] in {"vector_retrieval", "keyword_retrieval"}
        and e.get("status") != "not_executed"
        for e in trace.events
    )
    for event in trace.events:
        if event.get("status") == "not_executed":
            assert event.get("input_count") is None and event.get("output_count") is None


def test_explicit_person_and_requested_object_branches(settings):
    d = diagnostics()
    rows = [
        row(0, relation="visit", object_key="부산"),
        row(1, relation="visit", object_key="제주"),
    ]
    with d.start_trace(enabled=True) as trace:
        Service(SnapshotStore(rows), Models(), settings).search("부산 갔어", today="2026-10-17")
    excluded = [
        c
        for e in trace.events
        if e["stage"] == "structure_filter"
        for c in e.get("candidates", [])
        if c["status"] == "excluded"
    ]
    assert [(c["memory_ref"], c["reason"]) for c in excluded] == [
        (trace.memory_ref("memory-01"), "requested_object")
    ]
    rows = [row(0, actor="지연"), row(1, actor="민수")]
    with d.start_trace(enabled=True) as trace:
        Service(SnapshotStore(rows), Models(), settings).search(
            "지연 synthetic", today="2026-10-17"
        )
    excluded = [
        c
        for e in trace.events
        if e["stage"] == "structure_filter"
        for c in e.get("candidates", [])
        if c["status"] == "excluded"
    ]
    assert [(c["memory_ref"], c["reason"]) for c in excluded] == [
        (trace.memory_ref("memory-01"), "person_mismatch")
    ]
