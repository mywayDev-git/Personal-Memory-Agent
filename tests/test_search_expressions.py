import numpy as np
import pytest
from test_search_explain import row, service

from pma.chat.router import RetrievalRouter
from pma.search_explain import keyword_matches_batch, keyword_query, keyword_weight
from pma.search_expressions import (
    TOKEN,
    build_expansion,
    canonical_query,
    location_terms,
)

BASE = {"intent": "recall", "date_from": None, "date_to": None}


def edit(before, after, kind="translation", start=0):
    return {"before": before, "after": after, "kind": kind,
            "start": start, "end": start + len(before)}


@pytest.mark.parametrize("concept,variants", [
    ("python", ["Python", "파이썬", "파이선", "Ｐｙｔｈｏｎ"]),
    ("api", ["API", "에이피아이", "에이 피 아이", "ＡＰＩ"]),
    ("machine learning", ["machine learning", "머신러닝", "머신 러닝", "기계 학습"]),
    ("deep learning", ["deep learning", "딥러닝", "딥 러닝", "심층 학습", "심층학습"]),
])
def test_aliases_are_symmetric_and_duplicate_terms_do_not_add_scores(concept, variants):
    records = [row(i, "😀 " + variant + " 공부") for i, variant in enumerate(variants)]
    search = service(records)
    search.models.embed = lambda queries: [[1, 0] for _ in queries]
    signatures = []
    for query in variants + [" ".join(variants)]:
        terms, vocabulary = keyword_query(query, records)
        assert len(terms) == 1 and terms[0]["normalized"] == concept
        for record, found in zip(records, keyword_matches_batch(records, terms, vocabulary)):
            assert found and max(map(keyword_weight, found)) == 1
            assert all(record["text"][m["start"]:m["end"]] == m["quote"] for m in found)
        _, result = search._search(query)
        signatures.append([(r["id"], r["score"]) for r in result["results"]])
    assert all(signature == signatures[0] for signature in signatures)


@pytest.mark.parametrize("query,expected", [
    ("파이썬으로도", "python으로도"), ("파이선에서는", "python에서는"),
    ("에이 피 아이를", "api를"), ("머신 러닝으로", "machine learning으로"),
    ("기계  학습", "machine learning"),
])
def test_canonical_queries_preserve_particles(query, expected):
    assert canonical_query(query) == expected
    terms, _ = keyword_query(query, [])
    assert len(terms) == 1


@pytest.mark.parametrize("query,other", [
    ("C++", "C#"), ("C", "C++"), ("C#", "C"), (".NET", "net"),
    ("Node.js", "node js"), ("python", "pythonista"), ("파이썬", "파이썬입문"),
    ("API", "happy"), ("C++", "C+++"),
])
def test_distinct_identifiers_do_not_match(query, other):
    records = [row(1, other)]
    terms, vocabulary = keyword_query(query, records)
    assert keyword_matches_batch(records, terms, vocabulary) == [[]]


def test_symbol_and_fullwidth_spans():
    text = "😀 Ｃ＋＋ Ｃ＃ ．ＮＥＴ Ｎｏｄｅ．ｊｓ 에이 피 아이"
    assert TOKEN.findall(text) == ["Ｃ＋＋", "Ｃ＃", "．ＮＥＴ", "Ｎｏｄｅ．ｊｓ", "에이 피 아이"]
    records = [row(1, text)]
    terms, vocabulary = keyword_query("c++ c# .net node.js api", records)
    found = keyword_matches_batch(records, terms, vocabulary)[0]
    assert len(found) == 10
    assert all(text[m["start"]:m["end"]] == m["quote"] for m in found)


def test_location_and_routing_share_alias_policy():
    records = [row(1, "Python 공부")]
    records[0]["fact"].update(relation="other", object_key="python")
    assert location_terms("파이썬에서 공부", records) == []
    assert location_terms("회의에서 공부", records) == []
    assert location_terms("서울에서 여행", records) == ["서울"]
    assert location_terms("제주에서 공부", [row(2)]) == ["제주"]
    router = RetrievalRouter()
    assert {router.decide(q + " 설명해줘").mode for q in ("파이썬", "파이선", "Python")} == {"CHAT_ONLY"}
    _, result = service(records)._search("파이썬에서 공부")
    assert result["results"]


