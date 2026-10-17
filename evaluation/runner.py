"""CLI: validate, variants, run, import, reaggregate, inspect, cancel.

Runs use a consistent SQLite backup of an existing memory DB, never mutate its source.
Only explicit exact-match cases are automatically graded; other answers await review.
"""

import argparse
import hashlib
import json
import platform
import sqlite3
import subprocess
import tempfile
import time
from dataclasses import asdict
from pathlib import Path

from .adapters import adapt, load_dataset
from .diagnostics import diagnose
from .metrics import dashboard_metrics
from .repository import Repository
from .schema import Result
from .trace import TraceCollector


def aggregate(repo, run_id):
    run = repo.get_run(run_id)
    repo.replace_run_metrics(
        run_id, dashboard_metrics(repo.cases(run["dataset_id"]), repo.results(run_id))
    )


def execute(repo, dataset, service, config, commit_sha=None, trace_budget=8388608):
    repo.create_dataset(dataset)
    rid = repo.create_run(
        dataset.id,
        config=config,
        commit_sha=commit_sha,
        environment={"python": platform.python_version()},
    )
    print(json.dumps({"run_id": rid, "status": "running"}), flush=True)
    repo.update_run_status(rid, "running")
    previous_sink = service.diagnostic_sink
    try:
        for case in dataset.cases:
            if repo.get_run(rid)["status"] == "cancelled":
                break
            collector = TraceCollector(max_bytes=min(262144, trace_budget))
            repo.update_progress(rid, case.id, "query_understanding_start")

            def observe(event):
                collector(event)
                if event["stage"] in {
                    "query_understanding_start",
                    "question",
                    "retrieval_merge",
                    "selection",
                    "evidence",
                    "generation_start",
                    "answer",
                    "verification",
                    "result",
                }:
                    try:
                        repo.update_progress(rid, case.id, event["stage"])
                    except sqlite3.Error:
                        pass  # Diagnostics must not fail normal answer generation.

            service.diagnostic_sink = observe
            started = time.perf_counter()
            try:
                if case.metadata.get("conversation_context") or case.metadata.get(
                    "legacy_import_only"
                ):
                    # Current Service API has no conversation-context argument.
                    result = Result(
                        case_id=case.id,
                        verdict="not_applicable",
                        evaluation={"reason": "This case requires its original execution adapter"},
                    )
                else:
                    response = service.answer(
                        case.question, today=case.metadata.get("reference_time", "")[:10] or None
                    )
                    text = "\n".join(i["text"] for i in response.get("items", []))
                    behavior = (
                        "clarify"
                        if response.get("clarification")
                        else "answer"
                        if response.get("status") == "answered"
                        else "abstain"
                    )
                    merged = next(
                        (
                            e["candidates"]
                            for e in collector.events
                            if e["stage"] == "retrieval_merge"
                        ),
                        None,
                    )
                    selected = next(
                        (e["ids"] for e in collector.events if e["stage"] == "evidence"), None
                    )
                    correct = None
                    if (
                        case.metadata.get("grading_method") == "exact_match"
                        and case.expected_answer is not None
                    ):
                        correct = text.strip() == case.expected_answer.strip()
                    complete = (
                        all(set(selected).intersection(g) for g in case.gold_groups.values())
                        if selected is not None and case.gold_groups
                        else None
                    )
                    evaluation = dict(
                        answer_correct=correct,
                        final_evidence_complete=complete,
                        behavior_correct=behavior == case.expected_behavior,
                        retrieved_ids=[c["id"] for c in merged] if merged is not None else [],
                        retrieval_complete=merged is not None and not collector.truncated,
                        trace_status="truncated" if collector.truncated else "partial",
                        grading_method=case.metadata.get("grading_method", "pending_review"),
                        grading_version=config.get("grading_version", "dashboard-v1"),
                        claims_supported=None,
                    )
                    diagnosis = diagnose(case, collector.events, evaluation, behavior)
                    evaluation["diagnosis"] = diagnosis
                    checks = [evaluation["behavior_correct"]]
                    if case.expected_behavior == "answer":
                        checks.extend([correct, complete, evaluation["claims_supported"]])
                    verdict = (
                        "fail"
                        if False in checks
                        else "pending_review"
                        if None in checks
                        else "pass"
                    )
                    result = Result(
                        case_id=case.id,
                        actual_answer=text,
                        response_behavior=behavior,
                        verdict=verdict,
                        evaluation=evaluation,
                        claims=[
                            dict(
                                claim_text=i["text"],
                                support_status="uncertain",
                                evidence=i.get("citations", []),
                            )
                            for i in response.get("items", [])
                        ],
                        error_type=diagnosis["error_type"] if verdict == "fail" else None,
                    )
            except Exception as exc:
                result = Result(
                    case_id=case.id,
                    verdict="error",
                    error_type="unknown",
                    evaluation={"exception_type": type(exc).__name__},
                )
            result.latency_ms = (time.perf_counter() - started) * 1000
            repo.save_case_result(rid, result, collector.events)
            repo.update_progress(rid, case.id, "case_completed")
            trace_budget -= collector.bytes_used
            aggregate(repo, rid)
            print(
                json.dumps({"run_id": rid, "case_id": case.id, "verdict": result.verdict}),
                flush=True,
            )
        if repo.get_run(rid)["status"] != "cancelled":
            aggregate(repo, rid)
            repo.update_run_status(rid, "completed")
    except KeyboardInterrupt:
        repo.update_run_status(rid, "cancelled")
        raise
    except Exception as exc:
        repo.update_run_status(rid, "failed", type(exc).__name__)
        raise
    finally:
        service.diagnostic_sink = previous_sink
    return rid


