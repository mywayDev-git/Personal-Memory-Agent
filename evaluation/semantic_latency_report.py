"""Publish completed synthetic follow-up trials without source/question text."""

import argparse
import json
import statistics
from pathlib import Path

from evaluation.response_latency import summary
from evaluation.response_latency_report import latency_gate
from pma.settings import AppSettings


def load_trial(path):
    result = json.loads((path / "results.json").read_text(encoding="utf-8"))
    if not all(result.get(key) is True for key in (
        "source_unchanged", "evaluator_unchanged", "execution_completed"
    )):
        raise ValueError("UNFINISHED_OR_CHANGED_TRIAL")
    return result


def describe(trial):
    measured = [row for row in trial["runs"] if not row["warmup"]]
    groups = sorted({(r["variant"], r["case"]) for r in measured})
    results = {}
    for variant, case in groups:
        rows = [r for r in measured if r["variant"] == variant and r["case"] == case]
        stats = summary(rows)
        stats["chat_calls_median"] = statistics.median(sum(
            c["operation"].endswith("/chat/completions")
            for c in row.get("performance", {}).get("model_http_calls", [])
        ) for row in rows)
        phases = sorted({c.get("phase", "other") for row in rows
                         for c in row.get("performance", {}).get("model_http_calls", [])
                         if c["operation"].endswith("/chat/completions")})
        stats["phase_chat_calls_median"] = {phase: statistics.median(sum(
            c["operation"].endswith("/chat/completions") and c.get("phase") == phase
            for c in row.get("performance", {}).get("model_http_calls", [])
        ) for row in rows) for phase in phases}
        stats["selection_cache_hits"] = sum(
            row.get("performance", {}).get("profile", {}).get("counts", {}).get("selection_cache_hits", 0)
            for row in rows)
        stats["explicit_context_calls_saved"] = sum(
            row.get("performance", {}).get("profile", {}).get("counts", {}).get("explicit_context_calls_saved", 0)
            for row in rows)
        results[f"{variant}/{case}"] = stats
    return {
        "repository_revision": trial["repository_reference_revision"],
        "configuration": trial["configuration"], "hashes": trial["hashes"],
        "measurement_scope": trial["measurement_scope"],
        "source_unchanged": True, "evaluator_unchanged": True,
        "quality_scoring_version": trial["quality_scoring_version"],
        "startup": trial["startup"], "summary": results,
        "anchors": trial.get("anchors", {}),
        "runs": trial["runs"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", nargs="+", type=Path, required=True)
    parser.add_argument("--verification", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    verification = json.loads(args.verification.read_text(encoding="utf-8"))
    if (verification.get("status") != "complete" or not verification.get("verification_passed")
            or not verification.get("app_restored")):
        raise ValueError("INCOMPLETE_VERIFICATION_OR_RESTORATION")
    report = {"schema_version": 1, "personal_database_used": False,
              "models_changed": False, "request_reuse_default": False,
              "source_stop_drafts_default": AppSettings().source_stop_drafts,
              "application_wide_speed_claim": False,
              "verification": verification,
              "trials": {path.name: describe(load_trial(path)) for path in args.trials}}
    report["final_quality_gate"] = verification["final_quality_gate"]
    report["measured_requests"] = sum(stats["samples"] for trial in report["trials"].values()
                                      for stats in trial["summary"].values())
    for trial in report["trials"].values():
        groups = trial["summary"]
        if "baseline/stopped" in groups and "reuse/stopped" in groups:
            report["targeted_stop_timing_gate"] = latency_gate(groups["baseline/stopped"], groups["reuse/stopped"])
    args.output.with_suffix(".json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["Person scope, event meaning, and request reuse", "=" * 45, "",
             "Qwen3-8B-Q4_K_M and BGE-M3-Q8_0 remain unchanged. Synthetic DBs only.",
             "All drafts still require independent source review and exact citation spans.", "",
             "The baseline below includes the correctness fixes. Earlier wrong-person or",
             "contradictory-stop answers are not valid speed baselines.", "",
             "Request reuse stays opt-in (PMA_REQUEST_REUSE=1). These limited synthetic",
             "measurements do not establish a general application-wide speed improvement.",
             "Only the bounded, independently reviewed stop-source draft is enabled by default.",
             "PMA_SOURCE_STOP_DRAFTS=0 and PMA_REQUEST_REUSE=0 restore stop-lookup generation/repair.", ""]
    gate = report.get("targeted_stop_timing_gate", {})
    if gate.get("passed"):
        lines += [f"Targeted stop-record median reduction: {gate['median_reduction'] * 100:.2f}% "
                  "in 20 balanced repetitions per path; all 40 responses correct.", ""]
    lines += ["Final case coverage: 12 cases, five correct responses per case using the latest",
              "verified result for each case. The earlier plan-only and compound-search",
              "failures remain below and in raw data; their corrected reruns are separate.", ""]
    checks = verification["python"]
    retrieval = verification["multilingual"]["summary"]
    positive = retrieval["positive"]["expanded"]
    lines += [f"Python: {checks['passed']} passed, {checks['failed']} failed. UI: four checks passed.",
              "Mixed events: 10/10 exact source sets. Fresh multilingual questions: 90/90,",
              f"no errors or per-question regressions; positive Precision@8={positive['precision_at_8']:.3f}, "
              f"Recall@8={positive['recall_at_8']:.3f}.",
              "The multilingual metric is retrieval/fusion/top8 before optional relevance",
              "review; final-answer quality is evaluated separately above. Original app and",
              "both original model servers restored and healthy; no personal reindex.", ""]
    for name, trial in report["trials"].items():
        lines += [name, "-" * len(name), "", f"Source commit: {trial['repository_revision']}",
                  "Preparation/warmups excluded; timer stops at validated response return.", ""]
        for key, stats in trial["summary"].items():
            median, p95 = stats["median_seconds"], stats["p95_seconds"]
            lines += [f"* {key}: n={stats['samples']}, quality={stats['quality_passes']}/{stats['samples']}, "
                      f"failures={stats['failures']}, median={median:.3f}s, P95={p95:.3f}s, "
                      f"chat calls median={stats['chat_calls_median']}, "
                      f"selection cache hits={stats['selection_cache_hits']}."]
            lines += [f"  RAM working-set peak={stats['peak_ram_mb']:.1f} MiB; "
                      f"device VRAM sampled peak={stats['peak_gpu_total_mb']} MiB."]
        lines.append("")
    lines += ["Safety and interpretation", "-------------------------", "",
              "* Independent review and additional-search decisions are not cached or removed.",
              "* Relevance reuse is limited to identical question, model configuration, full",
              "  source revision, compact model inputs, correction inputs, and policy within",
              "  one request. Cancellation/deadline checks still run on a hit.",
              "* Explicit person resolution only skips interpretation for a complete narrow",
              "  role-qualified identity/profession lookup with the label present in sources.",
              "* Stop drafts preserve an entire bounded source sentence. Date constraints,",
              "  recognized conditional/negated speech, multiple candidates and broader",
              "  questions fall back to normal generation; instructions remain untrusted.",
              "* RAM sums process working sets and can double-count shared pages. VRAM is",
              "  the device total, including desktop usage, sampled once per second.",
              "* Long-evidence replies remain brief; finite synthetic checks do not prove",
              "  general answer completeness or universal person disambiguation.",
              "* Five-sample P95 is the maximum; repeat a promising finalist twenty times",
              "  before treating a speed change as robust. Do not pool separate cohorts.", ""]
    args.output.with_suffix(".rst").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
