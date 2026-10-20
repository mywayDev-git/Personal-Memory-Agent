"""Source interpretation, refusal and real SQLite action/import lifecycle regressions."""

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from evaluation.conversation_cases import cases
from pma.chat.actions import ActionManager
from pma.chat.automatic import run
from pma.chat.interpretation import analyze
from pma.chat.planner import ACTION_TYPES, RESPONSE_TYPES, enrich
from pma.chat.policy import memory_disabled, private_context
from pma.chat.router import RetrievalRouter
from pma.chat.store import ChatStore
from pma.errors import AppError
from pma.imports import TextImporter
from pma.store import Store


@pytest.fixture
def chat(tmp_path):
    return ChatStore(Store(tmp_path / "memory.db"))


def grounded_turn(
    chat,
    question="Python 이어서 공부하자",
    request="first",
    text="Python Part 1을 완료했다.",
    display=None,
):
    sid = chat.create_empty()["id"]
    record = chat.store.create(text, None)
    with chat.store.connect() as db:
        revision = db.execute(
            "SELECT id FROM revisions WHERE record_id=?", (record["record_id"],)
        ).fetchone()[0]
    evidence = [
        dict(
            id="m1",
            record_id=record["record_id"],
            revision_id=revision,
            version=1,
            source_text=text,
        )
    ]
    mid, _ = chat.begin(sid, request, question)
    response = {
        "status": "answered",
        "items": [{"text": text, "citations": ["m1"]}],
        "citation_details": [
            dict(
                item_index=0,
                memory_id="m1",
                record_id=record["record_id"],
                revision_id=revision,
                quote=text,
                start=0,
                end=len(text),
            )
        ],
    }
    if display:
        response["display"] = display
    chat.finish(sid, mid, response, evidence)
    return sid, mid, record, chat.get(sid)["messages"][0]["response"]


@pytest.mark.parametrize(
    "question",
    [
        "내 기록 말고 일반적으로 알려줘",
        "내 기억 없이 설명해줘",
        "기억을 사용하지 말아줘",
        "기록 쓰지 말아줘",
    ],
)
def test_memory_refusal_precedes_all_routes(question):
    assert memory_disabled(question)
    assert (
        RetrievalRouter().decide(question, explicit_search=True, force_memory=True).mode
        == "CHAT_ONLY"
    )


def test_latest_recorded_decision_is_not_general_knowledge():
    route = RetrievalRouter().decide(
        "PMA 검색 방식 마지막 결정 알려줘",
        classify=lambda: pytest.fail("general classifier called"),
    )
    assert route.mode == "MEMORY_REQUIRED" and route.reason_code == "RECORDED_STATE"


def test_past_record_explanation_is_explicit_recall():
    route = RetrievalRouter().decide(
        "Python 지난 기록 자연스럽게 설명해줘",
        classify=lambda: pytest.fail("general classifier called"),
    )
    assert route.mode == "MEMORY_REQUIRED"


def test_refusal_scrubs_all_recalled_sources_and_assistant_claims():
    original = {
        "context": {"summary": "private"},
        "evidence": [{"source_text": "private"}],
        "snapshot": {"secret": "x"},
        "messages": [
            {
                "question": "이전 질문",
                "mode": "memory",
                "response": {"items": [{"text": "private"}]},
            },
            {
                "question": "일반 문맥",
                "mode": "general",
                "response": {"items": [{"text": "private"}]},
            },
        ],
    }
    result = private_context(original)
    assert "private" not in str(result)
    assert original["context"]["summary"] == "private"


