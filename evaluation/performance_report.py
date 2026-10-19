"""Summarize completed or partial synthetic-model benchmark runs without hiding errors."""

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path


def summarize(result):
    grouped = defaultdict(list)
    for row in result["runs"]:
        if not row["warmup"]:
            grouped[row["scenario"]].append(row)
    summary = {}
    for scenario, rows in grouped.items():
        durations = [row["seconds"] for row in rows]
        completion = [sum(c["seconds"] for c in row["http_calls"]
                          if c["endpoint"] == "completions") for row in rows]
        chat = [row["chat_seconds"] for row in rows if "chat_seconds" in row]
        summary[scenario] = {
            "samples": len(rows),
            "median_seconds": statistics.median(durations),
            "max_seconds": max(durations),
            "model_completion_median_seconds": statistics.median(completion),
            "max_ram_mb": max(row["ram_peak_mb"] for row in rows),
            "max_gpu_total_mb": max((row["gpu_total_peak_mb"] for row in rows
                                     if row["gpu_total_peak_mb"] is not None), default=None),
            "statuses": [row["status"] for row in rows],
            "errors": [row["error_code"] for row in rows if "error_code" in row],
            "chat_median_seconds": statistics.median(chat) if chat else None,
        }
    for scenario, incomplete in result.get("incomplete_scenarios", {}).items():
        summary.setdefault(scenario, {"samples": 0, "statuses": [], "errors": []})
        summary[scenario]["incomplete"] = incomplete
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    results = {}
    for mode in ("cpu", "gpu"):
        source = args.root / mode / "results.json"
        if source.exists():
            results[mode] = summarize(json.loads(source.read_text(encoding="utf-8")))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
