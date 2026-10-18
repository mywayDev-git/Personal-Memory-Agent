"""UI contracts, topic isolation, search privacy, and cancellation races."""
# ruff: noqa: F811

import pytest
from test_chat import chat, seed  # noqa: F401

from pma.chat.evidence import direct_statement, identity_alternatives, selected_alternative
from pma.chat.presentation import presentation
from pma.errors import AppError
from scripts.memory_agent.llm_client import model_phase, observe_phases


def test_search_matches_messages_but_not_removed_answers(chat):  # noqa: F811
    rid, _, session = seed(chat)
    sid = session["id"]
    chat.message(sid, "a", "독특한 후속 질문")
    assert [s["id"] for s in chat.store.list("독특한")["items"]] == [sid]
    assert chat.store.list("담당자")["items"]
    chat.service.store.update(rid, 1, text="다른 기록이다.")
    assert not chat.store.list("담당자")["items"]
    assert chat.store.list("독특한")["items"]
    assert not chat.store.list("%_'")["items"]


def test_topic_isolation_replay_and_expiry(chat, models):  # noqa: F811
    rid, _, session = seed(chat)
    sid = session["id"]
    first = chat.message(sid, "first", "원래 주제")
    chat.message(sid, "second", "다른 주제")
    anchor = first["message_id"]
    response = chat.message(sid, "return", "그다음?", context_message_id=anchor)
    assert models.contexts[-1]["history"][-1]["question"] == "원래 주제"
    assert chat.store.get(sid)["messages"][-1]["context_message_id"] == anchor
    assert chat.message(sid, "return", "그다음?", context_message_id=anchor) == response
    with pytest.raises(AppError, match="REQUEST_CONFLICT"):
        chat.message(sid, "return", "그다음?")
    other = chat.store.create_empty()["id"]
    with pytest.raises(AppError, match="CONTEXT_EXPIRED"):
        chat.message(other, "foreign", "그다음?", context_message_id=anchor)
    chat.service.store.update(rid, 1, text="수정된 기록")
    with pytest.raises(AppError, match="CONTEXT_EXPIRED"):
        chat.message(sid, "stale", "그다음?", context_message_id=anchor)


def test_cancel_during_generation_discards_and_blocks_retry_until_worker_exits(chat, models):  # noqa: F811
    _, _, session = seed(chat)
    sid = session["id"]
    answer = models.answer

    def cancelled(*args, **kwargs):
        assert chat.request_status(sid, "a")["worker_active"]
        chat.store.cancel(sid, "a")
        with pytest.raises(AppError, match="CHAT_BUSY"):
            chat.message(sid, "a", "어떻게 했지?")
        return answer(*args, **kwargs)

    models.answer = cancelled
    with pytest.raises(AppError, match="CANCELLED"):
        chat.message(sid, "a", "어떻게 했지?")
    saved = chat.store.get(sid)["messages"][0]
    assert saved["response"] is None and saved["evidence"] == []
    assert saved["error_code"] == "CANCELLED"
    assert not chat.request_status(sid, "a")["worker_active"]
    models.answer = answer
    assert chat.message(sid, "a", "어떻게 했지?")["status"] == "answered"


def test_cancel_is_scoped_to_session(client, chat):  # noqa: F811
    a = chat.store.create_empty()["id"]
    b = chat.store.create_empty()["id"]
    chat.store.begin(a, "same", "안녕")
    chat.store.begin(b, "same", "안녕")
    path = f"/api/v1/chat/sessions/{a}/requests/same"
    assert client.post(path + "/cancel", json={}).status_code == 200
    assert client.get(path).json()["error_code"] == "CANCELLED"
    assert chat.store.request_state(b, "same")["state"] == "running"
    assert client.get("/api/v1/chat/sessions/missing/requests/same").status_code == 404
    assert (
        client.post(f"/api/v1/chat/sessions/{a}/requests/not-yet/cancel", json={}).status_code
        == 409
    )


