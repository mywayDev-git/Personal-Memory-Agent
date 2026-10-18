# ruff: noqa: F811
import pytest
from test_automatic_chat import automatic  # noqa: F401
from test_chat import chat, seed  # noqa: F401

from pma.chat.automatic import GENERAL
from pma.errors import AppError


def test_explicit_general_never_searches_even_on_rejection(automatic, models):
    session = automatic.store.create_empty()
    models.safe = False
    automatic.service._search = lambda *a, **kw: pytest.fail("general searched")
    result = automatic.message(session["id"], "g", "내 여행은?", mode="general")
    assert result["conversation_mode"] == "general"
    assert result["items"] == []


def test_mode_persistence_and_retry_conflict(automatic, models):
    session = automatic.store.create_empty()
    result = automatic.message(session["id"], "g", "Python 설명해줘", mode="general")
    saved = automatic.store.get(session["id"])
    assert saved["mode"] == "general"
    assert saved["messages"][0]["mode"] == "general"
    assert automatic.message(session["id"], "g", "Python 설명해줘", mode="general") == result
    with pytest.raises(AppError, match="REQUEST_CONFLICT"):
        automatic.message(session["id"], "g", "Python 설명해줘", mode="memory")
    automatic.message(session["id"], "g2", "예제도 보여줘", mode="general")
    data = [d for schema, d in models.seen if schema == GENERAL][-1]
    assert data["history"][0]["question"] == "Python 설명해줘"


def test_hybrid_uses_verified_memory_before_suggestions(automatic, models):
    _, _, session = seed(automatic)
    result = automatic.message(session["id"], "h", "담당자 기록을 참고해 조언해줘", mode="hybrid")
    assert result["conversation_mode"] == "hybrid"
    assert result["items"][0]["source_type"] == "personal_memory"
    assert result["items"][-1]["source_type"] == "inference"
    data = [d for schema, d in models.seen if schema == GENERAL][-1]
    assert data["verified_memory"]


def test_api_rejects_invalid_mode(client, automatic):
    sid = automatic.store.create_empty()["id"]
    response = client.post(
        f"/api/v1/chat/sessions/{sid}/messages",
        json={"request_id": "x", "question": "hello", "mode": "invalid"},
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "mode,route,expected",
    [
        ("general", "memory", 0),
        ("auto", "general", 0),
        ("memory", "general", 1),
        ("hybrid", "general", 1),
    ],
)
def test_search_and_generation_call_counts(automatic, models, mode, route, expected):
    _, _, session = seed(automatic)
    models.route_mode = route
    searches = []
    original = automatic.service._search

    def search(*args, **kwargs):
        searches.append(args[0])
        return original(*args, **kwargs)

    automatic.service._search = search
    result = automatic.message(session["id"], "count", "담당자에 대해 설명해줘", mode=mode)
    assert len(searches) == expected
    assert result["conversation_mode"] == ("general" if expected == 0 else mode)
    assert len([s for s, _ in models.seen if s == GENERAL]) == (0 if mode == "memory" else 1)


def test_auto_transitions_and_restart_context(automatic, models):
    from pma.chat.automatic import ROUTE
    from pma.chat.store import ChatStore
    from pma.store import Store

    _, _, session = seed(automatic)
    sid = session["id"]
    models.route_mode = "general"
    automatic.message(sid, "one", "Python 비동기를 설명해줘")
    models.route_mode = "hybrid"
    models.route_query = "내가 만들던 프로젝트"
    result = automatic.message(sid, "two", "내 프로젝트에도 적용할 수 있어?")
    assert result["conversation_mode"] == "hybrid"
    models.route_query = None
    models.route_mode = "general"
    automatic.store = ChatStore(Store(automatic.service.store.path))
    automatic.service._search = lambda *a, **kw: pytest.fail("general followup searched")
    automatic.message(sid, "three", "간단한 예제만 보여줘")
    route = [d for s, d in models.seen if s == ROUTE][-1]
    assert [m["question"] for m in route["history"]] == [
        "Python 비동기를 설명해줘",
        "내 프로젝트에도 적용할 수 있어?",
    ]


def test_hybrid_without_records_does_not_invent_memory(automatic, models):
    sid = automatic.store.create_empty()["id"]
    result = automatic.message(sid, "none", "내 취향으로 계획해줘", mode="hybrid")
    assert result["status"] == "insufficient_evidence"
    assert all(i["source_type"] == "inference" and not i["citations"] for i in result["items"])
    assert [d for s, d in models.seen if s == GENERAL][-1]["verified_memory"] == []


def test_hybrid_does_not_repeat_personal_claim_without_citation(automatic, models):
    from pma.chat.automatic import general

    models.general_text = (
        "당신이 개발하는 프로젝트는 검색 요청을 순차적으로 처리하는 구조입니다. 더 빠릅니다."
    )
    result = general(
        automatic,
        {
            "mode": "mixed",
            "question": "조언해줘",
            "verified_memory": [
                {
                    "text": "기록에 따르면, 당신이 개발하는 프로젝트는 검색 요청을 순차적으로 처리하는 구조입니다."
                }
            ],
        },
    )
    assert result is None


def test_hybrid_rejects_uncited_record_attribution(automatic, models):
    from pma.chat.automatic import general

    models.general_text = "기록에 따르면, 사용자의 프로젝트는 순차 처리 방식입니다."
    assert (
        general(automatic, {"mode": "mixed", "question": "조언해줘", "verified_memory": []}) is None
    )
