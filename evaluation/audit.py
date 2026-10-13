"""Read-only audit of saved extraction results; no model calls or output writes."""

import argparse
import json
from collections import Counter
from pathlib import Path

from config.settings import paths
from evaluation.semantic import check_expected
from scripts.memory_agent.validator import load_schema, validate_final_result


def rows(path):
    return [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def audit(dataset, results):
    by_id = {r["case_id"]: r for r in dataset}
    if len(by_id) != len(dataset):
        raise ValueError("Duplicate case IDs: use unique evaluation cases.")
    schema = load_schema(paths.final_schema)
    counts, violations = Counter(), []
    for r in results:
        case = by_id[r["case_id"]]
        result = r.get("result")
        if not result:
            counts["missing_results"] += 1
            continue
        report = validate_final_result(result, schema, case["input"]["text"])
        counts["structural_and_quote_pass"] += report["valid"]
        check = check_expected(case.get("expected", {}), result)
        if check["status"] == "fail":
            violations.append(
                {
                    "case_id": r["case_id"],
                    "failed_checks": [k for k, v in check["checks"].items() if not v],
                }
            )
    return {
        "cases": len(results),
        **counts,
        "expectation_violations": violations,
        "semantic_accuracy": None,
        "human_review_required": True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=paths.datasets_dir / "test.jsonl")
    parser.add_argument("--results", type=Path, default=paths.results_dir / "eval_results.jsonl")
    args = parser.parse_args()
    print(json.dumps(audit(rows(args.dataset), rows(args.results)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
