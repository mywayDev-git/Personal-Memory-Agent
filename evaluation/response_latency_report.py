"""Summarize isolated runs and rescore synthetic answers from their frozen sources."""

import argparse
import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from evaluation.response_latency import CASES, DOCUMENTS, quality, summary


def rescore(path):
    report = json.loads(path.read_text(encoding="utf-8"))
    original_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    for row in report["runs"]:
        if CASES[row["case"]].get("search") or row.get("error_code"):
            continue
        db_path = path.parent / f"{row['case']}-{row['sample']}-{row['variant']}.db"
        with closing(sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            message = db.execute("SELECT id,response FROM chat_messages WHERE request_id='measured'").fetchone()
            if message is None or not message[1]:
                row["quality"] = {"passed": False, "reason": "missing_completed_response"}
                continue
            response = json.loads(message[1])
            evidence = [json.loads(r[0]) for r in db.execute(
                "SELECT payload FROM chat_message_evidence WHERE message_id=?", (message[0],))]
            by_text = {text: key for key, text, *_ in DOCUMENTS}
            keys = {rid: by_text.get(text) for rid, text in db.execute("SELECT record_id,text FROM revisions")}
            row["quality"] = quality(CASES[row["case"]], response, evidence, keys)
            if CASES[row["case"]].get("background"):
                row["quality"]["passed"] &= row.get("arrival_during_extract", False) and row.get("background_status") == "succeeded"
    report["rescored_from_sha256"] = original_hash
    report["scoring_version"] = 2
    report["summary"] = {f"{variant}/{case}": summary([
        row for row in report["runs"] if row["variant"] == variant and row["case"] == case])
        for variant in report["configuration"]["variants"] for case in report["configuration"]["cases"]}
    return report


def latency_gate(baseline, candidate):
    """A timing gate is necessary, never sufficient for a model/default change."""
    if min(baseline["samples"], candidate["samples"]) < 20:
        return {"passed": False, "reason": "fewer_than_20_samples"}
    if any(row["quality_passes"] != row["samples"] or row["failures"] for row in (baseline, candidate)):
        return {"passed": False, "reason": "quality_or_execution_failure"}
    ratio = candidate["median_seconds"] / baseline["median_seconds"]
    passed = ratio <= .8 and candidate["p95_seconds"] <= baseline["p95_seconds"]
    return {"passed": passed, "median_reduction": 1 - ratio,
            "reason": "timing_gate_only" if passed else "speed_or_p95_target_not_met"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    summaries = {}
    for index, path in enumerate(args.inputs):
        report = rescore(path)
        target = args.output / f"{index:02d}-{path.parent.name}.json"
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        summaries[path.parent.name] = report["summary"]
    (args.output / "summary.json").write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summaries, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