def test_general_turn_never_reads_preferences_or_searches(monkeypatch):
    from pma.chat import automatic

    monkeypatch.setattr(
        "pma.memory.repository.MemoryRepository.preferences",
        lambda *a: pytest.fail("preference read"),
    )
    observed = []

    class Models:
        def count_tokens(self, *a):
            return 1

        def structured(self, prompt, data, schema, max_tokens=None):
            observed.append(data)
            return (
                {"safe": True}
                if schema == automatic.CHECK
                else {"text": "기초 개념부터 차근차근 설명할게요."}
            )

    engine = SimpleNamespace(
        models=Models(),
        service=SimpleNamespace(
            store=object(),
            trace=lambda *a, **k: None,
            settings=SimpleNamespace(context_tokens=10000),
        ),
    )
    response, evidence, metadata = run(
        engine, "내 기록 말고 일반적으로 설명해줘", {"messages": []}, "2026-10-20", "hybrid"
    )
    assert not evidence and not metadata["searches"]
    assert all(not d.get("saved_style_preferences") for d in observed)
    assert response["conversation_type"] == "general"


def test_short_social_reply_is_not_empty_when_model_echoes():
    from pma.chat import automatic

    class Models:
        def count_tokens(self, *args):
            return 1

        def structured(self, prompt, data, schema, max_tokens=None):
            assert schema == automatic.GENERAL
            return {"text": data["current_question"]}

    engine = SimpleNamespace(
        models=Models(),
        service=SimpleNamespace(
            store=object(),
            trace=lambda *a, **k: None,
            settings=SimpleNamespace(context_tokens=10000),
        ),
    )
    response, evidence, metadata = run(engine, "고마워", {"messages": []}, "2026-10-20", "general")
    assert response["items"] and response["items"][0]["text"] != "고마워"
    assert not evidence


def test_no_search_record_absence_claim_is_rejected_even_if_model_approves():
    from pma.chat import automatic

    class Models:
        def count_tokens(self, *args):
            return 1

        def structured(self, prompt, data, schema, max_tokens=None):
            return (
                {"safe": True}
                if schema == automatic.CHECK
                else {"text": "현재 기록이 비어 있어서 구체적인 내용을 제공할 수 없습니다."}
            )

    engine = SimpleNamespace(
        models=Models(),
        service=SimpleNamespace(store=object(), settings=SimpleNamespace(context_tokens=10000)),
    )
    assert (
        automatic.general(
            engine, {"question": "일반 설명", "mode": "general", "memory_disabled": True}
        )
        is None
    )


@pytest.mark.parametrize("case", cases(), ids=lambda c: c["id"])
def test_nat_source_interpretation_does_not_promote_unverified_progress(case):
    evidence = [
        dict(id=r["id"], record_id=r["id"], version=1, source_text=r["text"])
        for r in case["records"]
    ]
    result = analyze(case["message"], evidence)
    assert result["next_step"] is None
    assert all(o["status"] == "unknown" for o in result["observations"])
    assert {o["claim"] for o in result["observations"]} == {r["text"] for r in case["records"]}


@pytest.mark.parametrize(
    "text",
    [
        "Python 공부했다",
        "Python 완료 여부는 모른다",
        "Python 완료하지 않았다",
        "Python 완료했다고 AI가 잘못 답했다",
        "Python 완료했다면 좋겠다",
    ],
)
def test_interpreter_rejects_false_completion_and_fake_fields(text):
    result = analyze(
        "진도",
        [dict(id="a", record_id="r", version=1, source_text=text)],
        {
            "observations": [
                dict(
                    memory_id="a",
                    quote=text,
                    status="completed",
                    event_time="2026-10-20",
                    subject="invented",
                    event="",
                    condition="",
                )
            ]
        },
    )
    assert result["observations"][0]["status"] == "unknown"
    assert not result["observations"][0]["subject"] and not result["observations"][0]["event_time"]


