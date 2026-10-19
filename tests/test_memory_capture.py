import pytest

from pma.chat.store import ChatStore
from pma.errors import AppError
from pma.memory.api import OWNER, from_messages, natural_candidates
from pma.memory.repository import MemoryRepository
from pma.store import Store


def turn(store, sid, question, answer="캐시 도입을 제안합니다", mode="general"):
    chat = ChatStore(store)
    mid, _ = chat.begin(sid, question, question, mode=mode)
    chat.finish(sid, mid, {"status": "answered", "items": [{"text": answer, "citations": []}]}, [])
    return mid


def test_approval_and_restart(tmp_path):
    store = Store(tmp_path / "memory.db")
    repo = MemoryRepository(store)
    candidate = repo.propose("alice", content="내일 제주도에 갈 계획이다")
    assert store.list()["items"] == []
    with pytest.raises(AppError):
        repo.commit("alice", candidate["candidate_id"], approved=False, request_id="save")
    saved = repo.commit("alice", candidate["candidate_id"], approved=True, request_id="save")
    assert saved["epistemic_status"] == "user_reported"
    assert saved["memory_type"] == "plan"
    assert saved["index_status"] == "committed"
    assert (
        repo.commit("alice", candidate["candidate_id"], approved=True, request_id="save")[
            "memory_id"
        ]
        == saved["memory_id"]
    )
    restored = MemoryRepository(Store(store.path))
    assert restored.get("alice", saved["memory_id"])["content"] == candidate["content"]
    with pytest.raises(AppError):
        restored.get("bob", saved["memory_id"])


def test_duplicate_correction_delete(tmp_path):
    repo = MemoryRepository(Store(tmp_path / "memory.db"))
    first = repo.propose("alice", content="제주도에 민수와 갔다")
    saved = repo.commit("alice", first["candidate_id"], approved=True, request_id="first")
    duplicate = repo.propose("alice", content=first["content"])
    with pytest.raises(AppError):
        repo.commit("alice", duplicate["candidate_id"], approved=True, request_id="dup")
    corrected = repo.correct("alice", saved["memory_id"], "제주도에 영희와 갔다", 1)
    newer = repo.commit(
        "alice",
        corrected["candidate_id"],
        approved=True,
        request_id="correct",
        resolution="correct",
    )
    assert newer["record_version"] == 2
    assert len(repo.history("alice", newer["memory_id"])) == 2
    repo.delete("alice", newer["memory_id"], 2)
    assert repo.list("alice")["items"] == []


@pytest.mark.parametrize("mode", ["general", "memory", "hybrid"])
def test_modes_reference_and_provenance(tmp_path, mode):
    store = Store(tmp_path / "memory.db")
    sid = ChatStore(store).create_empty()["id"]
    original = turn(store, sid, "캐시 도입을 검토 중이다", mode=mode)
    mid = turn(store, sid, "이거 기억해", mode=mode)
    candidates = natural_candidates(store, sid, mid, "이거 기억해", mode)
    assert len(candidates) == 2
    assert candidates[0]["message_ids"] == [original]
    assert candidates[1]["memory_type"] == "proposal"
    assert candidates[1]["epistemic_status"] == "ai_proposed"
    assert store.list()["items"] == []
    assert natural_candidates(store, sid, mid, "오늘 날씨 어때?", mode) == []


def test_selection_and_cross_session_sources(tmp_path):
    store = Store(tmp_path / "memory.db")
    repo = MemoryRepository(store)
    sid = ChatStore(store).create_empty()["id"]
    other = ChatStore(store).create_empty()["id"]
    mid = turn(store, sid, "민수에게 선물을 주지 않았다. 내일 여행 계획이 있다.")
    candidate = from_messages(repo, sid, [mid], "user_message", "민수에게 선물을 주지 않았다.")
    assert candidate["content"] == "민수에게 선물을 주지 않았다."
    for session, text in [(other, None), (sid, "존재하지 않는 문장")]:
        with pytest.raises(AppError):
            from_messages(repo, session, [mid], "user_message", text)
    with store.connect(True) as db:
        db.execute("DELETE FROM chat_sessions WHERE id=?", (sid,))
    with pytest.raises(AppError):
        repo.commit(OWNER, candidate["candidate_id"], approved=True, request_id="deleted-source")
    assert store.list()["items"] == []


