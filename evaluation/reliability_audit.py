"""Reproduce existing failures in an isolated database; preserve baseline sources."""

import argparse
import hashlib
import json
import os
import sqlite3
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from pma.models import LocalModels
from pma.service import Service
from pma.settings import AppSettings
from pma.store import Store


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-db", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.run_dir.resolve() == args.source_db.resolve().parent:
        raise ValueError("Isolated run directory required")
    args.run_dir.mkdir(parents=True, exist_ok=True)
    settings = AppSettings.from_env()
    manifest = json.loads(
        Path("output/life-evaluation-20261013/manifest.json").read_text(encoding="utf-8")
    )
    settings = replace(
        settings,
        data_dir=args.run_dir,
        embedding_revision=manifest["embedding_revision"],
        llm=replace(settings.llm, model="qwen3"),
    )
    with sqlite3.connect(args.source_db.resolve().as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        rows = [
            dict(r)
            for r in db.execute(
                "SELECT r.id,v.text,v.reference_time,r.status FROM records r JOIN revisions v ON v.record_id=r.id AND v.version=r.version WHERE r.state='active' AND (r.status='failed' OR length(v.text)>=500) ORDER BY length(v.text),r.id"
            )
        ]
    sources_path = args.run_dir / "sources.json"
    if sources_path.exists():
        rows = json.loads(sources_path.read_text(encoding="utf-8"))
    else:
        sources_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    code_paths = [
        "pma/processing.py",
        "pma/models.py",
        "pma/store.py",
        "pma/service.py",
        "pma/facts.py",
        "pma/grounding.py",
        "scripts/memory_agent/pipeline.py",
        "scripts/memory_agent/provenance.py",
    ]
    (args.run_dir / f"manifest-{run_id}.json").write_text(
        json.dumps(
            dict(
                run_id=run_id,
                generation_revision=os.getenv("PMA_GENERATION_REVISION", "unconfigured"),
                embedding_revision=settings.embedding_revision,
                model=settings.llm.model,
                code_sha256={
                    p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in code_paths
                },
                sources_sha256=hashlib.sha256(sources_path.read_bytes()).hexdigest(),
                semantic_review="pending",
            ),
            indent=2,
        ),
        encoding="utf-8",
    )
    store = Store(args.run_dir / "memory.db")
    service = Service(store, LocalModels(settings), settings)
    store.recover()
    result_path = args.run_dir / "results.json"
    reports = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else []
    for row in rows:
        prior = next((r for r in reports if r["source_id"] == row["id"]), None)
        if prior and prior["status"] == "ready":
            continue
        with store.connect() as db:
            existing = db.execute(
                "SELECT record_id FROM revisions WHERE text=? AND reference_time=? ORDER BY rowid DESC LIMIT 1",
                (row["text"], row["reference_time"]),
            ).fetchone()
        rid = (
            existing[0]
            if existing
            else store.create(row["text"], row["reference_time"])["record_id"]
        )
        if store.get(rid)["status"] == "failed":
            store.retry(rid)
        reports = [r for r in reports if r["source_id"] != row["id"]]
        while store.get(rid)["status"] in {"queued", "processing"}:
            if not service.run_one():
                raise RuntimeError("No runnable job for pending audit record")
        record = store.get(rid)
        reports.append(
            dict(
                source_id=row["id"],
                record_id=rid,
                status=record["status"],
                diagnostic=record["processing_details"],
                memories=record["memories"],
                semantic_review="pending",
            )
        )
        (args.run_dir / "results.json").write_text(
            json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(
            len(reports),
            "/",
            len(rows),
            row["id"],
            record["status"],
            record["error_code"],
            flush=True,
        )
    store.checkpoint()


if __name__ == "__main__":
    main()