@pytest.mark.parametrize("question,change,reason", [
    ("Java", edit("Java", "자바섬"), "ambiguous_expression"),
    ("코드", edit("코드", "cord"), "ambiguous_expression"),
    ("code", edit("code", "chord"), "ambiguous_expression"),
    ("민수", edit("민수", "Minsu"), "protected_entity"),
    ("제주", edit("제주", "Jeju"), "protected_entity"),
    ("안", edit("안", "yes"), "protected_expression"),
    ("취소", edit("취소", "완료"), "protected_expression"),
    ("10월", edit("10월", "October"), "protected_expression"),
    ("학습은", edit("학습", "learning"), "partial_word"),
    ("학습", edit("학습", "学習"), "protected_expression"),
    ("학습", edit("자료", "learning"), "invalid_span"),
])
def test_expansion_rejects_constraints_and_ambiguous_or_invalid_edits(question, change, reason):
    record = row(1)
    record["fact"]["actor"] = "민수"
    result = build_expansion(question, [change], [record], BASE)
    assert result["status"] == "rejected" and result["rejected"][0]["reason"] == reason


def test_expansion_limits_weights_duplicates_and_context():
    question = "쿠버네티스 학습"
    edits = [edit("쿠버네티스", "Kubernetes", "transliteration"),
             edit("학습", "공부", "similar", 6), edit("학습", "learning", start=6)]
    result = build_expansion(question, edits, [], BASE)
    assert [item["weight"] for item in result["queries"]] == [0.8, 0.5]
    assert result["rejected"][0]["reason"] == "query_limit"
    assert build_expansion("파이썬", [edit("파이썬", "Python")], [], BASE)["queries"] == []
    assert build_expansion("코드 리뷰", [edit("코드", "code")], [], BASE)["status"] == "applied"


def test_unique_original_quote_can_resolve_model_offsets_but_repeated_quotes_cannot():
    result = build_expansion("😀 쿠버네티스 배포", [edit("쿠버네티스", "Kubernetes", start=3)], [], BASE)
    assert result["status"] == "applied"
    assert result["edits"][0]["start"] == 2
    assert result["edits"][0]["span_source"] == "unique_quote"
    result = build_expansion("학습 학습", [edit("학습", "learning", start=1)], [], BASE)
    assert result["status"] == "rejected"


def test_translation_must_change_language_and_original_only_disables_generated_queries():
    result = build_expansion("Kubernetes 내용", [edit("Kubernetes 내용", "Kubernetes 자료")], [], BASE)
    assert result["rejected"][0]["reason"] == "language_mismatch"
    assert build_expansion("API gateway", [edit("API gateway", "API 게이트웨이")], [], BASE)["status"] == "applied"
    svc, calls = expanded_service([row(1)], [edit("학습", "learning")])
    _, result = svc._search("학습", correction_enabled=False)
    assert calls == [["학습"]] and result["query_expansion"]["reason"] == "disabled"


@pytest.mark.parametrize("question,after,accepted", [
    ("코드 리뷰", "code", True), ("코드 리뷰", "chord", False),
    ("코드 진행", "chord", True), ("코드 진행", "code", False),
    ("코드 전선", "cord", True), ("코드 전선", "code", False),
    ("코드 여행", "code", False), ("코드 리뷰 음악", "code", False),
    ("Java 개발", "자바섬", False), ("Java 개발", "자바", True),
])
def test_ambiguous_translation_agrees_with_specific_context(question, after, accepted):
    before = "Java" if question.startswith("Java") else "코드"
    result = build_expansion(question, [edit(before, after)], [], BASE)
    assert (result["status"] == "applied") == accepted


def expanded_service(records, changes):
    svc = service(records)
    svc.models.understand = lambda *args: {**BASE, "expansions": changes}
    calls = []
    def embed(queries):
        calls.append(queries)
        return [[1, 0] for _ in queries]
    svc.models.embed = embed
    return svc, calls