def test_expiry_version_and_ai_type(tmp_path):
    repo = MemoryRepository(Store(tmp_path / "memory.db"))
    c = repo.propose("alice", content="아직 구현하지 않았다", source_type="assistant_message")
    with pytest.raises(AppError):
        repo.commit(
            "alice", c["candidate_id"], approved=True, request_id="bad", memory_type="event"
        )
    with pytest.raises(AppError):
        repo.commit(
            "alice", c["candidate_id"], approved=True, request_id="bad", candidate_version=2
        )
    repo.store.clock = lambda: "2999-01-01T00:00:00+00:00"
    with pytest.raises(AppError):
        repo.commit("alice", c["candidate_id"], approved=True, request_id="expired")
    assert repo.store.list()["items"] == []


def test_atomic_commit_rolls_back_job_failure(tmp_path, monkeypatch):
    repo = MemoryRepository(Store(tmp_path / "memory.db"))
    c = repo.propose("alice", content="서울에서 만났다")

    def broken(*args):
        raise RuntimeError("simulated storage error")

    monkeypatch.setattr(repo.store, "queue", broken)
    with pytest.raises(RuntimeError):
        repo.commit("alice", c["candidate_id"], approved=True, request_id="failure")
    assert repo.store.list()["items"] == []
    with repo.store.connect() as db:
        assert db.execute("SELECT count(*) FROM revisions").fetchone()[0] == 0


def test_index_publication_correction_and_delete(tmp_path):
    import numpy as np

    repo = MemoryRepository(Store(tmp_path / "memory.db"))

    def save(text, key, correcting=None):
        c = (
            repo.correct("alice", correcting["memory_id"], text, correcting["record_version"])
            if correcting
            else repo.propose("alice", content=text)
        )
        return repo.commit(
            "alice",
            c["candidate_id"],
            approved=True,
            request_id=key,
            resolution="correct" if correcting else "add",
        )

    def publish(saved):
        job = repo.store.claim()
        memory = dict(
            local_id="m1",
            memory_type="event",
            content=saved["content"],
            subject={"kind": "self", "value": "나"},
            predicate="방문",
            object={"value": "제주도"},
            assertion_polarity="affirmed",
            time={
                "raw": None,
                "start": None,
                "end": None,
                "precision": "unknown",
                "certainty": "uncertain",
            },
            evidence=[{"quote": saved["content"]}],
        )
        repo.store.publish(job, [memory], np.array([[1.0, 0.0]], dtype=np.float32), "test", {})

    first = save("제주도에 민수와 갔다", "first")
    publish(first)
    assert repo.get("alice", first["memory_id"])["index_status"] == "searchable"
    generation, rows = repo.store.snapshot("test")
    assert len(rows) == 1
    assert repo.store.snapshot_for_owner("test", "local-account")[1] == []
    assert len(repo.store.snapshot_for_owner("test", "alice")[1]) == 1
    newer = save("제주도에 영희와 갔다", "newer", first)
    assert repo.store.snapshot("test")[1] == []
    publish(newer)
    assert repo.store.snapshot("test")[0] > generation
    assert len(repo.store.snapshot("test")[1]) == 1
    repo.delete("alice", newer["memory_id"], 2)
    assert repo.store.snapshot("test")[1] == []


def test_api_approval_validation_and_sources(tmp_path):
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from fastapi.testclient import TestClient

    from pma.memory.api import router
    from pma.web import Input

    app = FastAPI()
    store = Store(tmp_path / "memory.db")
    app.state.store = store
    app.include_router(router(Input))

    @app.exception_handler(AppError)
    async def errors(request, exc):
        return JSONResponse({"code": exc.code}, status_code=exc.status)

    sid = ChatStore(store).create_empty()["id"]
    mid = turn(store, sid, "앞으로 한국어로 설명해줘. 기억해.")
    with TestClient(app) as client:
        payload = dict(session_id=sid, message_ids=[mid], source_type="user_message")
        result = client.post("/api/v1/memory/candidates", json=payload)
        assert result.status_code == 201, result.text
        cid = result.json()["candidate_id"]
        url = "/api/v1/memory/candidates/" + cid + "/commit"
        assert client.post(url, json={"approved": False, "request_id": "save"}).status_code == 409
        assert client.post(url, json={"approved": "true", "request_id": "save"}).status_code == 422
        result = client.post(url, json={"approved": True, "request_id": "save"})
        assert result.status_code == 202, result.text
        assert len(client.get("/api/v1/memory").json()["items"]) == 1
        assert (
            client.post(
                "/api/v1/memory/candidates", json=dict(payload, owner_id="other")
            ).status_code
            == 422
        )


