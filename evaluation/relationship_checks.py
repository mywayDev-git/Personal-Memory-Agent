"""Explicit fixture acceptance checks; these are not a general semantic judge."""

import argparse
import json
from collections import Counter
from pathlib import Path


def check_case(case, response, source_ids):
    spec = case.get("checks")
    if not spec:
        return None
    text = " ".join(item["text"] for item in response["items"])
    by_id = {r["id"]: source_ids[r["record_id"]] for r in response["results"]}
    citations = {
        by_id[cid] for item in response["items"] for cid in item["citations"] if cid in by_id
    }
    checks = {
        "status": response["status"] in spec["statuses"],
        "required_text": all(term in text for term in spec.get("contains", [])),
        "forbidden_text": all(term not in text for term in spec.get("excludes", [])),
        "required_citations": set(spec.get("citations", [])) <= citations,
        "forbidden_citations": not set(spec.get("exclude_citations", [])) & citations,
        "no_invented_filter": case.get("date_filter", False)
        or not any(response["filters"].values()),
    }
    return {"passed": all(checks.values()), "checks": checks, "human_review_required": True}


def review(dataset, report):
    cases = {c["id"]: c for c in dataset["questions"]}
    counts = Counter(entry["id"] for entry in report["questions"])
    if set(counts) - set(cases) or any(n > 1 for n in counts.values()):
        raise ValueError("Unknown or duplicate question IDs")
    reviewed = []
    for entry in report["questions"]:
        case = cases[entry["id"]]
        if case["question"] != entry["question"]:
            raise ValueError("Question changed since run")
        if "response" not in entry:
            reviewed.append(
                {
                    "id": entry["id"],
                    "passed": False,
                    "failure_stage": "runtime",
                    "error_type": entry["error_type"],
                }
            )
            continue
        sources = {
            r["record_id"]: sid
            for r, sid in zip(entry["response"]["results"], entry["retrieved_sources"])
        }
        result = check_case(case, entry["response"], sources)
        reviewed.append({"id": entry["id"], **(result or {"passed": False, "reason": "no_checks"})})
    missing = sorted(set(cases) - set(counts))
    reviewed.extend(
        {"id": qid, "passed": False, "failure_stage": "not_executed"} for qid in missing
    )
    return {
        "specified_checks_passed": sum(r["passed"] for r in reviewed),
        "cases": len(reviewed),
        "executed": sum(counts.values()),
        "missing": missing,
        "general_semantic_accuracy": None,
        "human_review_required": True,
        "results": reviewed,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("data/relationship_diagnostics.json"))
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = review(
        json.loads(args.dataset.read_text(encoding="utf-8")),
        json.loads(args.report.read_text(encoding="utf-8")),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "passed": result["specified_checks_passed"],
                "cases": result["cases"],
                "failures": [r for r in result["results"] if not r["passed"]],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
