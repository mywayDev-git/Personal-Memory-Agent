from copy import deepcopy

import pytest

from pma.answer_review import accepted
from pma.chat.automatic import search_question
from pma.chat.models import ChatLocalModels
from pma.chat.review_sources import source_catalog
from pma.facts import companions, mentions_person


def test_overview_keeps_intent_but_pronouns_can_resolve():
    assert search_question("지연이에 대해 이야기 해줘", "지연이와 사용자의 관계") == "지연이에 대해 이야기 해줘"
    assert search_question("부산 여행에 대해 정리해줘", "부산 여행 날짜") == "부산 여행에 대해 정리해줘"
    assert search_question("그 사람에 대해 알려줘", "회사 동료 민수에 대해 알려줘") == "회사 동료 민수에 대해 알려줘"


@pytest.mark.parametrize("content,expected", [
    ("지연과 서울숲을 산책했다", ["지연"]),
    ("민수랑 함께 식사했다", ["민수"]),
    ("지연 없이 서울숲을 산책했다", []),
    ("지연이 추천한 서울숲을 산책했다", []),
    ("지연과 함께 가지 않았다", []),
    ("지연과 식사한다면 좋겠다", []),
])
def test_companion_requires_explicit_grounded_event(content, expected):
    assert companions(content, content + ".") == expected
    assert companions(content, "다른 기록") == []


def test_name_boundaries_and_complete_negative_numeric_spans():
    assert mentions_person("지연이한테 선물했다", "지연")
    assert not mentions_person("일정이 지연되었다", "지연")
    assert not mentions_person("김지연에게 선물했다", "지연")
    text = "민수에게 3.5km를 달리라고 말하지 않았다. 실제로 뛰었는지는 모른다."
    rows, catalog = source_catalog([{"id": "m", "source_text": text}])
    assert len(catalog) == 2
    assert catalog["s0:0"]["quote"] == "민수에게 3.5km를 달리라고 말하지 않았다."
    assert rows[0]["source_context"] == text


@pytest.mark.parametrize("record_time", [False, True])
def test_review_uses_only_original_spans_and_display_cannot_reject_facts(record_time):
    source = {"id": "a", "source_text": "지연에게 빨간 컵을 줬어", "content": "요약은 인용 불가", "recorded_at": "2026-10-13"}
    response = {"status": "answered", "items": [{"text": "빨간 컵을 선물했습니다.", "citations": ["a"]}],
                "display": {"kind": "events", "items": []}}
    model = ChatLocalModels.__new__(ChatLocalModels)
    calls = []

    def structured(prompt, data, schema, max_tokens=None):
        calls.append(deepcopy(data))
        if "presentation_proposal" in data:
            raise ValueError("INVALID_DISPLAY")
        assert "display" not in data["proposed_answer"]
        assert "content" not in data["source_records"][0]
        assert ("record_metadata" in data["source_records"][0]) is record_time
        if record_time:
            assert data["source_records"][0]["record_metadata"]["stored_at"] == "2026-10-13"
        assert "span_id" in schema["properties"]["items"]["items"]["properties"]["evidence"]["items"]["required"]
        return {"fulfillment": "direct", "abstention": "not_applicable", "reason": "원문 확인",
                "items": [{"index": 0, "support": "supported", "relevant": True, "issue": "none",
                           "evidence": [{"id": "a", "span_id": "s0:0"}]}]}

    model.structured = structured
    result = model.review("언제 기록했어?" if record_time else "지연에 대해 이야기해줘", [source], response)
    assert accepted(result, response)
    assert result["presentation_valid"] is False
    assert result["items"][0]["evidence"] == [{"id": "a", "quote": source["source_text"]}]
    assert len(calls) == 2


@pytest.mark.parametrize("mode", ["wrong_source", "contradictory_review", "unsupported"])
def test_source_selection_never_bypasses_semantic_or_identity_checks(mode):
    sources = [{"id": "a", "source_text": "회사 동료 민수에게 선물을 주지 않았다."},
               {"id": "b", "source_text": "동창 민수에게 선물을 줬다."}]
    response = {"status": "answered", "items": [{"text": "회사 동료 민수에게 선물을 줬다.", "citations": ["a"]}]}
    model = ChatLocalModels.__new__(ChatLocalModels)
    model.structured = lambda *a, **kw: {
        "fulfillment": "direct", "abstention": "not_applicable", "reason": "검사",
        "items": [{"index": 0, "support": "unsupported" if mode == "unsupported" else "supported",
                   "relevant": True, "issue": "negation" if mode != "wrong_source" else "none",
                   "evidence": [{"id": "a", "span_id": "s1:0" if mode == "wrong_source" else "s0:0"}]}]}
    if mode == "unsupported":
        assert not accepted(model.review("동료 민수에게 선물 줬어?", sources, response), response)
    else:
        with pytest.raises(ValueError, match="INVALID_REVIEW_CITATION|INCONSISTENT_REVIEW"):
            model.review("동료 민수에게 선물 줬어?", sources, response)


