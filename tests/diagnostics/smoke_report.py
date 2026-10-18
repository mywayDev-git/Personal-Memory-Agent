"""Exercise the real store/service/evaluator with existing synthetic data and fake models.

This is a wiring check, NOT extraction quality, semantic accuracy, or live E2E.
"""

import json
import tempfile
from dataclasses import replace
from pathlib import Path

import numpy as np

from evaluation.diagnose_search import (
    analyze,
    capture_binding,
    load_cases,
    read_events,
    write_report,
)
from pma.diagnostics import start_trace
from pma.service import Service
from pma.settings import AppSettings
from pma.store import Store
from tests.conftest import memory
from tests.diagnostics.helpers import Models


def main():
    root = Path(".local/diagnostics-prompt10")
    root.mkdir(parents=True, exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix="synthetic-", dir=root))
    dataset = json.loads(Path("data/search_diagnostics.json").read_text("utf-8"))
    assert dataset["synthetic"] is True
    with tempfile.TemporaryDirectory(dir=root) as directory:
        settings = replace(
            AppSettings(),
            data_dir=Path(directory),
            embedding_dimensions=3,
            embedding_revision="a" * 64,
        )
        store = Store(settings.data_dir / "memory.db")
        aliases = {}
        for source in dataset["records"]:
            created = store.create(source["text"], source["reference_time"])
            aliases[source["id"]] = created["record_id"]
            job = store.claim()
            assert store.publish(
                job,
                [memory(source["text"])],
                np.array([[1, 0, 0]], dtype=np.float32),
                settings.embedding_key,
                {},
            )
        service = Service(store, Models(), settings)
        bindings = {}
        for case in dataset["questions"]:
            expected = service.answer(case["question"], today=dataset["today"])
            with start_trace(enabled=True, path=output / "trace.jsonl") as trace:
                assert service.answer(case["question"], today=dataset["today"]) == expected
            bindings.update(capture_binding(trace, case["id"], records=aliases))
        store.checkpoint()
    (output / "bindings.json").write_text(json.dumps(bindings, indent=2), encoding="utf-8")
    summary, cases = analyze(read_events(output / "trace.jsonl"), load_cases(dataset), bindings)
    summary["mode"] = "synthetic_mock_models"
    summary["limitations"].insert(
        0,
        "Synthetic wiring check: whole-record mock extraction, constant embeddings, fake selection/generation/verification. Do not infer product accuracy or production priorities.",
    )
    write_report(output, summary, cases)
    # Demonstrate honest null metrics when a historical trace has no ID sidecar.
    unavailable, unknown_cases = analyze(read_events(output / "trace.jsonl"), load_cases(dataset))
    write_report(output / "without-bindings", unavailable, unknown_cases)
    print(
        json.dumps(
            {
                "output": str(output.resolve()),
                "total": summary["total_questions"],
                "evaluable": summary["evaluable_questions"],
                "priorities": summary["priorities"],
            }
        )
    )


if __name__ == "__main__":
    main()