def test_unknown_quote_and_unreviewed_display_cannot_create_facts_or_conflicts():
    response = {
        "status": "answered",
        "items": [{"text": "일반 설명", "citations": []}],
        "display": {"kind": "conflict", "items": []},
    }
    enrich("설명", response, [], "s", "m", 1)
    assert response["primary_response_type"] != "CONFLICT"
    assert not response["interpretation"]["facts"]
    result = analyze(
        "진도",
        [dict(id="a", record_id="r", version=1, source_text="공부했다")],
        {"observations": [dict(memory_id="a", quote="완료했다", status="completed")]},
    )
    assert result["observations"][0]["claim"] == "공부했다"


def test_all_response_and_action_types_are_declared():
    assert len(RESPONSE_TYPES) == 27 and len(ACTION_TYPES) == 16


def test_sensitive_sources_require_relevant_explicit_topic():
    from pma.chat.policy import source_allowed

    row = {"source_text": "정신 건강 진료 기록"}
    assert not source_allowed("오늘 뭐부터 하지?", row)
    assert source_allowed("지난 진료 기록 알려줘", row)


def test_empty_topic_scope_never_sends_empty_review_enum():
    from pma.chat.engine import ChatEngine

    engine = ChatEngine.__new__(ChatEngine)
    engine.models = object()
    engine.resolve = lambda question, *args, **kwargs: (
        {"question": question, "needs_clarification": False},
        0,
    )
    result = engine.generate(
        "Python 공부 기록",
        {"evidence": [{"id": "a", "record_id": "r", "source_text": "Rust 공부 기록"}]},
        "2026-10-20",
    )
    assert result["status"] == "insufficient_evidence" and not result["items"]


@pytest.mark.parametrize(
    "question",
    [
        "Python 다시 공부하려고",
        "오랜만에 파이썬 다시 공부할까?",
        "Python 좀 공부하자",
        "Python Part 2 학습 진도와 마지막 공부 기록",
    ],
)
def test_resume_adverbs_are_not_the_study_topic(question):
    from pma.relevance import study_topic, topic_supported

    assert study_topic(question) == "python"
    assert topic_supported(question, {"source_text": "Python Part 1을 완료했다."})
    assert not topic_supported(question, {"source_text": "Rust Part 1을 완료했다."})


def test_unscoped_progress_is_not_assumed_to_be_a_python_record():
    from pma.relevance import topic_supported

    assert not topic_supported(
        "Python Part 2 학습 기록",
        {"source_text": "AI가 Part 2 완료라고 잘못 답했다. Part 1만 공부했다."},
    )


def test_explicit_conflict_guard_preserves_dates_projects_and_conditions():
    from pma.chat.interpretation import explicit_completion_conflicts

    positive = {"id": "a", "source_text": "2026-10-10 PMA API 설계를 완료했다."}
    negative = {"id": "b", "source_text": "2026-10-10 PMA API 설계는 완료하지 않았다."}
    assert explicit_completion_conflicts([positive, negative]) == [["a", "b"]]
    assert not explicit_completion_conflicts(
        [positive, {**negative, "source_text": negative["source_text"].replace("PMA", "YOLO")}]
    )
    assert not explicit_completion_conflicts(
        [positive, {**negative, "source_text": negative["source_text"].replace("10-10", "10-15")}]
    )
    assert not explicit_completion_conflicts(
        [
            {**positive, "source_text": "PMA API 설계를 완료했다."},
            {**negative, "source_text": "PMA API 설계는 완료하지 않았다."},
        ]
    )


def test_clear_answer_has_no_actions_and_resume_does_not_invent_part_two(chat):
    sid, mid, record, response = grounded_turn(chat, question="Python 기록 알려줘")
    assert not response["ui_actions"] and response["answer_text"] == "Python Part 1을 완료했다."
    sid, mid, record, response = grounded_turn(chat)
    assert [a["type"] for a in response["ui_actions"]] == ["CONTINUE", "REVIEW"]
    assert "Part 2" not in str(response)


