import copy
import json
import subprocess
import sys
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from evaluation.build_kiwi_dataset import build, validate
from evaluation.kiwi_compare import Experiment, make_schedule
from evaluation.kiwi_contract import ARMS, source_units, validate_result
from evaluation.kiwi_report import report
from evaluation.kiwi_runtime import MemoryDB
from evaluation.kiwi_scoring import apply_reviews, score_answer, score_extraction
from evaluation.life_diagnostics import write_json


def extracted(units):
    return dict(
        events=[
            dict(
                content="민수가 지연을 만났다.",
                predicate="만나다",
                actor="민수",
                recipient=None,
                object="지연",
                speaker=None,
                time=dict(raw=None, start=None, end=None, kind="unknown"),
                status="occurred",
                operators=[],
                uncertain_fields=[],
                evidence=[dict(sentence_id=units[0]["id"], quote=units[0]["text"])],
            )
        ],
        relations=[],
        questions=[],
    )


def test_dataset_counts_family_isolation_and_golds():
    data = build()
    validate(data)
    assert len({c["family"] for c in data["cases"]}) == 32
    schedule = make_schedule(data, "test", "ABCDEFGHL")
    assert sum(j["question_count"] for j in schedule if j["phase"] == "main") == 1944
    assert sum(j["phase"].startswith("repeat") for j in schedule) == 8 * 2 * 9
    assert make_schedule(data, "test", "ABCDEFGHL") == schedule
    assert len({j["run_id"] for j in schedule}) == len(schedule)


def test_factorial_has_only_one_change_for_kiwi_pairs():
    for plus, minus in [("C", "A"), ("D", "B"), ("G", "E"), ("H", "F")]:
        assert ARMS[plus] == {**ARMS[minus], "kiwi": True}


def test_grounding_uses_sentence_position_not_first_duplicate():
    records = [dict(text="2026-10-01\n달렸다.\n2026-10-03\n달렸다.", reference_time=None)]
    units = source_units(records)
    raw = extracted([units[-1]])
    checked = validate_result(raw, units)
    assert checked["events"][0]["evidence"][0]["start"] == records[0]["text"].rfind("달렸다.")
    assert "id" not in raw["events"][0]
    raw["events"][0]["evidence"][0]["quote"] = "없는 인용"
    with pytest.raises(ValueError, match="EVIDENCE"):
        validate_result(raw, units)


def test_invalid_time_and_references_rejected():
    units = source_units([dict(text="어제 민수가 지연을 만났다.", reference_time=None)])
    raw = extracted(units)
    raw["events"][0]["time"].update(start="2026-02-30", raw="어제")
    with pytest.raises(ValueError):
        validate_result(raw, units)
    raw = extracted(units)
    raw["questions"] = [dict(event=2, field="actor", text="누구?", candidates=[])]
    with pytest.raises(ValueError, match="REFERENCE"):
        validate_result(raw, units)
    raw = extracted(units)
    raw["events"][0]["actor"] = "null"
    with pytest.raises(ValueError, match="STRING_NULL"):
        validate_result(raw, units)


def test_payload_has_no_gold_and_kiwi_is_optional(settings):
    experiment = Experiment(settings)
    case = build()["cases"][0]
    payload, units, _ = experiment.payload(case["records"], "A")
    assert set(payload) == {"sentences"}
    assert not any(
        k in json.dumps(payload) for k in ["gold_events", "supporting_records", "questions"]
    )
    with pytest.raises(RuntimeError, match="KIWI_NOT_INITIALIZED"):
        experiment.payload(case["records"], "C")
    assert units == source_units(case["records"])


