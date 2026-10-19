"""Offline comparison against the repository's fixed search regression fixtures.

Run: python -m evaluation.chat_integration_eval --output <json path>
No production database or model endpoint is opened.
"""

import argparse
import importlib.util
import json
import statistics
import time
from pathlib import Path

from pma.chat.automatic import combine
from pma.chat.retrieval import retrieve
from pma.chat.router import RetrievalRouter


def evaluate():
    fixture = Path(__file__).parents[1] / "tests" / "test_search_explain.py"
    spec = importlib.util.spec_from_file_location("fixed_search_fixture", fixture)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    timings = {"existing_search": [], "chat_adapter": []}
    comparisons = []
    for count in (1, 2, 8, 12):
        svc = module.service([module.row(i) for i in range(count)])
        for _ in range(5):
            start = time.perf_counter()
            existing = svc.search("제주 여행", today="2026-10-19")
            timings["existing_search"].append((time.perf_counter() - start) * 1000)
            start = time.perf_counter()
            with svc.model_slot():
                _, found = retrieve(svc, "제주 여행", today="2026-10-19")
            selected = combine([found["results"]])
            timings["chat_adapter"].append((time.perf_counter() - start) * 1000)
        before = [r["id"] for r in existing["results"]]
        after = [r["id"] for r in selected]
        gold = {str(i) for i in range(count)}
        comparisons.append({"records": count, "same_order": before == after,
                            "recall_at_8_existing": len(set(before) & gold) / len(gold),
                            "recall_at_8_chat": len(set(after) & gold) / len(gold),
                            "mrr_existing": 1.0 if before and before[0] in gold else 0.0,
                            "mrr_chat": 1.0 if after and after[0] in gold else 0.0,
                            "missing_evidence": len(gold - set(after)),
                            "irrelevant_evidence": len(set(after) - gold)})
    cases = [
        ("안녕", "CHAT_ONLY", {}), ("파이썬이 뭐야", "CHAT_ONLY", {}),
        ("전에 뭐 했지?", "MEMORY_REQUIRED", {}),
        ("그때 어떻게 했었지?", "MEMORY_REQUIRED", {}),
        ("지난달 기록에서 찾아줘", "MEMORY_REQUIRED", {}),
        ("검색해줘", "MEMORY_REQUIRED", {}),
        ("그걸 왜?", "MEMORY_REQUIRED", {"history": [{"response": {"conversation_mode": "memory"}}]}),
        ("검색해줘", "CHAT_ONLY", {"memory_enabled": False}),
        ("제주", "EXPLICIT_SEARCH", {"explicit_search": True}),
        ("민수는?", "MEMORY_REQUIRED", {"classify": lambda: 1 / 0}),
    ]
    decisions = [RetrievalRouter().decide(q, **options) for q, _, options in cases]
    required = [i for i, (_, expected, _) in enumerate(cases) if expected == "MEMORY_REQUIRED"]
    return {
        "kind": "offline deterministic model doubles; not Qwen quality or production latency",
        "routing_cases": len(cases),
        "routing_accuracy": sum(d.mode == expected for d, (_, expected, _) in zip(decisions, cases)) / len(cases),
        "memory_required_recall": sum(decisions[i].mode == "MEMORY_REQUIRED" for i in required) / len(required),
        "search_comparison": comparisons,
        "latency_ms": {name: {"average": statistics.mean(values),
                              "median": statistics.median(values),
                              "p95": sorted(values)[int(len(values) * .95) - 1]}
                       for name, values in timings.items()},
        "unmeasured": ["real-model citation precision", "grounded claim rate",
                       "unsupported claim rate", "semantic context continuity",
                       "clarification necessity", "real-model latency and call counts"],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(evaluate(), ensure_ascii=False, indent=2), encoding="utf-8")