def test_action_idempotency_restart_expiry_and_owner_isolation(chat):
    sid, mid, record, response = grounded_turn(chat, question="Python 마지막 진행 상황 알려줘")
    aid = response["ui_actions"][0]["action_id"]
    manager = ActionManager(SimpleNamespace(store=chat))
    result = manager.run(sid, aid, "request", 1)
    assert result["effect"] == "history"
    assert (
        ActionManager(SimpleNamespace(store=ChatStore(Store(chat.store.path)))).run(
            sid, aid, "request", 1
        )
        == result
    )
    with pytest.raises(AppError, match="ACTION_RESOLVED"):
        manager.run(sid, aid, "new-request", 1)
    with pytest.raises(AppError, match="NOT_FOUND"):
        ActionManager(SimpleNamespace(store=ChatStore(chat.store, "foreign"))).run(
            sid, aid, "request", 1
        )
    chat.store.update(record["record_id"], 1, text="Python 공부 중")
    with pytest.raises(AppError, match="ACTION_EXPIRED"):
        manager.run(sid, aid, "request", 1)
    with chat.store.connect() as db:
        assert (
            db.execute("SELECT result FROM chat_ui_actions WHERE id=?", (aid,)).fetchone()[0]
            is None
        )


def test_multiple_tabs_cannot_execute_old_context(chat):
    sid, mid, record, response = grounded_turn(chat)
    chat.update_context(sid, {"active_topic": "다른 주제"}, 1)
    aid = response["ui_actions"][0]["action_id"]
    with pytest.raises(AppError, match="ACTION_EXPIRED"):
        ActionManager(SimpleNamespace(store=chat)).run(sid, aid, "request", 1)
    assert chat.get(sid)["messages"][0]["response"]["ui_actions"][0]["state"] == "EXPIRED"


def test_double_click_has_one_result_and_no_record_mutation(chat):
    sid, mid, record, response = grounded_turn(chat, question="Python 마지막 진도 알려줘")
    aid = response["ui_actions"][0]["action_id"]
    manager = ActionManager(SimpleNamespace(store=chat))

    def click(_):
        try:
            return manager.run(sid, aid, "same", 1)["effect"]
        except AppError as exc:
            return exc.code

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(click, range(2)))
    assert "history" in results and set(results) <= {"history", "ACTION_BUSY"}
    assert chat.store.get(record["record_id"])["version"] == 1


def test_followup_runs_with_server_target_and_expected_context(chat):
    sid, mid, record, response = grounded_turn(chat)
    calls = []

    def message(sid, request, question, today, anchor, mode, **kwargs):
        calls.append((question, anchor, kwargs))
        new, _ = chat.begin(
            sid, request, question, expected_context_version=kwargs["expected_context_version"]
        )
        chat.finish(sid, new, {"status": "answered", "items": []}, [])
        return {"message_id": new}

    manager = ActionManager(SimpleNamespace(store=chat, message=message))
    aid = response["ui_actions"][0]["action_id"]
    first = manager.run(sid, aid, "same", 1)
    assert manager.run(sid, aid, "same", 1) == first and len(calls) == 1
    assert calls[0][1] == mid and calls[0][2]["expected_context_version"] == 1
    assert "Python" in calls[0][0] and "Part 2" not in calls[0][0]


def test_source_delete_expires_actions_and_removes_private_answer(chat):
    sid, mid, record, response = grounded_turn(chat, question="Python 마지막 진도 알려줘")
    aid = response["ui_actions"][0]["action_id"]
    chat.store.trash(record["record_id"], expected_version=1)
    assert chat.get(sid)["messages"][0]["response"] is None
    with pytest.raises(AppError, match="ACTION_EXPIRED"):
        ActionManager(SimpleNamespace(store=chat)).run(sid, aid, "same", 1)
    chat.store.restore(record["record_id"])
    assert chat.store.get(record["record_id"])["state"] == "active"


