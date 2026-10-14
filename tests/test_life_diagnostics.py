import copy
import json
from collections import Counter

import pytest

from evaluation.build_life_dataset import ROOT, build, render, validate
from evaluation.life_diagnostics import Run, assess, expectation, summarize, write_json
from evaluation.life_report import apply_reviews, report
from evaluation.relationship_checks import review


@pytest.fixture(scope="module")
def fixture():
    return build()


def test_committed_fixture_matches_authoring_source(fixture):
    assert json.loads((ROOT / "data/life_diagnostics.json").read_text(encoding="utf-8")) == fixture
    validate(fixture)
    assert (
        len(
            json.loads((ROOT / "data/relationship_diagnostics.json").read_text(encoding="utf-8"))[
                "questions"
            ]
        )
        == 60
    )
    assert {r["recorded_at"][:7] for r in fixture["records"]} == {
        f"2026-{m:02}" for m in range(4, 10)
    }
    assert len({q["question"] for q in fixture["questions"]}) >= 570
    assert len({q["category"] for q in fixture["questions"] if q["repeat_at_snapshots"]}) == 6
    assert len({r["domain"] for r in fixture["records"] if r["event_id"]}) == 8


def test_unknown_dates_late_records_and_unfinished_events(fixture):
    assert any(r["event_time"] is None for r in fixture["records"])
    assert any(
        r["event_time"] and r["event_time"] < r["recorded_at"][:10] for r in fixture["records"]
    )
    assert any("정정한다" in r["text"] for r in fixture["records"])
    assert any("다시 예약하지 않았다" in r["text"] for r in fixture["records"])
    assert sum("long_diary" in r["tags"] and len(r["text"]) >= 500 for r in fixture["records"]) == 8
    assert sum("relative_date" in r["tags"] for r in fixture["records"]) == 8
    for event in fixture["events"]:
        assert {q["split"] for q in fixture["questions"] if q["event_id"] == event["id"]} == {
            event["split"]
        }


def test_future_evidence_is_not_the_answer(fixture):
    records = {r["id"]: r for r in fixture["records"]}
    case = next(q for q in fixture["questions"] if len(q["relevant"]) == 2)
    assert expectation(case, set(), records)["mode"] == "abstain_or_clarify"
    partial = expectation(case, {case["relevant"][0]}, records)
    assert partial["mode"] == "partial_evidence"
    assert len(partial["supporting_facts"]) == 1
    assert len(partial["not_yet_visible"]) == 1


def test_incomplete_execution_is_not_pass(fixture):
    report = summarize(fixture, [])
    assert report["planned"] == 780
    assert len(report["missing"]) == 780
    assert report["semantic_accuracy"] is None
    case = fixture["questions"][0]
    entry = dict(
        run_id="forward-300-" + case["id"],
        category=case["category"],
        split=case["split"],
        snapshot=300,
        variant="forward",
        elapsed_seconds=1,
        error_type="Timeout",
    )
    report = summarize(fixture, [entry, entry])
    assert report["duplicates"] == [entry["run_id"]]
    assert report["groups"]["all"]["errors"] == 2
    assert len(report["missing"]) == 779


def test_citation_validity_is_not_semantic_accuracy(fixture):
    case = fixture["questions"][0]
    expected = {"available_support": ["a"], "mode": "evidence"}
    response = {
        "status": "answered",
        "results": [{"id": "m", "record_id": "r"}],
        "items": [{"text": "전혀 틀린 답", "citations": ["m"]}],
    }
    result = assess(case, expected, response, {"r": "a"})
    assert result["signal"] == "evidence_checks_passed"
    assert result["semantic_correct"] is None
    response["items"][0]["citations"] = ["made-up"]
    assert not assess(case, expected, response, {"r": "a"})["citation_ids_valid"]


def test_rejects_unowned_directory(tmp_path):
    with pytest.raises(ValueError, match="RUN_DIRECTORY"):
        Run(ROOT / "data/life_diagnostics.json", tmp_path)


def test_checkpoint_retries_windows_reader_lock(tmp_path, monkeypatch):
    from pathlib import Path

    target = tmp_path / "state.json"
    target.write_text('{"old": true}', encoding="utf-8")
    real_replace = Path.replace
    attempts = []

    def replace(source, destination):
        attempts.append(source)
        if len(attempts) <= 2:
            assert json.loads(target.read_text(encoding="utf-8")) == {"old": True}
            raise PermissionError("reader holds file")
        return real_replace(source, destination)

    monkeypatch.setattr(Path, "replace", replace)
    monkeypatch.setattr("evaluation.life_diagnostics.time.sleep", lambda _: None)
    write_json(target, {"new": True})
    assert len(attempts) == 3
    assert json.loads(target.read_text(encoding="utf-8")) == {"new": True}
    assert not list(tmp_path.glob("*.tmp"))


