"""Local TestClient benchmark; empty SQLite results, no model server."""

import json
import statistics
import tempfile
import time
import tracemalloc
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

from pma.settings import AppSettings
from pma.web import create_app
from tests.conftest import FakeModels


def main():
    root = Path(".local/http-benchmark")
    root.mkdir(parents=True, exist_ok=True)
    results = {}
    for name, enabled, write in (
        ("off", False, False),
        ("on_memory", True, False),
        ("on_jsonl", True, True),
    ):
        with tempfile.TemporaryDirectory(dir=root) as directory:
            settings = replace(
                AppSettings(),
                data_dir=Path(directory),
                embedding_dimensions=3,
                diagnostics=enabled,
                diagnostics_path=Path(directory) / "trace.jsonl" if write else None,
            )
            app = create_app(settings, FakeModels(), run_worker=False)
            with TestClient(app, base_url=settings.origin) as client:
                client.headers["Origin"] = settings.origin
                session = client.post("/api/v1/session", json={"token": app.state.bootstrap_token})
                client.headers["X-CSRF-Token"] = session.json()["csrf"]

                def request():
                    response = client.post(
                        "/api/v1/answers", json={"question": "synthetic", "today": "2026-10-18"}
                    )
                    assert response.status_code == 200 and response.json()["items"] == []

                for _ in range(5):
                    request()
                timings = []
                for _ in range(30):
                    start = time.perf_counter()
                    request()
                    timings.append((time.perf_counter() - start) * 1000)
                tracemalloc.start()
                request()
                peak = tracemalloc.get_traced_memory()[1]
                tracemalloc.stop()
                results[name] = {"median_ms": statistics.median(timings), "peak_python_bytes": peak}
    report = {
        "workload": "TestClient, empty SQLite, fake models, 5 warmups + 30 requests per mode; sequential modes, indicative only",
        "results": results,
    }
    (root / "result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
