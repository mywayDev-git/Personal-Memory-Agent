from copy import deepcopy

import pytest

from pma.chat.source_fact import source_fact_draft


def row():
    return {"id": "original-id", "source_text": "2026년 10월 12일 민수에게 파란색 책을 선물했다.",
            "assertion_polarity": "affirmed", "memory_type": "event",
            "fact": {"state": "observed", "action_relation": "give", "object": "파란색 책"}}


def test_draft_quotes_complete_immutable_source_and_does_not_claim_validation():
    evidence = [row()]
    original = deepcopy(evidence)
    result = source_fact_draft("2026년 10월 12일 민수에게 무엇을 선물했어?", evidence)
    assert result["items"][0]["citations"] == ["original-id"]
    assert evidence[0]["source_text"] in result["items"][0]["text"]
    assert "validation" not in result and "display" not in result
    assert evidence == original


@pytest.mark.parametrize("question", ["누가 무엇을 선물했어?", "왜 선물했어?", "무엇을 선물할 계획이야?",
    "무엇을 받았어?", "무엇을 선물했고 이유는 뭐야?", "무엇을 선물하지 않았어?", "처음 선물한 것은 뭐야?",
    "무엇을 선물했는지 모두 찾아줘", "실제로 무엇을 선물했어?", "무엇을 선물했고 직업은 뭐야?"])
def test_does_not_replace_ambiguous_compound_or_execution_generation(question):
    assert source_fact_draft(question, [row()]) is None


@pytest.mark.parametrize("change", ["negated", "planned", "warning", "invented_object", "multiple_sentences", "long"])
def test_uncertain_changed_or_long_sources_keep_the_existing_generator(change):
    source = row()
    if change == "negated": source["assertion_polarity"] = "negated"
    if change == "planned": source["fact"]["state"] = "planned"
    if change == "warning": source["fact"]["warnings"] = ["review_required"]
    if change == "invented_object": source["fact"]["object"] = "노트북"
    if change == "multiple_sentences": source["source_text"] += " 이후 취소했다."
    if change == "long": source["source_text"] *= 10
    assert source_fact_draft("무엇을 선물했어?", [source]) is None
    assert source_fact_draft("무엇을 선물했어?", [row(), row()]) is None


@pytest.mark.parametrize("approved", [True, False])
def test_source_draft_still_requires_independent_review_and_keeps_rejected_fallback(approved):
    from types import SimpleNamespace
    from pma.chat.engine import ChatEngine
    from pma.settings import AppSettings
    source = row()
    source.update(record_id="r", revision_id="v", version=1,
                  evidence=[{"quote": source["source_text"], "start": 0, "end": len(source["source_text"])}])
    reviews, generations = [], []
    def answer(*a, **kw):
        generations.append(kw)
        return {"status": "answered", "items": [{"text": source["source_text"], "citations": [source["id"]]}]}
    def review(question, evidence, response):
        reviews.append(response)
        return {"fulfillment": "direct", "abstention": "not_applicable", "reason": "검토",
                "items": [{"index": 0, "support": "supported" if approved else "unsupported",
                    "issue": "none" if approved else "other", "relevant": True,
                    "answer_quote": response["items"][0]["text"],
                    "evidence": [{"id": source["id"], "quote": source["source_text"]}]}]}
    engine = ChatEngine.__new__(ChatEngine)
    engine.service = SimpleNamespace(settings=AppSettings(source_fact_drafts=True), trace=lambda *a, **kw: None)
    engine.models = SimpleNamespace(answer=answer, review=review)
    engine.resolve = lambda question, *a, **kw: ({"question": question, "needs_clarification": False}, 0)
    result = engine.generate("민수에게 무엇을 선물했어?", {"evidence": [source]}, "2026-10-19")
    assert len(reviews) == (1 if approved else 2)
    assert len(generations) == (0 if approved else 1)
    assert result["status"] == ("answered" if approved else "insufficient_evidence")
    if approved:
        assert result["validation"] == "model_checked"