@pytest.mark.parametrize("question,text,storage,reference", [
    ("지연에 대해 이야기해줘", "선물을 줬다", False, False),
    ("지연에 대해 이야기해줘", "어제 선물을 줬다", False, True),
    ("이 기록은 언제 저장했어?", "선물을 줬다", True, True),
])
def test_generation_time_metadata_is_scoped_to_question(monkeypatch, question, text, storage, reference):
    from pma.models import ANSWER_SCHEMA, LocalModels

    seen = []
    monkeypatch.setattr(LocalModels, "structured", lambda self, prompt, data, schema, max_tokens: seen.append(data))
    model = ChatLocalModels.__new__(ChatLocalModels)
    data = {"question": question, "feedback": None, "evidence": [{"source_context": text,
            "time_context": {"storage_timestamp": "2026-10-13", "document_reference_timestamp": "2026-10-13"}}]}
    original = deepcopy(data)
    model.structured("", data, ANSWER_SCHEMA)
    context = seen[0]["evidence"][0]["time_context"]
    assert ("storage_timestamp" in context) is storage
    assert ("document_reference_timestamp" in context) is reference
    assert data == original


def test_optional_display_budget_leaves_parent_and_preserves_call_metrics():
    from scripts.memory_agent.llm_client import optional_request_budget, request_budget

    with request_budget(1):
        with optional_request_budget(10) as allowed:
            assert not allowed
    with request_budget(30) as parent:
        deadline = parent.deadline
        with optional_request_budget(10) as allowed:
            assert allowed
        assert parent.deadline == deadline


def test_existing_facts_upgrade_without_changing_sources_or_embeddings(tmp_path):
    import json

    from pma.facts import FACT_VERSION
    from pma.store import Store

    store = Store(tmp_path / "memory.db")
    text = "지연과 서울숲을 산책했다."
    created = store.create(text, None)
    memory = {"content": text, "predicate": "산책했다", "subject": {"kind": "self"},
              "object": {"value": "서울숲"}, "memory_type": "event", "assertion_polarity": "affirmed",
              "evidence": [{"quote": text}],
              "time": {"raw": None, "start": None, "end": None, "precision": "unknown", "certainty": "uncertain"}}
    payload = json.dumps(memory, ensure_ascii=False)
    with store.connect(True) as db:
        revision = db.execute("SELECT id FROM revisions WHERE record_id=?", (created["record_id"],)).fetchone()[0]
        db.execute("INSERT INTO memories VALUES(?,?,?,?,?)", ("m", revision, created["job_id"], "local", payload))
        db.execute("INSERT INTO evidence VALUES(?,?,?,?,?)", ("m", 0, text, 0, len(text)))
        db.execute("INSERT INTO embeddings VALUES(?,?,?,?)", ("m", "test", 1, b"\x00\x00\x80\x3f"))
        db.execute("INSERT INTO facts VALUES(?,?,?,?,?,?,?)", ("m", 7, "self", None, "서울숲", "{}", "old"))
        db.execute("UPDATE records SET status='ready' WHERE id=?", (created["record_id"],))
    assert store.rebuild_facts() == 1
    _, rows = store.snapshot("test")
    assert rows[0]["fact"]["participants"] == ["지연"]
    assert rows[0]["fact"]["projection_version"] == FACT_VERSION
    assert rows[0]["text"] == text and rows[0]["memory"] == memory
    assert rows[0]["vector"] == b"\x00\x00\x80\x3f"
    assert (tmp_path / f"memory.db.before-facts-v{FACT_VERSION}.bak").exists()
    assert store.rebuild_facts() == 0


@pytest.mark.parametrize("question,sources,answer,issue", [
    ("왜 선물했어?", ["민수는 컵을 좋아한다.", "민수에게 컵을 줬다."], "컵을 좋아하기 때문에 선물했다.", "cause"),
    ("왜 선물했어?", ["컵을 좋아하기 때문에 선물했다."], "컵을 좋아하기 때문에 선물했다.", None),
    ("왜 선물했어?", ["민수에게 컵을 줬다."], "선물한 이유는 확인할 수 없습니다.", None),
    ("어떤 결정을 했어?", ["선물을 주기로 하지 않았다."], "선물을 주지 않기로 결정했다.", "negation"),
    ("어떤 결정을 했어?", ["선물을 주지 않기로 결정했다."], "선물을 주지 않기로 결정했다.", None),
    ("어떤 결정을 했어?", ["선물을 주기로 하지 않았다."], "선물을 주기로 하지 않았습니다.", None),
    ("어떤 결정을 했어?", ["선물을 주기로 하지 않았다."], "선물할 계획이 없습니다.", "negation"),
])
def test_meaning_guards_do_not_depend_on_model_approval(question, sources, answer, issue):
    from pma.chat.evidence import semantic_issue

    evidence = [{"id": str(i), "source_text": text} for i, text in enumerate(sources)]
    assert semantic_issue(question, {"text": answer, "citations": [r["id"] for r in evidence]}, evidence) == issue
