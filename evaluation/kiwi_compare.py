"""Run A-H factorial experiments and unchanged app L on isolated synthetic databases.

Examples: python -m evaluation.kiwi_compare --output output/kiwi-dev --split dev --limit 4
Resume with the same command without --limit. No data outside the owned run is modified.
"""

import argparse
import copy
import hashlib
import importlib.metadata
import json
import platform
import random
import tempfile
import time
from dataclasses import replace
from pathlib import Path

from pma.lock import DataLock
from pma.models import LocalModels
from pma.service import Service
from pma.settings import AppSettings
from pma.store import Store
from scripts.memory_agent.llm_client import local_session

from .build_kiwi_dataset import validate
from .kiwi_contract import (
    ARMS,
    BASE_PROMPT,
    GRAMMAR_PROMPT,
    SCHEMA,
    VERIFY_PROMPT,
    VERSION,
    source_units,
    validate_result,
)
from .kiwi_report import read_entries, report
from .kiwi_runtime import MemoryDB, Meter, answer
from .kiwi_scoring import score_answer, score_extraction
from .life_diagnostics import write_json

ROOT = Path(__file__).resolve().parents[1]


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def code_hash():
    paths = [
        p
        for folder in ("evaluation", "pma", "scripts", "config", "schema", "prompts")
        for p in (ROOT / folder).rglob("*")
        if p.suffix in {".py", ".json", ".txt"}
    ]
    return fingerprint(
        {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(paths)
        }
    )


def make_schedule(data, split, arms, repeats=True, supplements=True):
    cases = [c for c in data["cases"] if c["split"] == split]
    rng = random.Random(42)
    schedule, repeat_categories = [], set()
    for case in cases:
        order = list(arms)
        rng.shuffle(order)
        phases = ["main"]
        if case.get("before_questions"):
            phases.append("before")
        if supplements and case.get("supplement"):
            phases.append("supplement")
        if repeats and split == "test" and case["category"] not in repeat_categories:
            phases += ["repeat1", "repeat2"]
            repeat_categories.add(case["category"])
        for phase in phases:
            for arm in order:
                schedule.append(
                    dict(
                        run_id=f"{case['id']}-{arm}-{phase}",
                        case=case["id"],
                        arm=arm,
                        phase=phase,
                        category=case["category"],
                        question_count=len(case.get("before_questions", []))
                        if phase == "before"
                        else len(case["questions"]),
                    )
                )
    return schedule


def model_identity(settings):
    identities = {}
    with local_session() as session:
        for name, endpoint in [
            ("generation", settings.llm.endpoint),
            ("embedding", settings.embedding_endpoint),
        ]:
            r = session.get(
                LocalModels.base(endpoint) + "/v1/models", timeout=5, allow_redirects=False
            )
            r.raise_for_status()
            # Server creation timestamp changes across restarts; model metadata does not.
            payload = r.json()
            identities[name] = [
                {k: v for k, v in m.items() if k != "created"} for m in payload.get("data", [])
            ]
            if not identities[name]:
                raise ValueError("MODEL_IDENTITY_UNAVAILABLE")
    return identities