def test_common_path_stores_retrieves_and_answers_without_kiwi(tmp_path, settings):
    experiment = Experiment(settings)
    case = build()["cases"][0]

    class Models:
        def structured(self, prompt, payload, schema):
            if "question" in payload:
                return dict(
                    status="answered", items=[dict(text="민수가 지연을 만났다.", citations=["e0"])]
                )
            return extracted(payload["sentences"])

        def embed(self, texts):
            return np.asarray([[1, 0, 0] for _ in texts], dtype=np.float32)

    experiment.models = Models()
    job = dict(run_id="test-A-main", arm="A", phase="main", case=case["id"], category="roles")
    result = experiment.execute(case, job, tmp_path)
    assert result["status"] == "complete"
    assert len(result["answers"]) == 3
    assert result["answers"][0]["retrieved"][0]["id"] == "e0"
    assert result["answers"][0]["assessment"]["semantic_verdict"] is None
    assert result["result_hash"]


def test_verifier_receives_actual_output_but_never_gold(tmp_path, settings):
    experiment = Experiment(settings)
    case = build()["cases"][0]
    calls = []

    class Models:
        def structured(self, prompt, payload, schema):
            calls.append(copy.deepcopy(payload))
            if "question" in payload:
                return dict(status="insufficient_evidence", items=[])
            return extracted(payload["sentences"])

        def embed(self, texts):
            return np.asarray([[1, 0, 0] for _ in texts], dtype=np.float32)

    experiment.models = Models()
    result = experiment.execute(
        case, dict(run_id="E", arm="E", phase="main", case=case["id"]), tmp_path
    )
    assert result["status"] == "complete"
    assert "proposed" not in calls[0] and "proposed" in calls[1]
    assert "gold_events" not in json.dumps(calls)
    assert result["initial_extraction"] == calls[1]["proposed"]


def test_scoring_is_partial_and_counts_wrong_resolution():
    case = build()["cases"][0]
    units = source_units(case["records"])
    raw = extracted(units)
    second = copy.deepcopy(raw["events"][0])
    second.update(
        predicate="주다",
        actor="민수",
        recipient="지연",
        evidence=[dict(sentence_id=units[1]["id"], quote=units[1]["text"])],
    )
    raw["events"].append(second)
    result = validate_result(raw, units)
    score = score_extraction(case, result)
    assert score["semantic_precision"] is None
    assert sum(f["wrong_resolution"] for f in score["fields"]) == 2
    response = dict(status="answered", items=[dict(text="민수", citations=["bad"])])
    assessed = score_answer(case["questions"][0], response, result["events"])
    assert assessed["lexical_check"]
    assert not assessed["citation_ids_valid"]
    assert assessed["semantic_verdict"] is None


def test_report_counts_missing_failed_and_requires_review(tmp_path):
    jobs = [
        dict(
            run_id=f"job{i}", arm="A", category="roles", phase="main", case="case", question_count=3
        )
        for i in range(3)
    ]
    write_json(tmp_path / "manifest.json", dict(schedule=jobs))
    (tmp_path / "completed").mkdir()
    write_json(
        tmp_path / "completed" / "job0.json", dict(jobs[0], status="failed", answers=[], seconds=1)
    )
    result = report(tmp_path)
    row = next(r for r in result["summary"] if r["category"] == "ALL")
    assert row["planned"] == 3 and row["failed"] == 1 and row["not_executed"] == 2
    assert row["expected_answers"] == 9 and row["semantic_accuracy"] is None
    assert not result["complete_execution"]
    assert (tmp_path / "report.html").exists()


def test_reviews_reject_stale_hash_and_missing_attribution():
    entry = dict(run_id="x", result_hash="hash", answers=[dict(assessment={})])
    review = dict(
        run_id="x",
        result_hash="other",
        question=0,
        reviewer="human",
        rationale="Compared source and claim",
        verdict="correct",
    )
    with pytest.raises(ValueError, match="STALE"):
        apply_reviews([entry], [review])
    review.update(result_hash="hash", reviewer="")
    with pytest.raises(ValueError, match="ATTRIBUTION"):
        apply_reviews([entry], [review])


def test_databases_are_separate_and_stable(tmp_path):
    left, right = MemoryDB(tmp_path / "a.db"), MemoryDB(tmp_path / "b.db")
    try:
        units = source_units([dict(text="민수가 지연을 만났다.")])
        result = validate_result(extracted(units), units)
        left.publish(result, [[1, 0, 0]])
        assert left.search("민수", np.asarray([1, 0, 0]))
        assert right.search("민수", np.asarray([1, 0, 0])) == []
    finally:
        left.close()
        right.close()