def test_retry_after_failure_does_not_resolve_or_modify_record(chat):
    sid, mid, record, response = grounded_turn(chat)

    def message(*args, **kwargs):
        raise AppError("CHAT_TIMEOUT", "시간 초과", 504, True)

    manager = ActionManager(SimpleNamespace(store=chat, message=message))
    aid = response["ui_actions"][0]["action_id"]
    with pytest.raises(AppError, match="CHAT_TIMEOUT"):
        manager.run(sid, aid, "same", 1)
    assert chat.get(sid)["messages"][0]["response"]["ui_actions"][0]["state"] == "ACTIVE"
    assert chat.store.get(record["record_id"])["version"] == 1


@pytest.mark.parametrize("kind", sorted(ACTION_TYPES))
def test_all_server_authored_action_types_keep_source_record_unchanged(chat, kind):
    import json

    sid, mid, record, response = grounded_turn(chat)
    action = response["ui_actions"][0]
    action.update(type=kind, query="2026-10-10의 기록", target_ids=["m1"])
    with chat.store.connect(True) as db:
        db.execute(
            "UPDATE chat_ui_actions SET payload=? WHERE id=?",
            (json.dumps(action), action["action_id"]),
        )
    calls = []

    def message(*args, **kwargs):
        calls.append((args, kwargs))
        return {"message_id": "followup"}

    manager = ActionManager(SimpleNamespace(store=chat, message=message))
    result = manager.run(sid, action["action_id"], "request", 1)
    assert result["state"] == "RESOLVED"
    assert chat.store.get(record["record_id"])["version"] == 1
    assert chat.store.get(record["record_id"])["state"] == "active"
    if kind == "SAVE_PROGRESS":
        assert result["effect"] == "save_preview"
        assert result["candidates"][0]["lifecycle_status"] == "pending"
    elif kind in {"CONFIRM_PROGRESS", "CORRECT_RECORD"}:
        assert result["effect"] == "record_preview"
    elif calls:
        assert calls[0][0][4] == mid
        assert calls[0][1]["expected_context_version"] == 1
        if kind == "EXPAND_SCOPE":
            assert calls[0][1]["filters"] == {"date_from": None, "date_to": None}


def test_action_id_cannot_be_reused_in_another_session(chat):
    sid, mid, record, response = grounded_turn(chat)
    other = chat.create_empty()["id"]
    with pytest.raises(AppError, match="NOT_FOUND"):
        ActionManager(SimpleNamespace(store=chat)).run(
            other, response["ui_actions"][0]["action_id"], "r", 1
        )


def test_referenced_save_action_reuses_the_real_previous_message_candidates(chat):
    from pma.memory.api import natural_candidates

    sid = chat.create_empty()["id"]
    first, _ = chat.begin(sid, "first", "PMA API 설계를 완료했어")
    chat.finish(
        sid,
        first,
        {
            "status": "answered",
            "items": [{"text": "다음 작업을 검토할 수 있어요", "citations": []}],
        },
        [],
    )
    mid, _ = chat.begin(sid, "save", "이거 저장해줘")
    chat.finish(sid, mid, {"status": "answered", "items": []}, [])
    delivered = natural_candidates(chat.store, sid, mid, "이거 저장해줘", "auto")
    response = chat.get(sid)["messages"][-1]["response"]
    action = next(a for a in response["ui_actions"] if a["type"] == "SAVE_PROGRESS")
    result = ActionManager(SimpleNamespace(store=chat)).run(
        sid, action["action_id"], "save-action", 2
    )
    assert {c["candidate_id"] for c in result["candidates"]} == {
        c["candidate_id"] for c in delivered
    }
    assert all(c["message_ids"] == [first] for c in result["candidates"])
    assert not chat.store.list()["items"]


