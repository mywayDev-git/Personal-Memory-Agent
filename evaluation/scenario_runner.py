"""Deterministic projection/search probes, explicitly separate from real-model evaluation.

Fixtures inject extraction and fixed embeddings, never expected answers. Unimplemented
semantic/lifecycle adapters remain UNASSESSED, not successful cases.
"""

import argparse
import json
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path

import numpy as np

from evaluation.scenario_contract import load, validate
from evaluation.scenario_diagnostics import diagnose
from pma.service import Service
from pma.settings import AppSettings
from pma.store import Store

# Reuse the repository's existing injected model and memory contract.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from conftest import FakeModels, memory  # noqa: E402

PROBES = {
    "T01": ("민수", "책", "event", "observed"),
    "T02": ("self", "책", "event", "observed"),
    # A coarse extractor can validly emit event for an intention. Source must constrain it.
    "T03": ("민수", "책", "event", "planned"),
    "T04": ("민수", "책", "event", "negated"),
    "T05": ("민수", "책", "event", "review_required"),
}


def execute(case, store, settings, models):
    actor, obj, typ, expected_state = PROBES[case["case_id"]]
    records = []
    for r in case["records"]:
        rid = store.create(r["text"], r["reference_time"])["record_id"]
        records.append(rid)
        m = memory(r["text"])
        m.update(
            memory_type=typ,
            predicate=r["text"],
            subject=dict(
                kind="self" if actor == "self" else "entity",
                value="사용자" if actor == "self" else actor,
                value_type="string",
            ),
            object=dict(kind="literal", value=obj, value_type="string"),
        )
        store.publish(
            store.claim(),
            [m],
            np.asarray([[1, 0, 0]], dtype=np.float32),
            settings.embedding_key,
            {},
        )
    traces = []
    service = Service(store, models, settings, diagnostic_sink=traces.append)
    started = time.perf_counter()
    found = service.search(case["question"], today="2026-10-10")
    answer = service.answer(case["question"], today="2026-10-10")
    rows = store.snapshot(settings.embedding_key)[1]
    actual = rows[0]["fact"]["state"]
    return dict(
        case_id=case["case_id"],
        variable_ids=case["variable_ids"],
        mode="deterministic",
        scope="projection_probe",
        record_ids=records,
        expected_projection_state=expected_state,
        actual_projection_state=actual,
        projection_mismatch=actual != expected_state,
        expected_status=case["expected_status"],
        actual_status=answer["status"],
        actual_claims=[i["text"] for i in answer["items"]],
        expected_facts=case["expected_facts"],
        retrieved_evidence_ids=[r["id"] for r in found["results"]],
        expected_evidence_ids=[
            r["id"]
            for r in rows
            if any(
                s["record"] == records.index(r["record_id"]) for s in case["gold_evidence_spans"]
            )
        ],
        trace=traces,
        semantic_answer_scored=False,
        latency_seconds=time.perf_counter() - started,
    )


def run(output):
    variables, cases = load()
    errors = validate(variables, cases)
    if errors:
        raise ValueError(errors)
    output.parent.mkdir(parents=True, exist_ok=True)
    results = []
    for case in cases:
        if case["case_id"] not in PROBES:
            results.append(
                dict(
                    case_id=case["case_id"],
                    variable_ids=case["variable_ids"],
                    status="UNASSESSED",
                    reason="No validated execution adapter yet",
                )
            )
            continue
        with tempfile.TemporaryDirectory(dir=output.parent) as tmp:
            settings = replace(
                AppSettings(),
                data_dir=Path(tmp),
                embedding_dimensions=3,
                embedding_revision="a" * 64,
            )
            try:
                result = execute(case, Store(Path(tmp) / "memory.db"), settings, FakeModels())
                result.update(diagnose(result))
                result["status"] = "RED" if result["primary_failure_stage"] else "PASS_EXISTING"
            except Exception as exc:
                result = dict(
                    case_id=case["case_id"],
                    variable_ids=case["variable_ids"],
                    status="BLOCKED",
                    exception=type(exc).__name__,
                    detail=str(exc),
                )
                result.update(diagnose(result))
            results.append(result)
    output.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in results), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                s: sum(r["status"] == s for r in results)
                for s in ["PASS_EXISTING", "RED", "BLOCKED", "UNASSESSED"]
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output)
