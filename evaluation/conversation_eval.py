"""Isolated NAT real-model evaluation. Seeds are hand-authored; extraction is not measured."""

import argparse
import hashlib
import json
import os
import re
import statistics
import sys
import time
import traceback
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--implementation-root", type=Path)
    parser.add_argument("--cases", nargs="*")
    parser.add_argument("--embedding-revision", required=True)
    parser.add_argument("--embedding-endpoint", default="http://127.0.0.1:8082/v1/embeddings")
    args = parser.parse_args()
    if args.implementation_root:
        sys.path.insert(0, str(args.implementation_root.resolve()))
    from config.settings import Settings
    from evaluation.conversation_cases import cases
    from pma.chat.engine import ChatEngine
    from pma.models import LocalModels
    from pma.service import Service
    from pma.settings import AppSettings
    from pma.store import Store

    args.output.mkdir(parents=True, exist_ok=False)
    settings = AppSettings(
        data_dir=args.output,
        llm=Settings(timeout=180),
        chat_timeout=300,
        embedding_revision=args.embedding_revision,
        embedding_endpoint=args.embedding_endpoint,
    )
    models = LocalModels(settings)
    root = (args.implementation_root or Path.cwd()).resolve()
    source_hashes = {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for folder in ("pma", "scripts", "config")
        for p in (root / folder).rglob("*.py")
    }
    selected = [c for c in cases() if not args.cases or c["id"] in args.cases]
    results = []
    for case in selected:
        folder = args.output / case["id"]
        folder.mkdir()
        store = Store(folder / "memory.db", clock=lambda: "2026-10-20T09:00:00+09:00")
        vectors = models.embed([r["text"] for r in case["records"]]) if case["records"] else []
        keys = {}
        for source, vector in zip(case["records"], vectors, strict=True):
            record = store.create(source["text"], "2026-10-20T09:00:00+09:00")
            job = store.claim()
            text = source["text"]
            stamp = re.search(r"\d{4}-\d{2}-\d{2}", text)
            memory = {
                "local_id": "m1",
                "content": text,
                "subject": {"kind": "self", "value": "나", "value_type": "string"},
                "predicate": "기록했다",
                "object": {"kind": "entity", "value": "개인 기록", "value_type": "string"},
                "target": None,
                "memory_type": "event",
                "polarity": "neutral",
                "content_certainty": "explicit",
                "assertion_polarity": "affirmed",
                "evidence": [{"quote": text}],
                "time": {
                    "raw": stamp[0] if stamp else None,
                    "start": stamp[0] if stamp else None,
                    "end": None,
                    "precision": "day" if stamp else "unknown",
                    "certainty": "explicit" if stamp else "uncertain",
                },
            }
            store.publish(job, [memory], [vector], settings.embedding_key, {})
            keys[record["record_id"]] = source["id"]
        service = Service(store, models, settings)
        engine = ChatEngine(service)
        sid = engine.store.create_empty()["id"]
        started = time.perf_counter()
        cpu = time.process_time()
        row = {"id": case["id"], "message": case["message"], "expected": case, "mode": "auto"}
        try:
            response = engine.message(sid, "evaluation", case["message"], "2026-10-20")
            session = engine.store.get(sid)
            message = session["messages"][-1]
            text = response.get("answer_text") or "\n".join(
                i["text"] for i in response.get("items", [])
            )
            refs = response.get("citation_details", [])
            valid = all(
                any(
                    e["id"] == ref["memory_id"]
                    and e["source_text"][ref["start"] : ref["end"]] == ref["quote"]
                    for e in message["evidence"]
                )
                for ref in refs
            )
            checks = {
                "required_concepts": all(
                    re.search(pattern, text, re.I) for pattern in case["required_concepts"]
                ),
                "forbidden_claims": not any(
                    re.search(claim, text) for claim in case["forbidden_claims"]
                ),
                "exact_citations": valid,
                "memory_refusal": not message["evidence"] if case["id"] == "NAT-T09" else True,
                "no_irrelevant_memory": not refs if not case["expected_search"] else True,
                "answer_present": bool(response.get("items")),
            }
            row.update(
                response=response,
                evidence_ids=[keys.get(e["record_id"]) for e in message["evidence"]],
                checks=checks,
                passed=all(checks.values()),
                failure_code=None if all(checks.values()) else "NAT_EXPECTATION_FAILED",
                performance=message.get("snapshot", {}).get("performance", {}),
            )
        except Exception as exc:
            row.update(passed=False, failure_code=getattr(exc, "code", type(exc).__name__))
            row["diagnostic"] = traceback.format_exc()
            if getattr(exc, "response", None) is not None:
                row["http_error"] = {
                    "status": exc.response.status_code,
                    "body": exc.response.text[:1500],
                }
        row.update(
            elapsed_seconds=time.perf_counter() - started,
            python_cpu_seconds=time.process_time() - cpu,
        )
        if os.name == "nt":
            from evaluation.performance_benchmark import memory_mb

            row["python_working_set_mb"] = memory_mb([os.getpid()])
        results.append(row)
        durations = sorted(r["elapsed_seconds"] for r in results)

        def percentile(p):
            return durations[min(len(durations) - 1, round((len(durations) - 1) * p))]

        report = {
            "synthetic_only": True,
            "implementation_root": str(args.implementation_root or Path.cwd()),
            "source_hashes": source_hashes,
            "settings": {
                "context_tokens": settings.context_tokens,
                "chat_timeout": settings.chat_timeout,
                "generation_endpoint": settings.llm.endpoint,
                "embedding_endpoint": settings.embedding_endpoint,
            },
            "passed": sum(r["passed"] for r in results),
            "measured": len(results),
            "requested": len(selected),
            "latency_including_failures": {
                "p50": statistics.median(durations),
                "p95": percentile(0.95),
                "p99": percentile(0.99),
            },
            "naturalness_evaluation": "사람 검토 필요; 자동 사실 검사와 구분",
            "cases": results,
        }
        (args.output / "results.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(
            f"{case['id']} {'PASS' if row['passed'] else row['failure_code']} {row['elapsed_seconds']:.1f}s",
            flush=True,
        )
        store.checkpoint()


if __name__ == "__main__":
    main()