def test_cached_save_preview_never_resurrects_a_deleted_source(chat):
    import json

    sid, first, record, _ = grounded_turn(chat)
    mid, _ = chat.begin(sid, "save", "이거 저장해줘")
    chat.finish(sid, mid, {"status": "answered", "items": []}, [])
    action = next(
        a
        for a in chat.get(sid)["messages"][-1]["response"]["ui_actions"]
        if a["type"] == "SAVE_PROGRESS"
    )
    manager = ActionManager(SimpleNamespace(store=chat))
    manager.run(sid, action["action_id"], "same", 2)
    with chat.store.connect() as db:
        cached = json.loads(
            db.execute(
                "SELECT result FROM chat_ui_actions WHERE id=?", (action["action_id"],)
            ).fetchone()[0]
        )
    assert "candidates" not in cached and cached["candidate_ids"]
    chat.store.trash(record["record_id"])
    with pytest.raises(AppError, match="SOURCE_CHANGED"):
        manager.run(sid, action["action_id"], "same", 2)


def test_upload_atomic_idempotent_offsets_and_lifecycle(chat, monkeypatch):
    importer = TextImporter(chat.store)
    text = "😀 한글 Markdown\n" * 520
    preview = importer.preview("study.md", text)
    assert not chat.store.list()["items"]
    assert "".join(p["text"] for p in preview["chunks"]) == text
    assert all(len(p["text"]) <= 4000 for p in preview["chunks"])
    original = chat.store.queue

    def fail(*args):
        raise RuntimeError("injected queue failure")

    monkeypatch.setattr(chat.store, "queue", fail)
    with pytest.raises(RuntimeError):
        importer.commit(preview["import_id"], "first")
    assert not chat.store.list()["items"]
    monkeypatch.setattr(chat.store, "queue", original)
    result = importer.commit(preview["import_id"], "first")
    assert importer.commit(preview["import_id"], "first") == result
    for item in result["records"]:
        location = item["source_location"]
        assert (
            chat.store.get(item["record_id"])["text"] == text[location["start"] : location["end"]]
        )
    with chat.store.connect() as db:
        assert db.execute("SELECT source FROM record_imports").fetchone()[0] == ""


@pytest.mark.parametrize(
    "filename,text",
    [("../a.md", "x"), ("a.pdf", "x"), ("a.txt", " "), ("a.txt", "x\0"), ("a.md", "가" * 400000)],
    ids=["path", "format", "blank", "nul", "size"],
)
def test_upload_invalid_content(chat, filename, text):
    with pytest.raises(AppError, match="INVALID_IMPORT"):
        TextImporter(chat.store).preview(filename, text)


def test_memory_only_mode_never_adds_general_suggestions(monkeypatch):
    from pma.chat import automatic

    monkeypatch.setattr(
        "pma.chat.retrieval.retrieve", lambda *a, **kw: (None, {"results": [], "status": "ok"})
    )

    class Models:
        def count_tokens(self, *args):
            return 1

        def structured(self, prompt, data, schema, max_tokens=None):
            assert schema == automatic.NEXT
            return {"query": "" if data.get("searches") else "Python 학습 진도"}

    engine = SimpleNamespace(
        models=Models(),
        store=SimpleNamespace(freeze=lambda rows: rows),
        service=SimpleNamespace(
            trace=lambda *a, **kw: None,
            settings=SimpleNamespace(context_tokens=10000, embedding_key="test"),
        ),
    )
    response, _, _ = run(engine, "Python 다시 공부하려고", {"messages": []}, "2026-10-20", "memory")
    assert response["conversation_type"] == "memory" and not response["items"]


def test_greeting_does_not_force_memory_search_in_memory_mode():
    route = RetrievalRouter().decide("안녕", force_memory=True)
    assert route.mode == "CHAT_ONLY"


def test_progress_lookup_does_not_need_a_general_suggestion_stage():
    assert RetrievalRouter().decide("Python 마지막 진도 알려줘").mode == "MEMORY_REQUIRED"
    assert (
        RetrievalRouter().decide("Python 진도 확인하고 다음 단계 계획 세워줘").mode
        == "MEMORY_AUGMENTED"
    )


