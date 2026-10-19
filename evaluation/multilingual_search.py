"""Reproducible top-8 retrieval benchmark using actual local understanding/embeddings.

Runs the production retrieval/fusion/selection-limit path, before the optional LLM
relevance review. Baseline retains deterministic aliases but disables model expansion.
Only the synthetic dataset is used. Results are checkpointed after every case.
"""

import argparse
import hashlib
import json
import statistics
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from config.settings import Settings
from evaluation.multilingual_cases import dataset
from pma.models import LocalModels
from pma.service import Service
from pma.settings import AppSettings


def records(documents, vectors):
    result = []
    for doc, vector in zip(documents, vectors, strict=True):
        text = doc["text"]
        event = {"start": doc.get("date", "2026-05-12"), "end": None, "certainty": "certain"}
        result.append({"id": doc["id"], "record_id": doc["id"], "version": 1,
            "text": text, "content": text, "source_text": text,
            "memory": {"content": text, "subject": "나", "predicate": "정리", "object": doc["topic"],
                       "target": "", "memory_type": "event", "assertion_polarity": "positive"},
            "fact": {"relation": "other", "actor": doc.get("actor", "self"), "recipient": "",
                     "object_key": doc["topic"], "state": doc.get("state", "observed"), "event_time": event},
            "vector": np.asarray(vector, dtype="<f4").tobytes(),
            "evidence": [{"start": 0, "end": len(text), "quote": text}],
            "reference_time": None, "created_at": "2026-05-12"})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("evaluation/multilingual_results.json"))
    parser.add_argument("--limit", type=int, default=90)
    parser.add_argument("--model", default="qwen3")
    parser.add_argument("--replay", type=Path, help="Reuse saved actual model analyses; rerun production retrieval")
    parser.add_argument("--generation-endpoint", default="http://127.0.0.1:8081/v1/chat/completions")
    parser.add_argument("--embedding-endpoint", default="http://127.0.0.1:8082/v1/embeddings")
    parser.add_argument("--embedding-file", type=Path, default=Path("C:/models/bge-m3-Q8_0.gguf"))
    parser.add_argument("--embedding-model", default="bge-m3")
    parser.add_argument("--embedding-profile", choices=["raw-v1", "qwen3-retrieval-v1"], default="raw-v1")
    parser.add_argument("--current-only", action="store_true", help="Compare models on the current expanded search path; no separate expansion-off experiment")
    args = parser.parse_args()
    with args.embedding_file.open("rb") as stream:
        revision = hashlib.file_digest(stream, "sha256").hexdigest()
    settings = AppSettings(embedding_revision=revision, embedding_model=args.embedding_model,
                           embedding_endpoint=args.embedding_endpoint, embedding_profile=args.embedding_profile,
                           llm=Settings(model=args.model, endpoint=args.generation_endpoint, timeout=60, max_tokens=2048))
    evaluate(settings, args.output, limit=args.limit, replay=args.replay, current_only=args.current_only)


def evaluate(settings, output, *, limit=90, replay=None, current_only=False):
    args = SimpleNamespace(output=output, limit=limit, replay=replay, model=settings.llm.model)
    replay = json.loads(args.replay.read_text(encoding="utf-8")) if args.replay else None
    replay_cases = {case["id"]: case for case in replay["cases"]} if replay else {}
    revision = settings.embedding_revision
    models = LocalModels(settings)
    documents, cases = dataset()
    vectors = []
    for start in range(0, len(documents), 16):
        vectors.extend(models.embed([d["text"] for d in documents[start:start+16]]))
    rows = records(documents, vectors)
    store = SimpleNamespace(snapshot=lambda key: (1, rows), assert_generation=lambda generation: None,
                            links=lambda **kw: [])
    report = {"scope": "production top-8 retrieval before optional LLM relevance review",
              "baseline": "not run; current search path only" if current_only else "same deterministic aliases, model expansion disabled",
              "replayed_model_outputs": bool(replay),
              "embedding_key": settings.embedding_key,
              "model": args.model, "embedding_revision": revision, "documents": len(rows), "cases": []}
    report["evaluated_modes"] = ["expanded"] if current_only else ["baseline", "expanded"]
    for case_index, case in enumerate(cases[:args.limit]):
        try:
            expected = {doc["id"] for doc in documents if doc["topic"] in case["topics"]}
            entry = dict(case)
            modes = ("expanded",) if current_only else ("baseline", "expanded") if case_index % 2 == 0 else ("expanded", "baseline")
            for mode in modes:
                started = time.perf_counter()
                understanding_error = None
                if replay:
                    source = replay_cases[case["id"]][mode]
                    analysis = dict(source["understood"])
                    understanding_error = source["understanding_error"]
                    understanding_seconds = source["understanding_seconds"]
                else:
                    try:
                        analysis = models.understand(case["question"], "2026-10-19", expand=mode == "expanded")
                    except (ValueError, RuntimeError) as exc:
                        understanding_error = type(exc).__name__
                        analysis = {"intent": "recall", "date_from": None, "date_to": None}
                    understanding_seconds = time.perf_counter() - started
                if mode == "baseline":
                    analysis["expansions"] = []
                gateway = SimpleNamespace(understand=lambda *args: analysis, embed=models.embed,
                                          embed_queries=models.embed_queries)
                service = Service(store, gateway, settings)
                started = time.perf_counter()
                _, result = service._search(case["question"], today="2026-10-19")
                search_seconds = time.perf_counter() - started
                ids = [row["id"] for row in result["results"]]
                hits = len(set(ids) & expected)
                entry[mode] = {"ids": ids, "scores": [row["score"] for row in result["results"]],
                               "precision_at_8": hits / 8,
                               "recall_at_8": hits / len(expected),
                               "search_seconds": search_seconds,
                               "understanding_seconds": understanding_seconds,
                               "total_seconds": understanding_seconds + search_seconds,
                               "understanding_error": understanding_error,
                               "understood": analysis,
                               "query_expansion": result.get("query_expansion")}
            print(case["id"], {mode: entry[mode]["precision_at_8"] for mode in report["evaluated_modes"]}, flush=True)
        except Exception as exc:
            entry = {**case, "error": type(exc).__name__ + ": " + str(exc)[:160]}
            print(case["id"], entry["error"], flush=True)
        report["cases"].append(entry)
        completed = [c for c in report["cases"] if "error" not in c]
        report["summary"] = {"completed": len(completed), "errors": len(report["cases"])-len(completed)}
        report["summary"]["understanding_errors"] = sum(
            bool(case[mode].get("understanding_error"))
            for case in completed for mode in report["evaluated_modes"])
        for group in ("positive", "negative"):
            subset = [c for c in completed if c["group"] == group]
            report["summary"][group] = {mode: {
                key: statistics.mean(c[mode][key] for c in subset) if subset else None
                for key in ("precision_at_8", "recall_at_8", "search_seconds", "understanding_seconds", "total_seconds")}
                for mode in report["evaluated_modes"]}
        by_id = {case["id"]: case for case in completed}
        report["alias_checks"] = {}
        for topic in ("python", "api", "ml"):
            members = [by_id.get(f"positive-{topic}-{index}") for index in range(4)]
            if all(members):
                report["alias_checks"][topic] = {mode: all(
                    (member[mode]["ids"], member[mode].get("scores")) ==
                    (members[0][mode]["ids"], members[0][mode].get("scores"))
                    for member in members) for mode in report["evaluated_modes"]}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(".partial")
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(args.output)
    return report


if __name__ == "__main__":
    main()
