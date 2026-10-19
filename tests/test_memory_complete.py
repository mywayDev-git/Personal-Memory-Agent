from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from pma.errors import AppError
from pma.memory.api import OWNER
from pma.memory.conflict_resolver import DIMENSIONS, protect
from pma.memory.manager import MemoryCaptureManager
from pma.memory.repository import MemoryRepository
from pma.store import Store


def judgment(relation, left, right):
    return dict(
        relation=relation,
        candidate_quote=left,
        existing_quote=right,
        reason="비교",
        **{k: True for k in DIMENSIONS},
    )


@pytest.mark.parametrize(
    "left,right,kind,expected",
    [
        ("2026년 1월 2일 민수를 만났다", "2026년 1월 1일 민수를 만났다", "event", "needs_review"),
        ("민수가 영희에게 선물을 주었다", "영희가 민수에게 선물을 주었다", "event", "unrelated"),
        ("선물을 주지 않았다", "선물을 주었다", "event", "needs_review"),
        ("캐시를 도입할 계획이다", "캐시를 도입했다", "plan", "complementary"),
    ],
)
def test_semantic_guards(left, right, kind, expected):
    candidate = dict(content=left, memory_type=kind, epistemic_status="user_reported")
    row = dict(
        memory_id="old",
        record_version=1,
        content=right,
        memory_type="event",
        epistemic_status="user_reported",
    )
    assert (
        protect(candidate, row, judgment("semantic_duplicate", left, right))["relation"] == expected
    )


def service_for(relation="complementary", fail=False):
    def structured(prompt, data, schema, **kwargs):
        if fail:
            raise RuntimeError("offline")
        return {
            "comparisons": [
                dict(
                    judgment(relation, data["candidate"]["content"], r["content"]),
                    memory_id=r["memory_id"],
                )
                for r in data["records"]
            ]
        }

    return SimpleNamespace(
        settings=SimpleNamespace(chat_timeout=10),
        model_slot=lambda **kw: nullcontext(),
        models=SimpleNamespace(structured=structured),
    )


def test_review_links_edit_invalidation_and_idempotency(tmp_path):
    manager = MemoryCaptureManager(Store(tmp_path / "memory.db"), service_for())
    old = saved(manager.repo, "캐시를 도입하기로 했다")
    c = manager.repo.propose(OWNER, content="캐시 구현 담당자는 민수다")
    review = manager.review(OWNER, c["candidate_id"])
    args = dict(
        approved=True,
        request_id="save",
        review_id=review["review_id"],
        resolution="add_confirmed",
        link_memory_ids=[old["memory_id"]],
    )
    with pytest.raises(AppError, match="REVIEW_CHANGED"):
        manager.commit(OWNER, c["candidate_id"], content="다른 내용", **args)
    result = manager.commit(OWNER, c["candidate_id"], **args)
    assert result["related_memories"][0]["relation"] == "complementary"
    assert manager.commit(OWNER, c["candidate_id"], **args)["memory_id"] == result["memory_id"]


def test_failed_semantics_cannot_commit(tmp_path):
    manager = MemoryCaptureManager(Store(tmp_path / "memory.db"), service_for(fail=True))
    saved(manager.repo, "기존 기억")
    c = manager.repo.propose(OWNER, content="새로운 기억")
    review = manager.review(OWNER, c["candidate_id"])
    assert review["status"] == "failed"
    with pytest.raises(AppError, match="REVIEW_INCOMPLETE"):
        manager.commit(
            OWNER, c["candidate_id"], approved=True, request_id="bad", review_id=review["review_id"]
        )