def test_latest_progress_draft_is_bounded_to_one_explicit_course_and_event_date():
    from pma.chat.interpretation import dated_progress_draft

    rows = [
        {
            "id": "old",
            "source_text": "2026-10-10 Python Part 1을 완료했다.",
            "recorded_at": "2026-10-20",
        },
        {
            "id": "new",
            "source_text": "2026-10-15 Python Part 2를 완료했다.",
            "recorded_at": "2026-10-16",
        },
    ]
    draft = dated_progress_draft("Python 마지막 진도 알려줘", rows)
    assert draft["items"][0]["citations"] == ["new"]
    assert rows[1]["source_text"] in draft["items"][0]["text"]
    assert "Part 3" not in str(draft)
    assert dated_progress_draft("Rust 마지막 진도 알려줘", rows) is None
    assert dated_progress_draft("Python Part 1 마지막 진도", rows) is None
    assert (
        dated_progress_draft(
            "Python 마지막 진도",
            rows + [{"id": "cancel", "source_text": "Python 학습을 취소했다."}],
        )
        is None
    )
    assert (
        dated_progress_draft(
            "Python 마지막 진도",
            [rows[0], {**rows[1], "source_text": "2026-10-15 Rust Part 2를 완료했다."}],
        )
        is None
    )


def test_general_generation_never_receives_unverified_interpretation():
    from pma.chat import automatic

    seen = []

    class Models:
        def count_tokens(self, *args):
            return 1

        def structured(self, prompt, data, schema, max_tokens=None):
            seen.append(data)
            return (
                {"safe": True}
                if schema == automatic.CHECK
                else {"text": "일반적인 복습 계획부터 세울 수 있어요."}
            )

    engine = SimpleNamespace(
        models=Models(),
        service=SimpleNamespace(store=object(), settings=SimpleNamespace(context_tokens=10000)),
    )
    automatic.general(
        engine,
        {
            "question": "공부 계획",
            "mode": "mixed",
            "memory_disabled": True,
            "verified_memory": [],
            "history": [
                {
                    "question": "지난 작업",
                    "response": {
                        "conversation_mode": "memory",
                        "items": [{"text": "검증 전 개인 사실"}],
                    },
                }
            ],
            "memory_interpretation": {"observations": [{"claim": "검증 전 개인 사실"}]},
        },
    )
    assert seen and all("memory_interpretation" not in data for data in seen)
    assert all(not data["history"][0]["response"]["items"] for data in seen)


def test_memory_refusal_preserves_safe_general_conversation_context():
    session = {
        "messages": [
            {
                "mode": "auto",
                "response": {
                    "conversation_type": "general",
                    "items": [
                        {"text": "일반 예제 설명", "source_type": "general", "citations": []},
                        {"text": "개인 기록", "source_type": "personal_memory", "citations": ["a"]},
                    ],
                },
            }
        ]
    }
    safe = private_context(session)
    assert [i["text"] for i in safe["messages"][0]["response"]["items"]] == ["일반 예제 설명"]


def test_progress_citation_cannot_invent_a_different_part_or_hide_explicit_date():
    from pma.chat.evidence import semantic_issue

    rows = [{"id": "a", "source_text": "2026-10-15 Python Part 2를 완료했다."}]
    assert (
        semantic_issue(
            "Python 마지막 진도", {"text": "Part 1 날짜는 미상입니다.", "citations": ["a"]}, rows
        )
        == "other"
    )
    assert (
        semantic_issue(
            "Python 마지막 진도",
            {"text": "Part 2 완료 날짜는 기록에 명시되지 않았습니다.", "citations": ["a"]},
            rows,
        )
        == "time"
    )
    assert (
        semantic_issue(
            "Python 마지막 진도",
            {"text": "기록상 2026-10-15 Python Part 2를 완료했다.", "citations": ["a"]},
            rows,
        )
        is None
    )
