from copy import deepcopy

import pytest

from pma.chat.presentation import presentation, reviewed_display


def answer(kind="plain", states=("confirmed",), events=None, dates=None):
    return {"status": "answered", "items": [{"text": "검증된 내용", "citations": [f"m{i}"]} for i in range(len(states))],
            "display": {"kind": kind, "items": [
                {"index": i, "state": state, "event": (events or [""] * len(states))[i],
                 "event_date": (dates or [""] * len(states))[i]} for i, state in enumerate(states)]}}


def rendered(response):
    display = reviewed_display(response, {"presentation_valid": True})
    assert display is not None
    return presentation({**response, "display": display})


@pytest.mark.parametrize("kind,states,events,expected", [
    ("partial", ("confirmed", "unknown"), None, "claim_coverage"),
    ("conflict", ("confirmed", "confirmed"), None, "evidence_comparison"),
    ("same_event", ("confirmed", "confirmed"), ["trip", "trip"], "evidence_group"),
    ("events", ("confirmed", "confirmed"), ["lunch", "dinner"], "event_timeline"),
])
def test_reviewed_kinds(kind, states, events, expected):
    assert rendered(answer(kind, states, events))[0]["type"] == expected


def test_clarification_and_legacy_general_empty():
    assert presentation({"status": "needs_clarification", "items": [{"text": "점심"}]})[0]["type"] == "clarification_choices"
    for text in ("기록이 충돌합니다", "확인할 수 없습니다", "안녕하세요"):
        assert presentation({"items": [{"text": text}]}) == [{"type": "text", "item_indices": [0]}]
    assert presentation({"items": [], "validation": "rejected"}) == [{"type": "text", "item_indices": []}]


def test_metadata_rejection_does_not_remove_answer():
    response = answer("conflict", ("confirmed", "confirmed"))
    original = deepcopy(response)
    for review in ({}, {"presentation_valid": False}):
        assert reviewed_display(response, review) is None
        assert presentation(response)[0]["type"] == "text"
    assert response == original


@pytest.mark.parametrize("mutation", [
    lambda d: d["items"].append(dict(d["items"][0])),
    lambda d: d["items"][0].update(index=9),
    lambda d: d["items"][0].update(event_date="2025-02-30"),
    lambda d: d.update(kind="made_up"),
])
def test_invalid_metadata_falls_back(mutation):
    response = answer()
    mutation(response["display"])
    assert reviewed_display(response, {"presentation_valid": True}) is None


def test_same_person_is_not_same_event_and_negative_is_confirmed():
    assert reviewed_display(answer("same_event", ("confirmed", "confirmed"), ["lunch", "dinner"]), {"presentation_valid": True}) is None
    assert reviewed_display(answer("partial"), {"presentation_valid": True}) is None
    assert rendered(answer())[0]["type"] == "text"


def test_only_event_dates_sort_and_hybrid_item_survives():
    response = answer("events", ("confirmed", "confirmed", "confirmed"), ["unknown", "late", "early"], ["", "2025-09-12", "2025-05-15"])
    response["recorded_at"] = "2026-01-01"
    display = reviewed_display(response, {"presentation_valid": True})
    response["display"] = display
    response["items"].append({"text": "일반 제안", "citations": []})
    blocks = presentation(response)
    assert [b["item_indices"] for b in blocks] == [[2], [1], [0], [3]]
    assert blocks[2]["event_date"] == ""


def test_change_proposal_and_storage_date_require_semantic_review():
    response = answer("events", ("confirmed", "confirmed"), ["plan", "execution"], ["2026-10-14", "2026-11-20"])
    response["items"][1]["text"] = "11월 20일로 확정되었습니다."
    # Reviewer rejects interpreting a change under consideration as an execution,
    # or using the memo creation date as the event date.
    assert reviewed_display(response, {"presentation_valid": False}) is None


@pytest.mark.parametrize("approved", [True, False])
def test_engine_preserves_answer_but_only_attaches_reviewed_metadata(monkeypatch, approved):
    from types import SimpleNamespace

    import pma.chat.engine as module
    text = "민수와 점심을 먹었다."
    response = answer()
    response["items"] = [{"text": text, "citations": ["m0"]}]
    source = {"id": "m0", "record_id": "r0", "revision_id": "v0", "source_text": text}
    review = {"presentation_valid": approved, "fulfillment": "direct", "abstention": "not_applicable", "reason": "원문 일치",
              "items": [{"index": 0, "support": "supported", "relevant": True, "issue": "none", "answer_quote": text,
                         "evidence": [{"id": "m0", "quote": text}]}]}
    engine = module.ChatEngine.__new__(module.ChatEngine)
    engine.models = SimpleNamespace(answer=lambda *a, **kw: deepcopy(response), review=lambda *a: review)
    engine.service = SimpleNamespace(trace=lambda *a, **kw: None)
    engine.resolve = lambda *a, **kw: ({"needs_clarification": False, "question": "뭐 했어?"}, 0)
    monkeypatch.setattr(module, "direct_statement", lambda *a: None)
    monkeypatch.setattr(module, "claims_supported", lambda *a: True)
    monkeypatch.setattr(module, "causal_claims_supported", lambda *a: True)
    result = engine.generate("뭐 했어?", {"evidence": [source]}, "2026-10-18")
    assert result["items"][0]["text"] == text
    assert bool(result.get("display", {}).get("verified")) is approved
    assert result["citation_details"][0]["quote"] == text


def test_chat_model_requests_and_reviews_metadata_in_existing_calls(monkeypatch):
    from types import SimpleNamespace

    from pma.answer_review import REVIEW_SCHEMA
    from pma.chat.models import ChatLocalModels
    from pma.models import ANSWER_SCHEMA, LocalModels
    calls = []
    def fake(self, prompt, data, schema, max_tokens):
        calls.append((prompt, schema))
        return {}
    monkeypatch.setattr(LocalModels, "structured", fake)
    model = ChatLocalModels.__new__(ChatLocalModels)
    model.settings = SimpleNamespace(llm=SimpleNamespace(max_tokens=4096))
    model.structured("", {"question": "언제?", "feedback": None}, ANSWER_SCHEMA)
    assert "display" in calls[-1][1]["required"]
    model.structured("", {"proposed_answer": answer()}, REVIEW_SCHEMA)
    assert "presentation_valid" in calls[-1][1]["required"]
    assert "작성일" in calls[0][0] and "확정" in calls[-1][0]
    assert "display" not in ANSWER_SCHEMA["properties"]
