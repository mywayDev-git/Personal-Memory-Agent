import copy
import sqlite3

import pytest
from test_chat import chat, seed  # noqa: F401

from pma.chat.automatic import CHECK, GENERAL, LAYOUT, NEXT, ROUTE, display_block
from pma.chat.store import ChatStore
from pma.errors import AppError
from pma.store import Store


def test_timeline_requires_explicit_unambiguous_dates():
    items = [{"text": "2026년 7월 20일 취소했다."}, {"text": "2026-07-19 계획했다."}]
    assert display_block("일정 변경을 보여줘", items) == {
        "type": "timeline",
        "item_indices": [1, 0],
    }
    items[0]["text"] = "나중에 취소했다."
    assert display_block("일정 변경을 보여줘", items)["type"] == "list"
    items[0]["text"] = "2026년 2월 30일 취소했다."
    assert display_block("일정 변경을 보여줘", items)["type"] == "list"


@pytest.fixture
def automatic(chat, models):  # noqa: F811
    chat.fixed_evidence = False
    original = models.structured
    models.route_mode = "memory"
    models.route_query = None
    models.additional = []
    models.seen = []
    models.safe = True

    def structured(prompt, data, schema, max_tokens=None):
        models.seen.append((schema, copy.deepcopy(data)))
        if schema == ROUTE:
            return {
                "mode": models.route_mode,
                "query": models.route_query
                or ("" if models.route_mode == "general" else data["current_question"]),
            }
        if schema == NEXT:
            return {"query": models.additional.pop(0) if models.additional else ""}
        if schema == GENERAL:
            return {"text": getattr(models, "general_text", "안녕하세요. 편하게 이야기해 주세요.")}
        if schema == CHECK:
            return {"safe": models.safe}
        if schema == LAYOUT:
            return {"style": "paragraph"}
        return original(prompt, data, schema)

    models.structured = structured
    return chat


def test_empty_session_general_then_memory(client, automatic, models):
    sid = client.post("/api/v1/chat/sessions", json={}).json()["id"]
    models.route_mode = "general"
    original = automatic.service._search
    automatic.service._search = lambda *a, **kw: pytest.fail("general chat searched")
    r = automatic.message(sid, "greet", "안녕")
    assert r["conversation_type"] == "general" and r["items"][0]["citations"] == []
    automatic.service._search = original
    rid = automatic.service.store.create("담당자를 정했다.", None)["record_id"]
    automatic.service.run_one()
    models.route_mode = "memory"
    r = automatic.message(sid, "recall", "어떻게 했지?")
    assert r["status"] == "answered"
    saved = ChatStore(Store(automatic.service.store.path)).get(sid)
    assert saved["messages"][0]["evidence"] == []
    assert saved["messages"][1]["evidence"][0]["record_id"] == rid
    assert saved["messages"][1]["snapshot"]["searches"]
    assert automatic.message(sid, "recall", "어떻게 했지?") == r
    assert client.delete("/api/v1/chat/sessions/" + sid).status_code == 204


def test_followup_uses_new_query_and_bounded_search(automatic, models):
    _, _, selected = seed(automatic)
    models.route_query = "지연이는 나와 어떤 관계야?"
    models.additional = ["지연이 초등학교 관계", "지연이 친구", "never"]
    queries = []
    original = automatic.service._search

    def search(query, **kw):
        queries.append(query)
        return original(query, **kw)

    automatic.service._search = search
    automatic.message(selected["id"], "followup", "지연이가 누구야?")
    assert queries == ["지연이는 나와 어떤 관계야?", "지연이 초등학교 관계", "지연이 친구"]
    assert all("서울" not in q for q in queries)
    assert not any(schema == LAYOUT for schema, _ in models.seen)


def test_new_record_is_retrieved_even_when_previous_sources_unchanged(automatic, models):
    rid, _, session = seed(automatic)
    automatic.message(session["id"], "first", "어떻게 했지?")
    newer = automatic.service.store.create("담당자를 정하지 않았다.", None)["record_id"]
    automatic.service.run_one()
    automatic.message(session["id"], "followup", "어떻게 했지?")
    latest = automatic.store.get(session["id"])["messages"][-1]
    assert {row["record_id"] for row in latest["evidence"]} == {rid, newer}


def test_relationship_paraphrase_searches_missing_relationship(automatic, models):
    _, _, session = seed(automatic)
    response = automatic.message(session["id"], "relationship", "그 친구는 나하고 어떤 사이인데?")
    assert response["conversation_type"] == "memory"
    searches = automatic.store.get(session["id"])["messages"][-1]["snapshot"]["searches"]
    assert searches[-1]["question"] == "나의 지인들과 어떤 관계인지 알려줘"


