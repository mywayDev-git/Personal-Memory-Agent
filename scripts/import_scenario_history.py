"""Import saved scenario probes and JUnit results without regrading answers."""

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from evaluation.adapters import adapt, load_dataset
from evaluation.repository import Repository
from evaluation.runner import aggregate
from evaluation.schema import Case, Dataset, Result
from pma.settings import AppSettings


def save(repo, dataset, results, source):
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    repo.create_dataset(dataset)
    existing = repo.list_runs(dataset_id=dataset.id, limit=100)["items"]
    for run in existing:
        if run["config"].get("source_sha256") == digest and run["status"] == "completed":
            return dict(name=dataset.name, run_id=run["id"], count=len(results), reused=True)
    rid = repo.create_run(
        dataset.id,
        config=dict(
            source=str(source.resolve()),
            source_sha256=digest,
            grading_version="historical-import-v1",
            scope=dataset.name,
        ),
    )
    repo.update_run_status(rid, "running")
    try:
        for result in results:
            repo.save_case_result(rid, result)
        aggregate(repo, rid)
        repo.update_run_status(rid, "completed")
    except Exception:
        repo.update_run_status(rid, "failed", "History import failed")
        raise
    summary = repo.get_run_summary(rid)
    return dict(name=dataset.name, run_id=rid, count=len(results), summary=summary["case_counts"])


def main():
    root = Path(__file__).resolve().parents[1]
    folder = root / "output/scenario-evaluation"
    repo = Repository(AppSettings.from_env().data_dir / "evaluation/evaluation.db")
    imported = []
    for filename, label in [
        ("baseline_results.jsonl", "상황 변수 · 수정 전 (상태 투영 검사)"),
        ("patch_results.jsonl", "상황 변수 · 수정 후 (상태 투영 검사)"),
    ]:
        path = folder / filename
        dataset = load_dataset(root / "data/scenario_cases.json")
        dataset.id += "-" + path.stem
        dataset.name = label
        rows = [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]
        results = []
        for row in rows:
            result = adapt(row)
            result.evaluation.update(
                {
                    k: row[k]
                    for k in (
                        "expected_projection_state",
                        "actual_projection_state",
                        "projection_mismatch",
                        "primary_failure_stage",
                        "scope",
                    )
                    if k in row
                }
            )
            status = row.get("actual_status")
            result.response_behavior = {
                "answered": "answer",
                "insufficient_evidence": "abstain",
            }.get(status)
            results.append(result)
        if {r.case_id for r in results} != {c.id for c in dataset.cases}:
            raise ValueError("Incomplete historical scenario results")
        imported.append(save(repo, dataset, results, path))
    path = folder / "regression-pytest.xml"
    cases, results = [], []
    for index, node in enumerate(ET.parse(path).getroot().iter("testcase"), 1):
        cid = f"UNIT-{index:04}"
        failure = node.find("failure")
        error = node.find("error")
        skipped = node.find("skipped")
        verdict = (
            "error"
            if error is not None
            else "fail"
            if failure is not None
            else "not_applicable"
            if skipped is not None
            else "pass"
        )
        name = node.get("classname", "") + "::" + node.get("name", "")
        cases.append(
            Case(
                id=cid,
                question=name,
                question_type="unit_regression",
                metadata={
                    "legacy_import_only": True,
                    "scope": "pytest assertion; not answer quality",
                },
            )
        )
        results.append(
            Result(
                case_id=cid,
                verdict=verdict,
                actual_answer="pytest: " + verdict,
                latency_ms=float(node.get("time", "0")) * 1000,
                evaluation={
                    "grading_method": "pytest",
                    "grading_version": "junit-import-v1",
                    "answer_correct": None,
                    "scope": "software regression only",
                },
            )
        )
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    dataset = Dataset(
        id="pytest-regression-" + digest,
        name=f"전체 회귀 테스트 · {len(cases)}건 (답변 평가 아님)",
        version=digest,
        cases=cases,
    )
    imported.append(save(repo, dataset, results, path))
    receipt = dict(database=str(repo.path), imported=imported)
    (folder / "dashboard-import-receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
