from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest

from pma import interpretation_cache as cache
from pma.chat.engine import ChatEngine
from pma.models import LocalModels
from pma.settings import AppSettings
from scripts.memory_agent.llm_client import RequestDeadlineExceeded, request_budget


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    cache.clear_interpretations()
    monkeypatch.setenv("PMA_GENERATION_REVISION", "a" * 64)
    yield
    cache.clear_interpretations()


def question_model():
    model = LocalModels.__new__(LocalModels)
    model.settings = AppSettings(interpretation_reuse=True)
    calls = []
    def structured(*a, **kw):
        calls.append(1)
        return {"intent": "recall", "date_from": None, "date_to": None}
    model.structured = structured
    return model, calls


def resolver():
    engine = ChatEngine.__new__(ChatEngine)
    engine.service = SimpleNamespace(settings=AppSettings(interpretation_reuse=True))
    calls = []
    def structured(*a, **kw):
        calls.append(1)
        return {"question": "민수에게 무엇을 선물했어?", "needs_clarification": False,
                "alternatives": []}
    engine.models = SimpleNamespace(count_tokens=lambda _: 1, structured=structured)
    session = {"messages": [], "evidence": [{"id": "a", "record_id": "r", "version": 1,
                "revision_id": "v1", "source_text": "민수에게 책을 선물했다."}]}
    return engine, session, calls


def test_repeat_understanding_across_requests_and_copy_isolation():
    model, calls = question_model()
    with request_budget(30):
        first = model.understand("선물", "2026-10-21")
    first["intent"] = "aggregate"
    with request_budget(30):
        assert model.understand(question="선물", today="2026-10-21", expand=True)["intent"] == "recall"
    assert len(calls) == 1


def test_running_message_ids_do_not_invalidate_identical_context():
    engine, session, calls = resolver()
    session["messages"] = [{"id": "first", "state": "running", "response": None}]
    engine.resolve("民", session, "2026-10-21")
    session["messages"][0]["id"] = "second"
    engine.resolve("民", session, "2026-10-21")
    assert len(calls) == 1


@pytest.mark.parametrize("change", ["question", "date", "expand", "settings", "revision", "scope"])
def test_understanding_key_boundaries(change, monkeypatch):
    model, calls = question_model()
    model.understand("선물", "2026-10-21")
    question, today, expand = "선물", "2026-10-21", True
    if change == "question": question = "책"
    if change == "date": today = "2026-10-22"
    if change == "expand": expand = False
    if change == "settings": model.settings = replace(model.settings, llm=replace(model.settings.llm, seed=7))
    if change == "revision": monkeypatch.setenv("PMA_GENERATION_REVISION", "b" * 64)
    if change == "scope": model.settings = replace(model.settings, data_dir="other-owner")
    model.understand(question, today, expand=expand)
    assert len(calls) == 2


@pytest.mark.parametrize("change", [None, "source", "revision", "deleted", "history", "date", "original", "policy", "owner"])
def test_context_full_inputs(change, monkeypatch):
    engine, session, calls = resolver()
    engine.resolve("민수에게 무엇을 선물했어?", session, "2026-10-21")
    session = deepcopy(session)
    today, original = "2026-10-21", None
    if change == "source": session["evidence"][0]["source_text"] += " 주지 않았다."
    if change == "revision": session["evidence"][0]["revision_id"] = "v2"
    if change == "deleted": session["evidence"] = []
    if change == "history": session["messages"] = [{"state": "completed", "question": "그 사람?", "response": {"status": "answered"}}]
    if change == "date": today = "2026-10-22"
    if change == "original": original = "그 사람에게 뭘 줬어?"
    if change == "owner": session["owner_id"] = "someone-else"
    if change == "policy": monkeypatch.setattr("pma.chat.engine.RESOLVE_PROMPT", "different interpretation policy")
    second = engine.resolve("민수에게 무엇을 선물했어?", session, today, original_question=original)
    assert isinstance(second, tuple)
    assert len(calls) == (1 if change is None else 2)


