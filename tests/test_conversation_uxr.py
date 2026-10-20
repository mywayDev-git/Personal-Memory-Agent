"""UXR policy contracts plus genuine authenticated API lifecycle checks."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from pma.chat.planner import enrich
from pma.settings import AppSettings
from pma.web import create_app


def source(key, text):
    return dict(id=key, record_id="r" + key, revision_id="v" + key, version=1, source_text=text)


def response(status="answered", items=None, kind=None, mode="memory"):
    result = {"status": status, "items": items or [], "conversation_type": mode}
    if kind:
        result["display"] = {
            "kind": kind,
            "verified": True,
            "items": [
                dict(
                    index=i,
                    state="unknown" if kind == "partial" and i == 1 else "confirmed",
                    event="",
                    event_date="",
                )
                for i in range(len(items or []))
            ],
        }
    return result


def plan(question, result, rows=None, mode="auto", metadata=None):
    return enrich(question, result, rows or [], "s", "m", 1, mode=mode, metadata=metadata)


def test_UXR01_clear_answer_has_no_choice():
    result = plan(
        "완료 여부 알려줘",
        response(items=[{"text": "API 완료", "citations": ["a"]}]),
        [source("a", "API 완료")],
    )
    assert not result["ui_actions"]


def test_UXR02_actual_ambiguity_uses_source_target_ids():
    result = plan(
        "민수는 누구야?",
        response(
            "needs_clarification",
            [
                {"text": "회사 민수", "citations": ["a"]},
                {"text": "동아리 민수", "citations": ["b"]},
            ],
        ),
        [source("a", "회사 민수"), source("b", "동아리 민수")],
    )
    assert [a["target_ids"] for a in result["ui_actions"]] == [["a"], ["b"]]
    assert result["primary_response_type"] == "CLARIFY" and not result["interpretation"]["facts"]


def test_UXR03_selected_followup_preserves_topic_feature():
    result = plan(
        "그건 왜?",
        response(items=[{"text": "확인된 이유", "citations": ["a"]}]),
        [source("a", "확인된 이유")],
        metadata={"route": {"reason_code": "MEMORY_FOLLOWUP"}},
    )
    assert "FOLLOW_UP" in result["response_features"]


def test_UXR04_same_fact_keeps_all_provenance_without_counting_independent_confirmation():
    result = plan(
        "이유 알려줘",
        response(items=[{"text": "API 완료", "citations": ["a", "b"]}], kind="same_event"),
        [source("a", "API 완료"), source("b", "API 완료")],
    )
    assert len(result["interpretation"]["facts"]) == 1 and len(result["evidence_refs"]) == 2
    assert result["answer_text"] == "API 완료"


def test_UXR05_latest_state_does_not_use_storage_date_as_event_time():
    result = plan(
        "마지막 상태",
        response(items=[{"text": "이전 기록 기준 진행 중", "citations": ["a"]}]),
        [{**source("a", "진행 중"), "recorded_at": "2026-10-20"}],
    )
    assert result["primary_response_type"] == "LATEST"
    assert (
        result["evidence_refs"][0]["event_time"] is None
        and result["memory_context"]["status_as_of"] == []
    )


def test_UXR06_only_reviewed_conflict_shows_comparison():
    result = plan(
        "상태 알려줘",
        response(items=[{"text": "상반된 기록", "citations": ["a", "b"]}], kind="conflict"),
        [source("a", "완료"), source("b", "완료 아님")],
    )
    assert result["primary_response_type"] == "CONFLICT"
    assert [a["type"] for a in result["ui_actions"]] == ["COMPARE", "SHOW_HISTORY"]


def test_UXR07_partial_answer_keeps_uncertainty():
    result = plan(
        "언제 왜?",
        response(
            items=[
                {"text": "10월 방문", "citations": ["a"]},
                {"text": "이유 미상", "citations": ["a"]},
            ],
            kind="partial",
        ),
        [source("a", "10월 방문")],
    )
    assert (
        result["primary_response_type"] == "PARTIAL"
        and result["uncertainty"][0]["claim"] == "이유 미상"
    )


def test_UXR08_empty_search_has_retry_and_no_fake_facts():
    result = plan("지난 기록", response("insufficient_evidence"))
    assert result["primary_response_type"] == "NO_EVIDENCE"
    assert [a["type"] for a in result["ui_actions"]] == ["RETRY_SEARCH"] and not result[
        "interpretation"
    ]["facts"]


def test_UXR09_resume_action_cannot_invent_curriculum():
    result = plan(
        "Python 다시 공부하려고",
        response(items=[{"text": "Part 1 공부 기록", "citations": ["a"]}]),
        [source("a", "Part 1 공부 기록")],
    )
    assert result["primary_response_type"] == "RESUME_ACTIVITY" and "Part 2" not in str(result)


def test_UXR10_recommendation_is_an_optional_suggestion():
    result = plan(
        "PMA 다음 단계",
        response(
            items=[
                {"text": "API 완료", "citations": ["a"]},
                {
                    "text": "테스트부터 검토할 수 있어요",
                    "citations": [],
                    "source_type": "inference",
                },
            ],
            mode="mixed",
        ),
        [source("a", "API 완료")],
    )
    assert result["interpretation"]["suggestions"][0]["basis_ids"] == ["a"]
    assert result["ui_actions"][-1]["type"] == "DISMISS"


def test_UXR11_expired_context_cannot_be_overridden_by_client():
    # API rejects additional target/query/type fields rather than trusting browser state.
    from fastapi import FastAPI

    from pma.chat.api import router
    from pma.web import Input, QueryInput

    app = FastAPI()
    app.include_router(router(Input, QueryInput))
    with TestClient(app) as client:
        result = client.post(
            "/api/v1/chat/sessions/s/actions/a",
            json={"request_id": "r", "expected_context_version": 1, "target_id": "other"},
        )
        assert result.status_code == 422


def test_UXR12_duplicate_import_returns_one_set_of_records(tmp_path):
    from pma.imports import TextImporter
    from pma.store import Store

    store = Store(tmp_path / "test.db")
    importer = TextImporter(store)
    preview = importer.preview("a.txt", "가상 원문")
    assert importer.commit(preview["import_id"], "r") == importer.commit(preview["import_id"], "r")
    assert len(store.list()["items"]) == 1


def test_UXR13_progress_confirmation_requires_preview():
    result = plan(
        "Python 진도 알려줘",
        response(items=[{"text": "학습 중", "citations": ["a"]}]),
        [source("a", "학습 중")],
    )
    action = next(a for a in result["ui_actions"] if a["type"] == "CONFIRM_PROGRESS")
    assert action["required_permissions"] == ["memory_write"] and action["source_versions"] == {
        "ra": 1
    }


def test_UXR14_exact_source_spans_are_preserved():
    result = response(items=[{"text": "가상 사실", "citations": ["a"]}])
    result["citation_details"] = [
        dict(memory_id="a", record_id="ra", revision_id="va", start=2, end=7, quote="가상 사실")
    ]
    plan("기록", result, [source("a", "😀 가상 사실")])
    assert result["evidence_refs"][0]["spans"] == result["citation_details"]


def test_UXR15_record_deletion_uses_expected_version(tmp_path):
    from pma.errors import AppError
    from pma.store import Store

    store = Store(tmp_path / "test.db")
    record = store.create("원문", None)
    store.update(record["record_id"], 1, text="수정 원문")
    with pytest.raises(AppError, match="VERSION_CONFLICT"):
        store.trash(record["record_id"], 1)
    assert store.get(record["record_id"])["state"] == "active"


def test_UXR16_general_chat_has_no_evidence_or_choices():
    result = plan("안녕", response(items=[{"text": "안녕하세요", "citations": []}], mode="general"))
    assert (
        result["primary_response_type"] == "GENERAL"
        and not result["evidence_refs"]
        and not result["ui_actions"]
    )


def test_UXR17_memory_refusal_overrides_automatic_mode():
    result = plan(
        "내 기록 말고 일반적으로",
        response(items=[{"text": "일반 설명", "citations": []}], mode="general"),
    )
    assert not result["memory_context"]["enabled"] and result["grounding_status"] == "suppressed"


def test_UXR18_search_failure_is_error_not_empty_evidence():
    from pma.web import error_response

    result = error_response("MODEL_OFFLINE", "검색 실패", 503, "r", True)
    import json

    payload = json.loads(result.body)
    assert payload["primary_response_type"] == "ERROR" and payload["error_state"]["retryable"]


def test_UXR19_mixed_sources_are_separate():
    result = plan(
        "설명",
        response(
            items=[
                {"text": "확인 사실", "citations": ["a"]},
                {"text": "일반적 제안", "citations": [], "source_type": "inference"},
            ],
            mode="mixed",
        ),
        [source("a", "확인 사실")],
    )
    assert (
        len(result["interpretation"]["facts"]) == 1
        and len(result["interpretation"]["suggestions"]) == 1
    )
    assert "HYBRID" in result["response_features"]


def test_UXR20_import_authentication_and_approval(tmp_path):
    app = create_app(AppSettings(data_dir=tmp_path), models=SimpleNamespace(), run_worker=False)
    origin = app.state.settings.origin
    with TestClient(app, base_url=origin) as client:
        assert (
            client.post(
                "/api/v1/imports/preview",
                headers={"Origin": origin},
                json={"filename": "a.txt", "text": "원문"},
            ).status_code
            == 401
        )
        auth = client.post(
            "/api/v1/session", headers={"Origin": origin}, json={"token": app.state.bootstrap_token}
        )
        headers = {"Origin": origin, "X-CSRF-Token": auth.json()["csrf"]}
        preview = client.post(
            "/api/v1/imports/preview", headers=headers, json={"filename": "a.txt", "text": "원문"}
        ).json()
        assert not app.state.store.list()["items"]
        path = "/api/v1/imports/" + preview["import_id"] + "/commit"
        assert (
            client.post(path, headers={"Origin": origin}, json={"request_id": "r"}).status_code
            == 403
        )
        assert client.post(path, headers=headers, json={"request_id": "r"}).status_code == 202
        assert len(app.state.store.list()["items"]) == 1
