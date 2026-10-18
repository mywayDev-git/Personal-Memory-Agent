"""Must pass before production instrumentation exists; frozen behavior, not new policy."""

import json
from pathlib import Path

import pytest

from pma.facts import query_plan
from pma.models import LocalModels
from pma.service import Service

from .helpers import Models, SnapshotStore, row, run
from .test_filter_contract import FILTER_CASES


@pytest.mark.parametrize("scenario,question,changes,filters,reason", FILTER_CASES)
def test_filter_contract_inputs_reach_existing_exclusion(
    settings, scenario, question, changes, filters, reason
):
    item = row(**changes)
    if scenario == "missing":
        item["fact"] = None
    if scenario == "unknown_time":
        item["fact"]["event_time"] = dict(start=None, end=None, certainty="uncertain")
    events = []
    result, calls, _ = run(settings, [item], question=question, filters=filters, sink=events.append)
    assert result["results"] == []
    assert [c[0] for c in calls] == ["understand"]
    legacy_reason = {
        "fact_missing": "facts_pending",
        "relation_mismatch": "relation_state_or_quantity",
        "person_mismatch": "relation_state_or_quantity",
        "status_mismatch": "relation_state_or_quantity",
        "quantity_mismatch": "relation_state_or_quantity",
        "place_mismatch": "location",
        "time_unknown": "unknown_filtered_date",
        "time_mismatch": "date_range",
    }.get(reason, reason)
    assert [(e["id"], e["reason"]) for e in events if e["stage"] == "excluded"] == [
        (item["id"], legacy_reason)
    ]


def test_current_rrf_order_overlap_top_k_and_calls(settings):
    events = []
    response, model_calls, store_calls = run(
        settings, [row(i) for i in reversed(range(30))], sink=events.append
    )
    merged = next(e["candidates"] for e in events if e["stage"] == "retrieval_merge")
    assert [r["id"] for r in merged] == [f"memory-{i:02d}" for i in range(20)]
    assert [r["score"] for r in merged] == [2 / (60 + rank) for rank in range(1, 21)]
    assert [r["id"] for r in response["results"]] == [f"memory-{i:02d}" for i in range(8)]
    assert response["items"] == [
        dict(text="합성 답변", citations=["memory-00"], claim_kind="record", relation_ids=[])
    ]
    assert [c[0] for c in model_calls] == ["understand", "embed", "select", "answer", "verify"]
    assert [c[0] for c in store_calls] == [
        "snapshot",
        "links",
        "assert_generation",
        "assert_generation",
    ]


def test_structural_bonus_admits_beyond_dense_top_k(settings):
    events = []
    response, calls, _ = run(
        settings,
        [row(i, relation="run") for i in range(30)],
        question="달린 기록",
        sink=events.append,
    )
    merged = next(e["candidates"] for e in events if e["stage"] == "retrieval_merge")
    assert len(merged) == 24
    assert merged[0]["score"] == 1 / 61 + 1 / 60
    assert merged[20]["score"] == 1 / 60
    assert len(response["results"]) == 8
    assert [c[0] for c in calls] == ["understand", "embed"]


@pytest.mark.parametrize("mode", ["none", "capture", "broken"])
def test_legacy_sink_does_not_change_result_or_call_counts(settings, mode):
    rows = [row(i) for i in range(10)]
    expected = run(settings, rows)
    events = []

    def broken(event):
        raise OSError("PRIVATE SINK ERROR")

    actual = run(
        settings, rows, sink={"none": None, "capture": events.append, "broken": broken}[mode]
    )
    assert actual == expected


@pytest.mark.parametrize(
    "options,status,call_names",
    [
        ({"selected": []}, "insufficient_evidence", ["understand", "embed", "select"]),
        (
            {"selected": ["memory-00", "memory-00"]},
            "answered",
            ["understand", "embed", "select", "answer", "verify"],
        ),
        (
            {"verified": False},
            "insufficient_evidence",
            ["understand", "embed", "select", "answer", "verify"],
        ),
        (
            {"error": "understand"},
            "answered",
            ["understand", "embed", "select", "answer", "verify"],
        ),
    ],
)
def test_selection_fallback_and_verification_paths(settings, options, status, call_names):
    response, calls, _ = run(settings, [row()], **options)
    assert response["status"] == status
    assert [c[0] for c in calls] == call_names


@pytest.mark.parametrize(
    "options,message",
    [
        ({"selected": ["not-in-evidence"]}, "INVALID_SELECTION"),
        ({"error": "select"}, "INVALID_SELECTION_RESPONSE"),
        ({"error": "answer"}, "INVALID_ANSWER"),
    ],
)
def test_model_errors_keep_original_exception(settings, options, message):
    with pytest.raises(ValueError, match=message):
        run(settings, [row()], **options)


def test_empty_and_clarification_have_different_executed_paths(settings):
    response, calls, store_calls = run(settings, [])
    assert response["status"] == "insufficient_evidence"
    assert [c[0] for c in calls] == ["understand"]
    assert [c[0] for c in store_calls] == ["snapshot", "assert_generation"]
    response, calls, store_calls = run(settings, [row()], question="그때 synthetic")
    assert response["validation"] == "unresolved_time_anchor"
    assert response["clarification"] and response["results"]
    assert [c[0] for c in calls] == ["understand", "embed", "select"]
    assert [c[0] for c in store_calls] == ["snapshot", "links", "assert_generation"]


def test_query_plan_time_anchor_policy_is_preserved():
    plan = query_plan(
        "그때 서울숲에서 지연이 원한 선물이 뭐였지?",
        dict(intent="recall", date_from=None, date_to=None),
        "2026-10-17",
    )
    assert plan["needs_time_anchor"] is True
    assert plan["relation"] == "desire"


def test_local_selection_batches_and_final_limit(settings, monkeypatch):
    gateway = LocalModels(settings)
    calls = []

    def structured(prompt, data, schema, max_tokens=None):
        ids = schema["properties"]["ids"]["items"]["enum"]
        calls.append((ids, max_tokens))
        return {"ids": ids}

    monkeypatch.setattr(gateway, "compact_evidence", lambda evidence: [])
    monkeypatch.setattr(gateway, "structured", structured)
    assert gateway.select("synthetic", [row(i) for i in range(10)]) == [
        f"memory-{i:02d}" for i in range(8)
    ]
    assert calls == [
        ([f"memory-{i:02d}" for i in range(start, min(start + 4, 10))], 512) for start in (0, 4, 8)
    ]


@pytest.mark.parametrize(
    "case_id", ["synonym_when", "number_less", "unit_conversion", "unknown_when"]
)
def test_existing_case_retrieval_with_synthetic_projected_facts(settings, case_id):
    # The real dataset labels are RECORD aliases, not database memory IDs.
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
        aliases[rows[-1]["record_id"]] = alias
    result = Service(SnapshotStore(rows), Models(), settings).search(
        case["question"], today=data["today"]
    )
    observed = {aliases[r["record_id"]] for r in result["results"]}
    assert set(case["relevant"]) <= observed
    if case_id in {"number_less", "unit_conversion"}:
        assert observed == {"units"}
