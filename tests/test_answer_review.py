import copy
from dataclasses import replace

import pytest
import requests

from pma.answer_review import accepted, answer_found, validate_review
from pma.models import LocalModels


def fixture():
    source = "민수는 부산에 살고 있고 서울로 이사할 계획이다."
    row = dict(
        id="m1",
        content=source,
        source_text=source,
        evidence=[dict(quote=source)],
        time={},
        fact=dict(
            actor="민수", relation="other", state="observed", distance_m=[], review_reasons=[]
        ),
    )
    found = dict(
        results=[row],
        query_plan=dict(
            kind="current", relation="other", role_hints={}, self=False, distance_m=None
        ),
    )
    response = dict(
        status="answered",
        items=[dict(text="기록에 따르면 부산에 살고 있습니다.", citations=["m1"])],
    )
    review = dict(
        fulfillment="direct",
        abstention="not_applicable",
        reason="원문 일치",
        items=[
            dict(
                index=0,
                support="supported",
                relevant=True,
                issue="none",
                answer_quote="부산에 살고 있습니다",
                evidence=[dict(id="m1", quote="부산에 살고 있고")],
            )
        ],
    )
    return found, response, review


@pytest.mark.parametrize("change", ["index", "quote", "source", "id", "missing", "state"])
def test_review_rejects_invalid_provenance(change):
    found, response, review = fixture()
    row = review["items"][0]
    if change == "index":
        row["index"] = 1
    if change == "quote":
        row["answer_quote"] = "서울에 살고 있다"
    if change == "source":
        row["evidence"][0]["quote"] = "서울에 살고 있다"
    if change == "id":
        row["evidence"][0]["id"] = "other"
    if change == "missing":
        review["items"] = []
    if change == "state":
        review["abstention"] = "appropriate"
    with pytest.raises(ValueError):
        validate_review(review, response, found["results"])


def test_supported_but_incomplete_answer_does_not_pass():
    found, response, review = fixture()
    review["fulfillment"] = "missing"
    assert not accepted(validate_review(review, response, found["results"]), response)


class Gateway:
    def __init__(self, failures=0, error=None):
        self.found, self.response, self.verdict = fixture()
        self.calls = []
        self.failures, self.error = failures, error

    def answer(self, question, evidence, *, feedback=None):
        self.calls.append(("answer", copy.deepcopy(evidence), feedback))
        return copy.deepcopy(self.response)

    def review(self, question, evidence, response):
        self.calls.append(("review", copy.deepcopy(evidence), None))
        if self.error:
            raise self.error
        result = copy.deepcopy(self.verdict)
        if self.failures:
            self.failures -= 1
            result["fulfillment"] = "missing"
        return result


@pytest.mark.parametrize(
    "failures,expected,calls",
    [(0, "answered", 2), (1, "answered", 4), (2, "insufficient_evidence", 4)],
)
def test_single_repair_bound_and_identical_evidence(failures, expected, calls):
    gateway = Gateway(failures)
    before = copy.deepcopy(gateway.found)
    result = answer_found(gateway, "지금 어디 살아?", gateway.found, lambda *a, **k: None)
    assert result["status"] == expected
    assert len(gateway.calls) == calls
    assert all(c[1] == before["results"] for c in gateway.calls)
    assert gateway.found == before


@pytest.mark.parametrize("error", [ValueError("bad review"), requests.Timeout("timeout")])
def test_review_error_abstains_without_repair(error):
    gateway = Gateway(error=error)
    traces = []
    result = answer_found(
        gateway, "현재 상태?", gateway.found, lambda stage, **data: traces.append(stage)
    )
    assert result["status"] == "insufficient_evidence"
    assert len(gateway.calls) == 2
    assert "verification_error" in traces


def test_repair_citation_and_attributes_are_checked_again():
    gateway = Gateway(1)
    original = gateway.answer

    def answer(q, e, *, feedback=None):
        result = original(q, e, feedback=feedback)
        if feedback:
            result["items"][0]["citations"] = ["invented"]
        return result

    gateway.answer = answer
    assert (
        answer_found(gateway, "어디?", gateway.found, lambda *a, **k: None)["status"]
        == "insufficient_evidence"
    )
    assert len(gateway.calls) == 3


