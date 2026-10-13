"""Resumable real-model evaluation in an owned synthetic directory only.

Automatic evidence coverage is deliberately NOT semantic answer accuracy.
The original raw response and expected evidence remain available for human review.
"""

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import statistics
import time
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import numpy as np

from evaluation.build_life_dataset import ROOT, validate
from evaluation.search_diagnostics import TracedModels
from pma.service import Service
from pma.settings import AppSettings
from pma.store import Store


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + f".{uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Windows readers/virus scanners can briefly deny rename-over-existing. Keep the
    # old checkpoint intact and retry; separate temporary names avoid writer collisions.
    for attempt in range(12):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 11:
                raise
            time.sleep(min(0.025 * 2**attempt, 0.2))


class LifeModels(TracedModels):
    def extract(self, text, context):
        self.extraction_error = None
        try:
            return super().extract(text, context)
        except Exception as exc:
            safe_codes = {
                "INVALID_EXTRACTION_SCHEMA",
                "INVALID_EXTRACTION_EVIDENCE_OR_SCHEMA",
                "INVALID_SOURCE_CONTEXT",
                "MODEL_TRUNCATED",
                "CONTEXT_LIMIT",
            }
            self.extraction_error = dict(
                type=type(exc).__name__,
                code=str(exc) if str(exc) in safe_codes else getattr(exc, "code", None),
            )
            raise

    def reset_trace(self):
        self.last_stage = "query_interpretation"
        self.last_understanding = self.last_evidence = self.last_answer = None
        self.selection_candidates = None

    def select(self, question, evidence):
        self.selection_candidates = evidence
        return super().select(question, evidence)

    def embed(self, texts):
        vectors = super().embed(texts)
        self.last_vectors = vectors
        return vectors


def expectation(case, visible, records):
    """Missing future evidence must not become the expected answer at an earlier snapshot."""
    available = [sid for sid in case["relevant"] if sid in visible]
    missing = sorted(set(case["relevant"]) - set(available))
    return {
        **case["expected"],
        "available_support": available,
        "not_yet_visible": missing,
        "supporting_facts": [f for sid in available for f in records[sid]["gold_facts"]],
        "mode": "abstain_or_clarify"
        if not available
        else "partial_evidence"
        if missing
        else case["expected"]["mode"],
        "snapshot_requirement": "아직 입력하지 않은 기록을 근거로 답하지 않는다. 일부 근거만 있으면 알려진 부분과 불명인 부분을 구분한다.",
    }


def assess(case, expected, response, source_ids):
    rows = response.get("results", [])
    by_memory = {r["id"]: source_ids[r["record_id"]] for r in rows}
    retrieved = set(by_memory.values())
    cited_ids = {cid for item in response.get("items", []) for cid in item.get("citations", [])}
    cited = {by_memory[cid] for cid in cited_ids if cid in by_memory}
    needed = set(expected["available_support"])
    valid_citations = cited_ids <= set(by_memory)
    answered = response["status"] == "answered"
    if response["status"] == "unsupported_intent":
        signal = "unsupported_intent"
    elif expected["mode"] == "abstain_or_clarify":
        signal = "abstained" if not answered else "review_unsupported_claim_or_clarification"
    elif not needed <= retrieved:
        signal = "missing_expected_evidence"
    elif not answered:
        signal = "abstained_with_expected_evidence"
    elif not needed <= cited:
        signal = "incomplete_expected_citations"
    else:
        signal = "evidence_checks_passed"
    return dict(
        signal=signal,
        citation_ids_valid=valid_citations,
        retrieved_sources=sorted(retrieved),
        cited_sources=sorted(cited),
        expected_evidence_coverage=len(needed & retrieved) / len(needed) if needed else None,
        semantic_correct=None,
        semantic_review="pending",
        failure_stage="unconfirmed",
        suspected_stage=(
            "retrieval_or_query_interpretation"
            if signal == "missing_expected_evidence"
            else "answer"
            if signal == "abstained_with_expected_evidence"
            else None
        ),
        context_dependent=case["needs_conversation_context"],
    )


