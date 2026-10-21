"""Independent SQLite repository. Each operation owns its connection/transaction."""

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .schema import Case, Dataset, Result, content_hash


def now():
    return datetime.now(timezone.utc).isoformat()


def dump(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


class Repository:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if tables.intersection({"memories", "revisions", "records"}):
                raise ValueError("Evaluation storage must be separate from the memory database")
            db.execute("BEGIN IMMEDIATE")
            db.execute("CREATE TABLE IF NOT EXISTS eval_migrations(version INTEGER PRIMARY KEY)")
            for path in sorted((Path(__file__).parent / "migrations").glob("*.sql")):
                version = int(path.name.split("_")[0])
                if not db.execute(
                    "SELECT 1 FROM eval_migrations WHERE version=?", (version,)
                ).fetchone():
                    for statement in path.read_text("utf-8").split(";"):
                        if statement.strip():
                            db.execute(statement)
                    db.execute("INSERT INTO eval_migrations VALUES(?)", (version,))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def create_dataset(self, dataset: Dataset):
        digest = content_hash(dataset.model_dump())
        with self.connect() as db:
            existing = db.execute(
                "SELECT * FROM eval_datasets WHERE id=?", (dataset.id,)
            ).fetchone()
            if existing:
                if existing["content_hash"] != digest:
                    raise ValueError("Dataset is immutable; use a new ID/version")
                return dataset.id
            db.execute(
                "INSERT INTO eval_datasets VALUES(?,?,?,?,?)",
                (dataset.id, dataset.name, dataset.version, digest, now()),
            )
            for case in dataset.cases:
                # Database IDs are namespaced; public case IDs remain dataset-local.
                key = dump([dataset.id, case.id])
                db.execute(
                    "INSERT INTO eval_cases VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        key,
                        dataset.id,
                        case.question,
                        case.expected_answer,
                        case.question_type,
                        case.ambiguity_class,
                        case.answerability,
                        case.expected_behavior,
                        dump({**case.metadata, "_case_id": case.id}),
                    ),
                )
                for group, ids in case.gold_groups.items():
                    db.executemany(
                        "INSERT INTO eval_gold_evidence VALUES(?,?,?)",
                        [(key, mid, group) for mid in set(ids)],
                    )
        return dataset.id

    def datasets(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM eval_datasets ORDER BY id")]

    def cases(self, dataset_id):
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM eval_cases WHERE dataset_id=? ORDER BY id", (dataset_id,)
            ).fetchall()
            cases = []
            for row in rows:
                r = dict(row)
                metadata = json.loads(r["metadata_json"])
                groups = {}
                for gold in db.execute(
                    "SELECT * FROM eval_gold_evidence WHERE case_id=?", (r["id"],)
                ):
                    groups.setdefault(gold["requirement_group"], []).append(gold["memory_id"])
                cases.append(
                    Case(
                        id=metadata.pop("_case_id"),
                        question=r["question"],
                        expected_answer=r["expected_answer"],
                        question_type=r["question_type"],
                        ambiguity_class=r["ambiguity_class"],
                        answerability=r["answerability"],
                        expected_behavior=r["expected_behavior"],
                        metadata=metadata,
                        gold_groups=groups,
                    )
                )
            return cases

    def create_run(self, dataset_id, variant="pma", config=None, commit_sha=None, environment=None):
        rid = uuid.uuid4().hex
        config = config or {}
        with self.connect() as db:
            db.execute(
                "INSERT INTO eval_runs VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    rid,
                    dataset_id,
                    variant,
                    commit_sha,
                    content_hash(config),
                    dump(config),
                    dump(environment or {}),
                    "pending",
                    None,
                    None,
                    None,
                ),
            )
        return rid

    def update_run_status(self, run_id, status, error_message=None):
        self.get_run(run_id)
        with self.connect() as db:
            db.execute(
                "UPDATE eval_runs SET status=?, started_at=COALESCE(started_at,?), "
                "finished_at=?, error_message=? WHERE id=?",
                (
                    status,
                    now(),
                    now() if status in {"completed", "failed", "cancelled"} else None,
                    error_message,
                    run_id,
                ),
            )

    def update_progress(self, run_id, case_id, stage):
        with self.connect() as db:
            db.execute(
                "INSERT INTO eval_run_progress VALUES(?,?,?,?) "
                "ON CONFLICT(run_id) DO UPDATE SET case_id=excluded.case_id,"
                "stage=excluded.stage,updated_at=excluded.updated_at",
                (run_id, case_id, stage, now()),
            )

    def get_run(self, run_id):
        with self.connect() as db:
            row = db.execute(
                "SELECT r.*, d.content_hash FROM eval_runs r JOIN eval_datasets d "
                "ON d.id=r.dataset_id WHERE r.id=?",
                (run_id,),
            ).fetchone()
            if row is None:
                raise KeyError(run_id)
            result = dict(row)
            result["config"] = json.loads(result.pop("config_json"))
            result["environment"] = json.loads(result.pop("environment_json"))
            return result

    def list_runs(self, dataset_id=None, limit=20, offset=0):
        where, args = (" WHERE dataset_id=?", [dataset_id]) if dataset_id else ("", [])
        with self.connect() as db:
            total = db.execute("SELECT count(*) FROM eval_runs" + where, args).fetchone()[0]
            rows = db.execute(
                "SELECT id FROM eval_runs"
                + where
                + " ORDER BY started_at DESC,id LIMIT ? OFFSET ?",
                [*args, limit, offset],
            ).fetchall()
        items = [self.get_run(r["id"]) for r in rows]
        for item in items:
            item["summary_available"] = bool(self.get_run_summary(item["id"])["metrics"])
        return dict(items=items, total=total, limit=limit, offset=offset)

    def save_case_result(self, run_id, result: Result, events=()):
        run = self.get_run(run_id)
        key = dump([run["dataset_id"], result.case_id])
        result_id = dump([run_id, result.case_id])
        with self.connect() as db:
            db.execute(
                "INSERT INTO eval_case_results "
                "(id,run_id,case_id,actual_answer,response_behavior,verdict,latency_ms,"
                "error_type,evaluation_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(run_id,case_id) DO UPDATE SET actual_answer=excluded.actual_answer,"
                "response_behavior=excluded.response_behavior,verdict=excluded.verdict,"
                "latency_ms=excluded.latency_ms,error_type=excluded.error_type,"
                "evaluation_json=excluded.evaluation_json",
                (
                    result_id,
                    run_id,
                    key,
                    result.actual_answer,
                    result.response_behavior,
                    result.verdict,
                    result.latency_ms,
                    result.error_type,
                    dump(result.evaluation),
                    now(),
                ),
            )
            db.execute("DELETE FROM eval_trace_events WHERE result_id=?", (result_id,))
            db.executemany(
                "INSERT INTO eval_trace_events "
                "(result_id,stage,event_index,payload_json,created_at) VALUES(?,?,?,?,?)",
                [(result_id, e["stage"], i, dump(e), now()) for i, e in enumerate(events)],
            )
            db.execute("DELETE FROM eval_claims WHERE result_id=?", (result_id,))
            db.executemany(
                "INSERT INTO eval_claims VALUES(?,?,?,?,?)",
                [
                    (
                        uuid.uuid4().hex,
                        result_id,
                        c.get("claim_text", ""),
                        c["support_status"],
                        dump(c.get("evidence", [])),
                    )
                    for c in result.claims
                ],
            )

    def list_case_results(self, run_id, limit=20, offset=0, *, compact=False, **filters):
        self.get_run(run_id)
        where, args = ["r.run_id=?"], [run_id]
        for key in ("verdict", "error_type", "question_type", "ambiguity_class"):
            if filters.get(key):
                where.append(f"{'r' if key in {'verdict', 'error_type'} else 'c'}.{key}=?")
                args.append(filters[key])
        if filters.get("q"):
            where.append("c.question LIKE ?")
            args.append("%" + filters["q"] + "%")
        join = " FROM eval_case_results r JOIN eval_cases c ON c.id=r.case_id WHERE "
        join += " AND ".join(where)
        projection = "r.*,c.question,c.expected_answer,c.question_type,c.ambiguity_class,c.expected_behavior,c.metadata_json,"
        if compact:
            # Do not load large observation/source/trace payloads for the list view.
            projection = (
                "r.id,r.run_id,r.case_id,r.actual_answer,r.response_behavior,r.verdict,r.latency_ms,r.error_type,"
                "c.question,c.expected_answer,c.question_type,c.ambiguity_class,c.expected_behavior,"
                "json_object('_case_id',json_extract(c.metadata_json,'$._case_id')) AS metadata_json,"
                "json_object('suite_verdict',json_extract(r.evaluation_json,'$.suite_verdict'),"
                "'measurement_type',json_extract(r.evaluation_json,'$.measurement_type')) AS evaluation_json,"
            )
        with self.connect() as db:
            total = db.execute("SELECT count(*)" + join, args).fetchone()[0]
            rows = db.execute(
                "SELECT " + projection +
                "EXISTS(SELECT 1 FROM eval_trace_events t WHERE t.result_id=r.id) "
                "AS has_trace" + join + " ORDER BY c.id,r.id LIMIT ? OFFSET ?",
                [*args, limit, offset],
            ).fetchall()
        items = []
        for row in rows:
            r = dict(row)
            r["case_id"] = json.loads(r.pop("metadata_json"))["_case_id"]
            r["evaluation"] = json.loads(r.pop("evaluation_json"))
            items.append(r)
        return dict(items=items, total=total, limit=limit, offset=offset)

    def get_case_result(self, run_id, case_id):
        run = self.get_run(run_id)
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM eval_case_results WHERE run_id=? AND case_id=?",
                (run_id, dump([run["dataset_id"], case_id])),
            ).fetchone()
            if row is None:
                raise KeyError(case_id)
            result = dict(row)
            case = next(c for c in self.cases(run["dataset_id"]) if c.id == case_id)
            result.update(case.model_dump(), case_id=case_id, id=row["id"])
            result["evaluation"] = json.loads(result.pop("evaluation_json"))
            result["claims"] = [
                dict(c)
                for c in db.execute(
                    "SELECT claim_text,support_status,evidence_json FROM eval_claims WHERE result_id=?",
                    (row["id"],),
                )
            ]
            return result

    def results(self, run_id):
        self.get_run(run_id)
        with self.connect() as db:
            claims = {}
            for claim in db.execute(
                "SELECT c.* FROM eval_claims c JOIN eval_case_results r "
                "ON c.result_id=r.id WHERE r.run_id=?",
                (run_id,),
            ):
                claims.setdefault(claim["result_id"], []).append(
                    dict(
                        claim_text=claim["claim_text"],
                        support_status=claim["support_status"],
                        evidence=json.loads(claim["evidence_json"]),
                    )
                )
            return [
                Result(
                    case_id=json.loads(row["case_id"])[1],
                    actual_answer=row["actual_answer"],
                    response_behavior=row["response_behavior"],
                    verdict=row["verdict"],
                    latency_ms=row["latency_ms"],
                    error_type=row["error_type"],
                    evaluation=json.loads(row["evaluation_json"]),
                    claims=claims.get(row["id"], []),
                )
                for row in db.execute(
                    "SELECT * FROM eval_case_results WHERE run_id=? ORDER BY case_id", (run_id,)
                )
            ]

    def get_case_trace(self, run_id, case_id):
        result = self.get_case_result(run_id, case_id)
        with self.connect() as db:
            events = [
                json.loads(r[0])
                for r in db.execute(
                    "SELECT payload_json FROM eval_trace_events WHERE result_id=? ORDER BY event_index",
                    (result["id"],),
                )
            ]
        return dict(
            run_id=run_id,
            case_id=case_id,
            stages=events,
            trace_status=result["evaluation"].get("trace_status", "not_instrumented"),
            diagnosis=result["evaluation"].get("diagnosis", {"error_type": "unknown"}),
        )

    def replace_run_metrics(self, run_id, metrics):
        with self.connect() as db:
            db.execute("DELETE FROM eval_metrics WHERE run_id=?", (run_id,))
            db.executemany(
                "INSERT INTO eval_metrics VALUES(?,?,?,?,?,?)",
                [
                    (
                        run_id,
                        k,
                        v["numerator"],
                        v["denominator"],
                        v["value"],
                        dump(v.get("details", {})),
                    )
                    for k, v in metrics.items()
                ],
            )

    def get_run_summary(self, run_id):
        run = self.get_run(run_id)
        with self.connect() as db:
            progress = db.execute(
                "SELECT case_id,stage,updated_at FROM eval_run_progress WHERE run_id=?", (run_id,)
            ).fetchone()
            counts = dict(
                db.execute(
                    "SELECT verdict,count(*) FROM eval_case_results "
                    "WHERE run_id=? GROUP BY verdict",
                    (run_id,),
                ).fetchall()
            )
            metrics = {
                r["metric_name"]: dict(
                    numerator=r["numerator"],
                    denominator=r["denominator"],
                    value=r["value"],
                    status="not_applicable" if r["value"] is None else "available",
                    details=json.loads(r["details_json"]),
                )
                for r in db.execute("SELECT * FROM eval_metrics WHERE run_id=?", (run_id,))
            }
        return dict(
            run_id=run_id,
            progress=dict(progress) if progress else None,
            dataset_id=run["dataset_id"],
            variant=run["variant"],
            status=run["status"],
            case_counts={
                **counts,
                "total": len(self.cases(run["dataset_id"])),
                "recorded": sum(counts.values()),
                "evaluated": counts.get("pass", 0) + counts.get("fail", 0),
            },
            metrics=metrics,
        )
