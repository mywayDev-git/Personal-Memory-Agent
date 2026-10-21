"""Compare paired synthetic quality observations without invoking models."""

import argparse
import hashlib
import json
from pathlib import Path

from .first_response_cases import DEVELOPMENT, HOLDOUT, manifest


def compare(document):
    config = document["configuration"]
    expected = DEVELOPMENT if config.get("fixture_split") == "development" else HOLDOUT
    expected_hash = manifest()["sha256"]
    if config.get('fixture_split', '').startswith('integrity_'):
        from .answer_integrity_cases import load
        _, expected, declared = load(config['fixture_split'].removeprefix('integrity_'))
        expected_hash = declared['sha256']
    if config.get("fixture_split") == "identity_confirmation":
        from .identity_followup_cases import CASES, manifest as identity_manifest
        expected, expected_hash = CASES, identity_manifest()["sha256"]
    if config.get('fixture_split') == 'identity_search_confirmation':
        from .identity_search_cases import CASES, manifest as search_manifest
        expected, expected_hash = CASES, search_manifest()['sha256']
    if config.get('fixture_split') == 'identity_completion_confirmation':
        from .identity_completion_cases import CASES, manifest as completion_manifest
        expected, expected_hash = CASES, completion_manifest()['sha256']
    cases = {}
    for name in config["cases"]:
        grouped = {variant: [r for r in document.get("runs", [])
                             if r["case"] == name and r["variant"] == variant and not r.get("warmup")]
                   for variant in ("current", "candidate")}
        values = {variant: bool(rows) and all(not r.get("error_code") and
                      r.get("quality", {}).get("passed") is True for r in rows)
                  for variant, rows in grouped.items()}
        cases[name] = {"baseline_passed": values["current"], "candidate_passed": values["candidate"],
                       "regression": values["current"] and not values["candidate"],
                       "improvement": values["candidate"] and not values["current"],
                       "baseline_observations": len(grouped["current"]),
                       "candidate_observations": len(grouped["candidate"])}
    errors = [r for r in document.get("runs", []) if r.get("error_code")]
    candidate_errors = [r for r in errors if r["variant"] == "candidate"]
    approved_scope_errors = [{"case": row["case"], "variant": row["variant"], "sample": row.get("sample")}
                             for row in document.get("runs", []) if not row.get("warmup")
                             and (row.get("quality") or {}).get("validation") == "model_checked"
                             and (row.get("quality") or {}).get("source_scope_valid") is False]
    candidate_scope_errors = [row for row in approved_scope_errors if row["variant"] == "candidate"]
    fixture_complete = bool(document.get('execution_completed') and set(cases) == set(expected)
                            and config.get('fixture_manifest_sha256') == expected_hash)
    candidate_complete = fixture_complete and all(row['candidate_observations'] for row in cases.values())
    complete = candidate_complete and all(row['baseline_observations'] for row in cases.values())
    regressions = [key for key, row in cases.items() if row["regression"]]
    absolute_pass = candidate_complete and all(row["candidate_passed"] for row in cases.values()) and not candidate_errors
    return {"complete_split": complete, "regressions": regressions,
            "candidate_absolute_quality_passed": absolute_pass,
            'candidate_complete_split': candidate_complete,
            "improvements": [key for key, row in cases.items() if row["improvement"]],
            "unchanged_failures": [key for key, row in cases.items()
                                   if not row["baseline_passed"] and not row["candidate_passed"]],
            "errors": len(errors), "candidate_errors": len(candidate_errors),
            "automated_nonregression_gate": complete and not regressions and not candidate_errors,
            "approved_scope_errors": approved_scope_errors,
            "candidate_scope_guard_passed": candidate_complete and not candidate_scope_errors and not candidate_errors,
            "adoption": ("NOT_ELIGIBLE_SCOPE_FALSE_APPROVAL" if candidate_scope_errors else
                         "NOT_ELIGIBLE_REGRESSION_OR_ERROR" if regressions or candidate_errors else
                         'PENDING_BASELINE_SOURCE_REVIEW_AND_PERFORMANCE' if not complete else
                         "PENDING_SOURCE_REVIEW_AND_PERFORMANCE"),
            "manual_semantic_review": "PENDING", "cases": cases,
            "note": "Unchanged baseline failures are not counted as correct answers or target successes."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a new output; earlier reports are preserved")
    result = compare(json.loads(args.results.read_text(encoding="utf-8")))
    result.update(source_sha256=hashlib.sha256(args.results.read_bytes()).hexdigest(),
                  reporter_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("complete_split", "candidate_complete_split", "candidate_absolute_quality_passed", "regressions", "errors", "automated_nonregression_gate", "candidate_scope_guard_passed", "adoption")}))


if __name__ == "__main__":
    main()
