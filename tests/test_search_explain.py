from types import SimpleNamespace

import numpy as np

from pma.chat.automatic import combine
from pma.models import LocalModels
from pma.search_explain import keyword_matches, keyword_query, normalize, select_evidence
from pma.service import Service


def row(index, text="제주 여행", score=1, state="observed", source=None):
    return {
        "id": str(index),
        "record_id": source or str(index),
        "version": 1,
        "text": text,
        "source_text": text,
        "content": text,
        "memory": {
            "content": text,
            "subject": "나",
            "predicate": "여행",
            "object": "제주",
            "target": "",
            "memory_type": "event",
            "assertion_polarity": "positive",
        },
        "fact": {
            "relation": "visit",
            "actor": "self",
            "recipient": "",
            "object_key": "제주",
            "state": state,
            "event_time": {"start": "2026-05-12", "end": None, "certainty": "certain"},
        },
        "vector": np.array([1, 0], dtype="<f4").tobytes(),
        "evidence": [{"start": 0, "end": len(text), "quote": text}],
        "reference_time": None,
        "created_at": "2026-05-12",
        "score": score,
    }


def test_korean_normalization_retains_original_spans_and_negation():
    record = row(1, "😀 제주에 갔다. 여행은 취소하지 않았다. 고양이")
    terms, vocabulary = keyword_query("제주에서 갔어", [record])
    found = keyword_matches(record, terms, vocabulary)
    assert any(m["quote"] == "제주에" and m["kind"] == "normalized" for m in found)
    assert any(m["quote"] == "갔다" and m["kind"] == "normalized" for m in found)
    assert all(
        record["text"][m["start"] : m["end"]] == m["quote"]
        for m in found
        if m["field"] == "source_text"
    )
    assert normalize("고양이", vocabulary) == "고양이"
    assert normalize("않았다", vocabulary) == "않았다"


def test_exact_matches_outweigh_normalized_and_summary_is_separate():
    record = row(1, "부산 여행")
    record["memory"]["content"] = "제주 여행"
    terms, vocabulary = keyword_query("제주", [record])
    found = keyword_matches(record, terms, vocabulary)
    assert found and all(m["field"] == "content" for m in found)
    assert all(m["kind"] == "exact" for m in found)


def test_date_question_does_not_match_syllable_in_minsu():
    record = row(1, "[테스트 데이터 DEMO-01] 2026년 10월 1일 나는 캡스톤 프로젝트 회의에서 "
                 "백엔드 API 개발을 담당하기로 결정했다. 민수는 웹 화면 디자인을 맡기로 했다.")
    record["memory"]["content"] = "민수는 웹 화면 디자인을 맡기로 했다"
    terms, vocabulary = keyword_query("날짜를 어떻게 알 수 있나요?", [record])
    assert "수" not in {term["text"] for term in terms}
    assert keyword_matches(record, terms, vocabulary) == []
    _, result = service([record])._search("날짜를 어떻게 알 수 있나요?", today="2026-10-19")
    info = result["results"][0]["search_explanation"]
    assert info["keyword_matches"] == []
    assert info["ranks"]["keyword"] is None
    assert "keyword" not in info["methods"]


def test_keyword_matching_uses_whole_tokens_and_retains_short_keywords():
    record = row(1, "민수는 수박과 밤하늘을 봤다. 수 밤 API happy 10 100")
    terms, vocabulary = keyword_query("수 밤 api 10", [record])
    found = keyword_matches(record, terms, vocabulary)
    assert {match["quote"] for match in found} == {"수", "밤", "API", "10"}
    assert all(match["kind"] == "exact" for match in found)
    assert all(record["text"][m["start"]:m["end"]] == m["quote"] for m in found)


def test_person_particle_still_matches_without_matching_longer_names():
    record = row(1, "김민수는 민수는 민수에게 말했다")
    terms, vocabulary = keyword_query("민수", [record])
    found = keyword_matches(record, terms, vocabulary)
    assert {match["quote"] for match in found} == {"민수는", "민수에게"}
    assert all(match["kind"] == "normalized" for match in found)




def test_duplicate_memory_id_uses_best_score():
    assert select_evidence([row(1, score=0.1), row(1, score=0.9)])[0]["score"] == 0.9