def summarize(data, entries):
    groups = defaultdict(list)
    for e in entries:
        for key in (
            "all",
            "category:" + e["category"],
            "snapshot:" + str(e["snapshot"]),
            "split:" + e["split"],
            "variant:" + e["variant"],
        ):
            groups[key].append(e)
    result = {}
    for key, rows in groups.items():
        times = sorted(r["elapsed_seconds"] for r in rows)
        result[key] = dict(
            executed=len(rows),
            errors=sum("error_type" in r for r in rows),
            signals=dict(
                Counter(r.get("assessment", {}).get("signal", "runtime_error") for r in rows)
            ),
            median_seconds=round(statistics.median(times), 3),
            p95_seconds=round(times[min(len(times) - 1, int(len(times) * 0.95))], 3),
            semantic_reviewed=sum(
                r.get("assessment", {}).get("semantic_correct") is not None for r in rows
            ),
        )
    planned = {f"forward-300-{q['id']}" for q in data["questions"]}
    planned |= {
        f"forward-{n}-{q['id']}"
        for n in (30, 100)
        for q in data["questions"]
        if q["repeat_at_snapshots"]
    }
    planned |= {f"reverse-300-{q['id']}" for q in data["questions"] if q["repeat_at_snapshots"]}
    done = [e["run_id"] for e in entries]
    return dict(
        planned=len(planned),
        executed=len(done),
        missing=sorted(planned - set(done)),
        duplicates=[k for k, v in Counter(done).items() if v > 1],
        unexpected=sorted(set(done) - planned),
        groups=result,
        semantic_accuracy=None,
        note="Evidence coverage and citation IDs are separate from semantic correctness; pending review is not a pass.",
    )


