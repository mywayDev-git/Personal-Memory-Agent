import copy
from pathlib import Path

import pytest
from conftest import memory
from jsonschema import Draft202012Validator

from evaluation.query_paired import ARMS
from evaluation.query_paired_report import summarize
from evaluation.query_tree_run import prepare, read, write
from evaluation.validation_audit import (
    audit,
    checked_reviews,
    compare_sources,
    freeze_holdout,
    mechanical,
    review_item,
)
from evaluation.validation_cases import DATA, build, validate
from evaluation.validation_trace import ExtractionTrace, inspect_trace
from pma.service import Service


def test_fixtures_are_reproducible_disjoint_and_schema_valid():
    cases = build()
    validate(cases)
    assert read(DATA) == cases
    schema = read(Path("schema/memory_extraction_output.schema.json"))
    validator = Draft202012Validator(schema)
    for case in cases[::2]:
        assert sum(map(len, case["reference_memories"])) > 8
        for group in case["reference_memories"]:
            validator.validate(
                {
                    "memories": [
                        {k: v for k, v in m.items() if k not in {"_evidence_spans", "local_id"}}
                        for m in group
                    ]
                }
            )


def test_reference_mode_never_calls_models_or_changes_fixtures(tmp_path):
    case = build()[0]
    before = copy.deepcopy(case)
    result = prepare(case, None, None, tmp_path, "reference")
    result[0][0]["content"] = "changed"
    assert case == before


def test_repeated_quote_offsets_and_replay_content_are_checked():
    m = memory("같은 문장.")
    m["_evidence_spans"] = [dict(quote="같은 문장.", start=7, end=13)]
    entry = dict(records=[dict(text="같은 문장. 같은 문장.")], frozen_memories=[[m]], arms={})
    assert mechanical(entry) == []
    entry["frozen_memories"][0][0]["_evidence_spans"][0]["end"] = 12
    assert any("source_offset" in e for e in mechanical(entry))
    entry["frozen_memories"][0][0]["_evidence_spans"][0]["end"] = 13
    entry["arms"]["V0"] = dict(
        selected=[dict(id="n", record_no=0, content="무관한 사실", evidence=m["_evidence_spans"])]
    )
    assert any("replay_memory_mapping" in e for e in mechanical(entry))


def test_exact_quote_does_not_automatically_pass_semantics():
    item = review_item("memory_support", "case", dict(content="2026-10-10", quote="자전거를 탔다."))
    assert item["judgment"] == "needs_review"


def test_reviews_need_provenance_and_reject_changed_payload(tmp_path):
    path = tmp_path / "reviews.json"
    item = review_item("answer", "case", {"answer": "test"})
    item["judgment"] = "correct"
    write(path, [item])
    with pytest.raises(ValueError, match="REVIEW_REQUIRES"):
        checked_reviews(path)
    item.update(reason="source compared", reviewer="fixture author")
    write(path, [item])
    assert checked_reviews(path)[item["id"]]["judgment"] == "correct"
    item["payload"]["answer"] = "changed"
    write(path, [item])
    with pytest.raises(ValueError, match="PAYLOAD_CHANGED"):
        checked_reviews(path)


def test_holdout_requires_complete_identical_dev_and_one_run(tmp_path):
    dev = tmp_path / "dev"
    out = tmp_path / "held"
    identity = dict(
        files={"code": "hash"},
        settings={},
        models={},
        suite="paired-v1",
        arms=ARMS,
        validation=dict(split="holdout", memory_source="extracted"),
    )
    prior = copy.deepcopy(identity)
    prior["validation"]["split"] = "development"
    write(dev / "manifest.json", prior)
    cases = [dict(id="dev-1", split="development"), dict(id="held-1", split="holdout")]
    with pytest.raises(ValueError, match="DEVELOPMENT_INCOMPLETE"):
        freeze_holdout(dev, out, identity, cases)
    write(
        dev / "results" / "one.json",
        dict(case="dev-1", status="complete", arms=dict.fromkeys(ARMS)),
    )
    freeze_holdout(dev, out, identity, cases)
    freeze_holdout(dev, out, identity, cases)
    with pytest.raises(ValueError, match="ALREADY_CONSUMED"):
        freeze_holdout(dev, tmp_path / "another", identity, cases)
    changed = copy.deepcopy(identity)
    changed["files"]["code"] = "edited"
    with pytest.raises(ValueError, match="CONFIGURATION_CHANGED"):
        freeze_holdout(dev, out, changed, cases)


def test_trace_captures_sentence_mapping_cache_and_publish(store, settings, models):
    models.prompt = "test"
    models.raw_schema = {}
    models.count_tokens = lambda text: len(text)

    def extract(text, context, source_units=None, target_ids=None):
        picked = [u for u in source_units if u["id"] in target_ids]
        return {"memories": [memory(u["text"]) for u in picked]}, {
            "provenance": [{"evidence": [{"start": u["start"], "end": u["end"]}]} for u in picked]
        }

    models.extract = extract
    original = models.extract
    rid = store.create("같은 문장. 같은 문장.", None)["record_id"]
    with ExtractionTrace(models) as trace:
        Service(store, models, settings).run_one()
    assert models.extract is original
    assert store.get(rid)["status"] == "ready"
    assert {e["stage"] for e in trace.events} >= {
        "sentence_mapping",
        "chunk_cache",
        "deduplicated_publish",
    }
    published = next(e for e in trace.events if e["stage"] == "deduplicated_publish")
    assert len(published["memories"]) == len(published["metadata"]["provenance"]) == 2
    assert published["metadata"]["provenance"][0] != published["metadata"]["provenance"][1]
    assert (
        inspect_trace(dict(record=dict(text="같은 문장. 같은 문장."), events=trace.events))[
            "errors"
        ]
        == []
    )