def test_general_answer_cannot_claim_missing_records(automatic, models):
    models.route_mode = "general"
    models.general_text = "개인 기록에 명시되지 않았습니다."
    session = automatic.store.create_empty()
    response = automatic.message(session["id"], "missing", "다른 이야기를 해볼까?")
    assert response["conversation_type"] == "general"
    assert response["status"] == "insufficient_evidence"
    assert response["items"] == []
    assert automatic.store.get(session["id"])["messages"][-1]["snapshot"]["searches"] == []


def test_travel_topic_switch_cannot_skip_search(automatic, models):
    models.route_mode = "general"
    session = automatic.store.create_empty()
    response = automatic.message(session["id"], "travel", "그건 됐고, 제주 여행은 며칠로 바뀌었어?")
    assert response["conversation_type"] == "memory"
    assert not any(schema == GENERAL for schema, _ in models.seen)


def test_explicit_comfort_request_is_preserved_with_memory_answer(automatic, models):
    _, _, session = seed(automatic)
    models.general_text = "너무 자책하지 마세요."
    response = automatic.message(session["id"], "mixed", "담당자는 정했어? 위로도 해줘.")
    assert response["conversation_type"] == "mixed"
    assert response["items"][0]["citations"]
    assert response["items"][-1] == {
        "text": "너무 자책하지 마세요.",
        "citations": [],
        "source_type": "inference",
    }
    check_data = next(data for schema, data in models.seen if schema == CHECK)
    assert check_data["mode"] == "mixed"


def test_request_date_is_part_of_idempotency_and_survives_restart(automatic, models):
    models.route_mode = "general"
    session = automatic.store.create_empty()
    original = automatic.message(session["id"], "date", "안녕", "2026-10-18")
    automatic.store = ChatStore(Store(automatic.service.store.path))
    assert automatic.message(session["id"], "date", "안녕", "2026-10-18") == original
    with pytest.raises(AppError, match="REQUEST_CONFLICT"):
        automatic.message(session["id"], "date", "안녕", "2026-10-19")
    assert automatic.store.get(session["id"])["messages"][0]["request_today"] == "2026-10-18"
    automatic.store.begin(session["id"], "pending", "질문", "2026-10-18")
    with pytest.raises(AppError, match="REQUEST_CONFLICT"):
        automatic.store.begin(session["id"], "pending", "질문", "2026-10-19")


def test_v4_migration_preserves_answers_and_unknown_legacy_request_date(automatic, models):
    models.route_mode = "general"
    session = automatic.store.create_empty()
    original = automatic.message(session["id"], "legacy", "안녕")
    with sqlite3.connect(automatic.service.store.path) as db:
        db.execute("ALTER TABLE chat_messages DROP COLUMN request_input")
        db.execute("PRAGMA user_version=4")
    automatic.store = ChatStore(Store(automatic.service.store.path))
    assert automatic.message(session["id"], "legacy", "안녕") == original
    assert automatic.store.get(session["id"])["messages"][0]["request_today"] is None


def test_modified_and_deleted_answers_leave_other_turns(automatic, models):
    rid, _, s = seed(automatic)
    automatic.message(s["id"], "memory", "어떻게 했지?")
    models.route_mode = "general"
    automatic.message(s["id"], "general", "고마워")
    automatic.service.store.update(rid, 1, "수정된 원문")
    saved = automatic.store.get(s["id"])
    assert saved["state"] == "active"
    assert saved["messages"][0]["error_code"] == "SOURCE_MODIFIED"
    assert saved["messages"][0]["evidence"][0]["source_text"] == "담당자를 정했다."
    automatic.message(s["id"], "continue", "안녕")
    route_data = [d for schema, d in models.seen if schema == ROUTE][-1]
    assert [h["question"] for h in route_data["history"]] == ["고마워"]
    automatic.service.store.trash(rid)
    saved = automatic.store.get(s["id"])
    assert saved["messages"][0]["response"] is None
    assert saved["messages"][0]["evidence"] == []
    assert saved["messages"][1]["response"]["items"]
    automatic.service.store.restore(rid)
    assert automatic.store.get(s["id"])["messages"][0]["response"] is None