class Run:
    def __init__(self, dataset, directory):
        self.data = json.loads(dataset.read_text(encoding="utf-8"))
        validate(self.data)
        self.records = {r["id"]: r for r in self.data["records"]}
        self.directory = directory.resolve()
        # Never attach to an arbitrary existing database or the application's data directory.
        settings = AppSettings.from_env()
        if self.directory == settings.data_dir.resolve():
            raise ValueError("USER_DATABASE_FORBIDDEN")
        manifest = dict(
            synthetic_only=True,
            dataset_sha256=digest(dataset),
            code_sha256={
                str(p.relative_to(ROOT)): digest(p)
                for folder in ("pma", "scripts/memory_agent", "prompts", "schema")
                for p in sorted((ROOT / folder).glob("*"))
                if p.is_file() and p.suffix in {".py", ".txt", ".json"}
            },
            embedding_revision=settings.embedding_revision,
            generation_model=settings.llm.model,
            generation_parameters=dict(
                seed=settings.llm.seed,
                temperature=settings.llm.temperature,
                max_tokens=settings.llm.max_tokens,
                context_tokens=settings.context_tokens,
            ),
            source_records=self.data["records"],
        )
        marker = self.directory / "manifest.json"
        if self.directory.exists():
            if not marker.exists() or json.loads(marker.read_text(encoding="utf-8")) != manifest:
                raise ValueError("RUN_DIRECTORY_OR_VERSION_MISMATCH")
        else:
            self.directory.mkdir(parents=True)
            write_json(marker, manifest)
        snapshot_path = self.directory / "dataset.json"
        if snapshot_path.exists() and digest(snapshot_path) != manifest["dataset_sha256"]:
            raise ValueError("RUN_DATASET_SNAPSHOT_CHANGED")
        if not snapshot_path.exists():
            snapshot_path.write_bytes(dataset.read_bytes())
        self.settings = replace(settings, data_dir=self.directory)
        self.models = LifeModels(self.settings)
        self.cache = self.load("extractions.json", {})
        self.entries = self.load("questions.json", [])
        executions = self.load("executions.json", [])
        executions.append(
            dict(
                started_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                python=platform.python_version(),
                libraries={
                    name: importlib.metadata.version(name)
                    for name in ("numpy", "requests", "jsonschema")
                },
                evaluation_code={
                    str(p.relative_to(ROOT)): digest(p)
                    for p in (Path(__file__), ROOT / "evaluation/build_life_dataset.py")
                },
                generation_revision=os.getenv("PMA_GENERATION_REVISION", "unverified"),
            )
        )
        write_json(self.directory / "executions.json", executions)

    def load(self, name, default):
        path = self.directory / name
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default

    def import_cache(self, directory):
        if self.cache:
            origin = self.load("cache_origin.json", {})
            if origin.get("manifest_sha256") == digest(directory / "manifest.json") and origin.get(
                "extractions_sha256"
            ) == digest(directory / "extractions.json"):
                return
            raise ValueError("CACHE_ALREADY_PRESENT")
        old_manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        current = self.load("manifest.json", {})
        for key in (
            "synthetic_only",
            "code_sha256",
            "embedding_revision",
            "generation_model",
            "generation_parameters",
        ):
            if old_manifest.get(key) != current[key]:
                raise ValueError("INCOMPATIBLE_EXTRACTION_CACHE")
        cached = json.loads((directory / "extractions.json").read_text(encoding="utf-8"))
        if not set(cached) <= set(self.records):
            raise ValueError("UNKNOWN_CACHE_SOURCES")
        originals = {r["id"]: r for r in old_manifest["source_records"]}
        cached = {
            sid: result
            for sid, result in cached.items()
            if sid in originals
            and all(
                originals[sid][key] == self.records[sid][key]
                for key in ("text", "reference_time", "recorded_at")
            )
        }
        self.cache = cached
        write_json(self.directory / "extractions.json", cached)
        write_json(
            self.directory / "cache_origin.json",
            dict(
                manifest_sha256=digest(directory / "manifest.json"),
                extractions_sha256=digest(directory / "extractions.json"),
                reused_ids=sorted(cached),
            ),
        )

    def extract(self, checkpoints=False):
        store = Store(self.directory / "extraction.db")
        store.recover()
        service = Service(store, self.models, self.settings)
        for index, source in enumerate(self.data["records"], 1):
            sid = source["id"]
            if sid in self.cache:
                if checkpoints and index in (30, 100):
                    self.questions(counts=[index], reverse=False)
                continue
            store.clock = lambda s=source: s["recorded_at"]
            rid = store.create(source["text"], source["reference_time"])["record_id"]
            self.models.last_stage = "extraction"
            self.models.last_vectors = []
            started = time.monotonic()
            # A process interruption may leave an uncached job queued by recover().
            # Drain it before reading this record's vectors; never attribute another job's result.
            while store.get(rid)["status"] == "queued":
                service.run_one()
            result = store.get(rid)
            self.cache[sid] = dict(
                status=result["status"],
                memories=result["memories"],
                vectors=np.asarray(self.models.last_vectors).tolist()
                if result["status"] == "ready"
                else [],
                error_code=result["error_code"],
                failure_stage=self.models.last_stage if result["status"] != "ready" else None,
                elapsed_seconds=round(time.monotonic() - started, 3),
                diagnostic=getattr(self.models, "extraction_error", None),
                projected_facts=[
                    row["fact"]
                    for row in store.snapshot(self.settings.embedding_key)[1]
                    if row["record_id"] == rid
                ],
            )
            write_json(self.directory / "extractions.json", self.cache)
            print(f"extract {len(self.cache)}/300 {sid}: {result['status']}", flush=True)
            if checkpoints and index in (30, 100):
                self.questions(counts=[index], reverse=False)
        store.checkpoint()

    def populate(self, store, sources):
        mapping = {}
        for source in sources:
            store.clock = lambda s=source: s["recorded_at"]
            rid = store.create(source["text"], source["reference_time"])["record_id"]
            mapping[rid] = source["id"]
            job = store.claim()
            cached = self.cache.get(source["id"])
            if not cached or cached["status"] != "ready":
                store.fail(job, "EXTRACTION_INVALID")
            else:
                store.publish(
                    job,
                    cached["memories"],
                    np.asarray(cached["vectors"]),
                    self.settings.embedding_key,
                    {"synthetic_replay": True},
                )
        return mapping

    def evaluate(self, service, mapping, case, snapshot, variant):
        run_id = f"{variant}-{snapshot}-{case['id']}"
        if any(e["run_id"] == run_id for e in self.entries):
            return
        expected = expectation(case, set(mapping.values()), self.records)
        self.models.reset_trace()
        started = time.monotonic()
        entry = dict(
            run_id=run_id,
            id=case["id"],
            question=case["question"],
            category=case["category"],
            split=case["split"],
            snapshot=snapshot,
            variant=variant,
            expected=expected,
            visible_sources=list(mapping.values()),
            source_ids=mapping,
            source_failures=[
                s for s in expected["available_support"] if self.cache[s]["status"] != "ready"
            ],
        )
        try:
            response = service.answer(case["question"], today=self.data["today"])
            entry["response"] = response
            entry["assessment"] = assess(case, expected, response, mapping)
            if entry["source_failures"]:
                entry["assessment"]["upstream_extraction_failure"] = True
        except Exception as exc:
            entry.update(error_type=type(exc).__name__, failure_stage=self.models.last_stage)
        entry.update(
            elapsed_seconds=round(time.monotonic() - started, 3),
            understood=self.models.last_understanding,
            selection_candidates=self.models.selection_candidates,
            answer_input=self.models.last_evidence,
            unvalidated_answer=self.models.last_answer,
        )
        self.entries.append(entry)
        write_json(self.directory / "questions.json", self.entries)
        write_json(self.directory / "summary.json", summarize(self.data, self.entries))
        print(
            f"question {len(self.entries)}/780 {run_id}: {entry.get('assessment', {}).get('signal', entry.get('error_type'))}",
            flush=True,
        )

    def questions(self, counts=None, reverse=True):
        counts = counts or self.data["snapshots"]
        required = self.data["records"][: 300 if reverse else max(counts)]
        if not {r["id"] for r in required} <= set(self.cache):
            raise ValueError("EXTRACTION_INCOMPLETE")
        # Fresh uniquely named replay databases: resume never inserts duplicate records.
        import tempfile

        for count in counts:
            cases = [q for q in self.data["questions"] if count == 300 or q["repeat_at_snapshots"]]
            if all(
                any(e["run_id"] == f"forward-{count}-{q['id']}" for e in self.entries)
                for q in cases
            ):
                continue
            with tempfile.TemporaryDirectory(prefix="replay-", dir=self.directory) as tmp:
                store = Store(Path(tmp) / "memory.db")
                mapping = self.populate(store, self.data["records"][:count])
                service = Service(store, self.models, self.settings)
                for case in cases:
                    self.evaluate(service, mapping, case, count, "forward")
                store.checkpoint()
        if not reverse:
            return
        with tempfile.TemporaryDirectory(prefix="reverse-", dir=self.directory) as tmp:
            store = Store(Path(tmp) / "memory.db")
            mapping = self.populate(store, list(reversed(self.data["records"])))
            service = Service(store, self.models, self.settings)
            for case in self.data["questions"]:
                if case["repeat_at_snapshots"]:
                    self.evaluate(service, mapping, case, 300, "reverse")
            store.checkpoint()

    def lifecycle(self):
        import tempfile

        checks = self.load("lifecycle.json", [])
        for event in self.data["events"]:
            if any(c["event_id"] == event["id"] for c in checks):
                continue
            with tempfile.TemporaryDirectory(prefix="lifecycle-", dir=self.directory) as tmp:
                store = Store(Path(tmp) / "memory.db")
                mapping = self.populate(store, [self.records[s] for s in event["record_ids"]])
                store.clock = lambda: "2026-10-13T20:00:00+09:00"
                service = Service(store, self.models, self.settings)
                before = store.links()
                dismissed = []
                for link in before:
                    store.dismiss_link(link["id"])
                    dismissed.append(link["signature"] if "signature" in link else link["id"])
                # Force the derived index to regenerate, not a no-op rebuild.
                with store.connect(True) as db:
                    db.execute("UPDATE facts SET projection_version=0")
                while store.rebuild_facts():
                    pass
                rid = next(r for r, s in mapping.items() if s == event["record_ids"][3])
                old_ids = {
                    r["id"]
                    for r in store.snapshot(self.settings.embedding_key)[1]
                    if r["record_id"] == rid
                }
                question = next(
                    q
                    for q in self.data["questions"]
                    if q["event_id"] == event["id"] and q["category"] == "connection"
                )
                captures = []
                dismissed_stays_gone = not store.links()
                if dismissed:
                    self.models.reset_trace()
                    dismissal_entry = dict(
                        operation="dismiss_relation", question=question["question"]
                    )
                    try:
                        dismissal_entry["response"] = service.answer(
                            question["question"], today=self.data["today"]
                        )
                        dismissal_entry["dismissed_relations_absent"] = all(
                            not set(dismissed) & set(item.get("relation_ids", []))
                            for item in dismissal_entry["response"]["items"]
                        )
                    except Exception as exc:
                        dismissal_entry["error_type"] = type(exc).__name__
                    dismissal_entry["semantic_review"] = "pending"
                    captures.append(dismissal_entry)
                source = self.records[event["record_ids"][3]]
                store.update(
                    rid,
                    1,
                    "2026-10-13 정정: 이전 내용을 지웠다. 오늘 집에서 쉬었다.",
                    source["reference_time"],
                )
                service.run_one()
                for operation in ("edit", "trash", "purge"):
                    if operation == "trash":
                        store.trash(rid)
                    if operation == "purge":
                        store.purge(rid)
                    rows = store.snapshot(self.settings.embedding_key)[1]
                    remaining = {r["id"] for r in rows}
                    entry = dict(
                        operation=operation,
                        old_memories_absent=not old_ids & remaining,
                        old_links_absent=all(
                            not old_ids & set(link["citations"]) for link in store.links()
                        ),
                    )
                    self.models.reset_trace()
                    try:
                        entry["question"] = question["question"]
                        entry["response"] = service.answer(
                            question["question"], today=self.data["today"]
                        )
                        entry["stale_citations_absent"] = all(
                            not old_ids & set(item["citations"])
                            for item in entry["response"]["items"]
                        )
                    except Exception as exc:
                        entry["error_type"] = type(exc).__name__
                    entry["semantic_review"] = "pending"
                    captures.append(entry)
                checks.append(
                    dict(
                        event_id=event["id"],
                        dismissed_count=len(dismissed),
                        dismissal_status="tested" if dismissed else "not_exercised_no_links",
                        dismissed_stays_gone=dismissed_stays_gone if dismissed else None,
                        operations=captures,
                    )
                )
                store.checkpoint()
            write_json(self.directory / "lifecycle.json", checks)
            print(f"lifecycle {len(checks)}/40", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "data/life_diagnostics.json")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--snapshot", type=int, choices=(30, 100, 300))
    parser.add_argument(
        "--phase", choices=("extract", "questions", "lifecycle", "all"), default="all"
    )
    args = parser.parse_args()
    run = Run(args.dataset, args.run_dir)
    if args.cache_dir:
        run.import_cache(args.cache_dir)
    if args.phase in {"extract", "all"}:
        run.extract(checkpoints=args.phase == "all")
    if args.phase in {"questions", "all"}:
        run.questions(counts=[args.snapshot] if args.snapshot else None, reverse=not args.snapshot)
    if args.phase in {"lifecycle", "all"}:
        run.lifecycle()
    from evaluation.life_report import report

    report(args.dataset, args.run_dir)


if __name__ == "__main__":
    main()
