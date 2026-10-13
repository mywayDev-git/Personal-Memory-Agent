"""Opt-in real model/API smoke test using only synthetic data in a temporary DB."""

import json
import tempfile
import time
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

from pma.settings import AppSettings
from pma.web import create_app


def main():
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="pma-live-") as directory:
        settings = replace(AppSettings.from_env(), data_dir=Path(directory))
        app = create_app(settings, run_worker=False)
        with TestClient(app, base_url=settings.origin) as client:
            client.headers["Origin"] = settings.origin
            session = client.post("/api/v1/session", json={"token": app.state.bootstrap_token})
            assert session.status_code == 200
            client.headers["X-CSRF-Token"] = session.json()["csrf"]
            health = client.get("/api/v1/health").json()["models"]
            assert set(health.values()) == {"ready"}, health
            created = client.post(
                "/api/v1/records",
                json={
                    "text": "오늘 캡스톤 회의에서 나는 백엔드 개발을 담당하기로 결정했다.",
                    "reference_time": "2026-10-13T12:00:00+09:00",
                },
            )
            assert created.status_code == 202
            rid = created.json()["record_id"]
            app.state.service.run_one()
            record = client.get("/api/v1/records/" + rid).json()
            assert record["status"] == "ready", record["status"]
            response = client.post(
                "/api/v1/answers", json={"question": "캡스톤에서 내가 맡기로 한 역할은?"}
            )
            assert response.status_code == 200, response.status_code
            answer = response.json()
            assert answer["status"] == "answered", answer["status"]
            assert any("백엔드" in item["text"] for item in answer["items"])
            assert all(item["citations"] for item in answer["items"])
            assert client.delete("/api/v1/records/" + rid).status_code == 204
            absent = client.post("/api/v1/answers", json={"question": "내 역할은?"})
            assert absent.json()["status"] == "insufficient_evidence", absent.json()["status"]
            print(
                json.dumps(
                    {
                        "status": "passed",
                        "memories": len(record["memories"]),
                        "elapsed_seconds": round(time.monotonic() - started, 2),
                        "checks": ["extraction", "embedding", "grounded_answer", "trash_exclusion"],
                    }
                )
            )


if __name__ == "__main__":
    main()
