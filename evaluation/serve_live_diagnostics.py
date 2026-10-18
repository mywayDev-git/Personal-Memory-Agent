"""Open the completed synthetic evaluation in an isolated interactive app."""

import json
import sqlite3
import threading
import time
from dataclasses import replace
from pathlib import Path

import uvicorn

from pma.settings import AppSettings
from pma.web import create_app

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / ".local/live-20261018-003129/results"
PLAYGROUND = ROOT / ".local/search-live-playground"


class CompletedDataset:
    def __init__(self):
        self.data = json.loads((ROOT / "data/search_diagnostics.json").read_text("utf-8"))
        self.results = json.loads((RESULTS / "live_results.json").read_text("utf-8"))
        if self.data.get("synthetic") is not True:
            raise ValueError("Only synthetic data is supported")
        self.mapping = {r["id"]: r["record_id"] for r in self.results["records"]}

    def prepare(self, store, settings):
        if settings.data_dir.resolve() != PLAYGROUND.resolve():
            raise ValueError("Isolated playground directory required")

    def view(self, store):
        records = []
        for source in self.data["records"]:
            record = store.get(self.mapping[source["id"]])
            records.append(
                dict(
                    source,
                    record_id=record["id"] if "id" in record else self.mapping[source["id"]],
                    status=record["status"],
                    recorded_at=record.get("created_at", source.get("reference_time")),
                    category="진단 평가",
                    split="합성 데이터",
                )
            )
        questions = [
            dict(q, category="진단 평가", split="합성 데이터") for q in self.data["questions"]
        ]
        return dict(enabled=True, today=self.data["today"], records=records, questions=questions)


def main():
    dataset = CompletedDataset()
    PLAYGROUND.mkdir(parents=True, exist_ok=True)
    destination = PLAYGROUND / "memory.db"
    if not destination.exists():
        with sqlite3.connect(f"{(RESULTS / 'evaluation.db').as_uri()}?mode=ro", uri=True) as source:
            with sqlite3.connect(destination) as target:
                source.backup(target)
    settings = replace(
        AppSettings.from_env(),
        data_dir=PLAYGROUND,
        port=8767,
        embedding_revision=dataset.results["embedding_revision"],
    )
    app = create_app(settings, test_dataset=dataset)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8767, access_log=False))

    def ready():
        while not server.started and not server.should_exit:
            time.sleep(0.1)
        if server.started:
            (PLAYGROUND / "launch-url").write_text(
                settings.origin + "/#token=" + app.state.bootstrap_token, encoding="utf-8"
            )

    threading.Thread(target=ready, daemon=True).start()
    server.run()


if __name__ == "__main__":
    main()
