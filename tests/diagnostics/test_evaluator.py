from evaluation.diagnose_search import analyze, load_cases


def fixture(selected=("1",), unit="memory"):
    stages = [
        ("snapshot", ("1", "2", "3")),
        ("structure_filter", ("1", "2", "3")),
        ("vector_retrieval", ("1",)),
        ("keyword_retrieval", ("2",)),
        ("rank_fusion", ("1", "2")),
        ("evidence_selection", selected),
    ]
    events = [
        {
            "schema_version": "pma.search_trace.v1",
            "trace_id": "t",
            "event_sequence": i + 1,
            "stage": stage,
            "status": "completed",
            "candidates": [
                {
                    "memory_ref": f"memory-t-{n}",
                    "record_ref": f"record-t-{n}",
                    "status": "selected" if stage == "evidence_selection" else "included",
                    "rank": rank,
                }
                for rank, n in enumerate(ids, 1)
            ],
        }
        for i, (stage, ids) in enumerate(stages)
    ]
    events.append(
        {
            "schema_version": "pma.search_trace.v1",
            "trace_id": "t",
            "event_sequence": 7,
            "stage": "final_decision",
            "status": "abstention",
            "duration_ms": 12,
        }
    )
    case = {"id": "q", "unit": unit, "gold": [["a"], ["b"]], "has_expected": True}
    bindings = {"q": {"trace_id": "t", f"{unit}_refs": {"a": f"{unit}-t-1", "b": f"{unit}-t-2"}}}
    return events, case, bindings


def test_multi_evidence_union_and_selection_loss():
    events, case, bindings = fixture()
    summary, cases = analyze(events, [case], bindings, k=1)
    result = cases[0]
    assert result["stage_recall"]["retrieval_union"] == 1
    assert result["evidence_recall"] == 0.5
    assert result["complete_evidence_recall"] == 0
    assert result["loss_stage"] == "evidence_selection"
    assert summary["evaluable_questions"] == 1


def test_record_unit_only_with_source_links():
    events, case, bindings = fixture(unit="record")
    assert analyze(events, [case], bindings)[1][0]["evidence_recall"] == 0.5
    for e in events:
        for c in e.get("candidates", []):
            c.pop("record_ref", None)
    result = analyze(events, [case], bindings)[1][0]
    assert result["evidence_recall"] is None
    assert result["loss_stage"] == "unknown"


def test_missing_mapping_gold_and_truncation_are_not_failures():
    events, case, bindings = fixture()
    for gold, mapping, truncated in [
        ([], bindings, False),
        (case["gold"], {}, False),
        (case["gold"], bindings, True),
    ]:
        copy = [dict(e) for e in events]
        copy[-1]["truncated"] = truncated
        result = analyze(copy, [{**case, "gold": gold}], mapping)[1][0]
        assert result["evidence_recall"] is None and result["loss_stage"] == "unknown"
        assert result["evaluation_unavailable_reason"]


def test_answer_failure_and_clarification_require_labels():
    events, case, bindings = fixture(selected=("1", "2"))
    result = analyze(events, [case], bindings)[1][0]
    assert result["evidence_present_no_answer"] and result["evidence_present_answer_failed"] is None
    bindings["q"].update(answerable=True, expected_verified=True)
    assert analyze(events, [case], bindings)[1][0]["evidence_present_answer_failed"]
    bindings["q"].pop("expected_verified")
    events[-1]["status"] = "clarification"
    result = analyze(events, [case], bindings)[1][0]
    assert result["unnecessary_clarification"] is None
    bindings["q"].update(answerable=True, expected_verified=True)
    assert analyze(events, [case], bindings)[1][0]["unnecessary_clarification"] is True


def test_existing_dataset_does_not_invent_memory_ids():
    cases = load_cases(
        {
            "questions": [
                {
                    "id": "q",
                    "question": "PRIVATE",
                    "relevant": ["record-alias"],
                    "expected": "PRIVATE",
                }
            ]
        }
    )
    assert cases[0]["unit"] == "record" and cases[0]["gold"] == [["record-alias"]]
    assert "PRIVATE" not in str(cases)


def test_recall_at_k_does_not_change_actual_loss_stage():
    events, case, bindings = fixture()
    result = analyze(events, [case], bindings, k=1)[1][0]
    assert result["recall_at_k"]["rank_fusion"] == 0.5
    assert result["stage_recall"]["rank_fusion"] == 1
    assert result["loss_stage"] == "evidence_selection"


def test_alternative_group_and_fusion_rescue():
    events, case, bindings = fixture(selected=("1", "2"))
    events[3]["candidates"] = []
    result = analyze(events, [case], bindings)[1][0]
    assert result["stage_recall"]["retrieval_union"] == 0.5
    assert result["loss_stage"] == "none"
    case["gold"] = [["a", "b"]]
    events[5]["candidates"] = events[5]["candidates"][:1]
    assert analyze(events, [case], bindings)[1][0]["complete_evidence_recall"] == 1


def test_missing_branch_and_incomplete_sequence_are_unknown():
    events, case, bindings = fixture()
    events[3]["status"] = "error"
    result = analyze(events, [case], bindings)[1][0]
    assert result["stage_recall"]["retrieval_union"] is None
    assert result["evidence_recall"] == 0.5
    events[2]["event_sequence"] = 99
    assert analyze(events, [case], bindings)[1][0]["evidence_recall"] is None


def test_empty_structure_records_loss_without_invented_retrieval():
    events, case, bindings = fixture()
    events[1]["candidates"] = [
        {"memory_ref": "memory-t-1", "status": "excluded", "reason": "person_mismatch"},
        {"memory_ref": "memory-t-2", "status": "excluded", "reason": "quantity_mismatch"},
    ]
    events = events[:2] + [dict(events[-1], event_sequence=3)]
    result = analyze(events, [case], bindings)[1][0]
    assert result["evidence_recall"] == 0 and result["loss_stage"] == "structure_filter"
    assert result["stage_recall"]["retrieval_union"] is None
    assert len(result["gold_exclusions"]) == 2


def test_binding_export_never_allocates_unseen_ids():
    from evaluation.diagnose_search import capture_binding
    from pma.diagnostics import start_trace

    with start_trace(enabled=True) as trace:
        ref = trace.memory_ref("known")
    binding = capture_binding(trace, "q", memory_ids=["known", "missing"])
    assert binding["q"]["memory_refs"] == {"known": ref, "missing": None}
    assert trace.lookup_ref("memory", "missing") is None


def test_reports_and_malformed_input(tmp_path):
    import json

    import pytest

    from evaluation.diagnose_search import read_events, write_report

    events, case, bindings = fixture()
    summary, cases = analyze(events, [case], bindings)
    write_report(tmp_path, summary, cases)
    assert (
        json.loads((tmp_path / "diagnostic_summary.json").read_text("utf-8"))["total_questions"]
        == 1
    )
    assert (tmp_path / "diagnostic_cases.json").exists()
    assert (tmp_path / "diagnostic_report.md").exists()
    path = tmp_path / "broken.jsonl"
    path.write_text("PRIVATE-invalid", encoding="utf-8")
    with pytest.raises(ValueError, match="line 1") as error:
        read_events(path)
    assert "PRIVATE" not in str(error.value)
