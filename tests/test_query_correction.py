import pytest

from pma.query_correction import fuse, validate
from test_search_explain import row, service

BASE = {"intent": "recall", "date_from": None, "date_to": None}
TODAY = "2026-10-19"


def edit(before, after, start=0, kind="spelling"):
    return {"start": start, "end": start + len(before), "before": before,
            "after": after, "kind": kind}


def test_bounded_spelling_and_unicode_offsets():
    question = "😀 회의 내욜 알려줘"
    result = validate(question, [edit("내욜", "내용", 5)], BASE, TODAY, [])
    assert result["query"] == "😀 회의 내용 알려줘"
    assert result["status"] == "applied"


@pytest.mark.parametrize(("before", "after"), [
    ("민수", "민서"), ("10월", "11월"), ("15만", "150만"),
    ("안", ""), ("취소", "완료"), ("했던", "하려던"), ("API", "앱"),
    ("내용", "일정"), ("ㅇㄷ", "운동"), ("내욜이", "내용이"),
])
def test_protected_or_unverified_expressions(before, after):
    assert validate(before, [edit(before, after)], BASE, TODAY, [])["status"] == "rejected"


def test_known_name_and_partial_name_are_protected():
    record = row(1)
    record["fact"]["actor"] = "내욜"
    assert validate("내욜", [edit("내욜", "내용")], BASE, TODAY, [record])["status"] == "rejected"
    assert validate("내욜은", [edit("내욜", "내용")], BASE, TODAY, [])["status"] == "rejected"


def test_spacing_and_invalid_spans():
    assert validate("회의내용", [edit("회의내용", "회의 내용", kind="spacing")], BASE, TODAY, [])["status"] == "applied"
    assert validate("내욜", [edit("내욜", "내용", 1)], BASE, TODAY, [])["status"] == "rejected"
    assert validate("내욜", [edit("내욜", "내용")]*2, BASE, TODAY, [])["status"] == "rejected"


def test_duplicate_query_never_doubles_score():
    assert fuse([1, 2], [1, 2]) == fuse([1, 2], [])
    assert fuse([1], [2])[2] == 0.8 / 61


def configured(records):
    svc = service(records)
    svc.models.understand = lambda *args: {**BASE, "corrections": [edit("내욜", "내용", 3)]}
    calls = []
    def embed(texts):
        calls.append(texts)
        return [[1, 0] for _ in texts]
    svc.models.embed = embed
    return svc, calls


def test_search_batch_provenance_and_same_filter_scope():
    records = [row(1, "회의 내용"), row(2, "회의 내용")]
    records[1]["fact"]["event_time"]["start"] = "2025-01-01"
    svc, calls = configured(records)
    _, found = svc._search("회의 내욜", {"date_from": "2026-01-01", "date_to": None}, TODAY)
    assert calls == [["회의 내욜", "회의 내용"]]
    assert [r["id"] for r in found["results"]] == ["1"]
    assert found["query_correction"]["status"] == "applied"
    assert found["query_correction"]["original_query"] == "회의 내욜"
    assert found["query_correction"]["searched"] is True
    info = found["results"][0]["search_explanation"]
    assert info["query"] == "회의 내욜"
    assert any(m["term"] == "내용" for m in info["corrected_retrieval"]["keyword_matches"])


def test_disable_and_invalid_edit_keep_original_search():
    svc, calls = configured([row(1)])
    _, result = svc._search("회의 내욜", today=TODAY, correction_enabled=False)
    assert calls == [["회의 내욜"]]
    assert result["query_correction"]["reason"] == "disabled"
    assert result["query_correction"]["searched"] is False
    _, result = svc._search("다른 질문", today=TODAY)
    assert result["query_correction"]["status"] == "rejected"
    assert calls[-1] == ["다른 질문"]


def test_empty_candidates_still_report_correction():
    svc, calls = configured([])
    _, result = svc._search("회의 내욜", today=TODAY)
    assert result["query_correction"]["status"] == "applied"
    assert result["query_correction"]["searched"] is False
    assert not calls and not result["results"]


def test_batch_embedding_failure_retries_original_only():
    svc, _ = configured([row(1)])
    calls = []
    def embed(texts):
        calls.append(texts)
        if len(texts) == 2:
            raise ValueError("bad alternate embedding")
        return [[1, 0]]
    svc.models.embed = embed
    _, found = svc._search("회의 내욜", today=TODAY)
    assert calls == [["회의 내욜", "회의 내용"], ["회의 내욜"]]
    assert found["query_correction"]["reason"] == "embedding_failed"
    assert found["query_correction"]["searched"] is False
    assert found["results"]


def test_constraint_changing_edit_is_rejected():
    assert validate("여햄 언제", [edit("여햄", "여행")], BASE, TODAY, [])["status"] == "rejected"


def test_api_passes_opt_out_and_defaults_without_breaking_existing_clients():
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from pma.chat.api import router
    from pma.web import Input, QueryInput
    seen = []
    app = FastAPI()
    app.include_router(router(Input, QueryInput))
    def message(*args, **kwargs):
        seen.append(kwargs)
        return {"message_id": "m"}
    app.state.chat = SimpleNamespace(message=message, search=message)
    with TestClient(app) as client:
        for enabled in (True, False):
            response = client.post('/api/v1/chat/sessions/s/messages', json={
                "request_id": str(enabled), "question": "회의 내욜", "correction_enabled": enabled})
            assert response.status_code == 200
        response = client.post('/api/v1/chat/searches', json={
            "question": "회의 내욜", "correction_enabled": False})
        assert response.status_code == 200
    assert seen == [{}, {"correction_enabled": False}, {"correction_enabled": False}]


def test_opt_out_is_part_of_retry_identity(tmp_path):
    from pma.chat.store import ChatStore
    from pma.store import Store
    from pma.errors import AppError
    chat = ChatStore(Store(tmp_path / "correction.db"))
    sid = chat.create_empty()["id"]
    chat.begin(sid, "r", "회의 내욜", correction_enabled=False)
    with pytest.raises(AppError, match="REQUEST_CONFLICT"):
        chat.begin(sid, "r", "회의 내욜")
