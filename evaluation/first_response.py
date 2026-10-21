"""Explicit opt-in entry point for the frozen first-response experiment."""

import argparse
import json
import sys

from .first_response_cases import DEVELOPMENT, HOLDOUT, EXTRA_DOCUMENTS, HOLDOUT_DOCUMENTS, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--split", choices=["development", "holdout"], default="development")
    args, remaining = parser.parse_known_args()
    if not args.execute:
        print(json.dumps({"status": "PLAN_ONLY", "fixtures": manifest(), "split": args.split,
                          "model_arguments": remaining, "models_started": False}, ensure_ascii=False, indent=2))
        return
    # Importing or viewing the plan cannot load models or invoke any evaluation.
    from . import response_latency as runner
    if args.split == "development":
        runner.DOCUMENTS.extend(EXTRA_DOCUMENTS)
    else:
        runner.DOCUMENTS[:] = HOLDOUT_DOCUMENTS
    runner.CASES.update(DEVELOPMENT if args.split == "development" else HOLDOUT)
    if "--cases" not in remaining:
        remaining += ["--cases", *(DEVELOPMENT if args.split == "development" else HOLDOUT)]
    sys.argv = [sys.argv[0], *remaining]
    runner.main()


if __name__ == "__main__":
    main()
