from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest

from pma.chat.intermediate import propose, reuse
from pma.chat.engine import ChatEngine
from pma.settings import AppSettings


def fixture():
    answer = {"context": {"question": "민수에게 뭘 선물했어?", "needs_clarification": False,
                           "alternatives": []}, "query": "",
              "selection": [{"id": "a", "selected": True}]}
    calls = []
    def structured(*args, **kwargs):
        calls.append((args, kwargs))
        value = deepcopy(answer)
        if "question" not in args[2]["properties"]["context"]["properties"]:
            value["context"].pop("question", None)
        return value
    engine = ChatEngine.__new__(ChatEngine)
    engine.service = SimpleNamespace(settings=AppSettings(intermediate_planning=True))
    engine.models = SimpleNamespace(count_tokens=lambda _: 1, structured=structured)
    session = {"messages": [], "evidence": [{"id": "a", "record_id": "r", "version": 1,
                  "revision_id": "v1", "source_text": "민수에게 책을 선물했다."}]}
    return engine, session, answer, calls


def test_shared_call_preserves_full_inputs_and_resolver_checks():
    engine, session, _, calls = fixture()
    session["_intermediate"] = propose(engine, "민수에게 뭘 선물했어?", session, "2026-10-21", [])
    result, _ = engine.resolve("민수에게 뭘 선물했어?", session, "2026-10-21")
    assert result["needs_clarification"] is False
    assert reuse("민수에게 뭘 선물했어?", session, "2026-10-21", "selection") == ["a"]
    assert len(calls) == 1
    assert calls[0][0][1]["evidence"] == session["evidence"]
    first = reuse("민수에게 뭘 선물했어?", session, "2026-10-21", "context")
    first["question"] = "변경"
    assert reuse("민수에게 뭘 선물했어?", session, "2026-10-21", "context")["question"] != "변경"


@pytest.mark.parametrize("change", ["source", "deleted", "revision", "history", "date", "question", "order"])
def test_any_input_change_invalidates(change):
    engine, session, _, _ = fixture()
    question, today = "민수에게 뭘 선물했어?", "2026-10-21"
    session["_intermediate"] = propose(engine, question, session, today, [])
    if change == "source": session["evidence"][0]["source_text"] += " 주지 않았다."
    if change == "deleted": session["evidence"] = []
    if change == "revision": session["evidence"][0]["revision_id"] = "v2"
    if change == "history": session["messages"] = [{"state": "completed", "question": "다른 질문",
                                                     "response": {"status": "answered"}}]
    if change == "date": today = "2026-10-22"
    if change == "question": question = "누가?"
    if change == "order": session["evidence"].append({"id": "b", "source_text": "다른 근거"})
    assert reuse(question, session, today, "selection") is None


@pytest.mark.parametrize("invalid", ["duplicate", "missing", "schema", "oversize", "disabled"])
def test_invalid_proposal_falls_back(invalid):
    engine, session, answer, calls = fixture()
    if invalid == "duplicate": answer["selection"] *= 2
    if invalid == "missing": answer["selection"] = []
    if invalid == "schema": answer["context"]["needs_clarification"] = "false"
    if invalid == "oversize": engine.models.count_tokens = lambda _: 100000
    if invalid == "disabled": engine.service.settings = replace(engine.service.settings, intermediate_planning=False)
    assert propose(engine, "질문", session, "2026-10-21", []) is None
    if invalid in {"oversize", "disabled"}: assert calls == []


def test_exact_proposals_reuse_with_deadline_and_search_invalidation(monkeypatch):
    from pma.interpretation_cache import clear_interpretations
    from scripts.memory_agent.llm_client import RequestDeadlineExceeded, request_budget
    clear_interpretations()
    monkeypatch.setenv("PMA_GENERATION_REVISION", "a" * 64)
    engine, session, _, calls = fixture()
    engine.service.settings = replace(engine.service.settings, interpretation_reuse=True)
    first = propose(engine, "질문", session, "2026-10-21", [])
    assert propose(engine, "질문", session, "2026-10-21", []) == first
    assert len(calls) == 1
    propose(engine, "질문", session, "2026-10-21", [{"query": "다른 검색"}])
    assert len(calls) == 2
    with request_budget(10) as budget:
        budget.deadline = 0
        with pytest.raises(RequestDeadlineExceeded):
            propose(engine, "질문", session, "2026-10-21", [])
    assert len(calls) == 2
    clear_interpretations()


