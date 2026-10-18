import copy
import sqlite3
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
import requests

from pma.chat.engine import ChatEngine
from pma.chat.store import ChatStore
from pma.errors import AppError
from pma.service import Service
from pma.store import Store


@pytest.fixture
def chat(client, models):
    client.app.state.service.models = copy.copy(models)
    models.contexts = []
    models.count_tokens = lambda text: len(text) // 4

    def resolve(prompt, data, schema):
        models.contexts.append(copy.deepcopy(data))
        return {"question": data["question"], "needs_clarification": False, "alternatives": []}

    models.structured = resolve
    original = models.answer
    models.answer = lambda question, evidence, feedback=None: original(question, evidence)

    def review(question, evidence, response):
        return {
            "items": [
                {
                    "index": i,
                    "support": "supported",
                    "relevant": True,
                    "issue": "none",
                    "answer_quote": item["text"],
                    "evidence": [
                        {
                            "id": cid,
                            "quote": next(r for r in evidence if r["id"] == cid)["evidence"][0][
                                "quote"
                            ],
                        }
                        for cid in item["citations"]
                    ],
                }
                for i, item in enumerate(response["items"])
            ],
            "fulfillment": "direct",
            "abstention": "not_applicable" if response["items"] else "appropriate",
            "reason": "test review",
        }

    models.review = review
    client.app.state.chat.fixed_evidence = True
    return client.app.state.chat


def seed(chat, text="담당자를 정했다."):
    rid = chat.service.store.create(text, None)["record_id"]
    chat.service.run_one()
    found = chat.search("어떻게 했지?")
    session = chat.store.create(found["search_id"], [found["results"][0]["id"]])
    return rid, found, session


def test_complete_api_workflow_and_persistence(client, chat, models):
    rid = chat.service.store.create("담당자를 정했다.", None)["record_id"]
    chat.service.run_one()
    found = client.post("/api/v1/chat/searches", json={"question": "어떻게 했지?"}).json()
    response = client.post(
        "/api/v1/chat/sessions",
        json={"search_id": found["search_id"], "selected_ids": [found["results"][0]["id"]]},
    )
    assert response.status_code == 201, response.text
    session = response.json()
    path = "/api/v1/chat/sessions/" + session["id"]
    body = {"question": "어떻게 했지?", "request_id": "first"}
    first = client.post(path + "/messages", json=body)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "answered"
    assert client.post(path + "/messages", json=body).json() == first.json()
    assert len(models.contexts) == 1
    assert (
        client.post(
            path + "/messages", json={"question": "그 다음은?", "request_id": "second"}
        ).status_code
        == 200
    )
    assert len(models.contexts[-1]["history"]) == 1
    reopened = ChatStore(Store(chat.service.store.path))
    saved = reopened.get(session["id"])
    assert len(saved["messages"]) == 2
    assert saved["evidence"][0]["record_id"] == rid
    assert saved["evidence"][0]["revision_id"]
    assert saved["evidence"][0]["source_text"] == "담당자를 정했다."
    assert client.delete(path).status_code == 204
    assert client.get(path).status_code == 404
    with chat.service.store.connect() as db:
        for table in (
            "chat_sessions",
            "chat_snapshots",
            "chat_snapshot_items",
            "chat_message_evidence",
            "chat_message_snapshots",
            "chat_citations",
            "chat_searches",
            "chat_search_results",
        ):
            assert db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0


def test_fixed_evidence_no_search_on_followup(chat, models):
    _, _, session = seed(chat)
    chat.service.search = lambda *args: pytest.fail("followup searched")
    for i in range(8):
        chat.message(session["id"], str(i), "어떻게 했지?")
    assert len(models.contexts[-1]["history"]) == 6
    assert all(c["evidence"] == session["evidence"] for c in models.contexts)