def test_unrun_answer_has_no_timing():
    from test_query_paired_report import result

    entry = result("case")
    for arm in entry["arms"].values():
        del arm["response"]
    summary = summarize([entry], 1)
    assert all(a["effective_answer_median_seconds"] is None for a in summary["arms"])


def test_report_requires_semantic_reviews_and_changed_answers(tmp_path):
    from test_query_paired_report import result

    case = build()[0]
    entry = result(case["id"])
    entry.update(
        scale=0,
        question=case["questions"][0]["text"],
        gold=case["gold"],
        records=case["records"],
        frozen_memories=case["reference_memories"],
    )
    for label, arm in entry["arms"].items():
        arm.pop("response")
        arm["selected"] = []
        arm["metrics"]["selected"]["hits"] = [label == "V1"]
        arm["metrics"]["delivered"]["hits"] = [False]
    write(tmp_path / "run/manifest.json", dict(validation=dict(case_ids=[case["id"]])))
    write(tmp_path / "run/results/case.json", entry)
    summary = audit(tmp_path / "run", DATA, tmp_path / "report")
    assert summary["gate"] == "incomplete"
    assert len(summary["pending_changed_answers"]) == 2
    assert summary["stages"]["memory_support"]["accuracy"] is None
    assert all(r["answer_median_seconds"] is None for r in summary["arms"])
    assert (tmp_path / "report/answer-comparisons.json").exists()


def test_constraint_reviews_require_explicit_missing_and_contradiction_states(tmp_path):
    item = review_item("retrieval_constraints", "case", dict(constraints=[dict(field="time")]))
    item.update(judgment="wrong", reason="wrong date", reviewer="source reviewer")
    path = tmp_path / "reviews.json"
    write(path, [item])
    with pytest.raises(ValueError, match="CONDITION_STATES"):
        checked_reviews(path)
    item.update(
        direct_conditions=dict(time="contradictory"), delivered_conditions=dict(time="satisfied")
    )
    write(path, [item])
    assert checked_reviews(path)


def test_trace_rejects_wrong_sentence_id_even_when_quote_exists_in_source():
    text = "달렸다. 쉬었다."
    m = memory("쉬었다.")
    trace = dict(
        record=dict(text=text),
        events=[
            dict(
                stage="sentence_mapping",
                status="complete",
                target_ids=["s0", "s1"],
                source_units=[
                    dict(id="s0", text="달렸다.", start=0, end=4),
                    dict(id="s1", text="쉬었다.", start=5, end=9),
                ],
                raw_memories=[dict(evidence=[dict(sentence_id="s0")])],
                restored=[
                    dict(memories=[m]),
                    dict(provenance=[dict(evidence=[dict(start=5, end=9)])]),
                ],
            )
        ],
    )
    assert inspect_trace(trace)["errors"] == ["raw_restored_quote_mapping"]


def test_dataset_role_gold_does_not_turn_meeting_partner_into_recipient():
    cases = build()
    meet = next(c for c in cases if c["id"] == "mv-time-00-q1")
    fields = {c["field"] for c in meet["validation"]["constraints"]}
    assert "target" in fields and "recipient" not in fields and "action" in fields
    assert (
        "실제로" in next(c for c in cases if c["id"] == "mv-polarity-00-q1")["questions"][0]["text"]
    )
    assert (
        "전달하지 않았다는"
        in next(c for c in cases if c["id"] == "mv-polarity-00-q2")["questions"][0]["text"]
    )


def test_reference_holdout_cannot_enable_retuning_raw_holdout(tmp_path):
    cases = [dict(id="dev", split="development")]
    identity = dict(
        files={"code": "v1"},
        models={},
        settings={},
        suite="paired-v1",
        arms=ARMS,
        validation=dict(split="holdout", memory_source="reference"),
    )
    dev = tmp_path / "dev"
    prior = copy.deepcopy(identity)
    prior["validation"]["split"] = "development"
    write(dev / "manifest.json", prior)
    write(dev / "results/dev.json", dict(case="dev", status="complete", arms=dict.fromkeys(ARMS)))
    freeze_holdout(dev, tmp_path / "held-reference", identity, cases)
    identity["files"]["code"] = "v2"
    identity["validation"]["memory_source"] = "extracted"
    prior = copy.deepcopy(identity)
    prior["validation"]["split"] = "development"
    write(dev / "manifest.json", prior)
    with pytest.raises(ValueError, match="PROTOCOL_CHANGED"):
        freeze_holdout(dev, tmp_path / "held-raw", identity, cases)


def test_source_comparison_rejects_changed_model_and_matches_same_questions(tmp_path):
    from test_query_paired_report import result

    for source in ("extracted", "reference"):
        manifest = dict(
            files={}, settings={}, models={"id": "same"}, validation=dict(memory_source=source)
        )
        write(tmp_path / source / "manifest.json", manifest)
        entry = result("case")
        entry.update(question="question", records=[dict(text="source")])
        if source == "reference":
            entry["arms"]["V0"]["metrics"]["selected"]["all_required"] = True
        write(tmp_path / source / "results/case.json", entry)
    rows = compare_sources(tmp_path / "extracted", tmp_path / "reference", tmp_path / "report")
    assert len(rows) == 16
    assert rows[0]["outcome"] == "right_improved"
    manifest["models"]["id"] = "changed"
    write(tmp_path / "reference/manifest.json", manifest)
    with pytest.raises(ValueError, match="CONFIGURATION_CHANGED"):
        compare_sources(tmp_path / "extracted", tmp_path / "reference", tmp_path / "report")
