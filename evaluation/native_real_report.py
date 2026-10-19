"""Summarize only synthetic real-model measurements; retain failures separately."""

import argparse
import json
import sqlite3
import statistics
from pathlib import Path


def summarize(root):
    result = json.loads((root / "results.json").read_text(encoding="utf-8"))
    journal = root / "memory-journal.jsonl"
    if journal.exists():
        measurements = [
            json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()
        ]
        indexed = {
            tuple(x.get(k) for k in ("mode", "backend", "scenario", "sample")): x
            for x in measurements
        }
        for row in result["runs"]:
            values = indexed.get(
                tuple(row.get(k) for k in ("mode", "backend", "scenario", "sample")), {}
            )
            for key in ("ram_peak_mib", "gpu_total_peak_mib"):
                if key not in row and key in values:
                    row[key] = values[key]
    http_journal = root / "http-journal.jsonl"
    if http_journal.exists():
        http_lines = http_journal.read_text(encoding="utf-8").splitlines()
        memory_lines = journal.read_text(encoding="utf-8").splitlines() if journal.exists() else []
        for index, line in enumerate(http_lines):
            entry = json.loads(line)
            # Both observers completed together; a nested wrapper temporarily
            # hid the outer context in the memory-only journal. Align their
            # common suffix to retain failed-request peaks, without guessing IDs.
            if len(memory_lines) >= len(http_lines):
                paired = json.loads(memory_lines[len(memory_lines) - len(http_lines) + index])
                entry.update({k: paired[k] for k in ("ram_peak_mib", "gpu_total_peak_mib")})
            for row in result["runs"]:
                if all(
                    row.get(k) == entry.get(k) for k in ("mode", "backend", "scenario", "sample")
                ):
                    row.setdefault("http_calls", entry["http_calls"])
                    for key in ("ram_peak_mib", "gpu_total_peak_mib"):
                        if row.get(key) is None and key in entry:
                            row[key] = entry[key]
    observation = root / "observation-journal.jsonl"
    if observation.exists():
        for line in observation.read_text(encoding="utf-8").splitlines():
            entry = json.loads(line)
            for row in result["runs"]:
                if all(
                    row.get(k) == entry.get(k) for k in ("mode", "backend", "scenario", "sample")
                ):
                    for key in ("ram_peak_mib", "gpu_total_peak_mib", "http_calls"):
                        row.setdefault(key, entry[key])
    for mode in ("gpu", "cpu"):
        for backend in ("python", "cpp"):
            path = root / mode / f"{backend}.db"
            if not path.exists():
                continue
            with sqlite3.connect(path) as db:
                messages = db.execute(
                    "SELECT response,state,error_code FROM chat_messages ORDER BY created_at,id"
                ).fetchall()
            rows = [
                x
                for x in result["runs"]
                if x["mode"] == mode and x["backend"] == backend and x["scenario"] == "memory_chat"
            ]
            for row, (response, state, error) in zip(rows, messages):
                row["message_state"] = state
                if response:
                    value = json.loads(response)
                    row["phase_timings"] = value.get("phase_timings", {})
                    row["mentions_blue"] = any(
                        "파란" in item.get("text", "") for item in value.get("items", [])
                    )
    groups = []
    for mode in ("gpu", "cpu"):
        for scenario in ("search", "memory_chat"):
            for backend in ("python", "cpp"):
                rows = [
                    r
                    for r in result["runs"]
                    if r["mode"] == mode
                    and r["scenario"] == scenario
                    and r["backend"] == backend
                    and not r["warmup"]
                ]
                good = [r for r in rows if r["status"] in ("ok", "answered")]
                summary = dict(
                    mode=mode,
                    scenario=scenario,
                    backend=backend,
                    measured=len(rows),
                    succeeded=len(good),
                    requested=result["samples"],
                    errors=[r.get("error_code", r["status"]) for r in rows if r not in good],
                    failed_seconds=[r["seconds"] for r in rows if r not in good],
                )
                if good:
                    summary.update(
                        median_seconds=statistics.median(r["seconds"] for r in good),
                        max_seconds=max(r["seconds"] for r in good),
                        median_model_http_seconds=statistics.median(
                            sum(c.get("seconds", 0) for c in r.get("http_calls", [])) for r in good
                        ),
                        native_calls=sum(r["native_calls"] for r in good),
                    )
                for metric in ("ram_peak_mib", "gpu_total_peak_mib"):
                    values = [r[metric] for r in rows if r.get(metric) is not None]
                    if values:
                        summary[metric] = max(values)
                groups.append(summary)
    result["summary"] = groups
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = summarize(args.root)
    if args.output:
        args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