class Experiment:
    def __init__(self, settings, use_kiwi=False):
        self.settings = settings
        self.models = LocalModels(settings)
        self.kiwi = None
        self.kiwi_initialization_seconds = 0
        if use_kiwi:
            from kiwipiepy import Kiwi

            started = time.perf_counter()
            self.kiwi = Kiwi(num_workers=1)
            self.kiwi.tokenize("준비")
            self.kiwi_initialization_seconds = time.perf_counter() - started

    def payload(self, records, arm):
        units = source_units(records)
        payload = dict(sentences=units)
        seconds = 0
        if ARMS[arm]["kiwi"]:
            if self.kiwi is None:
                raise RuntimeError("KIWI_NOT_INITIALIZED")
            started = time.perf_counter()
            payload["morphology"] = [
                dict(
                    sentence_id=u["id"],
                    tokens=[
                        dict(form=t.form, tag=t.tag, start=u["start"] + t.start, length=t.len)
                        for t in self.kiwi.tokenize(u["text"])
                    ],
                )
                for u in units
            ]
            seconds = time.perf_counter() - started
        return payload, units, seconds

    def common(self, case, records, questions, arm, directory, meter, entry):
        payload, units, elapsed = self.payload(records, arm)
        entry["kiwi_seconds"] = elapsed
        entry["input"] = payload
        prompt = BASE_PROMPT + (GRAMMAR_PROMPT if ARMS[arm]["grammar"] else "")
        meter.stage = "extract"
        raw = self.models.structured(prompt, payload, SCHEMA)
        entry["initial_extraction"] = raw
        if ARMS[arm]["verify"]:
            meter.stage = "verify"
            raw = self.models.structured(VERIFY_PROMPT, dict(**payload, proposed=raw), SCHEMA)
            entry["verified_extraction"] = raw
        meter.stage = "grounding_validation"
        extracted = validate_result(raw, units)
        entry["extraction"] = extracted
        if entry["phase"] in {"main", "repeat1", "repeat2"}:
            entry["extraction_assessment"] = score_extraction(case, extracted)
        meter.stage = "event_embedding"
        vectors = self.models.embed([e["content"] for e in extracted["events"]])
        db = MemoryDB(directory / "events.db")
        try:
            db.publish(extracted, vectors)
            for q in questions:
                response, retrieved = answer(self.models, db, q["text"], meter)
                entry["answers"].append(
                    dict(
                        question=q["text"],
                        response=response,
                        retrieved=retrieved,
                        assessment=score_answer(q, response, retrieved),
                    )
                )
        finally:
            db.close()

    def legacy(self, case, records, questions, directory, meter, entry):
        settings = replace(self.settings, data_dir=directory)
        store = Store(directory / "legacy.db")
        service = Service(store, self.models, settings)
        mapping = {}
        for ri, record in enumerate(records):
            mapping[store.create(record["text"], record.get("reference_time"))["record_id"]] = ri
            meter.stage = "legacy_processing"
            service.run_one()
        for rid in mapping:
            if store.get(rid)["status"] not in {"ready", "ready_empty"}:
                raise ValueError("LEGACY_PROCESSING_FAILED")
        rows = store.snapshot(settings.embedding_key)[1]
        entry["legacy_memories"] = [{k: v for k, v in r.items() if k != "vector"} for r in rows]
        events = []
        for i, row in enumerate(rows):
            m = row["memory"]
            fact = row.get("fact") or {}
            events.append(
                dict(
                    id=f"e{i}",
                    content=m["content"],
                    predicate=m["predicate"],
                    actor=fact.get("actor"),
                    recipient=fact.get("recipient"),
                    object=m["object"]["value"],
                    speaker=fact.get("speaker"),
                    time=fact.get("event_time", m["time"]),
                    status={"observed": "occurred", "uncertain": "unknown"}.get(
                        fact.get("state"), fact.get("state")
                    ),
                    operators=[],
                    evidence=[dict(e, record=mapping[row["record_id"]]) for e in row["evidence"]],
                )
            )
        entry["extraction"] = dict(events=events, relations=[], questions=[])
        entry["legacy_relations"] = store.links()
        if entry["phase"] in {"main", "repeat1", "repeat2"}:
            entry["extraction_assessment"] = score_extraction(case, entry["extraction"])
            entry["extraction_assessment"]["note"] += (
                " Legacy scope/relation schema is not comparable; inspect legacy_relations."
            )
        for q in questions:
            meter.stage = "legacy_answer"
            response = service.answer(q["text"], today="2026-10-13")
            retrieved = [
                dict(r, evidence=[dict(e, record=mapping[r["record_id"]]) for e in r["evidence"]])
                for r in response.get("results", [])
            ]
            entry["answers"].append(
                dict(
                    question=q["text"],
                    response=response,
                    retrieved=retrieved,
                    assessment=score_answer(q, response, retrieved),
                )
            )

    def execute(self, case, job, directory):
        started = time.perf_counter()
        entry = dict(job, status="running", answers=[])
        records = copy.deepcopy(case["records"])
        questions = case["questions"]
        if job["phase"] == "before":
            records = records[:1]
            questions = case["before_questions"]
        elif job["phase"] == "supplement":
            records.append(dict(text=case["supplement"], reference_time=None))
            entry["supplement_note"] = (
                "Simulated authored clarification, separate condition; no application UI or automatic correctness claim."
            )
        meter = Meter(self.models)
        with tempfile.TemporaryDirectory(prefix="synthetic-", dir=directory) as temp, meter:
            try:
                if job["arm"] == "L":
                    self.legacy(case, records, questions, Path(temp), meter, entry)
                else:
                    self.common(case, records, questions, job["arm"], Path(temp), meter, entry)
                entry["status"] = "complete"
            except Exception as exc:
                entry.update(
                    status="failed",
                    failure_stage=meter.stage,
                    error_type=type(exc).__name__,
                    error_code=getattr(exc, "code", None),
                )
                if isinstance(exc, ValueError) and len(str(exc)) < 120:
                    entry["validation_error"] = str(exc)
        entry.update(seconds=time.perf_counter() - started, calls=meter.calls)
        entry["result_hash"] = fingerprint(entry)
        return entry


