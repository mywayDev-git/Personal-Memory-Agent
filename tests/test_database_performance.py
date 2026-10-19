import json
from contextlib import contextmanager
from types import SimpleNamespace

import numpy as np
import pytest
from test_search_explain import row

from evaluation.database_benchmark import seed
from evaluation.database_reference import Store as ReferenceStore
from pma.search_explain import keyword_matches, keyword_query
from pma.service import Service
from pma.store import Store


def test_evidence_batches_keep_order_and_isolation(tmp_path):
    path = tmp_path / "synthetic.db"
    seed(path, 1005, dimensions=2)
    store = Store(path)
    statements = []
    original_connect = store.connect

    @contextmanager
    def observed(*args, **kwargs):
        with original_connect(*args, **kwargs) as db:
            db.set_trace_callback(statements.append)
            yield db

    store.connect = observed
    generation, rows = store.snapshot("synthetic")
    assert (generation, rows) == ReferenceStore(path).snapshot("synthetic")
    evidence_queries = [sql for sql in statements if "SELECT memory_id,quote,start,end" in sql]
    assert len(evidence_queries) == 2
    assert rows[0]["id"] == "m00000001"  # row zero is archived
    for item in rows:
        assert len(item["evidence"]) == 1 + (int(item["id"][1:]) % 3 == 0)
    rows[0]["evidence"][0]["quote"] = "mutated"
    assert store.snapshot("synthetic")[1][0]["evidence"][0]["quote"] != "mutated"
    assert generation == store.snapshot("synthetic")[0]


def test_archive_owner_null_and_version_semantics(tmp_path):
    path = tmp_path / "synthetic.db"
    seed(path, 4, dimensions=2)
    store = Store(path)
    with store.connect(True) as db:
        db.execute("DELETE FROM captured_memories")
        for identifier, owner, rid, payload in [
            ("a", "local-account", "r00000000", {"record_version": 1, "lifecycle_status": "archived"}),
            ("b", "other", "r00000001", {}),
            ("c", "local-account", "r00000002", {"record_version": 0, "lifecycle_status": "archived"}),
            ("d", "local-account", "r00000003", {"lifecycle_status": "archived"}),
            # Duplicate exclusions must not duplicate included rows.
            ("e", "other2", "r00000001", {}),
        ]:
            db.execute("INSERT INTO captured_memories VALUES(?,?,?,?)", (identifier, owner, rid, json.dumps(payload)))
        store.bump(db)
    assert [r["id"] for r in store.snapshot("synthetic")[1]] == ["m00000001", "m00000002", "m00000003"]
    assert [r["id"] for r in store.snapshot_for_owner("synthetic", "local-account")[1]] == ["m00000002", "m00000003"]
    for owner in (None, "local-account", "other"):
        assert store.snapshot("synthetic", owner_id=owner) == ReferenceStore(path).snapshot(
            "synthetic", owner_id=owner)


def test_empty_snapshot_and_unknown_model(tmp_path):
    path = tmp_path / "synthetic.db"
    store = Store(path)
    assert store.snapshot("synthetic") == (0, [])
    seed_path = tmp_path / "seed.db"
    seed(seed_path, 3, dimensions=2)
    assert Store(seed_path).snapshot("unknown")[1] == []


def test_vector_cache_generation_model_order_subset_and_budget():
    settings = SimpleNamespace(embedding_key="first", embedding_dimensions=2)
    svc = Service(None, None, settings)
    rows = [row(1), row(2)]
    first = svc._candidate_matrix(1, rows)
    assert svc._candidate_matrix(1, rows) is first
    assert not first.flags.writeable
    for generation, candidates in [(2, rows), (2, rows[::-1]), (2, rows[:1])]:
        newer = svc._candidate_matrix(generation, candidates)
        assert newer is not first
        first = newer
    settings.embedding_key = "second"
    assert svc._candidate_matrix(2, rows[:1]) is not first
    svc.vector_cache_bytes = 0
    svc._candidate_matrix(3, rows)
    assert svc._vector_cache is None
    rows[0]["vector"] = np.array([float("nan"), 0], dtype="<f4").tobytes()
    with pytest.raises(ValueError, match="INVALID_EMBEDDING"):
        svc._candidate_matrix(4, rows)
    assert svc._vector_cache is None


def test_cached_search_after_edit_trash_and_model_change(tmp_path):
    path = tmp_path / "synthetic.db"
    seed(path, 3, dimensions=2)
    store = Store(path)
    models = SimpleNamespace(
        understand=lambda *a: dict(intent="recall", date_from=None, date_to=None),
        embed=lambda texts: [[1, 0] for _ in texts],
        select=lambda q, rows: [r["id"] for r in rows])
    svc = Service(store, models, SimpleNamespace(embedding_key="synthetic", embedding_dimensions=2))
    def ids():
        return {r["record_id"] for r in svc._search("제주 여행", today="2026-10-19")[1]["results"]}
    assert ids() == {"r00000001", "r00000002"}
    assert ids() == {"r00000001", "r00000002"}
    store.update("r00000001", 1, text="수정한 합성 기록")
    assert ids() == {"r00000002"}
    store.trash("r00000002")
    assert ids() == set()
    svc.settings.embedding_key = "different"
    assert ids() == set()


def test_keyword_cache_preserves_offsets_negation_and_vocabulary():
    records = [row(1, "😀 제주에 갔다. 여행은 취소하지 않았다. 고양이 API 수 밤"), row(2)]
    terms, vocabulary = keyword_query("제주 여행 취소하지 고양이 api 수", records)
    cache = {}
    for record in records:
        assert keyword_matches(record, terms, vocabulary) == keyword_matches(
            record, terms, vocabulary, normalization_cache=cache)
    assert len(cache) <= 16384
