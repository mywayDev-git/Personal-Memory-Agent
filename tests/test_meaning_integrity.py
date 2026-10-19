from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
from test_search_accuracy import memory
from test_search_explain import row, service

from pma.answer_review import accepted
from pma.chat.models import ChatLocalModels
from pma.chat.store import ChatStore
from pma.errors import AppError
from pma.facts import project
from pma.grounding import claims_supported
from pma.models import LocalModels
from pma.relevance import study_topic, topic_supported
from pma.settings import AppSettings
from pma.store import Store
from scripts.memory_agent.diagnostics import ProcessingError
from scripts.memory_agent.meaning import extraction_conflicts, meaning_conflict
from scripts.memory_agent.pipeline import process_text
from scripts.memory_agent.postprocess import make_source_context


@pytest.mark.parametrize("source,claim", [
    ("나 파이썬 공부 접었어", "파이썬 공부를 시작했습니다."),
    ("공부를 그만뒀다", "공부를 시작했다"),
    ("공부를 중단했다", "공부를 시작했다"),
    ("시험에 불합격했다", "시험에 합격했다"),
    ("실험에 실패했다", "실험에 성공했다"),
    ("회사에서 퇴사했다", "회사에 입사했다"),
    ("노트북을 판매했다", "노트북을 구매했다"),
    ("공부를 시작하지 않았다", "공부를 시작했다"),
    ("I stopped studying Python", "I started studying Python"),
])
def test_explicit_reversals_rejected_independently_of_model(source, claim):
    assert meaning_conflict(claim, source)
    evidence = [{"id": "a", "source_text": source, "evidence": [{"quote": source}]}]
    assert not claims_supported([{"text": claim, "citations": ["a"]}], evidence)


@pytest.mark.parametrize("source,claim", [
    ("시작했지만 중단했다", "시작했다"),
    ("공부를 중단하지 않았다", "공부를 중단하지 않았습니다"),
    ("시작하려고 했다", "시작하려고 했습니다"),
    ("공부를 접었어", "공부를 그만뒀습니다"),
    ("불합격했다", "불합격했습니다"),
    ("새 이야기를 시작했다", "새 이야기를 시작했습니다"),
    ("종이를 접었다", "종이 접기를 시작했다"),
    ("접은 노트북을 꺼냈다", "노트북 수리를 시작했다"),
    ("휴대폰이 떨어졌다", "휴대폰 수리에 성공했다"),
])
def test_history_negation_and_paraphrases_preserved(source, claim):
    assert not meaning_conflict(claim, source)


def test_summary_predicate_contradiction_marks_existing_projection_for_review():
    source = "나 파이썬 공부 접었어"
    m = memory(source, "파이썬 공부")
    m.update(content="파이썬 공부를 시작했다", predicate="접었다")
    assert extraction_conflicts([m])
    fact = project(m, source, None, "2026-10-20")
    assert "extraction_meaning_mismatch" in fact["review_reasons"]
    assert fact["state"] == "review_required"
    model_row = {"id": "a", "content": m["content"], "predicate": m["predicate"],
                 "evidence": m["evidence"], "source_text": source, "fact": fact}
    assert LocalModels.compact_evidence([model_row])[0]["content"] == source


@pytest.mark.parametrize("query", ["내가 python 공부한거", "파이썬 공부 이력", "파이선에서 공부", "Python을 공부했어?", "Python", "파이썬"])
def test_study_topic_uses_original_source_and_registered_aliases(query):
    assert study_topic(query) == "python"
    assert topic_supported(query, {"source_text": "파이썬을 공부하다 접었어"})
    assert topic_supported(query, {"source_text": "Python의 asyncio를 공부했다. gather를 배웠다.",
                                   "evidence": [{"quote": "gather를 배웠다."}]})
    assert not topic_supported(query, {"source_text": "지연에게 컵을 선물했다", "content": "Python 공부"})
    assert not topic_supported(query, {"source_text": "Python을 공부했다.\n\n지연에게 컵을 선물했다",
                                      "evidence": [{"quote": "지연에게 컵을 선물했다"}]})


def test_topic_filter_precedes_ai_review_and_keeps_stop_and_past_study():
    rows = [row(1, "나 파이썬 공부 접었어"), row(2, "Python의 asyncio를 공부했다"),
            row(3, "지연에게 컵을 선물했다"), row(4, "캡스톤 API 개발을 담당하기로 했다")]
    for record in rows:
        record["fact"].update(relation="other", object_key="")
    svc = service(rows)
    calls = []
    svc.models.select = lambda q, records: calls.append([r["id"] for r in records]) or calls[-1]
    result = svc._search("내가 python 공부한거")[1]
    assert {r["id"] for r in result["results"]} == {"1", "2"}
    assert calls == [["1", "2"]]
    assert {c["id"] for c in result["search_audit"]["candidates"] if c["reason"] == "topic_mismatch"} == {"3", "4"}


