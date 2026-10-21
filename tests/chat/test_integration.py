"""Offline contracts: real SQLite/API/search core, deterministic model doubles."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from pma.chat.context import merge_filters
from pma.chat.router import RetrievalRouter, RoutingMode
from pma.chat.store import ChatStore
from pma.errors import AppError
from pma.settings import AppSettings
from pma.store import Store
from pma.web import create_app
from tests.http_client import TestClient


@pytest.fixture
def chat(tmp_path):
    return ChatStore(Store(tmp_path / "memory.db"))


def complete(chat, sid, request="r", question="안녕"):
    mid, cached = chat.begin(sid, request, question)
    assert cached is None
    chat.finish(sid, mid, {"status": "answered", "items": []}, [])
    return mid


def test_store_idempotency_context_restart_and_pagination(chat):
    sid = chat.create_empty()["id"]
    for i in range(12):
        complete(chat, sid, str(i), f"질문 {i}")
    restored = ChatStore(Store(chat.store.path))
    assert restored.get(sid)["context"]["version"] == 12
    assert "질문 0" in restored.get(sid)["context"]["summary"]
    page = restored.messages(sid, 0, 5)
    assert len(page["items"]) == 5 and page["next_offset"] == 5
    assert restored.begin(sid, "0", "질문 0")[1]["status"] == "answered"
    with pytest.raises(AppError, match="REQUEST_CONFLICT"):
        restored.begin(sid, "0", "다른 질문")
    assert restored.store.list()["items"] == []


def test_owner_isolation_covers_all_access(chat):
    sid = chat.create_empty()["id"]
    other = ChatStore(chat.store, "other")
    assert not other.list()["items"]
    for call in [lambda: other.get(sid), lambda: other.delete(sid),
                 lambda: other.begin(sid, "r", "안녕"),
                 lambda: other.update_context(sid, {}, 0),
                 lambda: other.request_state(sid, "r")]:
        with pytest.raises(AppError, match="NOT_FOUND"):
            call()
    chat.delete(sid)
    with pytest.raises(AppError, match="NOT_FOUND"):
        chat.get(sid)


def test_concurrent_version_updates_and_message_begin(chat):
    sid = chat.create_empty()["id"]

    def update(_):
        try:
            chat.update_context(sid, {"active_topic": "주제"}, 0)
            return "ok"
        except AppError as exc:
            return exc.code

    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(update, range(2))) == ["STATE_CONFLICT", "ok"]
    chat.begin(sid, "one", "첫 질문")
    with pytest.raises(AppError, match="CHAT_BUSY"):
        chat.begin(sid, "two", "두 번째")
    chat.recover()
    assert chat.request_state(sid, "one")["error_code"] == "INTERRUPTED"


def test_generation_cannot_overwrite_concurrent_context_update(chat):
    sid = chat.create_empty()["id"]
    mid, _ = chat.begin(sid, "r", "안녕")
    chat.update_context(sid, {"active_topic": "새 주제"}, 0)
    with pytest.raises(AppError, match="STATE_CONFLICT"):
        chat.finish(sid, mid, {"status": "answered", "items": []}, [], {"context_version": 0})
    assert chat.get(sid)["context"]["active_topic"] == "새 주제"


def test_migration_json_fk_and_source_preservation(chat):
    import sqlite3

    record = chat.store.create("원본 보존", None)
    for _ in range(3):
        Store(chat.store.path)
    with chat.store.connect() as db:
        assert db.execute("SELECT text FROM revisions WHERE record_id=?",
                          (record["record_id"],)).fetchone()[0] == "원본 보존"
    sid = chat.create_empty()["id"]
    for key, payload in [(sid, "bad json"), ("missing", "{}")]:
        with pytest.raises(sqlite3.IntegrityError), chat.store.connect(True) as db:
            db.execute("INSERT INTO chat_context VALUES(?,0,?)", (key, payload))
    assert not chat.list("' OR 1=1 --")["items"]


@pytest.mark.parametrize("question,mode,reason", [
    ("안녕", "CHAT_ONLY", "GREETING"),
    ("파이썬이 뭐야", "CHAT_ONLY", "GENERAL_KNOWLEDGE"),
    ("전에 뭐 했지?", "MEMORY_REQUIRED", "PERSONAL_HISTORY"),
    ("그때 어떻게 했었지?", "MEMORY_REQUIRED", "PERSONAL_HISTORY"),
    ("지난달 기록에서 찾아줘", "MEMORY_REQUIRED", "EXPLICIT_RECALL"),
    ("검색해줘", "MEMORY_REQUIRED", "EXPLICIT_RECALL"),
])
def test_router_rules_without_model(question, mode, reason):
    result = RetrievalRouter().decide(question, classify=lambda: pytest.fail("model called"))
    assert result.mode == mode and result.reason_code == reason


def test_router_followup_switch_disable_and_failure():
    router = RetrievalRouter()
    history = [{"response": {"conversation_mode": "memory"}}]
    assert router.decide("그걸 왜?", history=history).reason_code == "MEMORY_FOLLOWUP"
    assert router.decide("검색해줘", memory_enabled=False).mode == RoutingMode.CHAT_ONLY
    assert router.decide("제주", explicit_search=True).mode == RoutingMode.EXPLICIT_SEARCH
    assert router.decide("B 프로젝트", classify=lambda: {"mode": "memory", "query": "B 프로젝트"}).query == "B 프로젝트"
    assert router.decide("민수는?", classify=lambda: 1 / 0).reason_code == "CLASSIFIER_FAILED"
    assert merge_filters({"date_from": "2020-01-01"}, {"date_from": "2026-01-01"}) == {"date_from": "2026-01-01"}


def test_citation_validation_and_lifecycle(chat):
    sid = chat.create_empty()["id"]
    record = chat.store.create("😀 제주에 갔다", None)
    with chat.store.connect() as db:
        rev = dict(db.execute("SELECT * FROM revisions WHERE record_id=?", (record["record_id"],)).fetchone())
    row = {"id": "memory", "record_id": record["record_id"], "version": 1,
           "source_text": rev["text"], "evidence": [{"start": 2, "end": 4, "quote": "제주"}]}
    row = chat.freeze([row])[0]
    mid, _ = chat.begin(sid, "r", "어디 갔지?")
    ref = {"item_index": 0, "memory_id": "memory", "record_id": record["record_id"],
           "revision_id": rev["id"], "start": 2, "end": 4, "quote": "제주"}
    response = {"status": "answered", "items": [{"text": "제주", "citations": ["memory"]}],
                "citation_details": [ref]}
    chat.finish(sid, mid, response, [row])
    cid = f"{mid}:0:memory"
    assert chat.citation(cid)["references"][0]["quote"] == "제주"
    with pytest.raises(AppError):
        ChatStore(chat.store, "other").citation(cid)
    with chat.store.connect(True) as db:
        db.execute("UPDATE records SET version=2 WHERE id=?", (record["record_id"],))
    with pytest.raises(AppError, match="SOURCE_CHANGED"):
        chat.citation(cid)
    with pytest.raises(AppError, match="SOURCE_CHANGED"):
        chat.begin(sid, "r", "어디 갔지?")
    assert chat.get(sid)["context"]["active_evidence"] == []


def test_api_security_pagination_and_alias(tmp_path):
    settings = AppSettings(data_dir=tmp_path)
    app = create_app(settings, models=OfflineModels(), run_worker=False)
    with TestClient(app, base_url=settings.origin) as client:
        assert client.get("/api/v1/chat/sessions").status_code == 401
        auth = client.post("/api/v1/session", headers={"Origin": settings.origin},
                           json={"token": app.state.bootstrap_token})
        headers = {"Origin": settings.origin, "X-CSRF-Token": auth.json()["csrf"]}
        assert client.post("/api/v1/chat/sessions", json={}, headers={"Origin": settings.origin}).status_code == 403
        sid = client.post("/api/v1/chat/sessions", json={}, headers=headers).json()["id"]
        complete(app.state.chat.store, sid)
        response = client.get(f"/api/v1/chat/sessions/{sid}/messages?limit=1")
        assert response.status_code == 200 and response.json()["total"] == 1
        assert client.get(f"/api/v1/chat/sessions/{sid}/messages?limit=1000").status_code == 422
        other = ChatStore(app.state.store, "other").create_empty()["id"]
        assert client.get(f"/api/v1/chat/sessions/{other}").status_code == 404
        assert client.post(f"/api/v1/chat/sessions/{other}/messages", headers=headers,
                           json={"client_message_id": "x", "question": "안녕"}).status_code == 404
        assert client.get("/api/v1/chat/sessions", headers={"Host": "evil"}).status_code == 403
        for path in ("/api/v1/search", "/api/v1/answers"):
            result = client.post(path, headers=headers, json={"question": "전에 뭐 했지?"})
            assert result.status_code == 200 and result.json()["results"] == []
        natural = client.post(f"/api/v1/chat/sessions/{sid}/messages", headers=headers,
                              json={"client_message_id": "search", "question": "검색해줘"})
        assert natural.status_code == 200 and natural.json()["status"] == "insufficient_evidence"
        assert client.post(f"/api/v1/chat/sessions/{sid}/clarifications", headers=headers,
                           json={"request_id": "clarify", "question": "민수"}).status_code == 422
        assert client.delete(f"/api/v1/chat/sessions/{sid}", headers=headers).status_code == 204


class OfflineModels:
    def __init__(self):
        self.calls = 0
        self.searches = 0

    def count_tokens(self, text):
        return len(text) // 2

    def structured(self, prompt, data, schema, max_tokens=None):
        self.calls += 1
        keys = schema["properties"]
        if "safe" in keys:
            return {"safe": True}
        if "text" in keys:
            return {"text": "반가워요. 무엇을 도와드릴까요?"}
        if "mode" in keys:
            return {"mode": "memory", "query": data.get("current_question", "여행")}
        if "query" in keys:
            return {"query": ""}
        raise AssertionError(keys)

    def understand(self, question, today):
        self.searches += 1
        return {"intent": "recall", "date_from": None, "date_to": None}

    def embed(self, text):
        return [[1, 0]]

    def select(self, question, evidence):
        return [r["id"] for r in evidence]


def test_orchestrator_ten_turns_then_five_memory_turns_and_retry(tmp_path):
    from pma.chat.orchestrator import ChatOrchestrator
    from pma.service import Service

    models = OfflineModels()
    settings = AppSettings(data_dir=tmp_path, embedding_dimensions=2)
    engine = ChatOrchestrator(Service(Store(tmp_path / "memory.db"), models, settings))
    sid = engine.store.create_empty()["id"]
    for i in range(10):
        result = engine.message(sid, str(i), "안녕")
        assert result["status"] == "answered"
    assert models.searches == 0 and models.calls == 20
    before = models.calls
    assert engine.message(sid, "0", "안녕")["status"] == "answered"
    assert models.calls == before
    for i in range(5):
        result = engine.message(sid, f"m{i}", "전에 뭐 했지?" if i == 0 else "그걸 왜?")
        assert result["status"] == "insufficient_evidence"
        assert result["items"] == []
    assert models.searches >= 5
    session = engine.store.get(sid)
    assert session["context"]["version"] == 15
    assert session["context"]["summary"]
    assert session["messages"][-1]["snapshot"]["route"]["reason_code"] == "MEMORY_FOLLOWUP"


def test_orchestrator_failure_then_recovery(tmp_path):
    from pma.chat.orchestrator import ChatOrchestrator
    from pma.service import Service

    models = OfflineModels()
    settings = AppSettings(data_dir=tmp_path, embedding_dimensions=2)
    engine = ChatOrchestrator(Service(Store(tmp_path / "memory.db"), models, settings))
    sid = engine.store.create_empty()["id"]
    good = models.structured
    models.structured = lambda *args, **kw: (_ for _ in ()).throw(ValueError("offline"))
    with pytest.raises(ValueError):
        engine.message(sid, "r", "안녕")
    assert engine.store.request_state(sid, "r")["state"] == "failed"
    models.structured = good
    assert engine.message(sid, "r", "안녕")["status"] == "answered"
    assert len(engine.store.get(sid)["messages"]) == 1
