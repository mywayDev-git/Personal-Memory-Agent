"""Synthetic transaction latency; no model calls or operational database access."""

import argparse
import json
import statistics
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from pma.memory.repository import MemoryRepository
from pma.store import Store


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    target = Path(args.output)
    if target.exists():
        parser.error("choose a fresh output path")
    measurements = []
    with TemporaryDirectory(prefix="capture-benchmark-") as directory:
        repo = MemoryRepository(Store(Path(directory) / "memory.db"))
        for i in range(30):
            start = time.perf_counter()
            candidate = repo.propose("benchmark", content=f"합성 테스트 기록 {i}")
            repo.commit(
                "benchmark",
                candidate["candidate_id"],
                approved=True,
                request_id=str(i),
                resolution="add_confirmed",
            )
            measurements.append((time.perf_counter() - start) * 1000)
        repo.store.checkpoint()
    result = dict(
        samples=30,
        mean_ms=statistics.mean(measurements),
        p95_ms=sorted(measurements)[28],
        model_calls=0,
        search_calls=0,
        scope="candidate + transactional commit; excludes background indexing",
        ram_vram="not measured",
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