def test_excessive_empty_answer_can_be_repaired():
    gateway = Gateway()
    original = gateway.answer

    def answer(q, e, *, feedback=None):
        if feedback:
            return original(q, e, feedback=feedback)
        gateway.calls.append(("answer", e, None))
        return dict(status="insufficient_evidence", items=[])

    original_review = gateway.review

    def review(q, e, r):
        if r["items"]:
            return original_review(q, e, r)
        gateway.calls.append(("review", e, None))
        return dict(
            items=[], fulfillment="missing", abstention="excessive", reason="현재 상태 명시"
        )

    gateway.answer, gateway.review = answer, review
    assert (
        answer_found(gateway, "어디?", gateway.found, lambda *a, **k: None)["status"] == "answered"
    )
    assert len(gateway.calls) == 4


def test_time_packaging_does_not_change_selection_or_source():
    found, _, _ = fixture()
    row = found["results"][0]
    row.update(recorded_at="2026-10-14", reference_time="2026-10-13", time={"raw": "어제"})
    before = copy.deepcopy(row)
    packed = LocalModels.answer_evidence([row])[0]
    assert packed["time_context"]["document_reference_timestamp"] == "2026-10-13"
    assert packed["time_context"]["storage_timestamp"] == "2026-10-14"
    assert packed["time_context"]["extracted_event_time"] == {"raw": "어제"}
    assert "reference_time" in LocalModels.compact_evidence([row])[0]
    assert row == before


def test_boolean_verify_compatibility(settings):
    models = LocalModels(replace(settings, answer_validation=True))
    found, response, review = fixture()
    models.review = lambda *args: review
    assert models.verify("어디?", found["results"], response["items"]) is True
    review["fulfillment"] = "missing"
    assert models.verify("어디?", found["results"], response["items"]) is False


@pytest.mark.parametrize("empty", [False, True])
def test_review_schema_binds_indexes_and_abstention_to_answer(settings, empty):
    models = LocalModels(settings)
    found, response, review = fixture()
    if empty:
        response = dict(status="insufficient_evidence", items=[])
        review = dict(items=[], fulfillment="missing", abstention="excessive", reason="근거 있음")
    captured = []

    def structured(prompt, data, schema, **kwargs):
        captured.append(schema)
        return review

    models.structured = structured
    models.review("어디?", found["results"], response)
    schema = captured[0]["properties"]
    assert schema["items"]["minItems"] == schema["items"]["maxItems"] == len(response["items"])
    if empty:
        assert schema["abstention"]["enum"] == ["appropriate", "excessive"]
    else:
        assert schema["abstention"]["enum"] == ["not_applicable"]
        assert schema["items"]["items"]["properties"]["index"]["enum"] == [0]


def test_irrelevant_true_item_does_not_pass():
    found, response, review = fixture()
    review["items"][0]["relevant"] = False
    assert not accepted(validate_review(review, response, found["results"]), response)


def test_appropriate_abstention_does_not_request_repair():
    gateway = Gateway()
    gateway.response = dict(status="insufficient_evidence", items=[])
    gateway.verdict = dict(
        items=[], fulfillment="missing", abstention="appropriate", reason="근거 없음"
    )
    result = answer_found(gateway, "왜?", gateway.found, lambda *a, **k: None)
    assert result["status"] == "insufficient_evidence"
    assert len(gateway.calls) == 2


def test_repair_rechecks_deterministic_attributes_even_if_reviewer_accepts():
    gateway = Gateway(1)
    original = gateway.answer

    def answer(q, e, *, feedback=None):
        result = original(q, e, feedback=feedback)
        if feedback:
            result["items"][0]["text"] = "부산에 살고 있습니다. 999km 달렸습니다."
        return result

    gateway.answer = answer
    result = answer_found(gateway, "어디?", gateway.found, lambda *a, **k: None)
    assert result["status"] == "insufficient_evidence"
    assert len(gateway.calls) == 4
