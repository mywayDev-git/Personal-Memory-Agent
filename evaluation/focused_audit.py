"""Frozen-copy, no-reextraction answer audit. Production search remains unchanged."""

import argparse
import hashlib
import json
import sqlite3
import sys
import time
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

from evaluation.focused_cases import GROUPS, cases, schedule
from evaluation.life_diagnostics import write_json
from evaluation.search_diagnostics import TracedModels
from pma.service import Service
from pma.settings import AppSettings
from pma.store import Store


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Models(TracedModels):
    def select(self, question, evidence):
        self.selection_candidates = evidence
        selected = super().select(question, evidence)
        self.selected_ids = selected
        return selected


class TracedService(Service):
    def _search(self, *args, **kwargs):
        self.search_trace = {}

        def trace(frame, event, arg):
            if frame.f_code is Service._search.__code__ and event == "return":
                values = frame.f_locals
                self.search_trace = {
                    "query_plan": values.get("plan"),
                    "filters": values.get("applied"),
                    "eligible_ids": [r["id"] for r in values.get("candidates", [])],
                    "ranked_ids": [values["candidates"][i]["id"] for i in values.get("order", [])],
                    "search_result": arg[1] if isinstance(arg, tuple) else None,
                }
            return trace

        previous = sys.gettrace()
        sys.settrace(trace)
        try:
            return super()._search(*args, **kwargs)
        finally:
            sys.settrace(previous)


def copy_database(source, target):
    with sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True) as src:
        with sqlite3.connect(target) as dst:
            src.backup(dst)