def test_disabled_unknown_revision_ttl_and_capacity(monkeypatch):
    model, calls = question_model()
    monkeypatch.setenv("PMA_GENERATION_REVISION", "unconfigured")
    model.understand("a", "2026-10-21")
    model.understand("a", "2026-10-21")
    assert len(calls) == 2 and cache.cache_info()["entries"] == 0
    monkeypatch.setenv("PMA_GENERATION_REVISION", "a" * 64)
    model.settings = replace(model.settings, interpretation_reuse=False)
    model.understand("a", "2026-10-21")
    assert cache.cache_info()["entries"] == 0
    model.settings = replace(model.settings, interpretation_reuse=True)
    now = [0]
    monkeypatch.setattr(cache.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(cache, "MAX_ENTRIES", 2)
    model.understand("a", "2026-10-21")
    now[0] = cache.TTL_SECONDS + 1
    model.understand("a", "2026-10-21")
    assert len(calls) == 5
    for q in ["b", "c"]: model.understand(q, "2026-10-21")
    assert cache.cache_info()["entries"] == 2


def test_deadline_and_failures_never_bypass_or_fill_cache():
    model, calls = question_model()
    model.understand("a", "2026-10-21")
    with request_budget(30) as budget:
        budget.deadline = 0
        with pytest.raises(RequestDeadlineExceeded): model.understand("a", "2026-10-21")
    def fail(*a, **kw): raise ValueError("invalid model structure")
    model.structured = fail
    for _ in range(2):
        with pytest.raises(ValueError): model.understand("b", "2026-10-21")
    assert cache.cache_info()["entries"] == 1


def test_cache_cannot_be_attached_to_final_review():
    with pytest.raises(ValueError): cache.reuse_interpretation("review")


def test_ambiguous_context_is_rechecked_instead_of_cached(monkeypatch):
    engine, session, calls = resolver()
    session["evidence"][0]["source_text"] = "회사 동료 민수는 개발자다. 동아리 친구 민수는 교사다."
    alternatives = [{"label": name, "quote": name, "evidence_id": "a"}
                    for name in ("회사 동료 민수", "동아리 친구 민수")]
    monkeypatch.setattr("pma.chat.engine.identity_alternatives", lambda *a: alternatives)
    for _ in range(2):
        result, _ = engine.resolve("민수는 누구야?", session, "2026-10-21")
        assert result["needs_clarification"]
    assert len(calls) == 2 and cache.cache_info()["entries"] == 0


def test_total_value_byte_limit(monkeypatch):
    model, _ = question_model()
    monkeypatch.setattr(cache, "MAX_BYTES", 256)
    for number in range(10): model.understand(str(number), "2026-10-21")
    info = cache.cache_info()
    assert 0 < info["entries"] < 10 and info["value_bytes"] <= 256


def test_sampling_interpretations_are_not_cached():
    model, calls = question_model()
    model.settings = replace(model.settings, llm=replace(model.settings.llm, temperature=.5))
    for _ in range(2): model.understand("a", "2026-10-21")
    assert len(calls) == 2 and cache.cache_info()["entries"] == 0


def test_warm_context_still_independently_reviews_each_answer(monkeypatch):
    engine, session, interpretations = resolver()
    engine.service.trace = lambda *a, **kw: None
    source = session["evidence"][0]["source_text"]
    draft = {"status": "answered", "items": [{"text": source, "citations": ["a"]}]}
    reviews = []
    def review(*a, **kw):
        reviews.append(1)
        return {"fulfillment": "direct", "abstention": "not_applicable", "reason": "verified",
                "items": [{"index": 0, "support": "supported", "relevant": True, "issue": "none",
                           "answer_quote": source, "evidence": [{"id": "a", "quote": source}]}]}
    engine.models.review = review
    monkeypatch.setattr("pma.chat.engine.direct_statement", lambda *a: deepcopy(draft))
    monkeypatch.setattr("pma.chat.engine.claims_supported", lambda *a: True)
    monkeypatch.setattr("pma.chat.engine.causal_claims_supported", lambda *a: True)
    for _ in range(2):
        response = engine.generate("민수에게 무엇을 선물했어?", deepcopy(session), "2026-10-21")
        assert response["status"] == "answered"
    assert len(interpretations) == 1 and len(reviews) == 2