def test_false_positive_review_cannot_approve_reversed_action_or_irrelevant_topic():
    model = ChatLocalModels.__new__(ChatLocalModels)
    model.structured = lambda *args, **kwargs: {
        "fulfillment": "direct", "abstention": "not_applicable", "reason": "통과",
        "items": [{"index": 0, "support": "supported", "relevant": True, "issue": "none",
                   "evidence": [{"id": "a", "span_id": "s0:0"}]}]}
    for source, claim in [("나 파이썬 공부 접었어", "파이썬 공부를 시작했습니다"),
                          ("지연에게 컵을 선물했다", "지연에게 컵을 선물했습니다")]:
        result = {"status": "answered", "items": [{"text": claim, "citations": ["a"]}]}
        checked = model.review("내가 python 공부한거", [{"id": "a", "source_text": source}], result)
        assert not accepted(checked, result)


def test_answer_generation_excludes_unselected_background_but_keeps_conflict(monkeypatch):
    import pma.chat.engine as module

    sources = [{"id": name, "record_id": name, "revision_id": "v1", "source_text": quote}
               for name, quote in [("a", "민수에게 컵을 줬다."), ("b", "지연과 산책했다."),
                                   ("c", "민수에게 컵을 주지 않았다.")]]
    for source in sources:
        source["evidence"] = [{"quote": source["source_text"]}]
    sources[2]["search_explanation"] = {"model_assessment": {"category": "conflicting_evidence"}}
    seen = []
    def answer(q, evidence, **kwargs):
        seen.append([r["id"] for r in evidence])
        return {"status": "answered", "items": [{"text": sources[0]["source_text"], "citations": ["a"]}]}
    def review(q, evidence, response):
        return {"fulfillment": "direct", "abstention": "not_applicable", "reason": "원문 확인",
                "items": [{"index": 0, "support": "supported", "relevant": True, "issue": "none",
                           "answer_quote": response["items"][0]["text"],
                           "evidence": [{"id": "a", "quote": sources[0]["source_text"]}]}]}
    engine = module.ChatEngine.__new__(module.ChatEngine)
    engine.models = SimpleNamespace(select=lambda *args: ["a"], answer=answer, review=review)
    engine.service = SimpleNamespace(trace=lambda *args, **kwargs: None)
    engine.resolve = lambda *args, **kwargs: ({"needs_clarification": False, "question": "어떤 기록이야?"}, 0)
    monkeypatch.setattr(module, "direct_statement", lambda *args: None)
    assert engine.generate("어떤 기록이야?", {"evidence": sources}, "2026-10-20")["status"] == "answered"
    assert seen == [["a", "c"]]


@pytest.mark.parametrize("approve_repair", [True, False])
def test_verbatim_repair_still_requires_independent_review(monkeypatch, approve_repair):
    import pma.chat.engine as module

    source = {"id": "a", "record_id": "r", "revision_id": "v", "source_text": "나 파이썬 공부 접었어",
              "evidence": [{"quote": "나 파이썬 공부 접었어"}]}
    calls = []
    def answer(*args, **kwargs):
        calls.append("answer")
        return {"status": "answered", "items": [{"text": "파이썬 공부를 시작했습니다", "citations": ["a"]}]}
    def review(q, evidence, response):
        calls.append("review")
        supported = len(calls) == 2 or approve_repair
        return {"fulfillment": "direct", "abstention": "not_applicable", "reason": "판정",
                "items": [{"index": 0, "support": "supported" if supported else "unsupported",
                           "relevant": True, "issue": "none", "answer_quote": response["items"][0]["text"],
                           "evidence": [{"id": "a", "quote": source["source_text"]}]}]}
    engine = module.ChatEngine.__new__(module.ChatEngine)
    engine.models = SimpleNamespace(answer=answer, review=review)
    engine.service = SimpleNamespace(trace=lambda *args, **kwargs: None)
    engine.resolve = lambda *args, **kwargs: ({"needs_clarification": False, "question": "내가 python 공부한거"}, 0)
    monkeypatch.setattr(module, "direct_statement", lambda *args: None)
    response = engine.generate("내가 python 공부한거", {"evidence": [source]}, "2026-10-20")
    assert calls == ["answer", "review", "review"]
    assert response["status"] == ("answered" if approve_repair else "insufficient_evidence")
    if approve_repair:
        assert "접었어" in response["items"][0]["text"]
        assert response["validation"] == "model_checked"