def test_fixture_rejects_split_leakage(fixture):
    bad = copy.deepcopy(fixture)
    bad["records"][0]["split"] = "holdout"
    with pytest.raises(AssertionError):
        validate(bad)
    assert Counter(q["category"] for q in fixture["questions"])["indirect"] == 100


def test_korean_particles_do_not_invent_names():
    assert (
        render("{p}은 {o}을 샀다. {p}이 말했다.", {"p": "민수", "o": "목도리"})
        == "민수는 목도리를 샀다. 민수가 말했다."
    )
    assert render("{p}이랑 {o}을 봤다.", {"p": "지연", "o": "머그컵"}) == "지연이랑 머그컵을 봤다."


def test_cache_reuses_only_identical_sources_and_report_uses_snapshot(
    tmp_path, settings, monkeypatch
):
    from pma.settings import AppSettings

    monkeypatch.setattr(AppSettings, "from_env", lambda: settings)
    source = ROOT / "data/life_diagnostics.json"
    old = Run(source, tmp_path / "old")
    ids = list(old.records)[:2]
    cached = {sid: {"status": "ready", "memories": [], "vectors": []} for sid in ids}
    (old.directory / "extractions.json").write_text(json.dumps(cached), encoding="utf-8")
    data = json.loads(source.read_text(encoding="utf-8"))
    data["records"][0]["text"] += " 추가 메모."
    updated = tmp_path / "updated.json"
    updated.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    new = Run(updated, tmp_path / "new")
    new.import_cache(old.directory)
    assert set(new.cache) == {ids[1]}
    new.import_cache(old.directory)
    assert set(new.cache) == {ids[1]}
    result = report(None, new.directory)
    assert result["executed"] == 0 and not result["complete_execution"]
    assert (new.directory / "report.html").exists()
    with pytest.raises(ValueError, match="REPORT_DATASET_VERSION_MISMATCH"):
        report(source, new.directory)


def test_old_regression_checker_reports_missing_questions():
    dataset = {"questions": [{"id": "a", "question": "A"}, {"id": "b", "question": "B"}]}
    result = review(dataset, {"questions": [{"id": "a", "question": "A", "error_type": "Timeout"}]})
    assert result["cases"] == 2 and result["executed"] == 1
    assert result["missing"] == ["b"] and result["specified_checks_passed"] == 0
    with pytest.raises(ValueError):
        review(dataset, {"questions": [{"id": "unknown"}]})


def test_semantic_review_requires_attribution_and_valid_stage():
    entries = [{"run_id": "a"}]
    item = {
        "run_id": "a",
        "verdict": "incorrect",
        "reviewer": "manual reviewer",
        "rationale": "답변은 선물한 색을 희망한 색으로 잘못 인용함",
        "failure_stage": "answer",
    }
    apply_reviews(entries, [item])
    assert entries[0]["assessment"]["semantic_correct"] is False
    with pytest.raises(ValueError):
        apply_reviews(entries, [item, item])
    with pytest.raises(ValueError):
        apply_reviews(entries, [{**item, "rationale": ""}])


@pytest.mark.parametrize("with_links", [True, False])
def test_lifecycle_runner_records_unexercised_links_and_stale_evidence(
    tmp_path, settings, models, fixture, with_links
):
    from conftest import memory

    run = Run.__new__(Run)
    event = fixture["events"][0]
    run.data = {**fixture, "events": [event]}
    run.records = {r["id"]: r for r in fixture["records"]}
    run.settings, run.models, run.directory = settings, models, tmp_path
    models.last_understanding = models.last_evidence = models.last_answer = None
    models.selection_candidates = None
    models.reset_trace = lambda: None
    run.cache = {
        sid: {
            "status": "ready",
            "memories": [dict(memory(run.records[sid]["text"]), memory_type="event")]
            if with_links
            else [],
            "vectors": [[1, 0, 0]] if with_links else [],
        }
        for sid in event["record_ids"]
    }
    run.lifecycle()
    result = json.loads((tmp_path / "lifecycle.json").read_text(encoding="utf-8"))[0]
    assert result["dismissal_status"] == ("tested" if with_links else "not_exercised_no_links")
    assert result["dismissed_stays_gone"] is (True if with_links else None)
    mutations = [r for r in result["operations"] if r["operation"] != "dismiss_relation"]
    assert [r["operation"] for r in mutations] == ["edit", "trash", "purge"]
    assert all(
        r["old_memories_absent"] and r["old_links_absent"] and r["stale_citations_absent"]
        for r in mutations
    )
