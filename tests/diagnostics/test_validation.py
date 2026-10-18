import pytest

from pma.answer_review import validate_review
from pma.diagnostics import start_trace
from pma.facts import query_plan
from pma.grounding import claims_supported

from .helpers import row


@pytest.mark.parametrize(
    "text,changes,question,kind",
    [
        ("5km", {"distance_m": ["3000"]}, "기록", "quantity"),
        ("파란 선물", {}, "기록", "color"),
        ("지연", {"review_reasons": ["actor_needs_context"]}, "누가", "role"),
        ("기록", {"relation": "visit"}, "달린 기록", "relation"),
    ],
)
def test_actual_attribute_rejection(text, changes, question, kind):
    evidence = [row(**changes)]
    items = [{"text": text, "citations": [evidence[0]["id"]]}]
    plan = query_plan(question, {"intent": "recall"}, "2026-10-17")
    expected = claims_supported(items, evidence, plan)
    with start_trace(enabled=True) as trace:
        assert claims_supported(items, evidence, plan) == expected is False
    failed = [
        e for e in trace.events if e["stage"] == "grounding_check" and e.get("passed") is False
    ]
    assert failed[0]["validation_type"] == kind
    assert failed[0]["evidence_refs"] == [trace.memory_ref(evidence[0]["id"])]


def test_missing_citations_do_not_activate_new_policy():
    # Existing claims_supported ignores unknown IDs when no checkable attribute exists.
    with start_trace(enabled=True) as trace:
        assert claims_supported([{"text": "PRIVATE", "citations": ["PRIVATE-ID"]}], [])
    assert "PRIVATE" not in str(trace.events)


def test_review_schema_error_is_observed():
    with start_trace(enabled=True) as trace:
        with pytest.raises(ValueError, match="INVALID_REVIEW_SCHEMA"):
            validate_review({}, {"items": []}, [])
    event = next(e for e in trace.events if e["stage"] == "review_check")
    assert event["status"] == "error" and event["reason_code"] == "invalid_response"


@pytest.mark.parametrize("failures", [0, 1, 2])
def test_review_repair_observation_preserves_calls(failures):
    from pma.answer_review import answer_found
    from tests.test_answer_review import Gateway

    expected_gateway = Gateway(failures)
    expected = answer_found(
        expected_gateway, "PRIVATE", expected_gateway.found, lambda *a, **k: None
    )
    gateway = Gateway(failures)
    with start_trace(enabled=True) as trace:
        assert answer_found(gateway, "PRIVATE", gateway.found, lambda *a, **k: None) == expected
    assert gateway.calls == expected_gateway.calls
    policy = next(e for e in trace.events if e["stage"] == "answer_policy")
    assert policy["retry_count"] == min(failures, 1)
    if failures:
        assert any(e.get("reason_code") == "incomplete_answer" for e in trace.events)
    assert "PRIVATE" not in str(trace.events)


def test_review_error_and_observation_failure_preserve_abstention(monkeypatch):
    import requests

    from pma.answer_review import answer_found
    from tests.test_answer_review import Gateway

    gateway = Gateway(error=requests.Timeout("PRIVATE"))
    with start_trace(enabled=True) as trace:
        monkeypatch.setattr(trace, "record_event", lambda *a, **k: 1 / 0)
        result = answer_found(gateway, "PRIVATE", gateway.found, lambda *a, **k: None)
    assert result["validation"] == "rejected" and len(gateway.calls) == 2
    assert trace.recording_failed
