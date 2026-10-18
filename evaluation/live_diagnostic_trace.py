"""Run unchanged LocalModels and Service on the existing synthetic search fixture."""

import argparse
import hashlib
import json
import time
from dataclasses import asdict, replace
from pathlib import Path

from evaluation.diagnose_search import (
    analyze,
    capture_binding,
    load_cases,
    read_events,
    write_report,
)
from pma.diagnostics import start_trace
from pma.models import LocalModels
from pma.service import Service
from pma.settings import AppSettings
from pma.store import Store


class MeasuredModels(LocalModels):
    def __init__(self, settings):
        super().__init__(settings)
        self.calls = []

    def structured(self, *args, **kwargs):
        started = time.perf_counter()
        succeeded = False
        try:
            result = super().structured(*args, **kwargs)
            succeeded = True
            return result
        finally:
            self.calls.append(
                {
                    "operation": "structured",
                    "succeeded": succeeded,
                    "seconds": time.perf_counter() - started,
                }
            )

    def extract(self, *args, **kwargs):
        started = time.perf_counter()
        try:
            return super().extract(*args, **kwargs)
        finally:
            self.calls.append({"operation": "extract", "seconds": time.perf_counter() - started})

    def embed(self, *args, **kwargs):
        started = time.perf_counter()
        try:
            return super().embed(*args, **kwargs)
        finally:
            self.calls.append({"operation": "embed", "seconds": time.perf_counter() - started})


def run(dataset_path, output):
    fixture = json.loads(dataset_path.read_text(encoding="utf-8"))
    if fixture.get("synthetic") is not True:
        raise ValueError("Only explicitly synthetic fixtures are accepted")
    output.mkdir(parents=True, exist_ok=False)
    settings = replace(AppSettings.from_env(), data_dir=output, diagnostics=False)
    settings.validate()
    models = MeasuredModels(settings)
    health = models.health()
    if any(value != "ready" for value in health.values()):
        raise RuntimeError("MODEL_NOT_READY")
    store = Store(output / "evaluation.db")
    service = Service(store, models, settings)
    report = {
        "mode": "live_local_models",
        "synthetic_only": True,
        "dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        "llm": asdict(settings.llm),
        "embedding_revision": settings.embedding_revision,
        "answer_validation": settings.answer_validation,
        "code_sha256": {
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [
                Path("pma/models.py"),
                Path("pma/service.py"),
                Path("pma/facts.py"),
                Path("pma/grounding.py"),
                Path("prompts/extraction.txt"),
            ]
        },
        "records": [],
        "questions": [],
        "calls": models.calls,
    }

    def save():
        (output / "live_results.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    aliases = {}
    for index, source in enumerate(fixture["records"], 1):
        print(f"record {index}/{len(fixture['records'])} {source['id']} starting", flush=True)
        started = time.perf_counter()
        created = store.create(source["text"], source.get("reference_time"))
        rid = created["record_id"]
        aliases[source["id"]] = rid
        service.run_one()
        record = store.get(rid)
        report["records"].append(
            {
                "id": source["id"],
                "record_id": rid,
                "status": record["status"],
                "error_code": record.get("error_code"),
                "memories": record["memories"],
                "seconds": time.perf_counter() - started,
            }
        )
        save()
        print(
            f"record {source['id']}: {record['status']} memories={len(record['memories'])}",
            flush=True,
        )
        if service.worker_paused:
            raise RuntimeError("MODEL_FAILURE_DURING_EXTRACTION")
    bindings = {}
    for index, case in enumerate(fixture["questions"], 1):
        print(f"question {index}/{len(fixture['questions'])} {case['id']} starting", flush=True)
        entry = {"id": case["id"], "question": case["question"], "expected": case["expected"]}
        started = time.perf_counter()
        before = len(models.calls)
        with start_trace(enabled=True, path=output / "trace.jsonl") as trace:
            try:
                entry["response"] = service.answer(case["question"], today=fixture["today"])
            except Exception as error:
                entry["error_type"] = type(error).__name__
        bindings.update(capture_binding(trace, case["id"], records=aliases))
        entry["seconds"] = time.perf_counter() - started
        entry["model_calls"] = len(models.calls) - before
        report["questions"].append(entry)
        (output / "bindings.json").write_text(json.dumps(bindings, indent=2), encoding="utf-8")
        save()
        print(
            f"question {case['id']}: {entry.get('response', {}).get('status', entry.get('error_type'))} {entry['seconds']:.1f}s",
            flush=True,
        )
    store.checkpoint()
    summary, cases = analyze(read_events(output / "trace.jsonl"), load_cases(fixture), bindings)
    summary["mode"] = "live_local_models"
    summary["limitations"][0] = (
        "Actual local extraction, embeddings and query/answer models were executed once; semantic answers require review."
    )
    summary["extraction_status"] = {r["id"]: r["status"] for r in report["records"]}
    write_report(output, summary, cases)
    print(
        json.dumps(
            {
                "output": str(output.resolve()),
                "evaluated": summary["evaluable_questions"],
                "losses": summary["loss_stage_counts"],
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("data/search_diagnostics.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.dataset, args.output)
