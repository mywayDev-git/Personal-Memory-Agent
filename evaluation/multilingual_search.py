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
    args = parser.parse_args()
    replay = json.loads(args.replay.read_text(encoding="utf-8")) if args.replay else None
    replay_cases = {case["id"]: case for case in replay["cases"]} if replay else {}
    revision = hashlib.file_digest(Path("C:/models/bge-m3-Q8_0.gguf").open("rb"), "sha256").hexdigest()
    settings = AppSettings(embedding_revision=revision, llm=Settings(model=args.model, timeout=60, max_tokens=2048))
    models = LocalModels(settings)
    documents, cases = dataset()
    vectors = []
    for start in range(0, len(documents), 16):
        vectors.extend(models.embed([d["text"] for d in documents[start:start+16]]))
    rows = records(documents, vectors)
    store = SimpleNamespace(snapshot=lambda key: (1, rows), assert_generation=lambda generation: None,
                            links=lambda **kw: [])
    report = {"scope": "production top-8 retrieval before optional LLM relevance review",
              "baseline": "same deterministic aliases, model expansion disabled",
              "replayed_model_outputs": bool(replay),
              "model": args.model, "embedding_revision": revision, "documents": len(rows), "cases": []}
    for case_index, case in enumerate(cases[:args.limit]):
        try:
            expected = {doc["id"] for doc in documents if doc["topic"] in case["topics"]}
            entry = dict(case)
            modes = ("baseline", "expanded") if case_index % 2 == 0 else ("expanded", "baseline")
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
                gateway = SimpleNamespace(understand=lambda *args: analysis, embed=models.embed)
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
            print(case["id"], entry["baseline"]["precision_at_8"], entry["expanded"]["precision_at_8"], flush=True)
        except Exception as exc:
            entry = {**case, "error": type(exc).__name__ + ": " + str(exc)[:160]}
            print(case["id"], entry["error"], flush=True)
        report["cases"].append(entry)
        completed = [c for c in report["cases"] if "error" not in c]
        report["summary"] = {"completed": len(completed), "errors": len(report["cases"])-len(completed)}
        for group in ("positive", "negative"):
            subset = [c for c in completed if c["group"] == group]
            report["summary"][group] = {mode: {
                key: statistics.mean(c[mode][key] for c in subset) if subset else None
                for key in ("precision_at_8", "recall_at_8", "search_seconds", "understanding_seconds", "total_seconds")}
                for mode in ("baseline", "expanded")}
        by_id = {case["id"]: case for case in completed}
        report["alias_checks"] = {}
        for topic in ("python", "api", "ml"):
            members = [by_id.get(f"positive-{topic}-{index}") for index in range(4)]
            if all(members):
                report["alias_checks"][topic] = {mode: all(
                    (member[mode]["ids"], member[mode].get("scores")) ==
                    (members[0][mode]["ids"], members[0][mode].get("scores"))
                    for member in members) for mode in ("baseline", "expanded")}
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