def sentence_report(experiment, cases):
    if experiment.kiwi is None:
        return dict(status="not_executed", reason="No Kiwi arm selected")
    return dict(
        status="needs_boundary_review",
        cases=[
            dict(
                case=c["id"],
                source=r["text"],
                current=[
                    dict(start=u["start"], end=u["end"], text=u["text"]) for u in source_units([r])
                ],
                kiwi=[
                    dict(start=s.start, end=s.end, text=s.text)
                    for s in experiment.kiwi.split_into_sents(r["text"])
                ],
            )
            for c in cases
            for r in c["records"]
        ],
    )


def run(args):
    data = json.loads(args.dataset.read_text(encoding="utf-8"))
    validate(data)
    arms = list(dict.fromkeys(args.arms.upper()))
    if not arms or set(arms) - set(ARMS):
        raise ValueError("Unknown arm")
    settings = AppSettings.from_env()
    settings = replace(
        settings,
        llm=replace(
            settings.llm, temperature=0, seed=42, max_tokens=args.max_tokens, timeout=args.timeout
        ),
    )
    if settings.embedding_revision == "unconfigured":
        raise ValueError("Set PMA_EMBEDDING_REVISION to the actual loaded embedding model SHA-256")
    directory = args.output.resolve()
    personal = settings.data_dir.resolve()
    if directory == personal or directory in personal.parents or personal in directory.parents:
        raise ValueError("Output must not overlap the application data directory")
    marker = directory / "manifest.json"
    if directory.exists() and any(directory.iterdir()) and not marker.exists():
        raise ValueError("Refusing nonempty unowned output directory")
    kiwi_version = None
    if any(ARMS[a]["kiwi"] for a in arms):
        kiwi_version = importlib.metadata.version("kiwipiepy")
        if kiwi_version != "0.24.0":
            raise ValueError("Use kiwipiepy==0.24.0")
    identity = dict(
        version=VERSION,
        dataset=fingerprint(data),
        code=code_hash(),
        models=model_identity(settings),
        settings=dict(
            llm=vars(settings.llm),
            embedding=settings.embedding_key,
            context=settings.context_tokens,
        ),
        kiwi=kiwi_version,
        python=platform.python_version(),
        arms=arms,
        split=args.split,
        repeats=not args.no_repeats,
        supplements=not args.no_supplements,
    )
    schedule = make_schedule(data, args.split, arms, not args.no_repeats, not args.no_supplements)
    if args.split == "test":
        if not args.freeze_from:
            raise ValueError("Test split requires --freeze-from completed development directory")
        previous = json.loads((args.freeze_from / "manifest.json").read_text(encoding="utf-8"))
        if previous["identity"]["split"] != "dev":
            raise ValueError("Freeze source must be development")
        for key in ("dataset", "code", "models", "settings", "kiwi", "python", "arms"):
            if previous["identity"][key] != identity[key]:
                raise ValueError(f"FROZEN_CONFIGURATION_CHANGED: {key}")
        done = {e["run_id"] for e in read_entries(args.freeze_from)}
        if done != {j["run_id"] for j in previous["schedule"]}:
            raise ValueError("Development execution incomplete")
    directory.mkdir(parents=True, exist_ok=True)
    with DataLock(directory / "run.lock"):
        if marker.exists():
            saved = json.loads(marker.read_text(encoding="utf-8"))
            if saved["identity"] != identity or saved["schedule"] != schedule:
                raise ValueError("RESUME_CONFIGURATION_MISMATCH")
        else:
            write_json(marker, dict(identity=identity, schedule=schedule, synthetic_only=True))
            write_json(directory / "dataset.json", data)
        completed = directory / "completed"
        completed.mkdir(exist_ok=True)
        expected_ids = {j["run_id"] for j in schedule}
        for previous_entry in read_entries(directory):
            recorded_hash = previous_entry.pop("result_hash", None)
            if (
                previous_entry["run_id"] not in expected_ids
                or fingerprint(previous_entry) != recorded_hash
            ):
                raise ValueError("CORRUPTED_CHECKPOINT")
        experiment = Experiment(settings, any(ARMS[a]["kiwi"] for a in arms))
        write_json(
            directory / "startup.json",
            dict(kiwi_initialization_seconds=experiment.kiwi_initialization_seconds),
        )
        cases = {c["id"]: c for c in data["cases"]}
        write_json(
            directory / "sentence_boundaries.json",
            sentence_report(experiment, [c for c in data["cases"] if c["split"] == args.split]),
        )
        selected = {c["id"] for c in data["cases"] if c["split"] == args.split}
        if args.limit:
            selected = {
                c["id"]
                for c in data["cases"]
                if c["split"] == args.split
                and c["id"] in list(cases_for_split(data, args.split))[: args.limit]
            }
        try:
            for job in schedule:
                path = completed / f"{job['run_id']}.json"
                if job["case"] not in selected or path.exists():
                    continue
                print(f"running {job['run_id']}", flush=True)
                entry = experiment.execute(cases[job["case"]], job, directory)
                write_json(path, entry)
                with (directory / "results.jsonl").open("a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                print(f"{entry['status']} {job['run_id']} {entry['seconds']:.1f}s", flush=True)
                write_json(
                    directory / "progress.json",
                    dict(
                        last_run=job["run_id"],
                        completed=len(list(completed.glob("*.json"))),
                        planned=len(schedule),
                    ),
                )
                if len(list(completed.glob("*.json"))) % len(arms) == 0:
                    report(directory)
        finally:
            report(directory)
        entries = read_entries(directory)
        main = [e for e in entries if e["phase"] == "main"]
        if main:
            estimate = sum(e["seconds"] for e in main) / len(main) * len(schedule)
            print(f"Measured schedule estimate: {estimate / 3600:.2f} hours; not a completion ETA.")


def cases_for_split(data, split):
    return [c["id"] for c in data["cases"] if c["split"] == split]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "data/kiwi_comparison.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--split", choices=["dev", "test"], default="dev")
    parser.add_argument("--arms", default="ABCDEFGHL")
    parser.add_argument(
        "--limit", type=int, help="Pilot case limit; omitted cases stay not_executed"
    )
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--freeze-from", type=Path)
    parser.add_argument("--no-repeats", action="store_true")
    parser.add_argument("--no-supplements", action="store_true")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("limit must be positive")
    run(args)


if __name__ == "__main__":
    main()