@pytest.mark.parametrize("deleting", [False, True])
def test_change_during_generation_retries_without_stale_answer(automatic, models, deleting):
    rid, _, s = seed(automatic)

    def change():
        models.after_answer = None
        if deleting:
            automatic.service.store.trash(rid)
        else:
            automatic.service.store.update(rid, 1, "담당자를 다시 정했다.")
            automatic.service.run_one()

    # run_one owns the same model lock; only source mutation happens in this hook.
    if not deleting:

        def change():
            models.after_answer = None
            automatic.service.store.update(rid, 1, "담당자를 다시 정했다.")

    models.after_answer = change
    r = automatic.message(s["id"], "x", "어떻게 했지?")
    assert r["status"] == "insufficient_evidence"
    assert automatic.store.get(s["id"])["messages"][0]["evidence"] == []


def test_repeated_changes_fail_retryably(automatic, models):
    rid, _, s = seed(automatic)
    original = automatic.store.finish
    attempts = []

    def finish(*args, **kwargs):
        attempts.append(1)
        raise AppError("SOURCE_CHANGED", "changed", 409, True)

    automatic.store.finish = finish
    with pytest.raises(AppError, match="SOURCE_CHANGED"):
        automatic.message(s["id"], "x", "질문")
    assert len(attempts) == 2
    assert automatic.store.get(s["id"])["messages"][0]["response"] is None
    automatic.store.finish = original


def test_rejected_general_answer_never_searches_or_leaks(automatic, models):
    s = automatic.store.create_empty()
    models.route_mode, models.safe = "general", False
    response = automatic.message(s["id"], "x", "내 친구는?")
    assert response["conversation_type"] == "general"
    assert response["status"] == "insufficient_evidence"
    assert response["items"] == []


def test_v3_answers_migrate_and_preserve_citations(automatic):
    rid, _, s = seed(automatic)
    automatic.fixed_evidence = True
    automatic.message(s["id"], "x", "질문")
    with sqlite3.connect(automatic.service.store.path) as db:
        db.execute("DELETE FROM chat_message_evidence")
        db.execute("DELETE FROM chat_message_snapshots")
        db.execute("PRAGMA user_version=3")
    migrated = ChatStore(Store(automatic.service.store.path)).get(s["id"])
    assert migrated["messages"][0]["evidence"][0]["record_id"] == rid
    assert migrated["messages"][0]["response"]["citation_details"]


def test_aggregate_does_not_claim_complete_count(automatic, models):
    seed(automatic)
    automatic.service.models.intent = "aggregate"
    s = automatic.store.create_empty()
    r = automatic.message(s["id"], "x", "총 몇 번이야?")
    assert r["status"] == "insufficient_evidence"
    assert "집계" in r["notice"]


def test_model_cannot_route_a_search_query_to_general(automatic, models):
    seed(automatic)
    models.route_mode = "general"
    models.route_query = "어떻게 했지?"
    s = automatic.store.create_empty()
    response = automatic.message(s["id"], "x", "어떻게 했지?")
    assert response["conversation_type"] == "memory"
    assert automatic.store.get(s["id"])["messages"][0]["evidence"]


def test_explicit_roles_disambiguate_even_if_model_misses_it():
    from pma.chat.evidence import identity_alternatives

    rows = [
        {"id": "a", "source_text": "회사 동료 민수는 디자이너이다."},
        {"id": "b", "source_text": "동아리 친구 민수는 간호사이다."},
    ]
    assert len(identity_alternatives("민수가 누구야?", rows)) == 2
    assert identity_alternatives("동아리 친구 민수가 누구야?", rows) == []
    assert identity_alternatives("민수 둘의 차이는?", rows) == []
    assert identity_alternatives("지연이는 누구야?", rows) == []


def test_message_evidence_deleted_when_conversation_deleted(automatic):
    _, _, s = seed(automatic)
    automatic.message(s["id"], "x", "어떻게 했지?")
    automatic.store.delete(s["id"])
    with automatic.service.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM chat_message_evidence").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM chat_message_snapshots").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM chat_citations").fetchone()[0] == 0


def test_modified_turn_not_reintroduced_after_restart(automatic):
    rid, _, s = seed(automatic)
    automatic.message(s["id"], "x", "어떻게 했지?")
    automatic.service.store.update(rid, 1, "새 버전")
    restarted = ChatStore(Store(automatic.service.store.path))
    from pma.chat.automatic import history

    assert history(restarted.get(s["id"])) == []
    assert restarted.get(s["id"])["messages"][0]["evidence"][0]["version"] == 1


def test_invalid_semantic_quote_is_rejected_not_published(automatic, models):
    _, _, s = seed(automatic)
    original = models.review

    def invalid(question, evidence, response):
        review = original(question, evidence, response)
        for item in review["items"]:
            for ref in item["evidence"]:
                ref["quote"] = "원문에 없는 검토 인용"
        return review

    models.review = invalid
    response = automatic.message(s["id"], "bad-review", "어떻게 했지?")
    assert response["status"] == "insufficient_evidence"
    assert response["items"] == []
    assert not response.get("citation_details")


