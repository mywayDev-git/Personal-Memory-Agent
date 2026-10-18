"""Private metadata for existing query rules. Never evaluates a filter twice."""

import re
from contextvars import ContextVar
from functools import wraps
from time import perf_counter

from .diagnostics import Reason, Stage, current_trace

_REASON = ContextVar("pma_fact_comparison_reason", default=None)


def comparison_reason(reason):
    state = _REASON.get()
    if state is not None:
        state["reason"] = reason
        comparison_check(
            {
                Reason.RELATION_MISMATCH: "relation",
                Reason.PERSON_MISMATCH: "person",
                Reason.STATUS_MISMATCH: "state",
                Reason.QUANTITY_MISMATCH: "quantity",
            }[reason],
            False,
            reason=reason,
        )


def comparison_check(name, passed, *, applied=True, reason=None):
    state = _REASON.get()
    if state is None:
        return
    trace = state["trace"]
    try:
        mid = state["id"]
        condition(
            trace,
            Stage.QUERY_CONDITION,
            name,
            applied,
            applied=applied,
            passed=passed if applied else None,
            phase="compared",
            reason=reason or (Reason.CONDITION_MATCHED if applied else Reason.COMPARISON_BYPASS),
            candidates=[] if mid is None else [{"memory_ref": trace.memory_ref(mid)}],
        )
    except Exception:
        trace.recording_failed = True


def condition(trace, stage, name, present, *, source="rule", reason=None, **fields):
    trace.record_event(
        stage,
        condition=name,
        present=bool(present),
        source=source,
        reason=reason or (Reason.CONDITION_PRESENT if present else Reason.CONDITION_ABSENT),
        **fields,
    )


def generated(trace, plan, question):
    common = {"phase": "generated", "applied": False}
    for name, present in (
        ("relation", plan["relation"] != "other"),
        ("time", any(plan["filters"].values())),
        ("person", plan["self"]),
        ("quantity", plan["distance_m"] is not None),
        ("state", plan["planned"] or plan["event_listing"] or plan["execution_check"]),
    ):
        condition(
            trace,
            Stage.QUERY_PLAN,
            name,
            present,
            relation_type=plan["relation"],
            query_kind=plan["kind"],
            operator=plan["operator"] if name == "quantity" else None,
            **common,
        )
    condition(
        trace,
        Stage.QUERY_PLAN,
        "time_anchor",
        plan["needs_time_anchor"],
        needs_time_anchor=bool(plan["needs_time_anchor"]),
        reason=Reason.UNRESOLVED_TIME_ANCHOR
        if plan["needs_time_anchor"]
        else Reason.CONDITION_ABSENT,
        **common,
    )
    for name, key in (("role_hint", "role_hints"), ("requested_slots", "requested_slots")):
        condition(
            trace,
            Stage.QUERY_PLAN,
            name,
            bool(plan[key]),
            source="unknown",
            reason=Reason.HINT_ONLY if plan[key] else Reason.CONDITION_ABSENT,
            **common,
        )
    # Lexical presence is diagnostic only: the plan has no dedicated negation filter.
    condition(
        trace,
        Stage.QUERY_PLAN,
        "negation",
        False,
        negation_present=bool(re.search(r"않|못|안\s", question)),
        **common,
    )


def resolved(trace, plan, applied, explicit):
    for key in ("date_from", "date_to"):
        condition(
            trace,
            Stage.QUERY_CONDITION,
            key,
            bool(applied.get(key)),
            source="explicit_input" if explicit is not None and key in explicit else "rule",
            phase="resolved",
            applied=False,
        )
    condition(
        trace,
        Stage.QUERY_CONDITION,
        "time_anchor",
        plan["needs_time_anchor"],
        needs_time_anchor=bool(plan["needs_time_anchor"]),
        phase="resolved",
        applied=False,
        source="explicit_input" if explicit is not None and explicit.get("date_to") else "rule",
        reason=Reason.UNRESOLVED_TIME_ANCHOR
        if plan["needs_time_anchor"]
        else Reason.CONDITION_ABSENT,
    )


def observed_facts(stage):
    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            trace = current_trace()
            if trace is None:
                return function(*args, **kwargs)
            state = {"trace": trace, "id": kwargs.get("diagnostic_id")}
            token = _REASON.set(state) if stage == Stage.FACT_COMPARISON else None
            started = perf_counter()
            result = None
            failed = False
            try:
                result = function(*args, **kwargs)
                return result
            except Exception:
                failed = True
                raise
            finally:
                try:
                    if failed:
                        trace.record_event(
                            stage,
                            status="error",
                            reason=Reason.INVALID_RESPONSE,
                            duration_ms=(perf_counter() - started) * 1000,
                        )
                    elif stage == Stage.QUERY_PLAN:
                        generated(trace, result, args[0] if args else kwargs["question"])
                    elif stage == Stage.DATE_PARSING:
                        condition(
                            trace,
                            stage,
                            "time",
                            any(result.values()),
                            date_certain=bool(result.get("date_from") and result.get("date_to")),
                            phase="generated",
                            applied=False,
                            duration_ms=(perf_counter() - started) * 1000,
                        )
                    else:
                        reason = state.get("reason", Reason.CONDITION_MATCHED)
                        mid = kwargs.get("diagnostic_id")
                        trace.record_event(
                            stage,
                            passed=result,
                            phase="compared",
                            applied=True,
                            source="rule",
                            reason=reason,
                            candidates=[]
                            if mid is None
                            else [
                                {
                                    "memory_ref": trace.memory_ref(mid),
                                    "status": "included" if result else "excluded",
                                    "reason": reason,
                                }
                            ],
                            duration_ms=(perf_counter() - started) * 1000,
                        )
                except Exception:
                    trace.recording_failed = True
                finally:
                    if token is not None:
                        _REASON.reset(token)

        return wrapped

    return decorate