def prepare(source, directory, settings):
    directory.mkdir(parents=True, exist_ok=False)
    data = json.loads(Path("data/life_diagnostics.json").read_text(encoding="utf-8"))
    copy_database(source, directory / "frozen.db")
    mapping = {}
    with sqlite3.connect(directory / "frozen.db") as db:
        for r in data["records"]:
            found = db.execute(
                "SELECT record_id FROM revisions WHERE version=1 AND text=? AND reference_time IS ?",
                (r["text"], r["reference_time"]),
            ).fetchone()
            if found:
                mapping[r["id"]] = found[0]
    selected = {s for group in GROUPS.values() for s in group}
    assert len(selected) == 42 and selected <= mapping.keys()
    write_json(
        directory / "oracle.json",
        dict(
            today=data["today"],
            groups=GROUPS,
            cases=cases(),
            sources=[r for r in data["records"] if r["id"] in selected],
        ),
    )
    environments = {
        "full": None,
        **{g: ids for g, ids in GROUPS.items()},
        "gift_before": GROUPS["G"][:5],
        "gift_after": GROUPS["G"][:5] + ["B037", "B097"],
        "run_before": GROUPS["R"][:5],
        "run_after": GROUPS["R"],
    }
    inventory = {}
    for env, ids in environments.items():
        path = directory / f"{env}.db"
        copy_database(directory / "frozen.db", path)
        store = Store(path)
        if ids is not None:
            keep = [mapping[s] for s in ids]
            with store.connect(True) as db:
                db.execute(
                    "DELETE FROM records WHERE id NOT IN (" + ",".join("?" for _ in keep) + ")",
                    keep,
                )
        _, rows = store.snapshot(settings.embedding_key)
        with store.connect() as db:
            states = [
                dict(r)
                for r in db.execute(
                    "SELECT r.id,r.version,r.state,r.status,v.text,v.reference_time FROM records r JOIN revisions v ON v.record_id=r.id AND v.version=r.version"
                )
            ]
        inventory[env] = dict(
            records=states, memories=[{k: v for k, v in r.items() if k != "vector"} for r in rows]
        )
        store.checkpoint()
    write_json(directory / "inventory.json", inventory)
    code = [p for folder in ("pma", "evaluation") for p in Path(folder).glob("*.py")]
    manifest = dict(
        created_at=datetime.now(timezone.utc).isoformat(),
        today=data["today"],
        mapping=mapping,
        frozen_sha256=digest(directory / "frozen.db"),
        oracle_sha256=digest(directory / "oracle.json"),
        code_sha256={str(p): digest(p) for p in code},
        llm=asdict(settings.llm),
        embedding_key=settings.embedding_key,
        planned=80,
        no_reextraction=True,
    )
    write_json(directory / "manifest.json", manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-db", type=Path, default=Path(".local/life-web/memory.db"))
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    base = AppSettings.from_env()
    revision = json.loads(
        Path("output/life-evaluation-20261013/manifest.json").read_text(encoding="utf-8")
    )["embedding_revision"]
    settings = replace(
        base,
        data_dir=args.run_dir,
        embedding_revision=revision,
        llm=replace(base.llm, model="qwen3"),
    )
    if not args.run_dir.exists():
        manifest = prepare(args.source_db, args.run_dir, settings)
    else:
        manifest = json.loads((args.run_dir / "manifest.json").read_text(encoding="utf-8"))
        assert all(digest(Path(p)) == h for p, h in manifest["code_sha256"].items()), (
            "Code changed; use new run directory"
        )
        assert digest(args.run_dir / "oracle.json") == manifest["oracle_sha256"]
        assert (
            asdict(settings.llm) == manifest["llm"]
            and settings.embedding_key == manifest["embedding_key"]
        )
    oracle = json.loads((args.run_dir / "oracle.json").read_text(encoding="utf-8"))
    by_id = {c["id"]: c for c in oracle["cases"]}
    inverse = {v: k for k, v in manifest["mapping"].items()}
    result_dir = args.run_dir / "runs"
    result_dir.mkdir(exist_ok=True)
    for index, (env, qid) in enumerate(schedule(), 1):
        dest = result_dir / f"{env}-{qid}.json"
        if dest.exists():
            continue  # Preserve first response, including failures.
        db_env = qid[0] if env == "small" else env
        store = Store(args.run_dir / f"{db_env}.db")
        model = Models(settings)
        service = TracedService(store, model, settings)
        started = time.monotonic()
        entry = dict(
            run_id=dest.stem,
            environment=env,
            question_id=qid,
            case=by_id[qid],
            started_at=datetime.now(timezone.utc).isoformat(),
            semantic_review="pending",
        )
        try:
            entry["response"] = service.answer(by_id[qid]["question"], today=manifest["today"])
        except Exception as exc:
            entry["execution_error"] = dict(
                type=type(exc).__name__, code=getattr(exc, "code", None)
            )
        entry.update(
            elapsed_seconds=round(time.monotonic() - started, 3),
            trace=service.search_trace,
            model_trace={
                k: getattr(model, k, None)
                for k in (
                    "last_stage",
                    "last_understanding",
                    "selection_candidates",
                    "selected_ids",
                    "last_evidence",
                    "last_answer",
                )
            },
        )
        response = entry.get("response", {})
        lookup = {
            r["id"]: inverse.get(r["record_id"], r["record_id"])
            for r in response.get("results", [])
        }
        citations = {c for item in response.get("items", []) for c in item.get("citations", [])}
        entry["automatic_checks"] = dict(
            citation_ids_exist=citations <= lookup.keys(),
            retrieved_sources=sorted(set(lookup.values())),
            cited_sources=sorted({lookup[c] for c in citations if c in lookup}),
        )
        with store.connect() as db:
            entry["input_not_ready"] = [
                sid
                for sid in by_id[qid]["required_sources"]
                if db.execute(
                    "SELECT status FROM records WHERE id=?", (manifest["mapping"][sid],)
                ).fetchone()[0]
                not in {"ready", "ready_empty"}
            ]
        write_json(dest, entry)
        print(
            index,
            "/ 80",
            dest.stem,
            response.get("status", "execution_error"),
            entry["elapsed_seconds"],
            flush=True,
        )


if __name__ == "__main__":
    main()