def test_expansion_runs_in_one_batch_and_keeps_original_conditions_and_selection():
    records = [row(1, "Kubernetes 공부"), row(2, "Kubernetes 공부")]
    records[1]["fact"]["event_time"]["start"] = "2020-01-01"
    svc, calls = expanded_service(records, [edit("쿠버네티스", "Kubernetes", "transliteration")])
    selected_questions = []
    svc.models.select = lambda q, rows: selected_questions.append(q) or [r["id"] for r in rows]
    _, result = svc._search("쿠버네티스", {"date_from": "2026-01-01"}, "2026-10-19")
    assert calls == [["쿠버네티스", "kubernetes"]]
    assert selected_questions == ["쿠버네티스"]
    assert [r["id"] for r in result["results"]] == ["1"]
    info = result["results"][0]["search_explanation"]["query_expansion"]
    assert info["searched"] and info["retrieval"][0]["contributed"]
    assert info["retrieval"][0]["keyword_matches"]


def test_expansion_embedding_failure_and_empty_candidates_keep_original():
    svc, calls = expanded_service([row(1)], [edit("학습", "learning")])
    def failing(queries):
        calls.append(queries)
        if len(queries) > 1:
            raise ValueError("alternate failed")
        return [[1, 0]]
    svc.models.embed = failing
    _, result = svc._search("학습")
    assert calls == [["학습", "learning"], ["학습"]]
    assert result["results"] and not result["query_expansion"]["searched"]
    assert result["query_expansion"]["reason"] == "embedding_failed"
    svc, calls = expanded_service([], [edit("학습", "learning")])
    _, result = svc._search("학습")
    assert not calls and not result["query_expansion"]["searched"]


def test_malformed_expansion_preserves_date_analysis():
    svc, _ = expanded_service([row(1)], "bad")
    svc.models.understand = lambda *args: {**BASE, "date_from": "2026-01-01", "expansions": "bad"}
    _, result = svc._search("2026-01-01 이후 학습")
    assert result["filters"]["date_from"] == "2026-01-01"
    assert result["query_expansion"]["reason"] == "invalid_expansions"


def test_local_model_decoder_requires_expansion_but_bad_optional_data_preserves_intent(monkeypatch):
    import json

    import pma.models as module
    from pma.settings import AppSettings

    model = module.LocalModels(AppSettings())
    model.budget = lambda *args: None
    seen = []
    def chat(*args, **kwargs):
        seen.append(kwargs["output_schema"])
        return json.dumps({**BASE, "date_from": "2026-01-01", "expansions": "bad"}), None, None
    monkeypatch.setattr(module, "chat", chat)
    result = model.understand("학습", "2026-10-19")
    assert "expansions" in seen[0]["required"]
    assert result["date_from"] == "2026-01-01"
    assert result["expansions"] == [] and result["expansions_invalid"]


def test_fixed_evaluation_set_contains_60_positive_and_30_contrast_cases():
    from evaluation.multilingual_cases import dataset
    documents, cases = dataset()
    assert sum(c["group"] == "positive" for c in cases) == 60
    assert sum(c["group"] == "negative" for c in cases) == 30
    assert len({c["id"] for c in cases}) == 90
    topics = {d["topic"] for d in documents}
    assert all(set(case["topics"]) <= topics for case in cases)


def test_expanded_only_semantic_candidates_receive_bounded_nonadditive_contribution():
    records = [row(i, ("unrelated " if i < 20 else "learning ") + str(i)) for i in range(25)]
    for r in records:
        r["fact"].update(relation="other", object_key="learning")
        r["vector"] = np.array([1, 0] if int(r["id"]) < 20 else [0, 1], dtype="<f4").tobytes()
    svc, _ = expanded_service(records, [edit("학습", "learning"), edit("학습", "studying", "similar")])
    svc.models.embed = lambda queries: [[1, 0]] + [[0, 1] for _ in queries[1:]]
    _, first = svc._search("학습")
    score = next(r["score"] for r in first["results"] if r["id"] == "20")
    assert score <= 2 * 0.8 / 61
    svc.models.understand = lambda *args: {**BASE, "expansions": [edit("학습", "learning")]}
    _, second = svc._search("학습")
    assert score == next(r["score"] for r in second["results"] if r["id"] == "20")
