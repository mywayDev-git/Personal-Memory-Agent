import copy
import json

import pytest
from conftest import memory

from pma.facts import compatible, query_plan
from pma.service import Service
from scripts.memory_agent.diagnostics import ProcessingError, failure
from scripts.memory_agent.provenance import normalize_time, sentences


def test_temporal_sentence_scope_and_precision():
    units = sentences("어제 수빈은 파스타를 원했다. 나는 아직 메뉴를 정하지 않았다.")
    first = memory()
    first["time"]["raw"] = "어제"
    second = copy.deepcopy(first)
    normalize_time(first, units[:1], "2026-07-15T20:00:00+09:00")
    normalize_time(second, units[1:], "2026-07-15T20:00:00+09:00")
    assert first["time"]["start"] == "2026-07-14"
    assert first["time"]["precision"] == "day"
    assert second["time"]["start"] is None
    first["time"]["raw"] = "토요일 오후 2시"
    normalize_time(
        first, sentences("2026-06-01 토요일 오후 2시로 약속을 잡았다."), "2026-06-01T20:00:00+09:00"
    )
    assert first["time"]["start"] is None


def test_role_direction_and_unresolved_anchor():
    p = query_plan("당시 지연에게 선물을 이미 줬나?", {"intent": "recall"}, "2026-10-13")
    assert p["needs_time_anchor"]
    f = dict(relation="give", actor="지연", recipient=None, state="observed", distance_m=[])
    assert not compatible(f, p)
    f.update(actor="self", recipient="지연")
    assert compatible(f, p)
    assert (
        query_plan("2026-06-01 기준 독서 모임 약속은?", {"intent": "recall"}, "2026-10-13")[
            "relation"
        ]
        != "give"
    )


def test_diagnostic_does_not_leak_exception_value():
    code, diagnostic = failure(ValueError("private diary secret"), "extract")
    assert code == "INTERNAL_PROCESSING_ERROR"
    assert "private" not in json.dumps(diagnostic)
    error = ProcessingError("MODEL_TRUNCATED", "extract", usage={"completion_tokens": 4096})
    assert failure(error, "unknown")[1]["usage"]["completion_tokens"] == 4096


def test_chunk_resume_no_partial_publication_and_edit_invalidation(store, settings, models):
    models.prompt = "test"
    models.raw_schema = {}
    models.count_tokens = lambda text: len(text)
    calls = []

    def extract(text, context, source_units, target_ids):
        calls.append(target_ids)
        if target_ids == ["s6"] and len(calls) == 2:
            raise ProcessingError("EVIDENCE_MISMATCH", "evidence")
        picked = [u for u in source_units if u["id"] in target_ids]
        return {"memories": [memory(u["text"]) for u in picked]}, {
            "provenance": [{"evidence": [{"start": u["start"], "end": u["end"]}]} for u in picked]
        }

    models.extract = extract
    rid = store.create("첫 기록. 둘 기록. 셋 기록. 넷 기록. 다섯 기록. 여섯 기록. 마지막.", None)[
        "record_id"
    ]
    service = Service(store, models, settings)
    service.run_one()
    assert store.get(rid)["status"] == "failed"
    assert not store.snapshot(settings.embedding_key)[1]
    store.retry(rid)
    service.run_one()
    assert store.get(rid)["status"] == "ready"
    assert calls.count(["s0", "s1", "s2", "s3", "s4", "s5"]) == 1
    assert len(store.get(rid)["memories"]) == 7
    store.update(rid, 1, text="수정된 기록.")
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM extraction_chunks").fetchone()[0] == 0


@pytest.mark.parametrize(
    "reference,expected",
    [
        ("2026-01-01T00:01:00+09:00", "2025-12-31"),
        ("2024-03-01T20:00:00+09:00", "2024-02-29"),
        ("2026-07-14T16:00:00+00:00", "2026-07-14"),
    ],
)
def test_relative_date_calendar_boundaries(reference, expected):
    m = memory()
    m["time"]["raw"] = "어제"
    normalize_time(m, sentences("어제 달렸다."), reference)
    assert m["time"]["start"] == expected


def test_date_header_and_following_day():
    units = sentences("2026-04-01\n나는 달렸다.\n다음 날 산책했다.")
    m = memory()
    m["time"]["raw"] = None
    normalize_time(m, [units[1]], None)
    assert m["time"]["start"] == "2026-04-01"
    m["time"]["raw"] = "다음 날"
    normalize_time(m, [units[2]], None)
    assert m["time"]["start"] == "2026-04-02"


def test_repeated_evidence_position_preserved(store, settings):
    text = "달렸다. 달렸다."
    rid = store.create(text, None)["record_id"]
    job = store.claim()
    import numpy as np

    store.publish(
        job,
        [memory("달렸다.")],
        np.array([[1, 0, 0]]),
        settings.embedding_key,
        {"provenance": [{"evidence": [{"start": 5, "end": 9}]}]},
    )
    row = store.snapshot(settings.embedding_key)[1][0]
    assert row["evidence"][0]["start"] == 5
    assert row["record_id"] == rid


