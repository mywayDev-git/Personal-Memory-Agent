"""Synthetic downstream regression. Frozen extraction isolates projection/QA changes.

Run before in a separate process with --baseline-code pointing at an archived pma tree.
No personal database is opened. Gold expectations are never passed to a model.
"""

import argparse
import copy
import hashlib
import json
import shutil
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path

DIAGNOSTIC_CASES = {
    "negation-1",
    "plan-0",
    "quote-1",
    "quote-2",
    "omission-1",
    "relative-0",
    "relative-2",
    "emotion-2",
    "cause-0",
    "cause-1",
    "recipient-0",
    "untrusted-2",
}


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def evidence_row(row):
    return dict(
        row["memory"],
        id=row["id"],
        fact=row["fact"],
        evidence=row["evidence"],
        source_text=row["text"],
        reference_time=row["reference_time"],
        recorded_at=row["created_at"],
        time=row["fact"]["event_time"],
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("output/kiwi-focused-v1"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline-code", type=Path)
    parser.add_argument("--mode", choices=["frozen", "live", "diagnostic"], default="frozen")
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--case-file",
        type=Path,
        help="Separate synthetic live cases, frozen before model execution",
    )
    args = parser.parse_args()
    if args.baseline_code:
        sys.path.insert(0, str(args.baseline_code.resolve()))
    from evaluation.kiwi_compare import model_identity
    from evaluation.kiwi_runtime import Meter
    from pma.models import LocalModels
    from pma.service import Service
    from pma.settings import AppSettings
    from pma.store import Store

    if args.case_file and args.mode != "live":
        raise ValueError("--case-file is only for independent live cases")
    cases = json.loads((args.case_file or args.source / "cases.json").read_text(encoding="utf-8"))
    prior = json.loads((args.source / "manifest.json").read_text(encoding="utf-8"))
    settings = AppSettings.from_env()
    settings = replace(
        settings,
        embedding_revision=prior["settings"]["embedding"].split(":")[1],
        llm=replace(settings.llm, **prior["settings"]["llm"]),
    )
    output = args.output.resolve()
    personal = settings.data_dir.resolve()
    if output == personal or personal in output.parents or output in personal.parents:
        raise ValueError("Personal database overlap")
    root = args.baseline_code or Path(".")
    code = {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for folder in ("pma", "scripts")
        for p in sorted((root / folder).rglob("*.py"))
    }
    code["runner"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    for folder in ("prompts", "schema", "config"):
        for p in sorted(Path(folder).rglob("*")):
            if p.suffix in {".txt", ".json", ".py"}:
                code[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
    inputs = {
        c["id"]: json.loads(
            (args.source / "completed" / f"{c['id']}-app.json").read_text(encoding="utf-8")
        )
        for c in cases
        if args.mode != "live"
    }
    identity = dict(
        mode=args.mode,
        cases=digest(cases),
        inputs=digest(inputs),
        code=code,
        settings=dict(llm=vars(settings.llm), embedding=settings.embedding_key),
        models=model_identity(settings),
    )
    output.mkdir(parents=True, exist_ok=True)
    manifest = output / "manifest.json"
    if manifest.exists():
        if json.loads(manifest.read_text(encoding="utf-8")) != identity:
            raise ValueError("Resume identity mismatch; choose a new output directory")
    elif any(output.iterdir()):
        raise ValueError("Unowned output directory")
    else:
        write(manifest, identity)
        write(output / "cases.json", cases)
        for folder in ("pma", "scripts", "config", "prompts", "schema"):
            source = root / folder if folder in {"pma", "scripts"} else Path(folder)
            shutil.copytree(
                source,
                output / "executed_source" / folder,
                ignore=shutil.ignore_patterns("__pycache__"),
            )
        shutil.copyfile(__file__, output / "executed_source" / "runner.py")
    count = 0
    for case in cases:
        if args.mode == "diagnostic" and case["id"] not in DIAGNOSTIC_CASES:
            continue
        dest = output / f"{case['id']}.json"
        if (
            dest.exists()
            and json.loads(dest.read_text(encoding="utf-8")).get("status") == "complete"
        ):
            continue
        models = LocalModels(settings)
        meter = Meter(models)
        traces = []
        entry = dict(case=case["id"], mode=args.mode, status="running", diagnostics=traces)
        started = time.perf_counter()
        with tempfile.TemporaryDirectory(prefix="synthetic-", dir=output) as tmp, meter:
            try:
                store = Store(Path(tmp) / "memory.db")
                service = Service(store, models, settings)
                if hasattr(service, "trace"):
                    service.diagnostic_sink = traces.append
                for record in case["records"]:
                    created = store.create(record["text"], record["reference_time"])
                    if args.mode == "live":
                        meter.stage = "extraction"
                        service.run_one()
                        if store.get(created["record_id"])["status"] not in {
                            "ready",
                            "ready_empty",
                        }:
                            raise ValueError("EXTRACTION_FAILED")
                    else:
                        job = store.claim()
                        rows = [
                            r
                            for r in inputs[case["id"]]["legacy_memories"]
                            if r["text"] == record["text"]
                        ]
                        memories = copy.deepcopy([r["memory"] for r in rows])
                        provenance = [{"evidence": r["evidence"]} for r in rows]
                        meter.stage = "frozen_embedding"
                        store.publish(
                            job,
                            memories,
                            models.embed([m["content"] for m in memories]),
                            settings.embedding_key,
                            {"provenance": provenance},
                        )
                _, snapshot = store.snapshot(settings.embedding_key)
                entry["memories"] = [
                    {k: v for k, v in r.items() if k != "vector"} for r in snapshot
                ]
                question = case["questions"][0]["text"]
                entry["question"] = question
                meter.stage = "application_qa"
                entry["response"] = service.answer(question, today="2026-10-13")
                if args.mode == "diagnostic":
                    variants = {
                        "selected": entry["response"]["results"],
                        "all_memories": [evidence_row(r) for r in snapshot],
                        "source": [
                            dict(
                                id=f"source-{i}",
                                content=r["text"],
                                source_text=r["text"],
                                reference_time=r["reference_time"],
                                evidence=[dict(quote=r["text"], start=0, end=len(r["text"]))],
                            )
                            for i, r in enumerate(case["records"])
                        ],
                    }
                    entry["conditions"] = {}
                    for label, evidence in variants.items():
                        meter.stage = label
                        response = models.answer(question, evidence)
                        ids = {r["id"] for r in evidence}
                        valid = (response["status"] == "answered") == bool(response["items"])
                        valid = valid and all(
                            c in ids for item in response["items"] for c in item["citations"]
                        )
                        verified = (
                            models.verify(question, evidence, response["items"])
                            if response["items"] and valid
                            else None
                        )
                        entry["conditions"][label] = dict(
                            response=response,
                            citation_valid=valid,
                            verified=verified,
                            evidence=evidence,
                        )
                entry["status"] = "complete"
            except Exception as exc:
                entry.update(status="failed", error=type(exc).__name__, detail=str(exc))
        entry.update(seconds=time.perf_counter() - started, calls=meter.calls)
        write(dest, entry)
        print(case["id"], entry["status"], round(entry["seconds"], 2), flush=True)
        count += 1
        if args.limit and count >= args.limit:
            break


if __name__ == "__main__":
    main()