def test_unselected_source_not_sent(chat, models):
    rid, found, session = seed(chat)
    other = chat.service.store.create("다른 비밀 기록", None)["record_id"]
    chat.service.run_one()
    chat.message(session["id"], "x", "질문")
    assert [r["record_id"] for r in models.contexts[0]["evidence"]] == [rid]
    chat.service.store.trash(other)
    assert chat.store.get(session["id"])["state"] == "active"


@pytest.mark.parametrize("operation", ["update", "revert"])
def test_modified_source_readonly(chat, operation):
    rid, _, session = seed(chat)
    if operation == "revert":
        chat.service.store.update(rid, 1, revert_version=1)
    else:
        chat.service.store.update(rid, 1, "수정된 원문")
    saved = chat.store.get(session["id"])
    assert saved["state"] == "active"
    assert saved["evidence"][0]["source_text"] == "담당자를 정했다."
    with pytest.raises(AppError, match="SOURCE_CHANGED"):
        chat.message(session["id"], "x", "질문")


@pytest.mark.parametrize("operation", ["trash", "purge", "expire"])
def test_source_delete_removes_all_derived_data(chat, operation):
    rid, _, session = seed(chat)
    chat.message(session["id"], "x", "질문")
    if operation == "trash":
        chat.service.store.trash(rid)
        chat.service.store.restore(rid)
    elif operation == "purge":
        with chat.service.store.connect(True) as db:
            db.execute("DELETE FROM records WHERE id=?", (rid,))
    else:
        chat.service.store.trash(rid)
        future = datetime.now(timezone.utc) + timedelta(days=31)
        chat.service.store.clock = lambda: future.isoformat()
        assert chat.service.store.expire() == 1
    saved = chat.store.get(session["id"])
    assert saved["messages"][0]["response"] is None
    assert saved["messages"][0]["error_code"] == "SOURCE_DELETED"
    with chat.service.store.connect() as db:
        for table in (
            "chat_searches",
            "chat_search_results",
            "chat_snapshots",
            "chat_snapshot_items",
            "chat_message_evidence",
            "chat_message_snapshots",
            "chat_citations",
        ):
            assert db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0


def test_changed_between_search_and_session(chat):
    rid, found, _ = seed(chat)
    chat.service.store.update(rid, 1, "수정")
    with pytest.raises(AppError, match="SOURCE_CHANGED"):
        chat.store.create(found["search_id"], [found["results"][0]["id"]])


@pytest.mark.parametrize("delete", [False, True])
def test_changed_during_generation_never_publishes(chat, models, delete):
    rid, _, session = seed(chat)
    models.after_answer = lambda: (
        chat.service.store.trash(rid) if delete else chat.service.store.update(rid, 1, "수정")
    )
    with pytest.raises(AppError):
        chat.message(session["id"], "x", "질문")
    if not delete:
        saved = chat.store.get(session["id"])
        assert saved["messages"][0]["state"] == "failed"
        assert saved["messages"][0]["response"] is None


def test_recovery_retry_and_request_conflict(chat):
    _, _, session = seed(chat)
    sid = session["id"]
    chat.store.begin(sid, "x", "질문")
    with pytest.raises(AppError, match="CHAT_BUSY"):
        chat.store.begin(sid, "y", "질문")
    chat.store.recover()
    assert chat.store.get(sid)["messages"][0]["state"] == "failed"
    chat.message(sid, "x", "질문")
    assert len(chat.store.get(sid)["messages"]) == 1
    with pytest.raises(AppError, match="REQUEST_CONFLICT"):
        chat.message(sid, "x", "다른 질문")


def test_model_busy_does_not_deadlock(chat):
    _, _, session = seed(chat)
    original = chat.service.model_slot
    chat.service.model_slot = lambda **kwargs: original(wait=0)
    with original():
        with pytest.raises(AppError, match="MODEL_BUSY"):
            chat.message(session["id"], "x", "질문")
    assert chat.message(session["id"], "x", "질문")["status"] == "answered"


