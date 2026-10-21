"""Explicit opt-in entry point for the frozen first-response experiment."""

import argparse
import json
import sys
from pathlib import Path

from .first_response_cases import DEVELOPMENT, HOLDOUT, EXTRA_DOCUMENTS, HOLDOUT_DOCUMENTS, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--split", choices=["development", "holdout", "identity_confirmation", "identity_search_confirmation", "identity_completion_confirmation", "integrity_development", "integrity_confirmation", "integrity_supplement", "integrity_v2_development", "integrity_v2_confirmation"], default="development")
    args, remaining = parser.parse_known_args()
    declared = json.loads(Path(__file__).with_name("first_response_manifest.json").read_text(encoding="utf-8"))
    if declared != manifest():
        parser.error("Frozen fixture manifest differs; explicitly version the fixture before running comparisons")
    if args.split == "identity_confirmation":
        from .identity_followup_cases import DOCUMENTS, CASES, manifest as identity_manifest
        declared = json.loads(Path(__file__).with_name("identity_followup_manifest.json").read_text("utf-8"))
        if declared != identity_manifest():
            parser.error("Frozen independent identity confirmation differs")
    if args.split == "identity_search_confirmation":
        from .identity_search_cases import DOCUMENTS, CASES, manifest as search_manifest
        declared = json.loads(Path(__file__).with_name('identity_search_manifest.json').read_text('utf-8'))
        if declared != search_manifest():
            parser.error('Frozen independent scoped-search confirmation differs')
    if args.split == 'identity_completion_confirmation':
        from .identity_completion_cases import DOCUMENTS, CASES, manifest as completion_manifest
        declared = json.loads(Path(__file__).with_name('identity_completion_manifest.json').read_text('utf-8'))
        if declared != completion_manifest():
            parser.error('Frozen independent direct-completion confirmation differs')
    if args.split.startswith('integrity_'):
        from .answer_integrity_cases import load
        DOCUMENTS, CASES, declared = load(args.split.removeprefix('integrity_'))
    if not args.execute:
        print(json.dumps({"status": "PLAN_ONLY", "fixtures": declared, "split": args.split,
                          "model_arguments": remaining, "models_started": False}, ensure_ascii=False, indent=2))
        return
    # Importing or viewing the plan cannot load models or invoke any evaluation.
    from . import response_latency as runner
    if args.split.startswith('integrity_') or args.split in {"identity_confirmation", "identity_search_confirmation", "identity_completion_confirmation"}:
        runner.DOCUMENTS[:] = DOCUMENTS
    elif args.split == "development":
        runner.DOCUMENTS.extend(EXTRA_DOCUMENTS)
    else:
        runner.DOCUMENTS[:] = HOLDOUT_DOCUMENTS
    cases = CASES if args.split.startswith('integrity_') or args.split in {"identity_confirmation", "identity_search_confirmation", "identity_completion_confirmation"} else DEVELOPMENT if args.split == "development" else HOLDOUT
    runner.CASES.update(cases)
    if "--cases" not in remaining:
        remaining += ["--cases", *cases]
    remaining += ["--fixture-manifest-sha256", declared["sha256"], "--fixture-split", args.split]
    sys.argv = [sys.argv[0], *remaining]
    runner.main()


if __name__ == "__main__":
    main()