def test_existing_record_correction_and_stale_version(tmp_path):
    store = Store(tmp_path / "memory.db")
    original = store.create("제주도에 민수와 갔다", None)
    repo = MemoryRepository(store)
    cid = "record:" + original["record_id"]
    assert repo.get(OWNER, cid)["epistemic_status"] == "unverified"
    candidate = repo.correct(OWNER, cid, "제주도에 영희와 갔다", 1)
    assert store.get(original["record_id"])["text"] == "제주도에 민수와 갔다"
    saved = repo.commit(
        OWNER, candidate["candidate_id"], approved=True, request_id="correct", resolution="correct"
    )
    assert saved["record_id"] == original["record_id"]
    assert repo.history(OWNER, saved["memory_id"])[1]["content"] == "제주도에 민수와 갔다"
    with pytest.raises(AppError):
        repo.correct(OWNER, saved["memory_id"], "다른 내용", 1)
    with pytest.raises(AppError):
        repo.delete(OWNER, saved["memory_id"], 1)
    with pytest.raises(AppError):
        repo.commit(
            OWNER, candidate["candidate_id"], approved=True, request_id="correct", resolution="add"
        )


def test_failed_index_retry_and_pending_rejection(tmp_path):
    store = Store(tmp_path / "memory.db")
    repo = MemoryRepository(store)
    c = repo.propose("alice", content="회의는 내일 진행할 계획이다")
    saved = repo.commit("alice", c["candidate_id"], approved=True, request_id="save")
    job = store.claim()
    store.fail(job, "MODEL_UNAVAILABLE", {})
    assert repo.get("alice", saved["memory_id"])["index_status"] == "index_failed"
    assert repo.retry("alice", saved["memory_id"])["index_status"] == "committed"
    assert repo.get("alice", saved["memory_id"])["content"] == c["content"]
    c2 = repo.propose("alice", content="보류할 새 후보")
    assert len(repo.pending("alice")["items"]) == 1
    repo.reject("alice", c2["candidate_id"])
    assert repo.pending("alice")["items"] == []
    with pytest.raises(AppError):
        repo.commit("alice", c2["candidate_id"], approved=True, request_id="reject")


@pytest.mark.parametrize(
    "kind",
    [
        "user_statement",
        "preference",
        "event",
        "project_decision",
        "plan",
        "proposal",
        "hypothesis",
        "correction",
        "conversation_summary",
    ],
)
def test_memory_types_roundtrip(tmp_path, kind):
    repo = MemoryRepository(Store(tmp_path / "memory.db"))
    candidate = repo.propose("alice", content="선택한 원문", memory_type=kind)
    saved = repo.commit("alice", candidate["candidate_id"], approved=True, request_id="save")
    assert repo.get("alice", saved["memory_id"])["memory_type"] == kind


def test_capture_security_middleware(tmp_path):
    from fastapi.testclient import TestClient

    from pma.settings import AppSettings
    from pma.web import create_app

    settings = AppSettings(data_dir=tmp_path)
    app = create_app(settings, models=object(), run_worker=False)
    with TestClient(app, base_url=settings.origin) as client:
        assert client.get("/api/v1/memory").status_code == 401
        auth = client.post(
            "/api/v1/session",
            headers={"Origin": settings.origin},
            json={"token": app.state.bootstrap_token},
        )
        assert auth.status_code == 200
        csrf = auth.json()["csrf"]
        assert (
            client.post(
                "/api/v1/memory/candidates", headers={"Origin": settings.origin}, json={}
            ).status_code
            == 403
        )
        assert client.get("/api/v1/memory").status_code == 200
        assert (
            client.post(
                "/api/v1/memory/candidates",
                headers={"Origin": "https://example.com", "X-CSRF-Token": csrf},
                json={},
            ).status_code
            == 403
        )