def main():
    from pma.settings import AppSettings

    settings = AppSettings.from_env()
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument(
        "--db", type=Path, default=settings.data_dir / "evaluation" / "evaluation.db"
    )
    subs = parser.add_subparsers(dest="command", required=True)
    subs.add_parser("variants")
    for name in ("validate", "run", "import"):
        sub = subs.add_parser(name)
        sub.add_argument("dataset", type=Path)
        if name == "run":
            sub.add_argument("--memory-db", type=Path, required=True)
            sub.add_argument("--variant", choices=["pma"], default="pma")
        if name == "import":
            sub.add_argument("results", type=Path)
    for name in ("inspect", "reaggregate", "cancel"):
        subs.add_parser(name).add_argument("run_id")
    args = parser.parse_args()
    if args.command == "variants":
        print(
            json.dumps(
                {
                    "pma": "available",
                    "baseline": "unsupported",
                    "pma_a": "unsupported",
                    "pma_b": "unsupported",
                    "pma_c": "unsupported",
                }
            )
        )
        return
    if args.command in {"validate", "run", "import"}:
        dataset = load_dataset(args.dataset)
        if args.command == "validate":
            print(f"Valid: {len(dataset.cases)} cases")
            return
    repo = Repository(args.db)
    if args.command == "inspect":
        print(json.dumps(repo.get_run_summary(args.run_id), ensure_ascii=False, indent=2))
    elif args.command == "reaggregate":
        aggregate(repo, args.run_id)
    elif args.command == "cancel":
        if repo.get_run(args.run_id)["status"] not in {"pending", "running"}:
            raise ValueError("Only pending/running runs may be cancelled")
        repo.update_run_status(args.run_id, "cancelled")
    elif args.command == "import":
        rows = [
            adapt(json.loads(line))
            for line in args.results.read_text("utf-8").splitlines()
            if line.strip()
        ]
        ids = [r.case_id for r in rows]
        if len(set(ids)) != len(ids) or not set(ids) <= {c.id for c in dataset.cases}:
            raise ValueError("Duplicate or unknown case IDs")
        repo.create_dataset(dataset)
        rid = repo.create_run(dataset.id, config={"grading_version": "legacy-import"})
        repo.update_run_status(rid, "running")
        try:
            for row in rows:
                repo.save_case_result(rid, row)
            aggregate(repo, rid)
            repo.update_run_status(
                rid,
                "completed" if len(rows) == len(dataset.cases) else "failed",
                None if len(rows) == len(dataset.cases) else "Incomplete import",
            )
        except Exception as exc:
            repo.update_run_status(rid, "failed", type(exc).__name__)
            raise
        print(rid)
    elif args.command == "run":
        from pma.models import LocalModels
        from pma.service import Service
        from pma.store import Store

        with tempfile.TemporaryDirectory() as temp:
            snapshot = Path(temp) / "memory.db"
            source = sqlite3.connect(args.memory_db.resolve().as_uri() + "?mode=ro", uri=True)
            target = sqlite3.connect(snapshot)
            try:
                source.backup(target)
            finally:
                source.close()
                target.close()
            digest = hashlib.sha256(snapshot.read_bytes()).hexdigest()
            config = dict(
                snapshot=digest,
                model=asdict(settings.llm),
                embedding=settings.embedding_key,
                grading_version="dashboard-v1",
                retrieval={
                    "answer_validation": settings.answer_validation,
                    "context_tokens": settings.context_tokens,
                },
            )
            commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True)
            config["working_tree_dirty"] = bool(
                subprocess.run(
                    ["git", "status", "--porcelain"], capture_output=True, text=True
                ).stdout.strip()
            )
            service = Service(Store(snapshot), LocalModels(settings), settings)
            execute(repo, dataset, service, config, commit.stdout.strip() or None)


if __name__ == "__main__":
    main()
