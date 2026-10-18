"""Evaluate chat independently of retrieval using synthetic fixed snapshots.

python -m evaluation.chat_eval --output output/chat-evaluation.json
Optional --db imports results into the existing evaluation dashboard.
"""

import argparse
import json
import tempfile
import time
from dataclasses import replace
from pathlib import Path

from pma.chat.engine import ChatEngine
from pma.facts import relation
from pma.models import LocalModels
from pma.service import Service
from pma.settings import AppSettings
from pma.store import Store

from .chat_cases import CASES
from .repository import Repository
from .runner import aggregate
from .schema import Case, Dataset, Result, content_hash


def fixed_session(engine, case):
    rows = []
    for index, text in enumerate(case["sources"]):
        rid = engine.service.store.create(text, "2026-10-18T12:00:00+09:00")["record_id"]
        rows.append(
            {
                "id": f"{case['id']}-{index}",
                "record_id": rid,
                "version": 1,
                "content": text,
                "source_text": text,
                "reference_time": "2026-10-18T12:00:00+09:00",
                "time": {"start": None, "end": None, "certainty": "uncertain"},
                "fact": {
                    "relation": relation(text),
                    "actor": None,
                    "recipient": None,
                    "state": None,
                    "review_reasons": [],
                    "distance_m": [],
                },
                "evidence": [{"quote": text, "start": 0, "end": len(text)}],
            }
        )
    found = engine.store.save_search(
        {"results": rows, "filters": {}, "connections": []},
        {
            "question": case["turns"][0][0],
            "filters": {},
            "connections": [],
            "search_version": "fixed-chat-fixture-v1",
            "model": engine.service.settings.llm.model,
        },
    )
    return engine.store.create(found["search_id"], [r["id"] for r in rows])


def run(engine, cases):
    results = []
    for case in cases:
        session = fixed_session(engine, case)
        for index, (question, expected, reference) in enumerate(case["turns"]):
            started = time.monotonic()
            events = []
            previous_sink = engine.service.diagnostic_sink
            engine.service.diagnostic_sink = events.append
            item = {
                "id": f"{case['id']}.{index}",
                "question": question,
                "expected_behavior": expected,
                "reference": reference,
                "sources": case["sources"],
                "semantic_review": "pending_review",
            }
            try:
                response = engine.message(session["id"], str(index), question, "2026-10-18")
                behavior = {
                    "answered": "answer",
                    "needs_clarification": "clarify",
                    "insufficient_evidence": "abstain",
                }[response["status"]]
                ids = {r["id"] for r in session["evidence"]}
                item.update(
                    response=response,
                    behavior=behavior,
                    behavior_correct=behavior == expected,
                    citation_valid=all(
                        c in ids for part in response["items"] for c in part["citations"]
                    ),
                )
            except Exception as exc:
                item.update(error_type=type(exc).__name__, error_code=getattr(exc, "code", None))
            finally:
                engine.service.diagnostic_sink = previous_sink
            item["validation_trace"] = [e for e in events if e["stage"] == "chat_validation"]
            item["latency_seconds"] = round(time.monotonic() - started, 3)
            results.append(item)
            print(
                json.dumps(
                    {
                        "case": item["id"],
                        "error": item.get("error_type"),
                        "behavior": item.get("behavior"),
                        "latency_seconds": item["latency_seconds"],
                    }
                ),
                flush=True,
            )
    return {
        "version": 1,
        "mode": "fixed_evidence_chat",
        "fixture_hash": content_hash(cases),
        "results": results,
        "metrics": {
            "turns": len(results),
            "errors": sum("error_type" in r for r in results),
            "behavior_correct": sum(r.get("behavior_correct", False) for r in results),
            "citation_valid": sum(r.get("citation_valid", False) for r in results),
            "groundedness": None,
            "followup_understanding": None,
            "semantic_review": "pending_review",
        },
    }


def publish(repo, report):
    dataset = Dataset(
        id="fixed-chat-" + report["fixture_hash"][:12],
        name="고정 근거 다중 턴 대화",
        version="1",
        cases=[
            Case(
                id=r["id"],
                question=r["question"],
                expected_answer=r["reference"],
                expected_behavior=r["expected_behavior"],
                question_type="chat",
                metadata={"conversation_context": True, "sources": r["sources"]},
            )
            for r in report["results"]
        ],
    )
    repo.create_dataset(dataset)
    rid = repo.create_run(
        dataset.id,
        variant="pma",
        config={"mode": "fixed_evidence_chat", "fixture_hash": report["fixture_hash"]},
    )
    repo.update_run_status(rid, "running")
    for row in report["results"]:
        response = row.get("response", {})
        repo.save_case_result(
            rid,
            Result(
                case_id=row["id"],
                actual_answer="\n".join(i["text"] for i in response.get("items", []))
                or response.get("clarification"),
                response_behavior=row.get("behavior"),
                verdict="error"
                if "error_type" in row
                else "fail"
                if not row["behavior_correct"]
                else "pending_review",
                error_type=row.get("error_type"),
                latency_ms=row["latency_seconds"] * 1000,
                evaluation={
                    "behavior_correct": row.get("behavior_correct"),
                    "citation_valid": row.get("citation_valid"),
                    "claims_supported": None,
                    "answer_correct": None,
                    "retrieval_complete": None,
                },
                claims=[
                    {
                        "claim_text": i["text"],
                        "support_status": "uncertain",
                        "evidence": i["citations"],
                    }
                    for i in response.get("items", [])
                ],
            ),
        )
    aggregate(repo, rid)
    repo.update_run_status(rid, "completed")
    return rid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("output/chat-evaluation.json"))
    parser.add_argument("--db", type=Path)
    parser.add_argument("--case", choices=[c["id"] for c in CASES])
    args = parser.parse_args()
    cases = [c for c in CASES if not args.case or c["id"] == args.case]
    with tempfile.TemporaryDirectory(prefix="pma-chat-eval-") as temporary:
        settings = replace(AppSettings.from_env(), data_dir=Path(temporary))
        engine = ChatEngine(
            Service(Store(settings.data_dir / "memory.db"), LocalModels(settings), settings)
        )
        report = run(engine, cases)
    report["model"] = settings.llm.model
    if args.db:
        report["run_id"] = publish(Repository(args.db), report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(args.output.resolve()))


if __name__ == "__main__":
    main()
