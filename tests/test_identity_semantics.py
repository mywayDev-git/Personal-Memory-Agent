import pytest

from pma.chat.evidence import semantic_issue
from pma.chat.identity import scoped_followup


def session(question="회사 동료 민수는 누구야?", quote="회사 동료 민수는 개발자다."):
    return {"messages": [{"state": "completed", "question": question, "response": {
        "status": "answered", "citation_details": [{"quote": quote}]}}]}


def test_followup_uses_source_backed_immediate_user_role():
    assert scoped_followup("그 사람 직업은 뭐야?", session()) == "회사 동료 민수 직업은 뭐야?"
    assert scoped_followup("그 사람의 직업은?", session()) == "회사 동료 민수의 직업은?"
    active = session()
    active["messages"].append({"state": "running", "question": "그 사람 직업은?"})
    assert scoped_followup("그 사람 직업은?", active) == "회사 동료 민수 직업은?"


@pytest.mark.parametrize("previous", [session(quote="민수는 개발자다."),
    session(question="회사 동료 민수와 동아리 친구 민수는 누구야?"),
    session(question="오늘 날씨는 어때?"), {"messages": []}])
def test_ambiguous_or_unverified_reference_is_not_invented(previous):
    assert scoped_followup("그 사람 직업은?", previous) == "그 사람 직업은?"


def test_current_explicit_role_wins():
    assert scoped_followup("동아리 친구 민수는 그 사람과 친해?", session()) == "동아리 친구 민수는 그 사람과 친해?"


@pytest.mark.parametrize("text,expected", [
    ("공부를 중단한 기록은 없습니다. 다만 공부를 접었다고 기록했습니다.", "negation"),
    ("중단한 사실은 확인되지 않습니다.", "negation"),
    ("공부를 접었습니다. 중단한 날짜는 확인되지 않습니다.", None),
    ("공부를 중단한 기록이 있습니다. 날짜는 모릅니다.", None),
])
def test_stop_fact_and_unknown_date_are_distinct(text, expected):
    evidence = [{"id": "a", "source_text": "파이썬 공부를 접었다."}]
    assert semantic_issue("파이썬 공부를 중단한 기록이 있어?",
                          {"text": text, "citations": ["a"]}, evidence) == expected


def test_other_person_cannot_supply_profession_even_if_model_approves():
    evidence = [{"id": "a", "source_text": "회사 동료 민수는 개발자다."},
                {"id": "b", "source_text": "동아리 친구 민수는 교사다."}]
    assert semantic_issue("회사 동료 민수 직업은?",
        {"text": "교사입니다.", "citations": ["b"]}, evidence) == "person"
    assert semantic_issue("회사 동료 민수 직업은?",
        {"text": "개발자입니다.", "citations": ["a"]}, evidence) is None
    assert semantic_issue("회사 동료 민수 직업은?",
        {"text": "동아리 친구 민수는 개발자입니다.", "citations": ["a"]}, evidence) == "person"


def test_profession_draft_uses_only_explicit_role_and_exact_source():
    from pma.chat.evidence import direct_statement

    rows = [{"id": "a", "source_text": "회사 동료 민수는 프론트엔드 개발자다."},
            {"id": "b", "source_text": "동아리 친구 민수는 수학 교사다."}]
    draft = direct_statement("회사 동료 민수 직업은 뭐야?", rows)
    assert draft["items"] == [{"text": "기록에 이렇게 남아 있습니다: “회사 동료 민수는 프론트엔드 개발자다.”",
                               "citations": ["a"]}]
    assert direct_statement("민수 직업은 뭐야?", rows) is None


@pytest.mark.parametrize("question,source,text,issue", [
    ("파이썬 공부를 중단한 기록이 있어?", "파이썬 공부를 접었다.",
     "중단한 기록은 없습니다. 다만 공부를 접었다고 기록했습니다.", "negation"),
    ("회사 동료 민수 직업은?", "동아리 친구 민수는 수학 교사다.", "수학 교사입니다.", "person"),
])
def test_independent_model_approval_cannot_override_semantic_guard(question, source, text, issue):
    from pma.answer_review import accepted
    from pma.chat.models import ChatLocalModels

    model = ChatLocalModels.__new__(ChatLocalModels)
    model.structured = lambda *a, **kw: {
        "fulfillment": "direct", "abstention": "not_applicable", "reason": "원문 확인",
        "items": [{"index": 0, "support": "supported", "relevant": True, "issue": "none",
                   "evidence": [{"id": "a", "span_id": "s0:0"}]}]}
    response = {"status": "answered", "items": [{"text": text, "citations": ["a"]}]}
    review = model.review(question, [{"id": "a", "source_text": source}], response)
    assert not accepted(review, response)
    assert review["items"][0]["issue"] == issue


@pytest.mark.parametrize("repair_accepted", [True, False])
def test_stop_quote_repair_requires_a_second_independent_review(repair_accepted):
    from types import SimpleNamespace

    from pma.chat.engine import ChatEngine

    source = "파이썬 공부를 접었다."
    evidence = [{"id": "a", "record_id": "r", "revision_id": "v", "source_text": source,
                 "evidence": [{"quote": source, "start": 0, "end": len(source)}]}]
    reviews = []

    def review(question, rows, response):
        reviews.append(response)
        passed = len(reviews) == 2 and repair_accepted
        return {"fulfillment": "direct", "abstention": "not_applicable", "reason": "검토",
                "items": [{"index": 0, "support": "supported" if passed else "unsupported",
                           "issue": "none" if passed else "negation", "relevant": True,
                           "answer_quote": response["items"][0]["text"],
                           "evidence": [{"id": "a", "quote": source}]}]}

    engine = ChatEngine.__new__(ChatEngine)
    engine.service = SimpleNamespace(trace=lambda *a, **kw: None)
    engine.models = SimpleNamespace(
        answer=lambda *a, **kw: {"status": "answered", "items": [
            {"text": "중단한 기록은 없습니다.", "citations": ["a"]}]}, review=review)
    engine.resolve = lambda q, *a, **kw: ({"question": q, "needs_clarification": False}, 0)
    result = engine.generate("파이썬 공부를 중단한 기록이 있어?", {"evidence": evidence}, "2026-10-19")
    assert len(reviews) == 2
    assert reviews[1]["items"][0]["text"] == "기록 원문: “파이썬 공부를 접었다.”"
    assert result["status"] == ("answered" if repair_accepted else "insufficient_evidence")