def test_clarification_choice_expires_after_another_completed_turn(chat):  # noqa: F811
    sid = chat.store.create_empty()["id"]
    mid, _ = chat.store.begin(sid, "clarify", "누구?")
    chat.store.finish(sid, mid, {"status": "needs_clarification", "items": []}, [], {})
    next_id, _ = chat.store.begin(sid, "next", "다른 이야기")
    chat.store.finish(sid, next_id, {"status": "answered", "items": []}, [], {})
    with pytest.raises(AppError, match="CONTEXT_EXPIRED"):
        chat.store.begin(sid, "choice", "회사 동료", context_message_id=mid)


def test_phase_listener_is_context_local_and_cleans_up():
    seen = []
    with observe_phases(seen.append), model_phase("search"):
        pass
    with model_phase("review"):
        pass
    assert seen == ["search"]


def test_presentation_does_not_invent_claims_or_allow_unknown_layouts():
    r = {
        "status": "answered",
        "items": [{"text": "검증된 답변"}],
        "blocks": [None, {"type": "script", "item_indices": [0, -1, True, 99]}],
    }
    assert presentation(r) == [{"type": "text", "item_indices": [0]}]
    r["status"] = "needs_clarification"
    assert presentation(r)[0]["type"] == "clarification_choices"


def test_short_role_selection_does_not_repeat_ambiguity():
    labels = ["동아리 친구 민수", "회사 동료 민수"]
    assert selected_alternative("동아리 민수", labels) == labels[0]
    assert selected_alternative("민수", labels) is None
    assert selected_alternative("동아리 민수 말고", labels) is None
    assert selected_alternative("회사 동아리 민수", labels) is None
    rows = [
        {"id": "a", "source_text": "동아리 친구 민수는 간호사다."},
        {"id": "b", "source_text": "회사 동료 민수는 디자이너다."},
    ]
    assert identity_alternatives("동아리 민수는 누구야?", rows) == []
    assert len(identity_alternatives("민수는 누구야?", rows)) == 2
    candidate = direct_statement("동아리 친구 민수는 누구야?", rows)
    assert candidate["items"][0]["citations"] == ["a"]
    assert "간호사" in candidate["items"][0]["text"]
    rows.append({"id": "c", "source_text": "동아리 친구 민수는 교사다."})
    assert direct_statement("동아리 친구 민수는 누구야?", rows) is None
    relation = [{"id": "friend", "source_text": "지연이는 나의 초등학교 동창이다."}]
    question = "그 사람은 나와 어떤 사이였지?\n참조 해석: 지연이는 나와 어떤 사이였지?"
    assert direct_statement(question, relation, "그 사람은 나와 어떤 사이였지?")["items"][0][
        "citations"
    ] == ["friend"]
    assert direct_statement(question, relation, "그걸 왜 봤지?") is None


@pytest.mark.parametrize(
    "question,expected",
    [
        ("동아리 민수", "동아리 친구 민수는 누구야?"),
        ("동아리 친구 민수", "동아리 친구 민수는 누구야?"),
        ("동아리 민수는 어디 갔어?", "동아리 민수는 어디 갔어?"),
        ("그건 됐고 제주 여행은 며칠이야?", "그건 됐고 제주 여행은 며칠이야?"),
    ],
)
def test_choice_resolves_original_question_without_overwriting_new_intent(
    chat,
    monkeypatch,
    question,
    expected,  # noqa: F811
):
    sid = chat.store.create_empty()["id"]
    mid, _ = chat.store.begin(sid, "first", "민수는 누구야?")
    chat.store.finish(
        sid,
        mid,
        {
            "status": "needs_clarification",
            "items": [
                {"text": "동아리 친구 민수", "citations": []},
                {"text": "회사 동료 민수", "citations": []},
            ],
        },
        [],
        {},
    )
    seen = []

    def generate(question, *args):
        seen.append(question)
        return {"status": "insufficient_evidence", "items": []}

    monkeypatch.setattr(chat, "generate", generate)
    chat.message(sid, "second", question, context_message_id=mid)
    assert seen == [expected]
    assert chat.store.get(sid)["messages"][-1]["question"] == question
