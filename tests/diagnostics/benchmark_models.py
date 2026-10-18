"""Real selection batching, synthetic structured responses; no network."""

import gc
import json
import statistics
import time
import tracemalloc
from pathlib import Path
from tempfile import TemporaryDirectory

from pma.diagnostics import start_trace
from pma.models import LocalModels
from pma.settings import AppSettings


def main():
    gateway = LocalModels(AppSettings())
    gateway.structured = lambda *a, **k: {"ids": a[2]["properties"]["ids"]["items"]["enum"]}
    rows = [{"id": f"synthetic-{i}"} for i in range(24)]
    root = Path(".local/model-benchmark")
    root.mkdir(parents=True, exist_ok=True)
    results = {name: {"samples_ms": []} for name in ("off", "on_memory", "on_jsonl")}
    with TemporaryDirectory(dir=root) as directory:

        def run(name):
            with start_trace(
                enabled=name != "off",
                path=Path(directory) / "trace.jsonl" if name == "on_jsonl" else None,
            ):
                assert gateway.select("synthetic", rows) == [r["id"] for r in rows[:8]]

        for name in results:
            for _ in range(10):
                run(name)
        names = list(results)
        for round_index in range(5):
            for name in names[round_index % 3 :] + names[: round_index % 3]:
                start = time.perf_counter()
                for _ in range(100):
                    run(name)
                results[name]["samples_ms"].append((time.perf_counter() - start) * 10)
        for name, result in results.items():
            gc.collect()
            tracemalloc.start()
            run(name)
            result["peak_python_bytes"] = tracemalloc.get_traced_memory()[1]
            tracemalloc.stop()
            result["median_ms"] = statistics.median(result["samples_ms"])
    report = {
        "workload": "24 synthetic rows, six real selection batches, mock structured; 5 x 100 requests, 10 warmups",
        "results": results,
    }
    text = json.dumps(report, indent=2)
    (root / "result.json").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
