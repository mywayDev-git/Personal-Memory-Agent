"""Content-free analysis of explicit latency experiments; never starts models."""

import argparse
import hashlib
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path


def finite(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def distribution(values):
    values = sorted(v for v in values if finite(v))
    if not values:
        return {"samples": 0, "median": None, "p95": None, "maximum": None}
    return {"samples": len(values), "median": statistics.median(values),
            "p95": values[math.ceil(.95 * len(values)) - 1], "maximum": values[-1]}


def analyze(document, target=10):
    groups = defaultdict(list)
    for row in document.get("runs", []):
        if not row.get("warmup"):
            groups[row["variant"], row["case"]].append(row)
    result = {"placement": document.get("configuration", {}).get("placement"),
              "target_seconds": target, "execution_completed": document.get("execution_completed", False),
              "model_hashes": document.get("hashes"), "semantic_review": "PENDING_REVIEW", "cases": {}}
    for (variant, case), rows in groups.items():
        completed = [r for r in rows if not r.get("error_code") and finite(r.get("seconds"))]
        stages, phases = defaultdict(list), defaultdict(list)
        for row in completed:
            performance = row.get("performance", {})
            for name, stage in performance.get("profile", {}).get("stages", {}).items():
                stages[name].append(stage.get("exclusive_seconds"))
            request_phases = defaultdict(lambda: {"seconds": 0, "calls": 0, "prefill_seconds": 0,
                                                   "decode_seconds": 0, "output_tokens": 0})
            for call in performance.get("model_http_calls", []):
                key = call.get("phase", "other") + ":" + call.get("operation", "unknown")
                phase = request_phases[key]
                phase["calls"] += 1
                phase["seconds"] += call["seconds"] if finite(call.get("seconds")) else 0
                timings = call.get("timings", {})
                for field, source in (("prefill_seconds", "prompt_ms"), ("decode_seconds", "predicted_ms")):
                    phase[field] += timings[source] / 1000 if finite(timings.get(source)) else 0
                phase["output_tokens"] += timings["predicted_n"] if finite(timings.get("predicted_n")) else 0
            for name, values in request_phases.items():
                phases[name].append(values)
        latency = distribution(r["seconds"] for r in completed)
        result["cases"][variant + "/" + case] = {
            "requested": len(rows), "completed": len(completed), "errors": len(rows) - len(completed),
            "automatic_quality_passes": sum(r.get("quality", {}).get("passed") is True for r in completed),
            "latency_seconds": latency,
            # Errors count against the target; fast failures are never wins.
            "target_successes": sum(r["seconds"] <= target and r.get("quality", {}).get("passed") is True
                                    for r in completed),
            "ram_peak_mb": max((r["ram_peak_mb"] for r in rows if finite(r.get("ram_peak_mb"))), default=None),
            "device_vram_peak_mb": max((r["gpu_total_peak_mb"] for r in rows
                                        if finite(r.get("gpu_total_peak_mb"))), default=None),
            "private_commit_peak_mb": max((r["private_commit_peak_mb"] for r in rows
                                           if finite(r.get("private_commit_peak_mb"))), default=None),
            "system_available_ram_min_mb": min((r["system_available_ram_min_mb"] for r in rows
                                                 if finite(r.get("system_available_ram_min_mb"))), default=None),
            "page_fault_delta": distribution(r.get("page_fault_delta") for r in rows),
            "exclusive_stages_seconds": {name: distribution(values) for name, values in stages.items()},
            "http_phases": {name: {field: distribution(v[field] for v in values)
                                    for field in values[0]} for name, values in phases.items()},
        }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target-seconds", type=float)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Use a new output file; previous observations are immutable")
    if args.target_seconds is not None and (not finite(args.target_seconds) or args.target_seconds <= 0):
        parser.error("Target must be positive and finite")
    reports = []
    for path in args.results:
        document = json.loads(path.read_text("utf-8"))
        target = args.target_seconds if args.target_seconds is not None else (60 if document.get("configuration", {}).get("placement") == "cpu" else 10)
        result = analyze(document, target)
        result.update(source=str(path), source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                  reporter_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  configuration=document.get("configuration"), startup=document.get("startup"),
                  source_unchanged=document.get("source_unchanged"), evaluator_unchanged=document.get("evaluator_unchanged"),
                      adoption="BASELINE_REFERENCE_ONLY" if document.get("configuration", {}).get("variants") == ["current"] else "PENDING_REVIEW")
        reports.append(result)
    args.output.write_text(json.dumps(reports[0] if len(reports) == 1 else reports, ensure_ascii=False, indent=2) + "\n", "utf-8")


if __name__ == "__main__":
    main()