def test_temporal_korean_date_and_no_reference():
    m = memory()
    m["time"]["raw"] = "2026년 7월 14일"
    normalize_time(m, sentences("2026년 7월 14일에 달렸다."), None)
    assert m["time"]["start"] == "2026-07-14"
    m["time"]["raw"] = "어제"
    normalize_time(m, sentences("어제 달렸다."), None)
    assert m["time"]["start"] is None


def test_role_constraints_apply_to_final_answer(store, settings, models):
    from test_relational_memory import insert

    insert(store, settings, "나는 지연에게 빨간색 머그컵을 줬다.", actor="self", when="2026-04-07")
    insert(
        store,
        settings,
        "지연은 빨간색 컵을 선물했다. 받은 사람은 내가 아니라 동생이다.",
        actor="지연",
        when="2026-06-05",
    )
    service = Service(store, models, settings)
    answer = service.answer("지연에게 선물을 줬나?")
    assert len(answer["items"]) == 1
    assert "사용자" in answer["items"][0]["text"]
    assert "2026-06-05" not in answer["items"][0]["text"]
    answer = service.answer("당시 지연에게 선물을 이미 줬나?")
    assert answer["status"] == "insufficient_evidence"
    assert answer["clarification"]
    assert query_plan("누가 선물했지?", {"intent": "recall"}, "2026-10-13")["actor"] is None


def test_connection_failure_pauses_worker(store, settings, models):
    import requests

    models.failure = requests.ConnectionError()
    store.create("모델 연결이 안 되는 동안 남긴 기록", None)
    store.create("대기해야 할 다음 기록", None)
    service = Service(store, models, settings)
    service.run_one()
    assert service.worker_paused
    assert store.processing_progress()["queued"] == 1


def test_context_limit_adapts_chunks(store, settings, models):
    from pma.errors import AppError

    models.prompt = "test"
    models.raw_schema = {}
    models.count_tokens = lambda text: len(text)
    calls = []

    def extract(text, context, source_units, target_ids):
        calls.append(target_ids)
        if len(target_ids) > 1:
            raise AppError("CONTEXT_LIMIT", "too long")
        picked = [u for u in source_units if u["id"] in target_ids]
        return {"memories": [memory(u["text"]) for u in picked]}, {
            "provenance": [{"evidence": [{"start": u["start"], "end": u["end"]}]} for u in picked]
        }

    models.extract = extract
    rid = store.create("첫 기록. 두 번째 기록.", None)["record_id"]
    Service(store, models, settings).run_one()
    record = store.get(rid)
    assert record["status"] == "ready"
    assert calls == [["s0", "s1"], ["s0"], ["s1"]]
    assert record["processing_details"]["recovered_diagnostics"][0]["code"] == "CONTEXT_LIMIT"


@pytest.mark.parametrize("always_invalid", [False, True])
def test_sentence_pipeline_repair_is_bounded(monkeypatch, always_invalid):
    from config.settings import Settings, paths
    from scripts.memory_agent import pipeline
    from scripts.memory_agent.validator import load_schema

    calls = []

    def extract(**kwargs):
        calls.append(kwargs)
        m = memory()
        m.pop("local_id")
        m["evidence"] = [{"sentence_id": "s0"}]
        if len(calls) == 1 or always_invalid:
            m["object"]["value"] = None
        return {"memories": [m]}, {}, 1.0

    monkeypatch.setattr(pipeline, "extract_memories", extract)
    args = dict(
        prompt="extract",
        output_schema=load_schema(paths.output_schema),
        final_schema=load_schema(paths.final_schema),
        session=None,
        settings=Settings(),
        source_units=sentences("담당자를 정했다. 주변 문장."),
        target_ids=["s0"],
    )
    if always_invalid:
        with pytest.raises(ProcessingError) as error:
            pipeline.process_text(
                "담당자를 정했다. 주변 문장.",
                {"source_id": "x", "reference_time": None, "language": "ko"},
                **args,
            )
        assert error.value.diagnostic["previous_attempts"]
    else:
        result, meta = pipeline.process_text(
            "담당자를 정했다. 주변 문장.",
            {"source_id": "x", "reference_time": None, "language": "ko"},
            **args,
        )
        assert result["memories"][0]["evidence"] == [{"quote": "담당자를 정했다."}]
        assert meta["repair_attempts"] and meta["latency_seconds"] == 2
    assert len(calls) == 2
    assert calls[0]["output_schema"]["$defs"]["evidence_item"]["properties"]["sentence_id"][
        "enum"
    ] == ["s0"]
