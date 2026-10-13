from datetime import datetime, timedelta, timezone

import numpy as np
import pytest
from conftest import memory

from pma.errors import AppError
from pma.lock import DataLock
from pma.service import Service


def test_save_extract_edit_and_revert(store, models, settings):
    service = Service(store, models, settings)
    first = store.create("담당자를 정했다.", None)
    service.run_one()
    assert store.get(first["record_id"])["status"] == "ready"
    assert len(store.snapshot(settings.embedding_key)[1]) == 1
    store.update(first["record_id"], 1, "다시 정했다.")
    assert store.snapshot(settings.embedding_key)[1] == []
    service.run_one()
    assert len(store.revisions(first["record_id"])) == 2
    store.update(first["record_id"], 2, revert_version=1)
    assert store.get(first["record_id"])["text"] == "담당자를 정했다."
    assert store.get(first["record_id"])["version"] == 3


def test_stale_job_cannot_publish_or_fail_new_version(store, settings):
    rid = store.create("담당자를 정했다.", None)["record_id"]
    stale = store.claim()
    store.update(rid, 1, "새 원문")
    assert not store.publish(stale, [memory()], np.array([[1, 0, 0]]), settings.embedding_key, {})
    store.fail(stale, "OLD_ERROR")
    assert store.get(rid)["status"] == "queued"


def test_version_conflict_preserves_source(store):
    rid = store.create("원문", None)["record_id"]
    with pytest.raises(AppError) as exc:
        store.update(rid, 2, "다른 내용")
    assert exc.value.status == 409
    assert store.get(rid)["text"] == "원문"


def test_trash_restore_purge_cascades(store, models, settings):
    service = Service(store, models, settings)
    rid = store.create("담당자를 정했다.", None)["record_id"]
    service.run_one()
    store.trash(rid)
    assert store.snapshot(settings.embedding_key)[1] == []
    assert store.get(rid)["memories"] == []
    store.restore(rid)
    assert store.get(rid)["status"] == "queued"
    service.run_one()
    store.trash(rid)
    store.purge(rid)
    with store.connect() as db:
        for table in ("records", "revisions", "jobs", "memories", "evidence", "embeddings"):
            assert db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0


def test_exact_expiration_and_restart(store):
    t = datetime(2026, 1, 1, tzinfo=timezone.utc)
    store.clock = lambda: t.isoformat()
    rid = store.create("개인 기록", None)["record_id"]
    store.trash(rid)
    t += timedelta(days=30, microseconds=-1)
    assert store.expire() == 0
    t += timedelta(microseconds=1)
    assert store.expire() == 1
    with pytest.raises(AppError):
        store.restore(rid)


def test_failure_retains_source_and_retry_deduplicates(store, models, settings):
    models.failure = ValueError("sensitive model content")
    rid = store.create("개인 원문", None)["record_id"]
    service = Service(store, models, settings)
    service.run_one()
    assert store.get(rid)["status"] == "failed"
    assert store.get(rid)["text"] == "개인 원문"
    assert store.get(rid)["error_code"] == "INTERNAL_PROCESSING_ERROR"
    assert store.retry(rid)["job_id"] == store.retry(rid)["job_id"]


def test_recover_invalidates_old_claim_token(store, settings):
    store.create("담당자를 정했다.", None)
    old = store.claim()
    store.recover()
    fresh = store.claim()
    assert old["token"] != fresh["token"]
    assert not store.publish(old, [], [], settings.embedding_key, {})
    assert store.publish(fresh, [], [], settings.embedding_key, {})


def test_bad_evidence_rolls_back_entire_publish(store, settings):
    rid = store.create("원문", None)["record_id"]
    job = store.claim()
    with pytest.raises(ValueError):
        store.publish(job, [memory("없는 인용")], np.array([[1, 0, 0]]), settings.embedding_key, {})
    assert store.get(rid)["memories"] == []


def test_empty_memories_are_distinct_state(store, models, settings):
    models.empty = True
    rid = store.create("아무 내용", None)["record_id"]
    Service(store, models, settings).run_one()
    assert store.get(rid)["status"] == "ready_empty"


def test_single_process_data_lock(tmp_path):
    with DataLock(tmp_path / "lock"):
        with pytest.raises(RuntimeError):
            with DataLock(tmp_path / "lock"):
                pass
    with DataLock(tmp_path / "lock"):
        pass
