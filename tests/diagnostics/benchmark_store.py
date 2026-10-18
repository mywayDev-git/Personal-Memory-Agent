"""Synthetic SQLite snapshot + relation lookup benchmark, no model server.

Run: python -B -m tests.diagnostics.benchmark_store
"""

import gc
import json
import statistics
import tempfile
import time
import tracemalloc
from dataclasses import replace
from pathlib import Path

import numpy as np

from pma.diagnostics import start_trace
from pma.settings import AppSettings
from pma.store import Store
from tests.conftest import memory


def main():
    root = Path(".local/store-benchmark")
    root.mkdir(parents=True, exist_ok=True)
    results = {}
    with tempfile.TemporaryDirectory(dir=root) as directory:
        store = Store(Path(directory) / "synthetic.db")
        settings = replace(AppSettings(), embedding_dimensions=3)
        for index in range(24):
            text = f"합성 담당자를 정했다 {index}"
            store.create(text, None)
            store.publish(
                store.claim(), [memory(text)], np.array([[1, 0, 0]]), settings.embedding_key, {}
            )
        _, rows = store.snapshot(settings.embedding_key)
        ids = [r["id"] for r in rows]
        with store.connect(True) as db:
            for index in range(1, 24):
                db.execute(
                    "INSERT INTO memory_links VALUES (?,?,?,?,?)",
                    (
                        f"link-{index}",
                        ids[0],
                        ids[index],
                        f"signature-{index}",
                        json.dumps({"kind": "synthetic"}),
                    ),
                )

        def request(enabled, path):
            with start_trace(enabled=enabled, path=path):
                store.snapshot(settings.embedding_key)
                store.links(memory_ids=set(ids))

        for name, enabled, path in (
            ("off", False, None),
            ("on_memory", True, None),
            ("on_jsonl", True, Path(directory) / "synthetic.jsonl"),
        ):
            for _ in range(10):
                request(enabled, path)
            samples = []
            for _ in range(5):
                started = time.perf_counter()
                for _ in range(100):
                    request(enabled, path)
                samples.append((time.perf_counter() - started) * 1000 / 100)
            gc.collect()
            tracemalloc.start()
            request(enabled, path)
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            results[name] = dict(
                median_ms_per_pair=statistics.median(samples),
                sample_ms_per_pair=samples,
                peak_python_bytes=peak,
            )
    report = dict(
        workload="24 synthetic memories, 23 explicit links; one snapshot + one links call",
        timing="10 warmups; 5 x 100 pairs; tracemalloc disabled for timing",
        memory="one pair peak Python allocation, not process RSS",
        results=results,
    )
    (root / "result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