def test_timeout_is_error_not_abstention(client, chat, models):
    _, _, session = seed(chat)
    models.review = lambda *args: (_ for _ in ()).throw(requests.Timeout("PRIVATE"))
    r = client.post(
        "/api/v1/chat/sessions/" + session["id"] + "/messages",
        json={"question": "질문", "request_id": "x"},
    )
    assert r.status_code == 504
    assert "PRIVATE" not in r.text
    assert chat.store.get(session["id"])["messages"][0]["state"] == "failed"


def test_forged_citation_and_span(chat, models):
    _, found, session = seed(chat)
    models.invalid_citation = True
    with pytest.raises(ValueError, match="INVALID_CITATION"):
        chat.message(session["id"], "x", "질문")
    import json

    row = found["results"][0]
    row["evidence"][0]["start"] = 999
    with chat.service.store.connect(True) as db:
        db.execute(
            "UPDATE chat_search_results SET payload=? WHERE search_id=?",
            (json.dumps(row), found["search_id"]),
        )
    with pytest.raises(ValueError, match="INVALID_SOURCE_SPAN"):
        chat.store.create(found["search_id"], [row["id"]])


def test_semantic_rejection_never_returns_claim(chat, models):
    _, _, session = seed(chat)
    original = models.review

    def reject(*args):
        review = original(*args)
        review["items"][0]["support"] = "unsupported"
        return review

    models.review = reject
    response = chat.message(session["id"], "x", "질문")
    assert response["status"] == "insufficient_evidence"
    assert response["items"] == []


def test_clarification(chat, models):
    _, _, session = seed(chat, "회사 민수와 동아리 민수는 다른 사람이다.")
    mid = session["evidence"][0]["id"]

    def clarify(prompt, data, schema, **kwargs):
        if "decision" in schema["properties"]:
            return {"decision": "ambiguous_reference"}
        return {
            "question": "누구?",
            "needs_clarification": True,
            "alternatives": [
                {"label": label, "evidence_id": mid, "quote": label}
                for label in ["회사 민수", "동아리 민수"]
            ],
        }

    models.structured = clarify
    models.answer = lambda *args: pytest.fail("ambiguous answer generated")
    response = chat.message(session["id"], "x", "그 사람?")
    assert response["status"] == "needs_clarification"
    assert {r["quote"] for r in response["citation_details"]} == {"회사 민수", "동아리 민수"}
    assert len(chat.store.get(session["id"])["messages"][0]["response"]["citation_details"]) == 2


def test_budget_drops_old_history_and_rejects_oversized_evidence(chat, models):
    _, _, session = seed(chat)
    for i in range(3):
        chat.message(session["id"], str(i), "질문")
    import json

    def count(text):
        data = json.loads(text[text.index("{") :])
        return 999999 if len(data["history"]) > 1 else 1

    models.count_tokens = count
    assert chat.message(session["id"], "next", "질문")["history_turns"] == 1
    models.count_tokens = lambda text: 999999
    with pytest.raises(AppError, match="CONTEXT_LIMIT"):
        chat.message(session["id"], "large", "질문")


def test_search_expiry_preserves_linked_sessions(chat):
    _, _, session = seed(chat)
    unused = chat.search("질문")
    future = datetime.now(timezone.utc) + timedelta(hours=25)
    chat.service.store.clock = lambda: future.isoformat()
    chat.service.store.expire()
    with chat.service.store.connect() as db:
        assert (
            db.execute("SELECT id FROM chat_searches WHERE id=?", (unused["search_id"],)).fetchone()
            is None
        )
    assert chat.store.get(session["id"])