@pytest.mark.parametrize("repair_succeeds", [True, False, "verbatim"])
def test_ingestion_retries_once_then_fails_closed(monkeypatch, repair_succeeds):
    models = LocalModels(AppSettings())
    from scripts.memory_agent import pipeline
    bad = memory("나 파이썬 공부 접었어", "파이썬 공부")
    bad.update(content="파이썬 공부를 시작했다", predicate="접었다",
               subject={"kind": "self", "value": "사용자", "value_type": "string"},
               object={"kind": "literal", "value": "파이썬 공부", "value_type": "string"},
               target=None, polarity="neutral", content_certainty="explicit")
    calls = []

    def extract(**kwargs):
        calls.append(kwargs)
        item = deepcopy(bad)
        if len(calls) == 2 and repair_succeeds is True:
            item["content"] = "파이썬 공부를 접었다"
        elif len(calls) == 2 and repair_succeeds is False:
            item["predicate"] = "시작했다"
        return {"memories": [item]}, {}, 0.1

    monkeypatch.setattr(pipeline, "extract_memories", extract)
    kwargs = dict(prompt="추출", output_schema=models.raw_schema, final_schema=models.final_schema,
                  session=None, settings=models.settings.llm)
    if repair_succeeds:
        result, meta = process_text("나 파이썬 공부 접었어", make_source_context("test"), **kwargs)
        assert result["memories"][0]["content"] == ("파이썬 공부를 접었다" if repair_succeeds is True else "나 파이썬 공부 접었어")
        if repair_succeeds == "verbatim":
            assert meta["summary_fallback"] == "verbatim_supported_predicate"
        assert meta["repair_attempts"][0]["code"] == "EXTRACTION_MEANING_MISMATCH"
    else:
        with pytest.raises(ProcessingError, match="EXTRACTION_MEANING_MISMATCH"):
            process_text("나 파이썬 공부 접었어", make_source_context("test"), **kwargs)
    assert len(calls) == 2


def test_atomic_derived_replacement_preserves_source_and_rollback(tmp_path):
    store = Store(tmp_path / "memory.db")
    text = "나 파이썬 공부 접었어"
    created = store.create(text, None)
    job = store.claim()
    m = memory(text, "파이썬 공부")
    m.update(local_id="m1", predicate="접었다")
    assert store.publish(job, [m], [np.array([1.])], "test", {})
    with store.connect() as db:
        originals = [tuple(r) for r in db.execute("SELECT * FROM revisions")]
        mid = db.execute("SELECT id FROM memories").fetchone()[0]
        revision = db.execute("SELECT id FROM revisions").fetchone()[0]
    # Register a new job without deleting the old published memory.
    with store.connect(True) as db:
        store.queue(db, revision)
    second = store.claim()
    with pytest.raises(AppError, match="SOURCE_CHANGED"):
        store.publish(second, [m], [np.array([1.])], "test", {}, replace_memory_ids=["stale"])
    with store.connect() as db:
        assert db.execute("SELECT id FROM memories").fetchone()[0] == mid
    broken = deepcopy(m)
    broken["evidence"] = [{"quote": "存在しない"}]
    with pytest.raises(ValueError, match="INVALID_EVIDENCE"):
        store.publish(second, [broken], [np.array([1.])], "test", {}, replace_memory_ids=[mid])
    with store.connect() as db:
        assert db.execute("SELECT id FROM memories").fetchone()[0] == mid
    assert store.publish(second, [m], [np.array([1.])], "test", {}, replace_memory_ids=[mid])
    with store.connect() as db:
        assert [tuple(r) for r in db.execute("SELECT * FROM revisions")] == originals
        assert db.execute("SELECT id FROM memories").fetchone()[0] != mid
        assert db.execute("SELECT count(*) FROM memories").fetchone()[0] == 1
    assert store.get(created["record_id"])["text"] == text
    # Even a saved search with the unchanged source version must not reuse an
    # earlier, superseded extracted memory after successful reprocessing.
    with store.connect() as db:
        with pytest.raises(AppError, match="SOURCE_CHANGED"):
            ChatStore(store).check_sources(db, [{"id": mid, "record_id": created["record_id"], "version": 1}])
