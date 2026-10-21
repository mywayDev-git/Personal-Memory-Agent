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