def test_model_batches_no_longer_truncate_later_matches():
    model = LocalModels.__new__(LocalModels)
    model.structured = lambda prompt, data, schema, **kw: {
        "ids": [r["id"] for r in data["evidence"]]
    }
    assert len(model.select("여행", [row(i) for i in range(12)])) == 12


def service(records):
    store = SimpleNamespace(
        snapshot=lambda key: (1, records),
        assert_generation=lambda generation: None,
        links=lambda **kw: [],
    )
    models = SimpleNamespace(
        understand=lambda *args: {"intent": "recall", "date_from": None, "date_to": None},
        embed=lambda text: [[1, 0]],
        select=lambda question, evidence: [r["id"] for r in evidence],
    )
    return Service(store, models, SimpleNamespace(embedding_key="test", embedding_dimensions=2))




def test_search_explanations_work_without_diagnostic_mode():
    records = [row(1), row(2)]
    records[1]["fact"]["event_time"]["start"] = None
    _, found = service(records)._search(
        "제주 여행", {"date_from": "2026-05-01", "date_to": "2026-05-31"}, "2026-10-19"
    )
    assert len(found["results"]) == 1
    info = found["results"][0]["search_explanation"]
    assert set(info["methods"]) == {"keyword", "semantic", "structure"}
    assert any(c["condition"] == "time" for c in info["conditions"])
    assert info["selection"]["reason"] == "model_selected"
    excluded = next(r for r in found["search_audit"]["candidates"] if r["id"] == "2")
    assert excluded["reason"] == "unknown_filtered_date"
    assert excluded["stages"]["conditions"]["status"] == "failed"
    assert excluded["stages"]["selection"]["status"] == "not_run"
    assert excluded["conditions"][0]["expected"] == {"start": "2026-05-01", "end": "2026-05-31"}
    assert "source_text" not in excluded and "content" not in excluded


def test_zero_candidates_retains_exclusion_reason():
    record = row(1)
    record["fact"] = None
    _, found = service([record])._search("여행", today="2026-10-19")
    assert not found["results"]
    assert found["search_audit"]["candidates"][0]["reason"] == "facts_pending"


def test_model_classification_requires_real_source_quote():
    model = LocalModels.__new__(LocalModels)
    model.structured = lambda *args, **kw: {
        "items": [
            {"id": "1", "category": "direct_answer", "quote": "제주 여행"},
            {"id": "2", "category": "direct_answer", "quote": "없는 문장"},
        ]
    }
    decisions = model.select_explained("여행", [row(1), row(2)])
    assert decisions["1"]["category"] == "direct_answer"
    assert decisions["2"]["category"] == "unverified_selection"


def test_direct_and_counter_evidence_outrank_background():
    background, direct, counter = row(1), row(2), row(3)
    for record, category in [
        (background, "supporting_context"),
        (direct, "direct_answer"),
        (counter, "conflicting_evidence"),
    ]:
        record["search_explanation"] = {"model_assessment": {"category": category}}
    assert {r["id"] for r in select_evidence([background, direct, counter], 2)} == {"2", "3"}


def test_service_propagates_model_assessment():
    svc = service([row(1), row(2)])
    svc.models.select_explained = lambda *args: {
        "1": {"category": "direct_answer", "quote": "제주 여행"},
        "2": {"category": "irrelevant", "quote": ""},
    }
    _, result = svc._search("제주 여행", today="2026-10-19")
    assert [r["id"] for r in result["results"]] == ["1"]
    assert result["results"][0]["search_explanation"]["model_assessment"]["quote"] == "제주 여행"
    assert (
        next(r for r in result["search_audit"]["candidates"] if r["id"] == "2")["reason"]
        == "irrelevant"
    )


def test_chat_defers_eight_record_limit_until_all_queries_are_combined():
    svc = service([row(i) for i in range(12)])
    _, normal = svc._search("제주 여행", today="2026-10-19")
    _, deferred = svc._search("제주 여행", today="2026-10-19", defer_limit=True)
    assert len(normal["results"]) == 8
    assert len(deferred["results"]) == 12
    assert len(combine([deferred["results"]])) == 8
    excluded = [r for r in normal["search_audit"]["candidates"] if r["status"] == "excluded"]
    assert len(excluded) == 4
    assert all(r["stages"]["conditions"]["status"] == "passed" for r in excluded)
    assert all(r["stages"]["selection"] == {"status": "excluded", "reason": "evidence_limit", "limit": 8} for r in excluded)




