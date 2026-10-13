"""Import synthetic records through the normal extraction and embedding pipeline.

Run with the app stopped and compatible model servers running.
Existing matching records are reused; existing source text is never overwritten.
Pending jobs already in the normal queue are processed before the new demo jobs.
"""

import json
from pathlib import Path

from pma.lock import DataLock
from pma.models import LocalModels
from pma.service import Service
from pma.settings import AppSettings
from pma.store import Store


def main():
    settings = AppSettings.from_env()
    if settings.embedding_revision == "unconfigured":
        raise RuntimeError("Set PMA_EMBEDDING_REVISION to the embedding file SHA-256 first.")
    records = json.loads(
        (Path(__file__).resolve().parents[1] / "data/demo_records.json").read_text("utf-8")
    )
    with DataLock(settings.data_dir / "app.lock"):
        store = Store(settings.data_dir / "memory.db")
        service = Service(store, LocalModels(settings), settings)
        ids = []
        for item in records:
            with store.connect() as db:
                existing = db.execute(
                    "SELECT r.id FROM records r JOIN revisions v "
                    "ON v.record_id=r.id AND v.version=r.version "
                    "WHERE r.state='active' AND v.text=? AND v.reference_time=?",
                    (item["text"], item["reference_time"]),
                ).fetchone()
            rid = existing["id"] if existing else store.create(**item)["record_id"]
            ids.append(rid)
        # Process the normal queue so every stored memory has real model output and vectors.
        while any(store.get(rid)["status"] == "queued" for rid in ids):
            if not service.run_one():
                break
            print("Processed one queued record", flush=True)
        states = [store.get(rid) for rid in ids]
        print(
            json.dumps(
                {
                    "records": len(ids),
                    "statuses": [r["status"] for r in states],
                    "memories": sum(len(r["memories"]) for r in states),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        if not all(r["status"] == "ready" for r in states):
            raise RuntimeError(
                "Some demo records are not searchable yet; inspect their job status."
            )
        result = service.answer("캡스톤 프로젝트에서 내가 맡기로 한 역할은?")
        print(json.dumps(result, ensure_ascii=False), flush=True)
        if not any(
            item["record_id"] == ids[0] and "백엔드" in item["content"]
            for item in result["results"]
        ):
            raise RuntimeError("Demo search verification failed")
        if result["status"] != "answered":
            print("Demo search passed, but the model did not generate an answer.", flush=True)


if __name__ == "__main__":
    main()
