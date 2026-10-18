"""Observe existing interpretation, including known unresolved-anchor behavior."""

from copy import deepcopy

import pytest

from pma import diagnostics as d
from pma.facts import compatible, explicit_dates, query_plan
from pma.service import Service

from .helpers import Models, SnapshotStore, row

QUESTIONS = [
    "그때 서울숲에서 지연이 원한 선물이 뭐였지?",
    "2026년 10월 3일 달린 기록",
    "서울숲에서 지연이 원한 선물이 뭐였지?",
    "내가 달리지 않은 기록",
    "5km 이상 달린 기록과 3km 기록 비교",
]


@pytest.mark.parametrize("question", QUESTIONS)
def test_plan_and_dates_unchanged(question):
    understood = {"intent": "recall", "date_from": None, "date_to": None}
    expected = query_plan(question, understood, "2026-10-17")
    dates = explicit_dates(question, "2026-10-17")
    original = deepcopy(understood)
    with d.start_trace(enabled=True) as trace:
        assert query_plan(question, understood, "2026-10-17") == expected
        assert explicit_dates(question, "2026-10-17") == dates
    assert understood == original
    events = [e for e in trace.events if e["stage"] == "query_plan"]
    assert events
    anchor = next(e for e in events if e.get("condition") == "time_anchor")
    assert anchor["needs_time_anchor"] == expected["needs_time_anchor"]
    assert anchor["reason"] == (
        "unresolved_time_anchor" if expected["needs_time_anchor"] else "condition_absent"
    )
    assert all("source" in e and "reason" in e for e in events)
    assert not any(word in str(trace.events) for word in (question, "서울숲", "지연", "2026-10-03"))


@pytest.mark.parametrize("filters", [None, {"date_to": "2026-10-03"}])
def test_clarification_and_override_unchanged(settings, filters):
    question = QUESTIONS[0]

    def run():
        return Service(SnapshotStore([]), Models(), settings).answer(
            question, filters, today="2026-10-17"
        )

    expected = run()
    with d.start_trace(enabled=True) as trace:
        assert run() == expected
    resolved = [
        e
        for e in trace.events
        if e["stage"] == "query_condition" and e.get("condition") == "time_anchor"
    ]
    assert resolved[-1]["needs_time_anchor"] is (filters is None)
    assert ("clarification" in expected) is (filters is None)


@pytest.mark.parametrize(
    "fact,reason",
    [
        (row(relation="visit")["fact"], "relation_mismatch"),
        (row(relation="run", actor="지연")["fact"], "person_mismatch"),
        (row(relation="run", state="planned")["fact"], "status_mismatch"),
        (row(relation="run", distance_m=["3000"])["fact"], "quantity_mismatch"),
        (row(relation="run", distance_m=["5000"])["fact"], "condition_matched"),
    ],
)
def test_actual_first_comparison_reason(fact, reason):
    plan = query_plan("내가 5km 이상 달린 기록", {"intent": "recall"}, "2026-10-17")
    expected = compatible(fact, plan)
    with d.start_trace(enabled=True) as trace:
        assert compatible(fact, plan) == expected
    event = next(e for e in trace.events if e["stage"] == "fact_comparison")
    assert event["passed"] == expected
    assert event["reason"] == reason
    assert "지연" not in str(trace.events)


def test_current_negation_and_multiple_quantities_are_not_repaired():
    with d.start_trace(enabled=True) as trace:
        negative = query_plan(QUESTIONS[3], {"intent": "recall"}, "2026-10-17")
        multiple = query_plan(QUESTIONS[4], {"intent": "recall"}, "2026-10-17")
    assert negative["relation"] == "run" and negative["planned"] is False
    assert multiple["distance_m"] is None and multiple["kind"] == "compare"
    assert any(
        e.get("condition") == "negation" and e.get("negation_present") and not e["present"]
        for e in trace.events
    )


def test_actual_short_circuit_does_not_claim_later_checks():
    plan = query_plan("내가 5km 이상 달린 기록", {"intent": "recall"}, "2026-10-17")
    with d.start_trace(enabled=True) as trace:
        assert not compatible(row(relation="visit")["fact"], plan, diagnostic_id="PRIVATE-ID")
    checks = [e for e in trace.events if e["stage"] == "query_condition"]
    assert [e["condition"] for e in checks] == ["relation"]
    assert checks[0]["applied"] and not checks[0]["passed"]
    assert checks[0]["candidates"][0]["memory_ref"] == trace.memory_ref("PRIVATE-ID")
    assert "PRIVATE" not in str(trace.events)


def test_partial_explicit_dates_have_per_bound_source(settings):
    with d.start_trace(enabled=True) as trace:
        Service(SnapshotStore([]), Models(), settings).search(
            QUESTIONS[1], {"date_to": "2026-10-05"}, today="2026-10-17"
        )
    bounds = {
        e["condition"]: e for e in trace.events if e.get("condition") in {"date_from", "date_to"}
    }
    assert bounds["date_from"]["source"] == "rule"
    assert bounds["date_to"]["source"] == "explicit_input"


def test_invalid_date_and_collector_failures_preserve_behavior(monkeypatch):
    assert explicit_dates("2026년 2월 30일", "2026-10-17") == {"date_from": None, "date_to": None}
    with d.start_trace(enabled=True) as trace:
        monkeypatch.setattr(trace, "record_event", lambda *a, **k: 1 / 0)
        plan = query_plan(QUESTIONS[0], {"intent": "recall"}, "2026-10-17")
        assert plan["needs_time_anchor"]
        assert compatible(row(relation="desire")["fact"], plan)
        with pytest.raises(ValueError):
            explicit_dates("오늘", "PRIVATE-invalid")
    assert trace.recording_failed


def test_labels_cannot_persist_arbitrary_values():
    with d.start_trace(enabled=True) as trace:
        trace.record_event(
            d.Stage.QUERY_PLAN,
            condition="PRIVATE",
            relation_type="PRIVATE",
            query_kind="PRIVATE",
            operator="PRIVATE",
            phase="PRIVATE",
        )
    assert "PRIVATE" not in str(trace.events)


def test_compare_bypasses_relation_without_claiming_a_match():
    plan = query_plan(QUESTIONS[4], {"intent": "recall"}, "2026-10-17")
    with d.start_trace(enabled=True) as trace:
        compatible(row(relation="visit")["fact"], plan)
    relation = next(e for e in trace.events if e.get("condition") == "relation")
    assert not relation["applied"] and relation["reason"] == "comparison_bypass"
    assert "passed" not in relation


def test_role_hints_are_observed_without_enforcing_names(settings):
    class HintModels(Models):
        def understand(self, question, today):
            return {
                "intent": "recall",
                "date_from": None,
                "date_to": None,
                "actor": {"value": "지연", "evidence": "지연이"},
            }

    with d.start_trace(enabled=True) as trace:
        result = Service(SnapshotStore([]), HintModels(), settings).search(
            QUESTIONS[2], today="2026-10-17"
        )
    assert result["query_plan"]["actor"] is None
    hint = next(
        e
        for e in trace.events
        if e.get("condition") == "role_hint" and e.get("phase") == "resolved"
    )
    assert hint["source"] == "unknown" and hint["reason"] == "hint_only" and not hint["applied"]
    assert "지연" not in str(trace.events)