def test_ai_extraction_cannot_become_personal_fact(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from pma.processing import extract_record

    store = Store(tmp_path / "memory.db")
    repo = MemoryRepository(store)
    c = repo.propose(
        "alice", content="캐시를 도입하는 것이 좋습니다", source_type="assistant_message"
    )
    saved = repo.commit("alice", c["candidate_id"], approved=True, request_id="ai")
    memory = {
        "memory_type": "event",
        "content": "캐시를 구현했다",
        "subject": {"kind": "self", "value": "나"},
        "assertion_polarity": "affirmed",
        "content_certainty": "explicit",
    }
    monkeypatch.setattr(
        "pma.processing._extract_record", lambda *args: ({"memories": [memory]}, {})
    )
    result, _ = extract_record(SimpleNamespace(store=store), {"record_id": saved["record_id"]}, {})
    extracted = result["memories"][0]
    assert extracted["assertion_polarity"] == "uncertain"
    assert extracted["subject"]["kind"] == "unknown"
    assert extracted["memory_type"] == "other"
    assert c["content"] in extracted["content"]
    assert "캐시를 구현했다" not in extracted["content"]


@pytest.mark.parametrize(
    "old,new",
    [
        ("2026년 1월 1일 민수를 만났다", "2026년 1월 2일 민수를 만났다"),
        ("민수를 만났다", "영희를 만났다"),
        ("민수에게 선물을 주었다", "민수에게 선물을 주지 않았다"),
        ("민수가 영희에게 선물을 주었다", "영희가 민수에게 선물을 주었다"),
        ("캐시를 도입할 계획이다", "캐시를 구현했다"),
    ],
)
def test_distinct_facts_are_never_automatic_duplicates(old, new):
    from pma.memory.deduplication import compare

    comparisons = compare(new, [{"memory_id": "old", "record_version": 1, "content": old}])
    assert not any(c["relation"] == "exact_duplicate" for c in comparisons)


def test_atomic_idempotency_for_concurrent_commits(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    repo = MemoryRepository(Store(tmp_path / "memory.db"))
    candidate = repo.propose("alice", content="동시 요청에서도 하나만 저장한다")

    def commit(_):
        return repo.commit("alice", candidate["candidate_id"], approved=True, request_id="same")

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(commit, range(2)))
    assert results[0]["memory_id"] == results[1]["memory_id"]
    assert len(repo.store.list()["items"]) == 1


def test_decision_capture_uses_actual_turns_and_preferences_update(tmp_path):
    store = Store(tmp_path / "memory.db")
    sid = ChatStore(store).create_empty()["id"]
    decision = turn(store, sid, "프로젝트에 캐시 도입을 결정했어. 아직 구현하지 않았다.")
    turn(store, sid, "그냥 잡담이야")
    mid = turn(store, sid, "이 대화에서 중요한 결정만 저장해줘")
    candidates = natural_candidates(store, sid, mid, "이 대화에서 중요한 결정만 저장해줘", "hybrid")
    assert len(candidates) == 1
    assert candidates[0]["message_ids"] == [decision]
    assert candidates[0]["memory_type"] == "project_decision"
    assert "아직 구현하지 않았다" in candidates[0]["content"]
    repo = MemoryRepository(store)
    c = repo.propose(OWNER, content="앞으로 자세히 설명해줘")
    saved = repo.commit(OWNER, c["candidate_id"], approved=True, request_id="preference")
    assert repo.preferences(OWNER) == [c["content"]]
    correction = repo.correct(OWNER, saved["memory_id"], "앞으로 간단히 설명해줘", 1)
    newer = repo.commit(
        OWNER, correction["candidate_id"], approved=True, request_id="update", resolution="correct"
    )
    assert repo.preferences(OWNER) == ["앞으로 간단히 설명해줘"]
    repo.delete(OWNER, newer["memory_id"], 2)
    assert repo.preferences(OWNER) == []