def test_app_and_baseline_import_without_kiwi():
    script = """
import sys
from importlib.abc import MetaPathFinder
class BlockKiwi(MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith('kiwipiepy'):
            raise ModuleNotFoundError('Kiwi intentionally unavailable')
sys.meta_path.insert(0, BlockKiwi())
import pma.web
from evaluation.kiwi_compare import Experiment
from pma.settings import AppSettings
assert Experiment(AppSettings(), False).kiwi is None
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", script], capture_output=True, text=True, timeout=20
    )
    assert result.returncode == 0, result.stderr


def test_resume_and_freeze_guards(tmp_path, settings, monkeypatch):
    from evaluation import kiwi_compare as runner

    settings = replace(settings, data_dir=tmp_path / "personal")
    monkeypatch.setattr(runner.AppSettings, "from_env", lambda: settings)
    monkeypatch.setattr(runner, "model_identity", lambda _: {"model": "fixed"})
    monkeypatch.setattr(runner, "code_hash", lambda: "fixed-code")
    calls = []

    class FakeExperiment:
        kiwi = None
        kiwi_initialization_seconds = 0

        def __init__(self, *args):
            pass

        def execute(self, case, job, directory):
            calls.append(job["run_id"])
            result = dict(job, status="complete", seconds=0, calls=[], answers=[])
            result["result_hash"] = runner.fingerprint(result)
            return result

    monkeypatch.setattr(runner, "Experiment", FakeExperiment)
    dataset = tmp_path / "data.json"
    dataset.write_text(json.dumps(build()), encoding="utf-8")
    args = SimpleNamespace(
        dataset=dataset,
        output=tmp_path / "run",
        split="dev",
        arms="A",
        limit=1,
        max_tokens=2048,
        timeout=120,
        freeze_from=None,
        no_repeats=False,
        no_supplements=False,
    )
    runner.run(args)
    count = len(calls)
    runner.run(args)
    assert len(calls) == count
    heldout = SimpleNamespace(
        **{**vars(args), "output": tmp_path / "test", "split": "test", "freeze_from": args.output}
    )
    with pytest.raises(ValueError, match="incomplete"):
        runner.run(heldout)
    args.max_tokens = 1024
    with pytest.raises(ValueError, match="MISMATCH"):
        runner.run(args)
    args.max_tokens = 2048
    path = next((args.output / "completed").glob("*.json"))
    row = json.loads(path.read_text(encoding="utf-8"))
    row["seconds"] = 99
    write_json(path, row)
    with pytest.raises(ValueError, match="CORRUPTED"):
        runner.run(args)


def test_ungrounded_time_is_quarantined_with_original_value():
    units = source_units([dict(text="민수가 지연을 만났다.")])
    raw = extracted(units)
    raw["events"][0]["time"].update(raw="2026-10-13", start="2026-10-13")
    result = validate_result(raw, units)
    assert result["events"][0]["time"]["start"] is None
    assert result["validation_issues"][0]["proposed"]["start"] == "2026-10-13"
    assert raw["events"][0]["time"]["start"] == "2026-10-13"


def test_actual_kiwi_hints_preserve_source_and_common_units(settings):
    pytest.importorskip("kiwipiepy")
    experiment = Experiment(settings, True)
    records = [dict(text="나는 지연에게 책을 주지 않기로 했다.", reference_time=None)]
    baseline, baseline_units, _ = experiment.payload(records, "A")
    kiwi, kiwi_units, elapsed = experiment.payload(records, "C")
    assert baseline_units == kiwi_units
    assert baseline["sentences"] == kiwi["sentences"]
    tokens = kiwi["morphology"][0]["tokens"]
    assert any(t["form"] == "않" and t["tag"] == "VX" for t in tokens)
    assert all(
        t["start"] >= 0 and t["start"] + t["length"] <= len(records[0]["text"]) for t in tokens
    )
    assert elapsed > 0
