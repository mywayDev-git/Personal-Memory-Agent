"""Compare paired synthetic quality observations without invoking models."""

import argparse
import json
from pathlib import Path

from .first_response_cases import DEVELOPMENT, HOLDOUT, manifest


def compare(document):
    config = document["configuration"]
    expected = DEVELOPMENT if config.get("fixture_split") == "development" else HOLDOUT
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
    complete = bool(document.get("execution_completed") and set(cases) == set(expected) and
                    config.get("fixture_manifest_sha256") == manifest()["sha256"] and
                    all(row["baseline_observations"] and row["candidate_observations"] for row in cases.values()))
    regressions = [key for key, row in cases.items() if row["regression"]]
    return {"complete_split": complete, "regressions": regressions,
            "improvements": [key for key, row in cases.items() if row["improvement"]],
            "unchanged_failures": [key for key, row in cases.items()
                                   if not row["baseline_passed"] and not row["candidate_passed"]],
            "errors": len(errors), "candidate_errors": len(candidate_errors),
            "automated_nonregression_gate": complete and not regressions and not candidate_errors,
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
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("complete_split", "regressions", "errors", "automated_nonregression_gate")}))


if __name__ == "__main__":
    main()