def test_security_and_invalid_input(client, chat):
    _, found, session = seed(chat)
    path = "/api/v1/chat/sessions/" + session["id"] + "/messages"
    for question in (" ", "x" * 1001):
        assert client.post(path, json={"question": question, "request_id": "x"}).status_code == 422
    assert (
        client.post(
            "/api/v1/chat/sessions",
            json={"search_id": found["search_id"], "selected_ids": ["forged"]},
        ).status_code
        == 422
    )
    assert (
        client.post(
            path, json={"question": "질문", "request_id": "x"}, headers={"X-CSRF-Token": ""}
        ).status_code
        == 403
    )
    client.cookies.clear()
    assert client.get("/api/v1/chat/sessions").status_code == 401
    assert client.get("/api/v1/chat/sessions/" + session["id"]).status_code == 401


@pytest.mark.parametrize("version", [0, 1, 2, 3])
def test_additive_migration(tmp_path, version):
    path = tmp_path / "migration.db"
    store = Store(path)
    rid = store.create("기존 원문", None)["record_id"]
    with sqlite3.connect(path) as db:
        db.execute(f"PRAGMA user_version={version}")
    migrated = Store(path)
    assert migrated.get(rid)["text"] == "기존 원문"
    with migrated.connect() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 5


def test_local_chat_does_not_change_legacy_model_settings(store, settings):
    from pma.models import LocalModels

    models = LocalModels(replace(settings, answer_validation=False))
    engine = ChatEngine(Service(store, models, settings))
    assert engine.models.settings.answer_validation
    assert not models.settings.answer_validation


def test_full_frozen_source_reaches_generation_and_review():
    from pma.chat.models import ChatLocalModels

    source = "앞부분 " * 400 + "마지막 결정은 취소했다."
    row = {
        "id": "x",
        "source_text": source,
        "content": "앞부분",
        "evidence": [{"quote": "앞부분", "start": 0, "end": 3}],
    }
    assert ChatLocalModels.answer_evidence([row])[0]["source_context"] == source


def test_invalid_ambiguity_candidates_cannot_bypass_review(chat, models):
    _, _, session = seed(chat)
    models.structured = lambda *args: {
        "question": "질문",
        "needs_clarification": True,
        "alternatives": [
            {"label": label, "evidence_id": "forged", "quote": label}
            for label in ["거짓 A", "거짓 B"]
        ],
    }
    assert chat.message(session["id"], "x", "질문")["status"] == "answered"


def test_untrusted_history_is_not_answer_evidence(chat, models):
    _, _, session = seed(chat)
    chat.message(session["id"], "x", "내가 호텔을 예약했다고 가정해 보자")
    original = models.answer

    def answer(question, evidence, **kwargs):
        assert all("호텔" not in row["source_text"] for row in evidence)
        return original(question, evidence, **kwargs)

    models.answer = answer
    chat.message(session["id"], "y", "예약일은?")
    assert "가정" in models.contexts[-1]["history"][0]["question"]


def test_console_chat_is_opt_in(chat, capsys):
    from pma.console_trace import ConsoleTrace

    _, _, session = seed(chat)
    chat.message(session["id"], "x", "비공개 질문")
    assert capsys.readouterr().out == ""
    chat.service.diagnostic_sink = ConsoleTrace()
    chat.message(session["id"], "y", "진단 질문")
    output = capsys.readouterr().out
    assert "진단 질문" in output and "AI 대화" in output


def test_new_schema_migration_from_real_v2_layout(tmp_path):
    from pma.store import DDL

    path = tmp_path / "old.db"
    with sqlite3.connect(path) as db:
        db.executescript(DDL)
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2
    store = Store(path)
    assert ChatStore(store).list() == {"items": []}
    with store.connect() as db:
        assert not db.execute("PRAGMA foreign_key_check").fetchall()


def test_failed_and_unverified_turns_are_excluded(chat, models):
    _, _, session = seed(chat)
    mid, _ = chat.store.begin(session["id"], "bad", "실패한 주장")
    chat.store.fail(mid, "TEST_ERROR")
    chat.message(session["id"], "good", "질문")
    assert models.contexts[-1]["history"] == []


