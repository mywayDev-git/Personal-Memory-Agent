import pytest

from pma.answer_review import accepted
from pma.chat.models import ChatLocalModels


def plan_row():
    return {"id": "p", "source_text": "도서관 책은 2026년 10월 25일까지 반납할 계획이다.",
            "fact": {"object_key": "도서관책"}}


def test_plan_draft_preserves_future_plan_and_limits_execution_claim():
    from pma.chat.execution import execution_draft

    draft = execution_draft("도서관 책은 실제로 반납했어?", [plan_row()])
    assert plan_row()["source_text"] in draft["items"][0]["text"]
    assert "실제 반납 여부를 확인할 수 없습니다" in draft["items"][0]["text"]
    assert draft["items"][0]["citations"] == ["p"]


def test_execution_draft_defers_when_execution_or_multiple_plans_exist():
    from pma.chat.execution import execution_draft

    other = {"id": "done", "source_text": "도서관 책을 반납했다.", "fact": {"object_key": "도서관책"}}
    assert execution_draft("도서관 책은 실제로 반납했어?", [plan_row(), other]) is None
    assert execution_draft("도서관 책은 실제로 반납했어?", [plan_row(), {**plan_row(), "id": "p2"}]) is None
    assert execution_draft("도서관 책을 실제로 반납할 계획이 맞아?", [plan_row()]) is None


def test_plan_draft_bounds_the_statement_without_changing_original_words():
    from pma.chat.execution import execution_draft

    row = plan_row()
    row["source_text"] = "\n " * 1500 + row["source_text"] + "\n "
    draft = execution_draft("도서관 책은 실제로 반납했어?", [row])
    assert plan_row()["source_text"] in draft["items"][0]["text"]
    assert len(draft["items"][0]["text"]) < 300


@pytest.mark.parametrize("limited", [True, False])
def test_model_approval_cannot_make_plan_only_answer_fulfill_execution_question(limited):
    from pma.chat.execution import execution_draft

    question = "도서관 책은 실제로 반납했어?"
    response = execution_draft(question, [plan_row()]) if limited else {
        "status": "answered", "items": [{"text": "도서관 책은 반납할 계획이었습니다.", "citations": ["p"]}]}
    model = ChatLocalModels.__new__(ChatLocalModels)
    model.structured = lambda *a, **kw: {
        "fulfillment": "direct", "abstention": "not_applicable", "reason": "원문 확인",
        "items": [{"index": 0, "support": "supported", "relevant": True, "issue": "none",
                   "evidence": [{"id": "p", "span_id": "s0:0"}]}]}
    review = model.review(question, [plan_row()], response)
    assert accepted(review, response) is limited
    if not limited:
        assert review["fulfillment"] == "missing"


def test_compound_parts_are_literal_independent_questions():
    from pma.chat.questions import question_parts

    question = "회사 동료 민수의 직업과 부산 여행을 취소한 이유는 뭐야?"
    parts = question_parts(question)
    assert parts == ["회사 동료 민수의 직업", "부산 여행을 취소한 이유는 뭐야?"]
    assert all(part in question for part in parts)


@pytest.mark.parametrize("question", [
    "회사 동료 민수의 직업은 뭐야?", "부산 여행은 왜 취소했어?",
    "회사 동료 민수의 직업과 관련된 부산 여행을 취소한 이유는 뭐야?",
    "회사 동료 민수의 직업과 부산 여행 취소 이유의 관계는 뭐야?",
])
def test_dependent_or_single_question_is_not_split(question):
    from pma.chat.questions import question_parts

    assert question_parts(question) == []


@pytest.mark.parametrize("intermediate", [False, True])
def test_literal_facets_keep_separate_retrieval_conditions_and_next_search_review(monkeypatch, intermediate):
    from types import SimpleNamespace

    from pma.chat import automatic, retrieval
    from pma.chat.questions import question_parts

    question = "회사 동료 민수의 직업과 부산 여행을 취소한 이유는 뭐야?"
    searched, decisions = [], []
    def retrieve(service, query, **kwargs):
        searched.append((query, kwargs["selection_question"]))
        return None, {"results": [], "filters": {}, "query_plan": {}, "status": "ok"}
    def structured(engine, prompt, data, schema, max_tokens=1024):
        decisions.append(schema)
        return {"query": ""}
    monkeypatch.setattr(retrieval, "retrieve", retrieve)
    monkeypatch.setattr(automatic, "structured", structured)
    engine = SimpleNamespace(
        service=SimpleNamespace(settings=SimpleNamespace(embedding_key="test", intermediate_planning=intermediate), trace=lambda *a, **kw: None),
        store=SimpleNamespace(freeze=lambda rows: rows))
    _, _, metadata = automatic.run(engine, question, {"messages": [], "context": {}}, "2026-10-19", "memory")
    assert searched == [(part, part) for part in question_parts(question)]
    assert decisions == [automatic.NEXT] * (1 if intermediate else 2)
    assert metadata["question_parts"] == question_parts(question)


def test_causal_check_does_not_require_a_cause_for_independent_profession_fact():
    from pma.chat.evidence import causal_claims_supported, semantic_issue

    question = "회사 동료 민수의 직업과 부산 여행을 취소한 이유는 뭐야?"
    rows = [{"id": "who", "source_text": "회사 동료 민수는 프론트엔드 개발자다."},
            {"id": "why", "source_text": "부산 여행은 취소했다. 비가 많이 내렸기 때문이다."}]
    job = {"text": rows[0]["source_text"], "citations": ["who"]}
    reason = {"text": "부산 여행은 비가 많이 내렸기 때문에 취소했습니다.", "citations": ["why"]}
    assert semantic_issue(question, job, rows) is None
    assert causal_claims_supported(question, {"items": [job, reason]}, rows, require_coverage=True)
    assert not causal_claims_supported(question, {"items": [job]}, rows, require_coverage=True)
    assert not causal_claims_supported("부산 여행은 왜 취소했어?", {"items": [job]}, rows)
