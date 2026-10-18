import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from pma import diagnostics as d
from pma.errors import AppError
from pma.service import Service
from tests.test_answer_review import Gateway

from .helpers import Models, SnapshotStore, row, run


def test_fusion_limit_keeps_dropped_ids_and_real_components(settings):
    with d.start_trace(enabled=True) as trace:
        result, _, _ = run(
            settings, [row(i, relation="run") for i in range(30)], question="달린 기록"
        )
    event = next(e for e in trace.events if e["stage"] == "rank_fusion")
    assert event["input_count"] == 30 and event["output_count"] == 24
    assert len([c for c in event["candidates"] if c.get("reason") == "candidate_limit"]) == 6
    assert event["candidates"][0]["score_components"] == dict(
        vector=1 / 61, keyword=0, role=0, structure=1 / 60
    )
    assert len(result["results"]) == 8


def test_instrumentation_failure_preserves_answer_and_calls(settings, monkeypatch):
    expected = run(settings, [row()])
    with d.start_trace(enabled=True) as trace:

        def fail(*args, **kwargs):
            raise RuntimeError("PRIVATE")

        monkeypatch.setattr(trace, "memory_ref", fail)
        assert run(settings, [row()]) == expected
    assert d.current_trace() is None


def test_parallel_requests_on_one_service_are_isolated(settings, tmp_path):
    path = tmp_path / "parallel.jsonl"
    service = Service(
        SnapshotStore([row()]), Models(), replace(settings, diagnostics=True, diagnostics_path=path)
    )
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(
            pool.map(lambda _: service.answer("synthetic", today="2026-10-17"), range(6))
        )
    assert all(r == results[0] for r in results)
    events = [json.loads(line) for line in path.read_text("utf-8").splitlines()]
    ids = {e["trace_id"] for e in events}
    assert len(ids) == 6
    for trace_id in ids:
        request = [e for e in events if e["trace_id"] == trace_id]
        assert len([e for e in request if e["stage"] == "final_decision"]) == 1
        assert request[-1]["status"] == "answer"


def test_aggregate_marks_retrieval_unexecuted(settings):
    models = Models()
    models.understand = lambda *args: dict(intent="aggregate", date_from=None, date_to=None)
    with d.start_trace(enabled=True) as trace:
        result = Service(SnapshotStore([row()]), models, settings).answer(
            "총 몇 번?", today="2026-10-17"
        )
    assert result["status"] == "unsupported_intent"
    retrieval = next(e for e in trace.events if e["stage"] == "vector_retrieval")
    assert retrieval["status"] == "not_executed"
    assert retrieval["input_count"] is None
    assert trace.events[-1]["reason"] == "unsupported_intent"


@pytest.mark.parametrize("failure", ["select", "answer"])
def test_error_stage_observed_without_response_leak(settings, failure):
    with d.start_trace(enabled=True) as trace:
        with pytest.raises(ValueError):
            run(settings, [row()], error=failure)
    expected_stage = "evidence_selection" if failure == "select" else "answer_generation"
    assert any(e["stage"] == expected_stage and e["status"] == "error" for e in trace.events)
    assert trace.events[-1]["stage"] == "final_decision"
    assert trace.events[-1]["status"] == "error"


def test_role_bonus_is_measured_without_changing_rank(settings):
    models = Models()
    models.understand = lambda *args: dict(
        intent="recall", date_from=None, date_to=None, actor={"value": "민수", "evidence": "민수"}
    )
    service = Service(SnapshotStore([row(actor="민수")]), models, settings)
    with d.start_trace(enabled=True) as trace:
        result = service.search("민수 synthetic", today="2026-10-17")
    candidate = next(e for e in trace.events if e["stage"] == "rank_fusion")["candidates"][0]
    assert candidate["score_components"]["role"] == pytest.approx(1 / 600)
    assert candidate["score"] == result["results"][0]["score"]


@pytest.mark.parametrize("failures", [0, 1, 2])
def test_review_repair_preserves_calls_and_response(settings, failures):
    def execute(enabled):
        gateway = Gateway(failures)
        gateway.found.update(status="ok", connections=[])
        service = Service(
            SimpleNamespace(assert_generation=lambda _: None),
            gateway,
            replace(settings, answer_validation=True),
        )
        service._search = lambda *args: (1, gateway.found)
        with d.start_trace(enabled=enabled) as trace:
            response = service.answer("현재 어디 살아?")
        return response, gateway.calls, trace

    expected, calls, _ = execute(False)
    actual, observed_calls, trace = execute(True)
    assert actual == expected and observed_calls == calls
    summary = [e for e in trace.events if e["stage"] == "answer_validation"][-1]
    assert summary["retry_count"] == min(failures, 1)
    assert trace.events[-1]["status"] == ("abstention" if failures == 2 else "answer")


def test_source_change_is_not_misreported_as_relation_failure(settings):
    store = SnapshotStore([row()])
    original = AppError("SOURCE_CHANGED", "PRIVATE", 409, True)

    def fail(_):
        raise original

    store.assert_generation = fail
    with d.start_trace(enabled=True) as trace:
        with pytest.raises(AppError) as caught:
            Service(store, Models(), settings).answer("synthetic")
    assert caught.value is original
    assert trace.events[-2]["stage"] == "source_validation"
    assert trace.events[-1]["reason"] == "source_changed"
    assert not any(e["stage"] == "relation_lookup" and e["status"] == "error" for e in trace.events)


@pytest.mark.parametrize(
    "case_id", ["synonym_when", "number_less", "unit_conversion", "unknown_when"]
)
def test_oracle_survives_observed_search_stages(settings, case_id):
    data = json.loads(
        (Path(__file__).parents[2] / "data/search_diagnostics.json").read_text("utf-8")
    )
    case = next(c for c in data["questions"] if c["id"] == case_id)
    specs = [
        ("fight", "conflict", "2026-10-12", []),
        ("run5", "run", "2026-10-04", ["5000"]),
        ("units", "run", "2026-10-09", ["3000"]),
        ("unknown_date", "conflict", None, []),
    ]
    rows, aliases = [], {}
    for index, (alias, relation, when, distances) in enumerate(specs):
        source = next(r for r in data["records"] if r["id"] == alias)
        rows.append(
            row(index, text=source["text"], relation=relation, when=when, distance_m=distances)
        )
        aliases[alias] = rows[-1]["id"]
    with d.start_trace(enabled=True) as trace:
        Service(SnapshotStore(rows), Models(), settings).answer(
            case["question"], today=data["today"]
        )
    gold = {trace.memory_ref(aliases[alias]) for alias in case["relevant"]}

    def candidates(stage, statuses):
        return {
            c["memory_ref"]
            for e in trace.events
            if e["stage"] == stage
            for c in e.get("candidates", [])
            if c["status"] in statuses
        }

    assert gold <= candidates("structure_filter", {"included"})
    assert gold <= candidates("vector_retrieval", {"included"}) | candidates(
        "keyword_retrieval", {"included"}
    )
    assert gold <= candidates("rank_fusion", {"included"})
    assert gold <= candidates("evidence_selection", {"selected"})
    assert gold <= set(trace.events[-1]["citation_refs"])
