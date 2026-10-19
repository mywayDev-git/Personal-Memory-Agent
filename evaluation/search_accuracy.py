"""Offline mixed-event regression evaluation, not an LLM accuracy benchmark.

Uses production fact projection/search with deterministic model doubles. Use the
separate multilingual_search replay for real multilingual embedding measurements.
"""

import argparse
import json
import math
import statistics
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from pma.facts import project
from pma.search_expressions import build_expansion
from pma.service import Service

BASE = {"intent": "recall", "date_from": None, "date_to": None}


def change(before, after, kind="translation"):
    return dict(start=0, end=len(before), before=before, after=after, kind=kind)


def vector(text):
    topics = (("머신", "기계 학습", "machine learning", "딥러닝", "deep learning"),
              ("달렸", "달린", "달리기"), ("노트북", "notebook"),
              ("회의", "meeting"), ("식물", "plant"), ("불확실",), ("대기",))
    values = [float(any(term in text.casefold() for term in words)) for words in topics]
    return values + [float(not any(values))]


def dataset():
    documents = [
        ("study-ko", "머신러닝을 공부했다.", "study", False),
        ("study-en", "machine learning 자료를 공부했다.", "study", False),
        ("run", "공원에서 실제로 달렸다.", "run", False),
        ("purchase", "notebook 노트북을 구매했다.", "purchase", False),
        ("meeting", "팀 회의를 진행했다.", "meeting", False),
        ("other", "식물 plant 자료를 정리했다.", "other", False),
        ("uncertain", "불확실한 내용을 메모했다.", "unknown", False),
        ("pending", "대기 기록을 정리했다.", "pending", True),
    ]
    rows = []
    for mid, text, semantic_event, pending in documents:
        memory = {"content": text, "predicate": "기록했다", "subject": {"kind": "self"},
                  "object": {"value": semantic_event}, "target": "", "memory_type": "event",
                  "assertion_polarity": "uncertain" if semantic_event == "unknown" else "affirmed",
                  "evidence": [{"quote": text}], "time": {"raw": None, "start": None,
                  "end": None, "precision": "unknown", "certainty": "uncertain"}}
        evidence = [{"start": 0, "end": len(text), "quote": text}]
        rows.append({"id": mid, "record_id": mid, "version": 1, "memory": memory,
                     "text": text, "source_text": text, "content": text,
                     "fact": None if pending else project(memory, text, None, "2026-10-19", evidence),
                     "vector": np.array(vector(text), dtype="<f4").tobytes(),
                     "evidence": evidence, "created_at": "2026-10-19", "reference_time": None})
    cases = [("머신러닝이란 공부 기록", {"study-ko", "study-en"}),
             ("머신러닝과는 관련된 공부", {"study-ko", "study-en"}),
             ("machine learning 자료", {"study-ko", "study-en"}),
             ("달린 기록", {"run"}), ("노트북 구매", {"purchase"}),
             ("팀 회의 내용", {"meeting"}), ("식물 자료", {"other"}),
             ("불확실한 내용", {"uncertain"}), ("대기 기록", set()),
             ("천문 관측", set())]
    return rows, cases


def evaluate():
    rows, cases = dataset()
    store = SimpleNamespace(snapshot=lambda key: (1, rows), assert_generation=lambda g: None,
                            links=lambda **kwargs: [])
    entries = []
    for question, gold in cases:
        calls = {"understanding": 0, "embedding": 0, "verification": 0}
        def understand(q, today, *, expand=True):
            calls["understanding"] += 1
            return dict(BASE)
        def embed(queries):
            calls["embedding"] += 1
            return [vector(q) for q in queries]
        def select(q, records):
            # Deliberately transparent relevance double, not an oracle using gold IDs.
            qv = np.array(vector(q))
            return [r["id"] for r in records if qv @ np.array(vector(r["source_text"])) > 0]
        svc = Service(store, SimpleNamespace(understand=understand, embed=embed, select=select),
                      SimpleNamespace(embedding_key="offline", embedding_dimensions=8))
        started = time.perf_counter()
        found = svc._search(question, today="2026-10-19")[1]
        seconds = time.perf_counter() - started
        ids = [r["id"] for r in found["results"]]
        hits = set(ids) & gold
        excluded = {r["id"] for r in found["search_audit"]["candidates"]
                    if r.get("reason") == "relation_mismatch"}
        entries.append({"question": question, "gold": sorted(gold), "ids": ids,
                        "recall_at_8": len(hits) / len(gold) if gold else None,
                        "precision_returned": len(hits) / len(ids) if ids else None,
                        "mrr": next((1 / rank for rank, mid in enumerate(ids, 1) if mid in gold), 0),
                        "exact_set": set(ids) == gold, "wrong_filter": bool(gold & excluded),
                        "seconds": seconds, "calls": calls})
    proposals = [("学習", "learning", "translation", False),
                 ("학습", "notebook", "translation", False),
                 ("학습", " ", "similar", False), ("학습", "...", "similar", False),
                 ("민수", "Minsu", "translation", False), ("서울", "Seoul", "translation", False),
                 ("식물", "plant", "translation", True), ("planet", "행성", "translation", True),
                 ("쿠버네티스", "Kubernetes", "transliteration", True),
                 ("영수증", "receipt", "translation", True), ("학습", "공부", "similar", True)]
    validation = []
    for before, after, kind, valid in proposals:
        result = build_expansion(before, [change(before, after, kind)], [], BASE)
        validation.append({"before": before, "after": after, "expected_valid": valid,
                           "approved": bool(result["queries"]), "reason": result["rejected"]})
    latencies = sorted(e["seconds"] for e in entries)
    return {"scope": "offline production projection/search with deterministic model doubles",
            "personal_database_used": False, "reverse_translation_calls": 0,
            "records": [{"id": r["id"], "relation": (r["fact"] or {}).get("relation")}
                        for r in rows], "cases": entries, "expansion_checks": validation,
            "summary": {"cases": len(entries), "exact_sets": sum(e["exact_set"] for e in entries),
                        "mean_recall_at_8": statistics.mean(e["recall_at_8"] for e in entries if e["recall_at_8"] is not None),
                        "wrong_filter_questions": sum(e["wrong_filter"] for e in entries),
                        "wrong_expansion_approvals": sum(v["approved"] and not v["expected_valid"] for v in validation),
                        "valid_expansion_rejections": sum(not v["approved"] and v["expected_valid"] for v in validation),
                        "mean_seconds": statistics.mean(latencies),
                        "p95_seconds": latencies[math.ceil(.95 * len(latencies)) - 1]}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = evaluate()
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0 if all(e["exact_set"] for e in report["cases"]) and not any(
        v["approved"] != v["expected_valid"] for v in report["expansion_checks"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
