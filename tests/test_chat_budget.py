"""Request deadlines cover all model calls and transactional publication."""

from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_chat import chat, seed  # noqa: F401

from pma.errors import AppError
from scripts.memory_agent import llm_client


def test_transport_uses_remaining_budget_and_rejects_late_response(monkeypatch):
    clock = [10.0]
    monkeypatch.setattr(llm_client, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    timeouts = []

    def post(*args, **kwargs):
        timeouts.append(kwargs["timeout"])
        clock[0] += 3
        return SimpleNamespace(status_code=200, json=lambda: {})

    session = SimpleNamespace(post=post)
    with llm_client.request_budget(5) as budget:
        llm_client.post_json(session, "http://127.0.0.1:8081/tokenize", {}, 180)
        with pytest.raises(llm_client.RequestDeadlineExceeded):
            llm_client.post_json(session, "http://127.0.0.1:8081/tokenize", {}, 180)
        assert timeouts == [5, 2]
        assert len(budget.calls) == 2
    # Context cleanup must not affect ordinary search, indexing, or later turns.
    llm_client.post_json(session, "http://127.0.0.1:8081/tokenize", {}, 180)
    assert timeouts[-1] == 180


def test_deadline_rolls_back_answer_and_can_retry(chat, monkeypatch):  # noqa: F811
    _, _, session = seed(chat)
    original = chat.store.finish

    def expire_before_commit(*args, **kwargs):
        budget = kwargs["budget"]
        budget.deadline = 0
        return original(*args, **kwargs)

    monkeypatch.setattr(chat.store, "finish", expire_before_commit)
    with pytest.raises(AppError, match="CHAT_TIMEOUT") as error:
        chat.message(session["id"], "retry", "어떻게 했지?")
    assert error.value.retryable and error.value.status == 504
    message = chat.store.get(session["id"])["messages"][0]
    assert message["state"] == "failed" and message["response"] is None
    assert message["evidence"] == [] and message["snapshot"] == {}
    with chat.service.store.connect() as db:
        assert db.execute("SELECT count(*) FROM chat_citations").fetchone()[0] == 0
    monkeypatch.setattr(chat.store, "finish", original)
    result = chat.message(session["id"], "retry", "어떻게 했지?")
    assert result["status"] == "answered"
    assert len(chat.store.get(session["id"])["messages"]) == 1


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), 3601])
def test_invalid_request_budget(chat, value):  # noqa: F811
    with pytest.raises(ValueError, match="INVALID_CHAT_TIMEOUT"):
        replace(chat.service.settings, chat_timeout=value).validate()
