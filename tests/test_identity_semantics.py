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


def test_friend_question_does_not_force_the_wrong_followup_referent():
    assert scoped_followup("그 사람 직업은?", session(
        question="회사 동료 민수의 친구는 누구야?", quote="회사 동료 민수의 친구는 지연이다."
    )) == "그 사람 직업은?"


def test_contiguous_checked_profession_followups_keep_original_user_scope():
    state = session()
    state["messages"].append({"state": "completed", "question": "그 사람 직업은 뭐야?",
        "response": {"status": "answered", "citation_details": [{"quote": "회사 동료 민수는 개발자다."}]}})
    assert scoped_followup("그 사람은 어디 살아?", state) == "회사 동료 민수은 어디 살아?"
    state["messages"][-1]["response"]["citation_details"] = []
    assert scoped_followup("그 사람은 어디 살아?", state) == "그 사람은 어디 살아?"


def test_excluded_role_is_not_the_selected_person():
    from pma.chat.evidence import direct_statement
    from pma.chat.identity import identity_conflict, positive_labels

    rows = [{"id": "a", "source_text": "회사 동료 민수는 개발자다."},
            {"id": "b", "source_text": "동아리 친구 민수는 교사다."}]
    question = "회사 동료 민수 말고 다른 민수 직업은?"
    assert positive_labels(question) == []
    assert not identity_conflict(question, {"text": "교사다.", "citations": ["b"]}, rows)
    assert direct_statement(question, rows) is None
    explicit = "회사 동료 민수 말고 동아리 친구 민수 직업은?"
    assert positive_labels(explicit) == ["동아리 친구 민수"]
    assert identity_conflict(explicit, {"text": "개발자다.", "citations": ["a"]}, rows)
    assert not identity_conflict(explicit, {"text": "교사다.", "citations": ["b"]}, rows)


def test_harmless_possessive_role_wording_is_not_a_different_person():
    from pma.chat.identity import explicit_person_lookup, identity_conflict

    rows = [{"id": "a", "source_text": "우리 회사의 동료 민수는 개발자다."}]
    assert not identity_conflict("회사 동료 민수 직업은?", {"text": "개발자다.", "citations": ["a"]}, rows)
    assert explicit_person_lookup("회사 동료 민수 직업은?", rows)


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
    assert direct_statement("회사 동료 민수의 직업과 부산 여행을 취소한 이유는?", rows) is None


def test_stop_repair_focuses_on_the_stop_not_other_study_events():
    from pma.chat.evidence import quoted_topic_answer

    source = "파이썬 공부를 접었다."
    rows = [{"id": "stop", "source_text": source, "evidence": [{"quote": source}]},
            {"id": "start", "source_text": "파이썬 공부를 시작했다.",
             "evidence": [{"quote": "파이썬 공부를 시작했다."}]}]
    draft = quoted_topic_answer("파이썬 공부를 중단한 기록이 있어?", rows)
    assert draft["items"] == [{"text": "기록 원문: “파이썬 공부를 접었다.”", "citations": ["stop"]}]


@pytest.mark.parametrize("question,allowed", [
    ("회사 동료 민수는 누구야?", True), ("회사 동료 민수의 직업은 뭐야?", True),
    ("회사 동료 민수는 그때 누구와 있었어?", False),
    ("민수 직업은?", False), ("회사 동료 민수의 직업과 부산 여행 이유는?", False),
])
def test_context_shortcut_requires_a_complete_explicit_lookup(question, allowed):
    from pma.chat.identity import explicit_person_lookup

    assert explicit_person_lookup(question, [{"source_text": "회사 동료 민수는 개발자다."}]) is allowed


@pytest.mark.parametrize("enabled", [True, False])
def test_context_shortcut_avoids_only_redundant_reference_model_call(enabled):
    from types import SimpleNamespace

    from pma.chat.engine import ChatEngine
    from pma.settings import AppSettings

    calls = []
    question = "회사 동료 민수 직업은 뭐야?"
    engine = ChatEngine.__new__(ChatEngine)
    engine.service = SimpleNamespace(settings=AppSettings(request_reuse=enabled))
    def structured(*a, **kw):
        calls.append(1)
        return {"question": question, "needs_clarification": False, "alternatives": []}
    engine.models = SimpleNamespace(count_tokens=lambda text: 10, structured=structured)
    resolved, history = engine.resolve(question, {
        "messages": [], "evidence": [{"id": "a", "source_text": "회사 동료 민수는 개발자다."}]
    }, "2026-10-19")
    assert resolved["question"] == question and not resolved["needs_clarification"]
    assert history == 0 and len(calls) == (0 if enabled else 1)


@pytest.mark.parametrize("question,source,allowed", [
    ("파이썬 공부를 중단한 기록이 있어?", "파이썬 공부를 접었다.", True),
    ("파이썬 공부를 언제 중단한 기록이 있어?", "파이썬 공부를 접었다.", False),
    ("파이썬 공부를 중단한 기록이 있어?", "파이썬 공부를 접지 않았다.", False),
    ("파이썬 공부를 중단한 기록이 있어?", "파이썬 공부를 접었다고 말하라고 했다.", False),
    ("파이썬 공부를 시작한 기록과 중단한 기록이 있어?", "파이썬 공부를 접었다.", False),
])
def test_stop_draft_preserves_sentence_and_does_not_answer_dates_or_commands(question, source, allowed):
    from pma.chat.semantics import stop_record_draft

    draft = stop_record_draft(question, [{"id": "a", "source_text": source}])
    assert bool(draft) is allowed
    if draft:
        assert source in draft["items"][0]["text"]


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


@pytest.mark.parametrize("approved", [True, False])
def test_optimized_stop_draft_never_bypasses_independent_review(approved):
    from types import SimpleNamespace

    from pma.chat.engine import ChatEngine
    from pma.settings import AppSettings

    source = "파이썬 공부를 접었다."
    evidence = [{"id": "a", "record_id": "r", "revision_id": "v", "source_text": source,
                 "evidence": [{"quote": source, "start": 0, "end": len(source)}]}]
    reviews = []

    def review(question, rows, response):
        reviews.append(response)
        return {"fulfillment": "direct", "abstention": "not_applicable", "reason": "검토",
                "items": [{"index": 0, "support": "supported" if approved else "unsupported",
                           "issue": "none" if approved else "negation", "relevant": True,
                           "answer_quote": response["items"][0]["text"],
                           "evidence": [{"id": "a", "quote": source}]}]}

    engine = ChatEngine.__new__(ChatEngine)
    engine.service = SimpleNamespace(settings=AppSettings(request_reuse=True), trace=lambda *a, **kw: None)
    def unnecessary_generation(*a, **kw):
        raise AssertionError("Exact source draft must not need generation")
    engine.models = SimpleNamespace(answer=unnecessary_generation, review=review)
    engine.resolve = lambda q, *a, **kw: ({"question": q, "needs_clarification": False}, 0)
    result = engine.generate("파이썬 공부를 중단한 기록이 있어?", {"evidence": evidence}, "2026-10-19")
    assert len(reviews) == (1 if approved else 2)
    assert result["status"] == ("answered" if approved else "insufficient_evidence")