def test_snapshot_change_rejects_approval(tmp_path):
    from pma.chat.store import ChatStore
    from pma.memory.api import from_messages

    store = Store(tmp_path / "memory.db")
    chat = ChatStore(store)
    sid = chat.create_empty()["id"]
    mid, _ = chat.begin(sid, "request", "민수를 만났다", mode="general")
    chat.finish(sid, mid, {"status": "answered", "items": [{"text": "확인", "citations": []}]}, [])
    repo = MemoryRepository(store)
    c = from_messages(repo, sid, [mid], "user_message")
    with store.connect(True) as db:
        db.execute("UPDATE chat_messages SET question=? WHERE id=?", ("영희를 만났다", mid))
    with pytest.raises(AppError, match="SOURCE_CHANGED"):
        repo.commit(OWNER, c["candidate_id"], approved=True, request_id="save")


def test_policy_and_archived_preference(tmp_path):
    repo = MemoryRepository(Store(tmp_path / "memory.db"))
    assert repo.policy(OWNER) == "MANUAL"
    repo.set_policy(OWNER, "SUGGEST")
    assert repo.policy(OWNER) == "SUGGEST"
    with pytest.raises(AppError):
        repo.set_policy(OWNER, "AUTO")
    item = saved(repo, "앞으로 한국어로 설명해줘")
    repo.archive(OWNER, item["memory_id"], 1)
    assert repo.preferences(OWNER) == []


def test_api_review_contract(tmp_path):
    from fastapi.testclient import TestClient

    from pma.chat.store import ChatStore
    from pma.settings import AppSettings
    from pma.web import create_app

    settings = AppSettings(data_dir=tmp_path)
    app = create_app(settings, models=service_for().models, run_worker=False)
    with TestClient(app, base_url=settings.origin) as client:
        auth = client.post(
            "/api/v1/session",
            headers={"Origin": settings.origin},
            json={"token": app.state.bootstrap_token},
        )
        headers = {"Origin": settings.origin, "X-CSRF-Token": auth.json()["csrf"]}
        chat = ChatStore(app.state.store)
        sid = chat.create_empty()["id"]
        mid, _ = chat.begin(sid, "seed", "캐시를 도입하기로 결정했다", mode="hybrid")
        chat.finish(
            sid, mid, {"status": "answered", "items": [{"text": "제안", "citations": []}]}, []
        )
        candidate = client.post(
            "/api/v1/memory/candidates",
            headers=headers,
            json={"session_id": sid, "message_ids": [mid], "source_type": "user_message"},
        ).json()
        path = "/api/v1/memory/candidates/" + candidate["candidate_id"]
        edit = {
            "content": "캐시를 도입하기로 결정했다. 아직 구현하지 않았다.",
            "memory_type": "project_decision",
            "project_scope": "테스트 프로젝트",
            "event_time": "2026-10-18",
        }
        review = client.post(path + "/review", headers=headers, json=edit)
        assert review.status_code == 200, review.text
        payload = dict(edit, approved=True, request_id="save", review_id=review.json()["review_id"])
        result = client.post(path + "/commit", headers=headers, json=payload)
        assert result.status_code == 202, result.text
        item = result.json()
        assert item["project_scope"] == "테스트 프로젝트"
        assert item["provenance"]["source_snapshots"][0]["text"] == "캐시를 도입하기로 결정했다"
        assert (
            client.post(path + "/commit", headers=headers, json=payload).json()["memory_id"]
            == item["memory_id"]
        )
        assert (
            client.put(
                "/api/v1/memory/policy", headers=headers, json={"policy": "AUTO"}
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/v1/memory/" + item["memory_id"] + "/archive",
                headers=headers,
                json={"expected_version": 1},
            ).status_code
            == 200
        )
        assert client.get("/api/v1/memory").json()["items"] == []


def test_inference_does_not_hold_write_transaction(tmp_path):
    store = Store(tmp_path / "memory.db")
    manager = MemoryCaptureManager(store, service_for())
    saved(manager.repo, "기존 기억")
    c = manager.repo.propose(OWNER, content="후보")
    original = manager.service.models.structured

    def concurrent_write(*args, **kwargs):
        saved(manager.repo, "동시에 추가된 기록")
        return original(*args, **kwargs)

    manager.service.models.structured = concurrent_write
    with pytest.raises(AppError, match="REVIEW_STALE"):
        manager.review(OWNER, c["candidate_id"])