def test_repeated_lookup_broadens_missing_relation(automatic, models):
    _, _, s = seed(automatic)
    models.route_query = "지연이와의 관계"
    models.additional = ["지연이와의 관계", ""]
    queries = []
    original = automatic.service._search

    def search(query, **kwargs):
        queries.append(query)
        return original(query, **kwargs)

    automatic.service._search = search
    automatic.message(s["id"], "who", "지연이가 누구야?")
    assert queries == ["지연이와의 관계", "나의 지인들과 어떤 관계인지 알려줘"]


def test_event_and_its_reason_are_not_entity_alternatives(chat, models):  # noqa: F811
    _, _, s = seed(chat)
    row = s["evidence"][0]
    original = models.structured

    def resolve(prompt, data, schema, **kwargs):
        if "alternatives" in schema.get("properties", {}):
            return {
                "question": data["question"],
                "needs_clarification": True,
                "alternatives": [
                    {"label": label, "quote": row["source_text"], "evidence_id": row["id"]}
                    for label in ["담당자를 정했다.", "정했다."]
                ],
            }
        return original(prompt, data, schema, **kwargs)

    models.structured = resolve
    resolved, _ = chat.resolve("왜 정했지?", s, "2026-10-18")
    assert not resolved["needs_clarification"]


def test_evidence_cap_preserves_each_lookup_and_removes_duplicates():
    from pma.chat.automatic import combine

    a = [{"id": "a" + str(i)} for i in range(8)]
    b = [{"id": "b" + str(i)} for i in range(8)]
    selected = combine([a, b, a])
    assert len(selected) == 8
    assert len({r["id"] for r in selected}) == 8
    assert selected[:2] == [a[0], b[0]]


def test_direct_statement_requires_unique_explicit_source():
    from pma.chat.evidence import direct_statement

    row = {
        "id": "one",
        "source_text": "지연이는 나의 초등학교 동창이다.",
        "fact": {"object_key": "지연이"},
    }
    candidate = direct_statement("지연이가 누구야?", [row])
    assert candidate and row["source_text"] in candidate["items"][0]["text"]
    assert direct_statement("민수가 누구야?", [row]) is None
    other = {**row, "id": "two", "source_text": "지연이는 나의 직장 동료이다."}
    assert direct_statement("지연이가 누구야?", [row, other]) is None
    # Old causal wording in reference context must not change today's intent.
    assert direct_statement("그 선물 줬어? 참조: 머그컵을 본 이유", [row], "그 선물 줬어?") is None


def test_personal_schedule_does_not_fall_through_to_general(automatic, models):
    models.route_mode = "general"
    s = automatic.store.create_empty()
    response = automatic.message(s["id"], "schedule", "회의는 최종적으로 무슨 요일이야?")
    assert response["conversation_type"] == "memory"
    assert response["status"] == "insufficient_evidence"


def test_hypothetical_setup_is_not_accepted_as_a_record(automatic, models):
    s = automatic.store.create_empty()
    response = automatic.message(s["id"], "hypothetical", "예약했다고 가정해 보자.")
    assert response["conversation_type"] == "general"
    assert "가정" in response["items"][0]["text"]
    assert automatic.store.get(s["id"])["messages"][0]["evidence"] == []


def test_execution_lookup_does_not_inherit_observation_date_or_place():
    from pma.chat.automatic import search_question

    query = "2026년 7월 19일 서울숲에서 파란색 머그컵을 지연이에게 실제로 줬는지"
    relaxed = search_question("그 선물 실제로 줬어?", query)
    assert "2026" not in relaxed and "서울숲" not in relaxed
    assert "머그컵" in relaxed and "지연이" in relaxed
    assert "2026" in search_question("그날 실제로 줬어?", query)
    assert "2026" in search_question("7월 19일에 실제로 줬어?", query)


def test_explicit_uncertainty_quote_does_not_invent_execution():
    from pma.chat.evidence import direct_statement

    row = {
        "id": "x",
        "source_text": "회의는 화요일이다. 다른 기록에는 수요일이라고 되어 있어 최종 요일은 확인되지 않았다.",
        "fact": {"actor": "회의"},
    }
    answer = direct_statement("회의는 최종적으로 무슨 요일이야?", [row])
    assert answer and row["source_text"] in answer["items"][0]["text"]
    assert "열렸다" not in answer["items"][0]["text"]
    newer = {**row, "id": "y", "source_text": "회의는 수요일로 확정했다."}
    assert direct_statement("회의는 최종적으로 무슨 요일이야?", [row, newer]) is None