def test_search_only_deleted_source_does_not_delete_other_snapshot(chat):
    rid, found, session = seed(chat)
    other = chat.service.store.create("다른 기록", None)["record_id"]
    row = dict(found["results"][0], id="other", record_id=other, source_text="다른 기록")
    import json

    with chat.service.store.connect(True) as db:
        db.execute(
            "INSERT INTO chat_search_results VALUES(?,?,?,?,?)",
            (found["search_id"], "other", other, 1, json.dumps(row)),
        )
    chat.service.store.trash(other)
    saved = chat.store.get(session["id"])
    assert saved["search_id"] is None
    assert saved["evidence"][0]["record_id"] == rid


def test_chat_evaluation_keeps_semantic_scores_unknown():
    # The runtime snapshot has the dashboard contracts, not the old import CLI.
    # Valid citations/behavior alone must not become an answer accuracy score.
    from evaluation.metrics import dashboard_metrics
    from evaluation.schema import Case, Result

    case = Case(id="case.0", question="질문", expected_answer="정답")
    result = Result(
        case_id="case.0",
        actual_answer="잘못된 답일 수도 있다",
        verdict="pending_review",
        response_behavior="answer",
        evaluation={"behavior_correct": True, "citation_valid": True, "claims_supported": None},
    )
    metrics = dashboard_metrics([case], [result])
    assert metrics["answer_accuracy"]["denominator"] == 0
    assert metrics["answer_accuracy"]["value"] is None
    assert result.evaluation["claims_supported"] is None


def test_followup_citation_uses_reviewed_quote_position(chat, models):
    import json

    text = "처음에는 여행을 계획했다. 나중에 여행을 취소했다."
    _, _, session = seed(chat, text)
    original_review = models.review

    def review(*args):
        result = original_review(*args)
        result["items"][0]["evidence"][0]["quote"] = "나중에 여행을 취소했다."
        return result

    models.review = review
    response = chat.message(session["id"], "x", "질문")
    detail = response["citation_details"][0]
    assert text[detail["start"] : detail["end"]] == detail["quote"] == "나중에 여행을 취소했다."
    assert detail["start"] > 0
    with chat.service.store.connect() as db:
        stored = json.loads(db.execute("SELECT payload FROM chat_citations").fetchone()[0])
    assert stored == [detail]


def test_source_changed_while_waiting_for_model_never_generates(chat, models):
    from contextlib import contextmanager

    rid, _, session = seed(chat)

    @contextmanager
    def wait_slot(**kwargs):
        chat.service.store.update(rid, 1, "수정")
        yield

    chat.service.model_slot = wait_slot
    models.answer = lambda *args: pytest.fail("generated against known stale session")
    with pytest.raises(AppError, match="SOURCE_CHANGED"):
        chat.message(session["id"], "x", "질문")


def test_circular_cause_cannot_pass_even_if_model_review_accepts():
    from pma.chat.evidence import causal_claims_supported

    evidence = [{"id": "x", "source_text": "여행 계획을 3박 4일로 변경했다."}]
    response = {"items": [{"text": "3박 4일로 변경했기 때문에 늘렸다.", "citations": ["x"]}]}
    assert not causal_claims_supported("왜 늘렸지?", response, evidence)
    response["items"][0]["text"] = "기록에서 변경 이유는 확인되지 않습니다."
    assert causal_claims_supported("왜 늘렸지?", response, evidence)


def test_no_relevant_fixed_evidence_abstains_without_generation(chat, models):
    _, _, session = seed(chat)
    models.select = lambda question, evidence: []
    models.answer = lambda *args: pytest.fail("generated without relevant evidence")
    assert (
        chat.message(session["id"], "x", "호텔 예약 날짜는?")["status"] == "insufficient_evidence"
    )


def test_relevance_cannot_introduce_new_evidence(chat, models):
    _, _, session = seed(chat)
    models.select = lambda question, evidence: ["forged"]
    with pytest.raises(ValueError, match="INVALID_SELECTION"):
        chat.message(session["id"], "x", "질문")