def test_source_owner_and_migration_preserve_records(tmp_path):
    from pma.chat.store import ChatStore
    from pma.memory.api import from_messages

    store = Store(tmp_path / "memory.db")
    chat = ChatStore(store)
    sid = chat.create_empty(owner_id="other")["id"]
    chat = ChatStore(store, owner_id="other")
    mid, _ = chat.begin(sid, "r", "다른 소유자", mode="general")
    chat.finish(sid, mid, {"status": "answered", "items": [{"text": "답변", "citations": []}]}, [])
    with pytest.raises(AppError, match="SOURCE_OWNER_MISMATCH"):
        from_messages(MemoryRepository(store), sid, [mid], "user_message")
    existing = store.create("마이그레이션 보존 대상", None)
    reopened = Store(store.path)
    with reopened.connect() as db:
        assert (
            db.execute(
                "SELECT text FROM revisions WHERE record_id=?", (existing["record_id"],)
            ).fetchone()[0]
            == "마이그레이션 보존 대상"
        )


def test_natural_capture_response_retry_is_idempotent(tmp_path):
    from pma.chat.store import ChatStore
    from pma.memory.api import natural_candidates

    store = Store(tmp_path / "memory.db")
    chat = ChatStore(store)
    sid = chat.create_empty()["id"]
    text = "앞으로 한국어로 설명해줘. 기억해줘"
    mid, _ = chat.begin(sid, "r", text, mode="general")
    chat.finish(sid, mid, {"status": "answered", "items": [{"text": "답변", "citations": []}]}, [])
    first = natural_candidates(store, sid, mid, text, "general")[0]
    again = natural_candidates(store, sid, mid, text, "general")[0]
    assert first["candidate_id"] == again["candidate_id"]


@pytest.mark.parametrize(
    "text,kind,intent",
    [
        ("앞으로 코드를 한국어로 자세히 설명해줘. 기억해줘", "preference", True),
        ("캐시 도입을 결정했어", "project_decision", False),
        ("제주도에 영희와 갔다. 저장해줘", "event", True),
        ("그 기록은 민수가 아니라 영희야", "correction", True),
        ("내일 여행할 계획이야", "plan", False),
        ("아마 캐시가 필요할 것 같아", "hypothesis", False),
        ("오늘 날씨 어때?", "user_statement", False),
        ("안녕", "user_statement", False),
    ],
)
def test_capture_intent_and_type_cases(text, kind, intent):
    from pma.chat.memory_capture import capture_intent, classify

    assert classify(text) == kind
    assert capture_intent(text) == intent


def test_scope_separates_identical_words(tmp_path):
    manager = MemoryCaptureManager(Store(tmp_path / "memory.db"), service_for("semantic_duplicate"))
    saved(manager.repo, "캐시를 도입했다", project_scope="프로젝트 A")
    c = manager.repo.propose(OWNER, content="캐시를 도입했다", project_scope="프로젝트 B")
    review = manager.review(OWNER, c["candidate_id"])
    assert review["comparisons"][0]["relation"] == "unrelated"


def test_archived_record_stays_excluded_after_legacy_restore(tmp_path):
    repo = MemoryRepository(Store(tmp_path / "memory.db"))
    item = saved(repo, "보관된 사용자 선호", memory_type="preference")
    repo.archive(OWNER, item["memory_id"], 1)
    repo.store.trash(item["record_id"])
    repo.store.restore(item["record_id"])
    assert repo.get(OWNER, "record:" + item["record_id"])["lifecycle_status"] == "archived"
    with repo.store.connect() as db:
        assert repo.corpus(db, OWNER) == []
    assert repo.preferences(OWNER) == []
    assert repo.store.snapshot("unused")[1] == []