def test_deduplication_retains_full_source_warnings_and_offsets():
    engine, session, _, calls = fixture()
    row = session["evidence"][0]
    source = "민수에게 책을 주지 않았다. " * 100
    row.update(source_text=source, content=source,
               evidence=[{"quote": "주지 않았다.", "start": 7, "end": 14}],
               fact={"warnings": ["주체 확인 필요"], "state": "planned"})
    propose(engine, "질문", session, "2026-10-21", [])
    sent = calls[0][0][1]["evidence"][0]
    assert sent["source_text"] == source
    assert sent["evidence"] == row["evidence"]
    assert sent["fact"] == row["fact"]
    assert row["content"] == source


def test_previously_budgeted_exact_proposal_does_not_rebudget_unused_duplicate_input():
    engine, session, _, calls = fixture()
    question = "민수에게 뭘 선물했어?"
    session["_intermediate"] = propose(engine, question, session, "2026-10-21", [])
    def unused_budget(_):
        raise AssertionError("unused legacy duplicated prompt must not be budgeted")
    engine.models.count_tokens = unused_budget
    result, _ = engine.resolve(question, session, "2026-10-21")
    assert result["question"] == question
    assert len(calls) == 1


def compound_fixture(query=""):
    engine, session, answer, calls = fixture()
    question = "회사 동료 민수의 직업과 부산 여행을 취소한 이유는 뭐야?"
    session["evidence"] = [
        {"id": "a", "source_text": "회사 동료 민수는 개발자다.", "record_id": "r1"},
        {"id": "b", "source_text": "부산 여행은 비 때문에 취소했다.", "record_id": "r2"},
        {"id": "c", "source_text": "동아리 친구 민수는 교사다.", "record_id": "r3"}]
    answer.update(selection=[{"id": "a", "selected": True}, {"id": "b", "selected": True}],
                  coverage=[{"part": 0, "ids": ["a"]}, {"part": 1, "ids": ["b"]}], query=query)
    return engine, session, answer, calls, question


def test_selection_uses_the_exact_existing_answer_scope_but_planning_keeps_every_source():
    engine, session, _, calls, question = compound_fixture()
    session["_intermediate"] = propose(engine, question, session, "2026-10-21", [])
    assert session["_intermediate"] is not None
    data = calls[0][0][1]
    assert {r["id"] for r in data["evidence"]} == {"a", "b", "c"}
    assert data["scopes"]["selection"]["ids"] == ["a", "b"]
    selected_session = {**session, "evidence": session["evidence"][:2]}
    assert reuse(question, selected_session, "2026-10-21", "selection") == ["a", "b"]
    assert reuse(question, session, "2026-10-21", "selection") is None
    selected_session["evidence"][0]["source_text"] += " 개발자가 아니다."
    assert reuse(question, selected_session, "2026-10-21", "selection") is None


def test_invalid_search_plan_is_not_reused_or_cached_but_valid_scoped_parts_remain(monkeypatch):
    from pma.interpretation_cache import clear_interpretations
    clear_interpretations()
    monkeypatch.setenv("PMA_GENERATION_REVISION", "a" * 64)
    engine, session, _, calls, question = compound_fixture("민수의 친구 관계는?")
    engine.service.settings = replace(engine.service.settings, interpretation_reuse=True)
    result = propose(engine, question, session, "2026-10-21", [])
    assert result["query"] is None
    assert result["context"] and result["selection"] == ["a", "b"]
    propose(engine, question, session, "2026-10-21", [])
    assert len(calls) == 2
    clear_interpretations()
