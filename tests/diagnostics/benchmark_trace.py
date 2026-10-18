"""Standalone collector benchmark; no model, DB, or application latency claims.

Run from repository root:
  python -B -m tests.diagnostics.benchmark_trace
Results and synthetic JSONL are written only under .local/trace-benchmark/.
"""

import gc
import json
import statistics
import tempfile
import time
import tracemalloc
from pathlib import Path

from pma.diagnostics import Stage, record_candidates, record_event, start_trace


def request(enabled, path=None):
    with start_trace(enabled=enabled, path=path) as trace:
        # Instrumentation must guard preparation work while diagnostics are off.
        if trace is not None:
            candidates = [
                dict(
                    memory_ref=trace.memory_ref(f"synthetic-{i}"),
                    rank=i + 1,
                    score=1 / (61 + i),
                    status="included",
                )
                for i in range(24)
            ]
            for stage in (
                Stage.STRUCTURE_FILTER,
                Stage.VECTOR_RETRIEVAL,
                Stage.KEYWORD_RETRIEVAL,
                Stage.RANK_FUSION,
            ):
                record_candidates(stage, candidates, input_count=24, output_count=24)
        record_event(Stage.FINAL_DECISION, status="answer")


def main():
    root = Path(".local/trace-benchmark")
    root.mkdir(parents=True, exist_ok=True)
    results = {}
    with tempfile.TemporaryDirectory(dir=root) as directory:
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
                median_ms_per_request=statistics.median(samples),
                sample_ms_per_request=samples,
                peak_python_bytes=peak,
            )
    result = dict(
        workload="5 events; 4 x 24 candidates per enabled request",
        timing="5 rounds x 100 requests; 10 warmups; tracemalloc disabled for timing",
        memory="one request peak Python allocation; not process RSS",
        results=results,
    )
    (root / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