def test_extraction_rejects_fabricated_source(tmp_path):
    from pma.chat.store import ChatStore

    store = Store(tmp_path / "memory.db")
    chat = ChatStore(store)
    sid = chat.create_empty()["id"]
    mid, _ = chat.begin(sid, "r", "결정했다. 아직 구현하지 않았다.", mode="hybrid")
    chat.finish(sid, mid, {"status": "answered", "items": [{"text": "답변", "citations": []}]}, [])
    service = service_for()
    service.models.structured = lambda *args, **kwargs: {
        "items": [{"message_id": mid, "quote": "구현했다"}]
    }
    manager = MemoryCaptureManager(store, service)
    with pytest.raises(AppError, match="INVALID_EXTRACTION"):
        manager.extract(OWNER, sid)
    assert manager.repo.pending(OWNER)["items"] == []


def saved(repo, content, owner=OWNER, **kwargs):
    c = repo.propose(owner, content=content, **kwargs)
    return repo.commit(
        owner,
        c["candidate_id"],
        approved=True,
        request_id=c["candidate_id"],
        resolution="add_confirmed",
    )


def test_legacy_alias_cannot_read_another_owner(tmp_path):
    repo = MemoryRepository(Store(tmp_path / "memory.db"))
    other = saved(repo, "다른 사용자의 기록", owner="other")
    with pytest.raises(AppError):
        repo.get(OWNER, "record:" + other["record_id"])


def test_correction_preserves_ai_origin(tmp_path):
    repo = MemoryRepository(Store(tmp_path / "memory.db"))
    old = saved(repo, "캐시 도입을 제안합니다", source_type="assistant_message")
    candidate = repo.correct(OWNER, old["memory_id"], "분산 캐시 도입을 제안합니다", 1)
    assert candidate["epistemic_status"] == "ai_proposed"
    with pytest.raises(AppError):
        repo.commit(
            OWNER,
            candidate["candidate_id"],
            approved=True,
            request_id="escalate",
            resolution="correct",
            memory_type="event",
        )


def test_legacy_alias_preserves_registered_provenance(tmp_path):
    repo = MemoryRepository(Store(tmp_path / "memory.db"))
    old = saved(repo, "캐시를 제안합니다", source_type="assistant_message")
    alias = "record:" + old["record_id"]
    assert repo.get(OWNER, alias)["epistemic_status"] == "ai_proposed"
    candidate = repo.correct(OWNER, alias, "분산 캐시를 제안합니다", 1)
    assert candidate["epistemic_status"] == "ai_proposed"
    assert candidate["supersedes_memory_id"] == old["memory_id"]


def test_prepared_review_becomes_stale(tmp_path):
    from pma.memory.manager import MemoryCaptureManager

    store = Store(tmp_path / "memory.db")
    manager = MemoryCaptureManager(store)
    c = manager.repo.propose(OWNER, content="한국어 설명을 선호한다")
    review = manager.review(OWNER, c["candidate_id"])
    saved(manager.repo, "새로운 기록")
    with pytest.raises(AppError, match="REVIEW_STALE"):
        manager.commit(
            OWNER,
            c["candidate_id"],
            approved=True,
            request_id="save",
            review_id=review["review_id"],
        )


def test_archival_and_retention(tmp_path):
    repo = MemoryRepository(Store(tmp_path / "memory.db"))
    item = saved(repo, "보관할 기록")
    repo.archive(OWNER, item["memory_id"], 1)
    assert repo.get(OWNER, item["memory_id"])["lifecycle_status"] == "archived"
    assert repo.list(OWNER)["items"] == []
    repo.unarchive(OWNER, item["memory_id"], 1)
    assert repo.get(OWNER, item["memory_id"])["index_status"] == "committed"
    pending = repo.propose(OWNER, content="만료된 임시 후보")
    repo.store.clock = lambda: "2999-01-01T00:00:00+00:00"
    repo.cleanup()
    with repo.store.connect() as db:
        assert not db.execute(
            "SELECT 1 FROM capture_candidates WHERE id=?", (pending["candidate_id"],)
        ).fetchone()
    assert repo.get(OWNER, item["memory_id"])["content"] == "보관할 기록"
