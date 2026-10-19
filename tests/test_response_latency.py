import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from pma.chat.engine import ChatEngine
from pma.chat.store import ChatStore
from pma.service import Service
from pma.settings import AppSettings
from pma.store import Store
from scripts.memory_agent import performance
from scripts.memory_agent.llm_client import post_json, request_budget, token_count
from scripts.memory_agent.performance import count, measure, profile_request


def test_nested_times_are_exclusive_and_live_snapshot_does_not_mutate(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(performance.time, "perf_counter", lambda: now[0])
    with profile_request() as profile:
        with measure("parent"):
            now[0] = 2.0
            with measure("child"):
                now[0] = 5.0
                live = profile.snapshot()
                assert sum(s["exclusive_seconds"] for s in live["stages"].values()) == 5
                assert profile.stages == {}
            now[0] = 7.0
        count("search_iterations")
    result = profile.snapshot()
    assert result["stages"]["parent"]["inclusive_seconds"] == 7
    assert result["stages"]["parent"]["exclusive_seconds"] == 4
    assert result["stages"]["child"]["exclusive_seconds"] == 3
    assert result["counts"] == {"search_iterations": 1}
    with profile_request() as other:
        assert other.snapshot()["counts"] == {}


def test_failure_measurement_never_includes_exception_or_request_text():
    with profile_request() as profile:
        with pytest.raises(ValueError):
            with measure("generation"):
                raise ValueError("PRIVATE SOURCE")
    result = profile.snapshot("failed")
    assert result["stages"]["generation"]["failures"] == 1
    assert "PRIVATE" not in json.dumps(result)


def test_transport_usage_is_allowlisted():
    payload = {"usage": {"prompt_tokens": 12, "completion_tokens": 3,
                         "total_tokens": 15, "private": "SECRET"}, "text": "SECRET"}
    session = SimpleNamespace(post=lambda *a, **k: SimpleNamespace(status_code=200, json=lambda: payload))
    with request_budget(10) as budget:
        assert post_json(session, "http://127.0.0.1:1234/v1/chat/completions", {}, 10) == payload
    assert budget.calls[0]["usage"] == {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15}
    assert "SECRET" not in json.dumps(budget.calls)


def test_failed_request_persists_profile_without_source_text(tmp_path):
    settings = AppSettings(data_dir=tmp_path)
    models = SimpleNamespace(count_tokens=lambda _: 1,
                             structured=lambda *a, **k: (_ for _ in ()).throw(ValueError("SECRET")))
    engine = ChatEngine(Service(Store(tmp_path / "synthetic.db"), models, settings))
    sid = engine.store.create_empty()["id"]
    with pytest.raises(ValueError):
        engine.message(sid, "failed", "안녕")
    message = engine.store.get(sid)["messages"][-1]
    assert message["snapshot"]["performance"]["profile"]["outcome"] == "failed"
    assert "SECRET" not in json.dumps(message["snapshot"])
    # Retry uses the existing message and must be able to write a fresh snapshot.
    mid, _ = engine.store.begin(sid, "failed", "안녕")
    engine.store.fail(mid, "MODEL_FAILED", performance={"profile": {"outcome": "failed"}})
    assert ChatStore(engine.service.store).get(sid)["messages"][-1]["state"] == "failed"


def test_token_cache_is_exact_bounded_and_request_local():
    calls = []
    def post(*args, **kwargs):
        calls.append(kwargs["json"])
        return SimpleNamespace(status_code=200, json=lambda: {"tokens": [1, 2, 3]})
    session = SimpleNamespace(post=post)
    def read(text="private", special=False, identity="v1"):
        return token_count(session, "http://127.0.0.1:1234/tokenize", text, 10,
                           add_special=special, cache=True, identity=identity)
    with request_budget(10) as budget:
        assert read() == read() == 3
        assert len(calls) == 1
        read(special=True)
        read(identity="v2")
        assert len(calls) == 3
        for index in range(150):
            read(str(index))
        assert len(budget.token_counts) == 128
        assert "private" not in repr(budget.token_counts)
    with request_budget(10):
        read()
    assert len(calls) == 154


@pytest.mark.parametrize("batch_size", [4, 8])
def test_selection_batches_review_every_candidate_without_truncating_sources(batch_size):
    from pma.models import LocalModels

    settings = replace(AppSettings(), selection_batch_size=batch_size)
    models = LocalModels(settings)
    evidence = [{"id": str(i), "source_text": f"원문 {i}", "content": f"원문 {i}"}
                for i in range(17)]
    seen = []
    def structured(prompt, data, schema, max_tokens=None):
        rows = data["evidence"]
        seen.extend(row["id"] for row in rows)
        return {"items": [{"id": row["id"], "category": "direct_answer", "quote": row["source_context"]}
                          for row in rows]}
    models.structured = structured
    result = models.select_explained("무엇?", evidence)
    assert set(result) == set(seen) == {row["id"] for row in evidence}
    assert len(seen) == 17


def test_plain_presentation_preserves_fact_policy_and_independent_review(monkeypatch):
    from pma.chat.models import FACT_POLICY, ChatLocalModels
    from pma.models import LocalModels

    models = ChatLocalModels(replace(AppSettings(), chat_presentation="plain"))
    observed = []
    def structured(self, prompt, data, schema, max_tokens=None):
        observed.append((prompt, data, schema))
        return {}
    monkeypatch.setattr(LocalModels, "structured", structured)
    schema = {"properties": {}, "required": []}
    models.structured("generation", {"question": "파이썬 공부?", "evidence": [], "feedback": None}, schema)
    assert FACT_POLICY in observed[-1][0]
    assert "display" not in observed[-1][2]["properties"]
    models.structured("review", {"question": "파이썬 공부?", "proposed_answer": {"items": []}}, schema)
    assert "기억 대화 필수 정책" in observed[-1][0]


def test_embedding_profile_separates_index_and_only_prefixes_queries(monkeypatch):
    from pma.models import LocalModels

    settings = replace(AppSettings(), embedding_revision="a" * 64)
    alternate = replace(settings, embedding_profile="qwen3-retrieval-v1")
    assert settings.embedding_key == f"bge-m3:{'a' * 64}:1024"
    assert alternate.embedding_key != settings.embedding_key
    sent = []
    def post(session, endpoint, body, timeout):
        sent.append(body["input"])
        return {"data": [{"index": i, "embedding": [1.0] * 1024} for i in range(len(body["input"]))]}
    monkeypatch.setattr("pma.models.post_json", post)
    monkeypatch.setattr(LocalModels, "budget", lambda *a, **kw: None)
    models = LocalModels(alternate)
    models.embed(["document"])
    models.embed_queries(["question"])
    assert sent[0] == ["document"]
    assert sent[1][0].startswith("Instruct: ")
    assert sent[1][0].endswith("\nQuery: question")


def test_benchmark_quality_requires_current_message_citation_source():
    from evaluation.response_latency import quality, summary

    case = {"gold": ["gift"]}
    response = {"status": "answered", "validation": "model_checked", "citation_details": [
        {"memory_id": "m", "record_id": "r", "start": 0, "end": 2, "quote": "원문"}]}
    evidence = [{"id": "m", "record_id": "r", "source_text": "원문"}]
    assert quality(case, response, evidence, {"r": "gift"})["passed"]
    assert not quality(case, response, [], {"r": "gift"})["passed"]
    result = summary([{"seconds": 1, "warmup": False, "quality": {"passed": True}},
                      {"seconds": .1, "warmup": False, "error_code": "FAILED"},
                      {"seconds": 100, "warmup": True}])
    assert result["median_seconds"] == 1 and result["failure_rate"] == .5


def test_benchmark_seed_covers_real_search_fields(tmp_path):
    from evaluation.response_latency import DOCUMENTS, seed_database

    settings = replace(AppSettings(), embedding_dimensions=2)
    path = tmp_path / "synthetic.db"
    seed_database(path, SimpleNamespace(embed=lambda texts: [[1., 0.]] * len(texts)), settings)
    models = SimpleNamespace(understand=lambda *a: {"intent": "recall", "date_from": None, "date_to": None},
                             embed=lambda texts: [[1., 0.]] * len(texts))
    result = Service(Store(path), models, settings).search("민수에게 무엇을 선물했어?", today="2026-10-19")
    assert len(DOCUMENTS) == 11 and result["results"]


def test_timing_gate_requires_twenty_quality_checked_samples():
    from evaluation.response_latency_report import latency_gate

    baseline = {"samples": 20, "quality_passes": 20, "failures": 0, "median_seconds": 10, "p95_seconds": 12}
    candidate = {**baseline, "median_seconds": 7, "p95_seconds": 10}
    assert latency_gate(baseline, candidate)["passed"]
    assert not latency_gate(baseline, {**candidate, "samples": 5})["passed"]
    assert not latency_gate(baseline, {**candidate, "quality_passes": 19})["passed"]
    assert not latency_gate(baseline, {**candidate, "p95_seconds": 13})["passed"]


def test_current_path_multilingual_comparison_uses_fresh_understanding(tmp_path, monkeypatch):
    from evaluation import multilingual_search as evaluation

    understood = []
    class Models:
        def __init__(self, settings):
            pass
        def embed(self, texts):
            return [[1., 0.]] * len(texts)
        embed_queries = embed
        def understand(self, question, today, *, expand):
            understood.append(expand)
            return {"intent": "recall", "date_from": None, "date_to": None}
    monkeypatch.setattr(evaluation, "LocalModels", Models)
    monkeypatch.setattr(evaluation, "dataset", lambda: (
        [{"id": "one", "text": "Python 공부", "topic": "python"}],
        [{"id": "test", "question": "파이썬 공부", "topics": ["python"], "group": "positive"}]))
    report = evaluation.evaluate(replace(AppSettings(), embedding_dimensions=2), tmp_path / "result.json", current_only=True)
    assert understood == [True]
    assert not report["replayed_model_outputs"]
    assert report["evaluated_modes"] == ["expanded"]
    assert "baseline" not in report["cases"][0]


def test_model_comparison_reuses_source_ids_and_only_rebuilds_vectors(tmp_path):
    import numpy as np

    from evaluation.response_latency import seed_database

    settings = replace(AppSettings(), embedding_dimensions=2)
    models = SimpleNamespace(embed=lambda texts: np.asarray([[1., 0.]] * len(texts)))
    first, repeated, alternate = (tmp_path / name for name in ("first.db", "repeat.db", "alternate.db"))
    original_keys = seed_database(first, models, settings)
    assert seed_database(repeated, models, settings) == original_keys
    changed_settings = replace(settings, embedding_profile="qwen3-retrieval-v1")
    assert seed_database(alternate, models, changed_settings, template=first) == original_keys
    for table, columns in (("revisions", "id,text,created_at"), ("memories", "id,payload"), ("evidence", "memory_id,quote,start,end")):
        with Store(first).connect() as a, Store(alternate).connect() as b:
            assert [tuple(r) for r in a.execute(f"SELECT {columns} FROM {table} ORDER BY 1")] == [tuple(r) for r in b.execute(f"SELECT {columns} FROM {table} ORDER BY 1")]
    with Store(alternate).connect() as db:
        assert {r[0] for r in db.execute("SELECT DISTINCT model_key FROM embeddings")} == {changed_settings.embedding_key}
