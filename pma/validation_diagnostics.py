"""Observe existing validation branches; never decide whether an answer is valid."""

from contextvars import ContextVar
from functools import wraps
from time import perf_counter

from .diagnostics import Reason, Stage, current_trace

_RETRY = ContextVar("pma_validation_retry", default=0)


def retry(number):
    if current_trace() is not None:
        _RETRY.set(number)


def check(kind, passed, evidence=None, reason=None, *, stage=Stage.GROUNDING_CHECK, **fields):
    trace = current_trace()
    if trace is None:
        return
    try:
        trace.record_event(
            stage,
            validation_type=kind,
            executed=True,
            passed=passed,
            status="error" if passed is None else "passed" if passed else "failed",
            reason_code=reason
            or (Reason.CONDITION_MATCHED if passed else Reason.UNSUPPORTED_ATTRIBUTES),
            evidence_refs=None
            if evidence is None
            else [trace.memory_ref(r["id"]) for r in evidence],
            retry_count=_RETRY.get(),
            **fields,
        )
    except Exception:
        trace.recording_failed = True


def compatible_evidence(row, plan):
    from .facts import compatible

    def excluded(reason):
        kind = {
            Reason.RELATION_MISMATCH: "relation",
            Reason.PERSON_MISMATCH: "role",
            Reason.QUANTITY_MISMATCH: "quantity",
        }.get(reason, "rule")
        check(kind, False, [row], reason)

    return compatible(row["fact"], plan, on_exclude=excluded)


def observed_validation(stage):
    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            trace = current_trace()
            if trace is None:
                return function(*args, **kwargs)
            started = perf_counter()
            token = _RETRY.set(0) if stage == Stage.ANSWER_POLICY else None
            try:
                result = function(*args, **kwargs)
            except Exception as exc:
                code = exc.args[0] if exc.args and type(exc.args[0]) is str else None
                reason = (
                    Reason.INVALID_CITATION
                    if code
                    in {"INVALID_REVIEW_CITATION", "MISSING_REVIEW_EVIDENCE", "INVALID_CITATION"}
                    else Reason.INVALID_RESPONSE
                )
                check(
                    "rule",
                    None,
                    reason=reason,
                    stage=stage,
                    duration_ms=(perf_counter() - started) * 1000,
                )
                raise
            else:
                if stage == Stage.GROUNDING_CHECK:
                    check(
                        "attributes",
                        result,
                        stage=stage,
                        duration_ms=(perf_counter() - started) * 1000,
                    )
                elif stage == Stage.REVIEW_CHECK:
                    for item in result.get("items", []):
                        passed = (
                            item["support"] == "supported"
                            and item["relevant"]
                            and item["issue"] == "none"
                        )
                        reason = {
                            "person": Reason.PERSON_MISMATCH,
                            "time": Reason.TIME_MISMATCH,
                        }.get(item["issue"], Reason.VERIFICATION_REJECTED)
                        check(
                            "llm",
                            passed,
                            item.get("evidence") or None,
                            Reason.CONDITION_MATCHED if passed else reason,
                            stage=stage,
                        )
                    check(
                        "schema", True, stage=stage, duration_ms=(perf_counter() - started) * 1000
                    )
                else:
                    check(
                        "rule",
                        result.get("status") == "answered",
                        stage=stage,
                        policy_path="review",
                        regenerated=_RETRY.get() > 0,
                        reason=Reason.VERIFICATION_REJECTED
                        if result.get("validation") == "rejected"
                        else Reason.CONDITION_MATCHED,
                        duration_ms=(perf_counter() - started) * 1000,
                    )
                return result
            finally:
                if token is not None:
                    _RETRY.reset(token)

        return wrapped

    return decorate
