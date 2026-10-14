"""Serial, synthetic-only fixed-evidence ablations and full-path replay.

python -m evaluation.answer_validation --phase prepare|fixed|application|live|repeat
Baseline snapshot must be preserved before edits under ROOT/baseline-code.
"""

import argparse
import copy
import hashlib
import importlib.util
import json
import random
import shutil
import tempfile
import time
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import requests

from evaluation.downstream_regression import digest, write
from evaluation.kiwi_compare import model_identity
from evaluation.kiwi_runtime import Meter
from pma import models as models_module
from pma.answer_review import answer_found
from pma.errors import AppError
from pma.grounding import claims_supported, grounded_response
from pma.models import ANSWER_SCHEMA, LocalModels
from pma.service import Service
from pma.settings import AppSettings
from pma.store import Store
from scripts.memory_agent.validator import schema_errors

ROOT = Path("output/answer-validation-v1")
CORE = {
    "state-0",
    "state-1",
    "state-2",
    "relative-2",
    "untrusted-2",
    "negation-1",
    "distractor-negative",
    "cause-1",
}


def baseline():
    import sys

    path = ROOT / "baseline-code/pma"
    spec = importlib.util.spec_from_file_location(
        "av_baseline", path / "__init__.py", submodule_search_locations=[str(path)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    from av_baseline.grounding import grounded_response as old_grounded
    from av_baseline.models import LocalModels as OldModels
    from av_baseline.service import Service as OldService

    return OldModels, OldService, old_grounded


def cases():
    original = json.loads(
        Path("output/downstream-final-v8-frozen/cases.json").read_text(encoding="utf-8")
    )
    distractors = json.loads(Path("data/downstream_distractors.json").read_text(encoding="utf-8"))
    new = json.loads(Path("data/answer_validation_cases.json").read_text(encoding="utf-8"))
    return original + distractors + new


def fixed_found(entry):
    found = copy.deepcopy(entry["response"])
    for key in ("items", "validation", "clarification"):
        found.pop(key, None)
    found["status"] = "ok"
    # Aggregate/unsupported questions have no query_plan and no selected evidence.
    found.setdefault("query_plan", {})
    return found


def legacy_answer(models, old_models, question, found, trace, grounding, *, improved=False):
    if not found["results"] or found["query_plan"].get("needs_time_anchor"):
        return dict(status="insufficient_evidence", items=[])
    response = grounding(found)
    structured = response is not None
    if response is None:
        response = models.answer(question, found["results"])
    trace("answer", structured=structured, response=response)
    if schema_errors(response, ANSWER_SCHEMA):
        raise ValueError("INVALID_ANSWER")
    ids = {r["id"] for r in found["results"]}
    if (response["status"] == "answered") != bool(response["items"]) or any(
        c not in ids for item in response["items"] for c in item["citations"]
    ):
        raise ValueError("INVALID_CITATION")
    if response["items"] and not claims_supported(
        response["items"], found["results"], found["query_plan"]
    ):
        return dict(status="insufficient_evidence", items=[], validation="rejected_attributes")
    if response["items"] and not structured:
        # Same answer-only evidence packaging in both answer and old verifier.
        proxy = old_models(models.settings)
        proxy.structured = models.structured
        if improved:
            proxy.compact_evidence = LocalModels.answer_evidence
        try:
            verified = proxy.verify(question, found["results"], response["items"])
        except (ValueError, requests.RequestException, AppError) as exc:
            verified = False
            trace("verification_error", error=type(exc).__name__, code=getattr(exc, "code", None))
        trace("verification", supported=verified)
        if not verified:
            return dict(status="insufficient_evidence", items=[], validation="rejected")
    return response


def application(case, models, service_type, settings, output, meter, frozen=None):
    traces = []
    with tempfile.TemporaryDirectory(prefix="synthetic-", dir=output) as tmp:
        store = Store(Path(tmp) / "memory.db")
        service = service_type(store, models, settings, diagnostic_sink=traces.append)
        for record in case["records"]:
            created = store.create(record["text"], record["reference_time"])
            if frozen is None:
                meter.stage = "extraction"
                service.run_one()
                if store.get(created["record_id"])["status"] not in {"ready", "ready_empty"}:
                    raise ValueError("EXTRACTION_FAILED")
            else:
                job = store.claim()
                rows = [r for r in frozen["memories"] if r["text"] == record["text"]]
                memories = copy.deepcopy([r["memory"] for r in rows])
                meter.stage = "frozen_embedding"
                store.publish(
                    job,
                    memories,
                    models.embed([m["content"] for m in memories]),
                    settings.embedding_key,
                    {"provenance": [{"evidence": r["evidence"]} for r in rows]},
                )
        _, snapshot = store.snapshot(settings.embedding_key)
        meter.stage = "application_qa"
        response = service.answer(case["questions"][0]["text"], today="2026-10-13")
        return dict(
            response=response,
            diagnostics=traces,
            memories=[{k: v for k, v in r.items() if k != "vector"} for r in snapshot],
        )


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument(
        "--phase", choices=["prepare", "fixed", "application", "live", "repeat"], required=True
    )
    parser.add_argument("--split", choices=["development", "holdout", "all"], default="development")
    parser.add_argument("--ids", nargs="*")
    parser.add_argument(
        "--conditions", nargs="*", choices=["baseline", "answer", "review", "repair"]
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument("--tag", default="run-1")
    args = parser.parse_args()
    old_models, old_service, old_grounded = baseline()
    prior = json.loads(
        Path("output/downstream-final-v8-frozen/manifest.json").read_text(encoding="utf-8")
    )
    settings = AppSettings.from_env()
    settings = replace(
        settings,
        answer_validation=True,
        embedding_revision=prior["settings"]["embedding"].split(":")[1],
        llm=replace(settings.llm, **prior["settings"]["llm"]),
    )
    all_cases = cases()
    output = ROOT / args.tag / args.phase
    personal = settings.data_dir.resolve()
    if (
        personal in output.resolve().parents
        or output.resolve() in personal.parents
        or personal == output.resolve()
    ):
        raise ValueError("PERSONAL_DB_OVERLAP")
    output.mkdir(parents=True, exist_ok=True)
    code = {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest()
        for folder in ["pma", "scripts", "config", "prompts", "schema"]
        for p in Path(folder).rglob("*")
        if p.is_file() and p.suffix in {".py", ".json", ".txt"}
    }
    code[__file__] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    identity = dict(
        code=code,
        cases=digest(all_cases),
        baseline={
            str(p.relative_to(ROOT / "baseline-code")): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (ROOT / "baseline-code").rglob("*")
            if p.is_file() and "__pycache__" not in p.parts
        },
        prepared={
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (ROOT / "prepared").glob("*.json")
        }
        if args.phase != "prepare"
        else {},
        settings=dict(
            llm=vars(settings.llm),
            embedding=settings.embedding_key,
            answer_validation=settings.answer_validation,
        ),
        models=model_identity(settings),
    )
    manifest = output / "manifest.json"
    if manifest.exists():
        if json.loads(manifest.read_text(encoding="utf-8")) != identity:
            raise ValueError("RESUME_IDENTITY_MISMATCH")
    else:
        write(manifest, identity)
        write(output / "cases.json", all_cases)
        for folder in ["pma", "scripts", "config", "prompts", "schema"]:
            shutil.copytree(
                folder,
                output / "executed_source" / folder,
                ignore=shutil.ignore_patterns("__pycache__"),
            )
        shutil.copyfile(__file__, output / "executed_source/runner.py")
    cache = ROOT / "prepared"
    cache.mkdir(exist_ok=True)
    count = 0
    for case in all_cases:
        cid = case["id"]
        if args.ids and cid not in args.ids:
            continue
        if args.split != "all" and case.get("split", "development") != args.split:
            continue
        if args.phase == "repeat" and cid not in CORE:
            continue
        prepared = cache / f"{cid}.json"
        if args.phase == "prepare":
            if prepared.exists():
                continue
            if not cid.startswith("av-"):
                source = (
                    Path(
                        "output/downstream-final-v8-distractors"
                        if cid.startswith("distractor")
                        else "output/downstream-final-v8-frozen"
                    )
                    / f"{cid}.json"
                )
                entry = json.loads(source.read_text(encoding="utf-8"))
                entry["provenance"] = dict(
                    path=str(source), sha256=hashlib.sha256(source.read_bytes()).hexdigest()
                )
                write(prepared, entry)
                continue
            labels = ["baseline_prepare"]
        elif args.phase in {"fixed", "repeat"}:
            labels = (
                ["baseline", "answer", "review", "repair"]
                if args.phase == "fixed"
                else ["repeat-2", "repeat-3"]
            )
            random.Random(42 + all_cases.index(case)).shuffle(labels)
        else:
            labels = [args.phase]
        if args.conditions and args.phase == "fixed":
            labels = [label for label in labels if label in args.conditions]
        for label in labels:
            dest = output / f"{cid}--{label}.json"
            if (
                dest.exists()
                and json.loads(dest.read_text(encoding="utf-8")).get("status") == "complete"
            ):
                continue
            model = (
                old_models(settings)
                if label in {"baseline", "baseline_prepare"}
                else LocalModels(settings)
            )
            meter = Meter(model)
            traces = []
            entry = dict(case=cid, condition=label, status="running", diagnostics=traces)
            started = time.perf_counter()
            with meter, patch("av_baseline.models.post_json", models_module.post_json):
                try:
                    if args.phase == "prepare":
                        entry.update(application(case, model, old_service, settings, output, meter))
                    elif args.phase in {"application", "live"}:
                        frozen = (
                            json.loads(prepared.read_text(encoding="utf-8"))
                            if args.phase == "application"
                            else None
                        )
                        entry.update(
                            application(case, model, Service, settings, output, meter, frozen)
                        )
                    else:
                        cached = json.loads(prepared.read_text(encoding="utf-8"))
                        found = fixed_found(cached)
                        entry["evidence_hash"] = digest(found)
                        entry["prepared_sha256"] = hashlib.sha256(prepared.read_bytes()).hexdigest()
                        entry["found"] = found
                        question = case["questions"][0]["text"]

                        def trace(stage, **data):
                            traces.append(copy.deepcopy(dict(stage=stage, **data)))

                        meter.stage = label
                        if label in {"baseline", "answer"}:
                            response = legacy_answer(
                                model,
                                old_models,
                                question,
                                found,
                                trace,
                                old_grounded
                                if label == "baseline"
                                else lambda f: grounded_response(f, semantic_current=True),
                                improved=label == "answer",
                            )
                        elif found["query_plan"].get("needs_time_anchor"):
                            response = dict(status="insufficient_evidence", items=[])
                        else:
                            response = answer_found(
                                model, question, found, trace, repair=label != "review"
                            )
                        entry["response"] = response
                    entry["status"] = "complete"
                except Exception as exc:
                    entry.update(status="failed", error=type(exc).__name__, detail=str(exc))
            entry.update(seconds=time.perf_counter() - started, calls=meter.calls)
            write(dest, entry)
            if args.phase == "prepare" and entry["status"] == "complete":
                write(prepared, entry)
            print(cid, label, entry["status"], round(entry["seconds"], 2), flush=True)
        count += 1
        if args.limit and count >= args.limit:
            break


if __name__ == "__main__":
    main()
