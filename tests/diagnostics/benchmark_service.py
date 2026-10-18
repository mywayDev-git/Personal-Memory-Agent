"""Synthetic service benchmark with interleaved modes; no LLM server or DB I/O."""

import gc
import json
import statistics
import tempfile
import time
import tracemalloc
from dataclasses import replace
from pathlib import Path

from pma.service import Service
from pma.settings import AppSettings
from tests.diagnostics.helpers import Models, SnapshotStore, row


def main():
    root = Path(".local/service-benchmark")
    root.mkdir(parents=True, exist_ok=True)
    results = {}
    with tempfile.TemporaryDirectory(dir=root) as directory:
        services = {}
        for name, enabled, path in (
            ("off", False, None),
            ("on_memory", True, None),
            ("on_jsonl", True, Path(directory) / "trace.jsonl"),
        ):
            settings = replace(
                AppSettings(), embedding_dimensions=3, diagnostics=enabled, diagnostics_path=path
            )
            services[name] = Service(SnapshotStore([row(i) for i in range(30)]), Models(), settings)
            results[name] = {"samples_ms": []}

        def request(service):
            service.models.calls.clear()
            service.store.calls.clear()
            return service.answer("synthetic", today="2026-10-17")

        expected = request(services["off"])
        for service in services.values():
            for _ in range(10):
                assert request(service) == expected
        names = list(services)
        for round_index in range(5):
            for name in names[round_index % 3 :] + names[: round_index % 3]:
                started = time.perf_counter()
                for _ in range(100):
                    request(services[name])
                results[name]["samples_ms"].append((time.perf_counter() - started) * 10)
        for name, service in services.items():
            gc.collect()
            tracemalloc.start()
            request(service)
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            results[name]["median_ms_per_request"] = statistics.median(results[name]["samples_ms"])
            results[name]["peak_python_bytes"] = peak
    report = dict(
        workload="30 synthetic memories, fake models and snapshot store",
        timing="5 interleaved rounds x 100 requests per mode; 10 warmups",
        memory="one request peak Python allocation; not RSS",
        results=results,
    )
    (root / "result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
