"""Transactional record lifecycle. No network or inference inside a transaction."""

import json
import sqlite3
import time
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from .diagnostics import Reason, Stage, Status, current_trace
from .errors import AppError
from .facts import FACT_VERSION, connection, fingerprint, project


def now():
    return datetime.now(timezone.utc).isoformat()


def identifier():
    return str(uuid4())


def _start_observation():
    try:
        trace = current_trace()
        return (trace, time.perf_counter()) if trace is not None else None
    except Exception:
        return None


def _observe_read(stage, observation, rows, *, selected_ids=None, record_id=None, executed=True):
    """Observe materialized results after closing the transaction; never query here."""
    if observation is None:
        return
    trace, started = observation
    try:
        duration_ms = (time.perf_counter() - started) * 1000
        if stage == Stage.SNAPSHOT:
            trace.record_event(
                stage,
                input_count=None,
                output_count=len(rows),
                duration_ms=duration_ms,
                unobserved_reason=Reason.NOT_OBSERVED,
                candidates=[
                    dict(
                        memory_ref=trace.memory_ref(row["id"]),
                        record_ref=trace.record_ref(row["record_id"]),
                        status=Status.INCLUDED,
                        has_fact=row["fact"] is not None,
                        has_embedding=row["vector"] is not None,
                        has_record=row["record_id"] is not None,
                    )
                    for row in rows
                ],
            )
        else:
            trace.record_event(
                stage,
                input_count=len(selected_ids) if selected_ids is not None else None,
                output_count=len(rows),
                duration_ms=duration_ms,
                executed=executed,
                evidence_refs=(
                    [trace.memory_ref(mid) for mid in selected_ids]
                    if selected_ids is not None
                    else None
                ),
                record_refs=[trace.record_ref(record_id)] if record_id else None,
                relation_refs=[trace.relation_ref(row["id"]) for row in rows],
                candidates=[
                    dict(
                        relation_ref=trace.relation_ref(row["id"]),
                        memory_ref=trace.memory_ref(mid),
                        record_ref=trace.record_ref(rid),
                        status=Status.INCLUDED,
                    )
                    for row in rows
                    for mid, rid in zip(row["citations"], row["records"], strict=True)
                ],
            )
    except Exception:
        # Even preparation failures must not affect the original query result.
        # Do not log exception strings: they may contain original record data.
        try:
            trace.recording_failed = True
        except Exception:
            pass


DDL = """
CREATE TABLE IF NOT EXISTS metadata (id INTEGER PRIMARY KEY CHECK(id=1), generation INTEGER NOT NULL);
INSERT OR IGNORE INTO metadata VALUES (1,0);
CREATE TABLE IF NOT EXISTS records (
 id TEXT PRIMARY KEY, version INTEGER NOT NULL, state TEXT NOT NULL CHECK(state IN ('active','trash')),
 status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 deleted_at TEXT, purge_at TEXT);
CREATE TABLE IF NOT EXISTS revisions (
 id TEXT PRIMARY KEY, record_id TEXT NOT NULL REFERENCES records(id) ON DELETE CASCADE,
 version INTEGER NOT NULL, text TEXT NOT NULL, reference_time TEXT, created_at TEXT NOT NULL,
 UNIQUE(record_id,version));
CREATE TABLE IF NOT EXISTS jobs (
 id TEXT PRIMARY KEY, revision_id TEXT NOT NULL REFERENCES revisions(id) ON DELETE CASCADE,
 status TEXT NOT NULL CHECK(status IN ('queued','running','succeeded','failed','cancelled')),
 attempts INTEGER NOT NULL DEFAULT 0, token TEXT, error_code TEXT, metadata TEXT,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS one_live_job ON jobs(revision_id)
 WHERE status IN ('queued','running');
CREATE TABLE IF NOT EXISTS memories (
 id TEXT PRIMARY KEY, revision_id TEXT NOT NULL REFERENCES revisions(id) ON DELETE CASCADE,
 job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE, local_id TEXT NOT NULL,
 payload TEXT NOT NULL, UNIQUE(job_id,local_id));
CREATE TABLE IF NOT EXISTS extraction_chunks (
 revision_id TEXT NOT NULL REFERENCES revisions(id) ON DELETE CASCADE,
 cache_key TEXT NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY(revision_id,cache_key));
CREATE TABLE IF NOT EXISTS evidence (
 memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
 position INTEGER NOT NULL, quote TEXT NOT NULL, start INTEGER NOT NULL, end INTEGER NOT NULL,
 PRIMARY KEY(memory_id,position), CHECK(start>=0 AND end>start));
CREATE TABLE IF NOT EXISTS embeddings (
 memory_id TEXT PRIMARY KEY REFERENCES memories(id) ON DELETE CASCADE,
 model_key TEXT NOT NULL, dimensions INTEGER NOT NULL, vector BLOB NOT NULL,
 CHECK(length(vector)=dimensions*4));
CREATE INDEX IF NOT EXISTS revision_record ON revisions(record_id);
CREATE INDEX IF NOT EXISTS memory_revision ON memories(revision_id);
CREATE TABLE IF NOT EXISTS facts (
 memory_id TEXT PRIMARY KEY REFERENCES memories(id) ON DELETE CASCADE,
 projection_version INTEGER NOT NULL, actor TEXT, recipient TEXT, object_key TEXT,
 payload TEXT NOT NULL, signature TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS fact_candidates ON facts(object_key,actor);
CREATE TABLE IF NOT EXISTS memory_links (
 id TEXT PRIMARY KEY, left_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
 right_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
 signature TEXT NOT NULL UNIQUE, payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS link_right ON memory_links(right_id);
CREATE TABLE IF NOT EXISTS dismissed_links (
 signature TEXT PRIMARY KEY,
 left_revision TEXT NOT NULL REFERENCES revisions(id) ON DELETE CASCADE,
 right_revision TEXT NOT NULL REFERENCES revisions(id) ON DELETE CASCADE);
PRAGMA user_version=2;
"""


class Store:
    def __init__(self, path, clock=now):
        self.path, self.clock = path, clock
        path.parent.mkdir(parents=True, exist_ok=True)
        initial = sqlite3.connect(path)
        try:
            initial.execute("PRAGMA journal_mode=WAL")
        finally:
            initial.close()
        with self.connect() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1, 2, 3, 4, 5):
                raise RuntimeError("UNSUPPORTED_DATABASE_VERSION")
            from .chat.migrations import DDL as CHAT_EXTENSION_DDL
            from .chat.schema import DDL as CHAT_DDL
            from .chat.schema import upgrade_v4, upgrade_v5
            from .memory.repository import DDL as CAPTURE_DDL

            has_request_input = any(
                row["name"] == "request_input"
                for row in db.execute("PRAGMA table_info(chat_messages)")
            )

            db.executescript(
                "BEGIN IMMEDIATE;\n"
                + DDL
                + CHAT_DDL
                + upgrade_v4(version)
                + upgrade_v5(has_request_input)
                + CAPTURE_DDL
                + CHAT_EXTENSION_DDL
                + "\nCOMMIT;"
            )

    @contextmanager
    def connect(self, write=False):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA secure_delete=ON")
        try:
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def bump(db):
        db.execute("UPDATE metadata SET generation=generation+1 WHERE id=1")

    @staticmethod
    def require(db, record_id, state=None):
        r = db.execute("SELECT * FROM records WHERE id=?", (record_id,)).fetchone()
        if r is None:
            raise AppError("NOT_FOUND", "기록을 찾을 수 없습니다.", 404)
        if state and r["state"] != state:
            raise AppError("INVALID_RECORD_STATE", "현재 상태에서 실행할 수 없습니다.", 409)
        return r

    def queue(self, db, revision_id):
        job_id, ts = identifier(), self.clock()
        db.execute(
            "INSERT INTO jobs(id,revision_id,status,created_at,updated_at) VALUES(?,?,'queued',?,?)",
            (job_id, revision_id, ts, ts),
        )
        return job_id

    def create(self, text, reference_time):
        rid, rev, ts = identifier(), identifier(), self.clock()
        with self.connect(True) as db:
            db.execute(
                "INSERT INTO records VALUES(?,1,'active','queued',?,?,NULL,NULL)", (rid, ts, ts)
            )
            db.execute(
                "INSERT INTO revisions VALUES(?,?,1,?,?,?)", (rev, rid, text, reference_time, ts)
            )
            job = self.queue(db, rev)
            self.bump(db)
        return dict(record_id=rid, version=1, job_id=job, status="queued")

    def invalidate(self, db, rid, keep_chunks=False):
        if not keep_chunks:
            db.execute(
                "DELETE FROM extraction_chunks WHERE revision_id IN (SELECT id FROM revisions WHERE record_id=?)",
                (rid,),
            )
        db.execute(
            "DELETE FROM memories WHERE revision_id IN (SELECT id FROM revisions WHERE record_id=?)",
            (rid,),
        )
        db.execute(
            "UPDATE jobs SET status='cancelled',token=NULL,metadata=NULL WHERE status IN ('queued','running') AND revision_id IN (SELECT id FROM revisions WHERE record_id=?)",
            (rid,),
        )
        self.bump(db)

    def update(self, rid, expected_version, text=None, reference_time=None, revert_version=None):
        with self.connect(True) as db:
            r = self.require(db, rid, "active")
            if r["version"] != expected_version:
                raise AppError(
                    "RECORD_VERSION_CONFLICT", "기록이 변경되었습니다. 다시 확인하세요.", 409
                )
            if revert_version is not None:
                old = db.execute(
                    "SELECT * FROM revisions WHERE record_id=? AND version=?", (rid, revert_version)
                ).fetchone()
                if not old:
                    raise AppError("NOT_FOUND", "수정 이력을 찾을 수 없습니다.", 404)
                text, reference_time = old["text"], old["reference_time"]
            self.invalidate(db, rid)
            version, rev, ts = r["version"] + 1, identifier(), self.clock()
            db.execute(
                "INSERT INTO revisions VALUES(?,?,?,?,?,?)",
                (rev, rid, version, text, reference_time, ts),
            )
            db.execute(
                "UPDATE records SET version=?,status='queued',updated_at=? WHERE id=?",
                (version, ts, rid),
            )
            job = self.queue(db, rev)
        return dict(record_id=rid, version=version, job_id=job, status="queued")

    def get(self, rid):
        with self.connect() as db:
            r = dict(self.require(db, rid))
            rev = dict(
                db.execute(
                    "SELECT * FROM revisions WHERE record_id=? AND version=?", (rid, r["version"])
                ).fetchone()
            )
            r.update(text=rev["text"], reference_time=rev["reference_time"])
            r["memories"] = [
                json.loads(x[0])
                for x in db.execute(
                    "SELECT payload FROM memories WHERE revision_id=?", (rev["id"],)
                )
            ]
            j = db.execute(
                "SELECT id,error_code,metadata FROM jobs WHERE revision_id=? ORDER BY rowid DESC LIMIT 1",
                (rev["id"],),
            ).fetchone()
            r["job_id"], r["error_code"] = (j[0], j[1]) if j else (None, None)
            metadata = json.loads(j[2] or "{}") if j else {}
            r["processing_details"] = metadata
            missing = db.execute(
                "SELECT count(*) FROM memories m LEFT JOIN facts f ON f.memory_id=m.id AND f.projection_version=? WHERE m.revision_id=? AND f.memory_id IS NULL",
                (FACT_VERSION, rev["id"]),
            ).fetchone()[0]
            r["facts_status"] = "pending" if missing else "ready"
            return r

    def list(self, state="active", cursor=None, limit=30):
        with self.connect() as db:
            rows = db.execute(
                "SELECT r.*, substr(v.text,1,140) AS preview FROM records r JOIN revisions v ON v.record_id=r.id AND v.version=r.version WHERE r.state=? AND (? IS NULL OR r.id>?) ORDER BY r.id LIMIT ?",
                (state, cursor, cursor, limit + 1),
            ).fetchall()
            return {
                "items": [dict(x) for x in rows[:limit]],
                "next_cursor": rows[limit - 1]["id"] if len(rows) > limit else None,
            }

    def revisions(self, rid):
        with self.connect() as db:
            self.require(db, rid)
            return [
                dict(x)
                for x in db.execute(
                    "SELECT version,text,reference_time,created_at FROM revisions WHERE record_id=? ORDER BY version DESC",
                    (rid,),
                )
            ]

    def trash(self, rid):
        with self.connect(True) as db:
            r = self.require(db, rid)
            if r["state"] == "trash":
                return
            self.invalidate(db, rid)
            ts = self.clock()
            expiry = (datetime.fromisoformat(ts) + timedelta(days=30)).isoformat()
            db.execute(
                "UPDATE records SET state='trash',status='trashed',deleted_at=?,purge_at=?,updated_at=? WHERE id=?",
                (ts, expiry, ts, rid),
            )

    def restore(self, rid):
        self.expire()
        with self.connect(True) as db:
            r = self.require(db, rid, "trash")
            rev = db.execute(
                "SELECT id FROM revisions WHERE record_id=? AND version=?", (rid, r["version"])
            ).fetchone()[0]
            db.execute(
                "UPDATE records SET state='active',status='queued',deleted_at=NULL,purge_at=NULL,updated_at=? WHERE id=?",
                (self.clock(), rid),
            )
            job = self.queue(db, rev)
            self.bump(db)
        return dict(record_id=rid, version=r["version"], job_id=job, status="queued")

    def purge(self, rid):
        with self.connect(True) as db:
            self.require(db, rid, "trash")
            db.execute("DELETE FROM records WHERE id=?", (rid,))
            self.bump(db)
        self.checkpoint()

    def expire(self):
        from .memory.repository import MemoryRepository

        MemoryRepository(self).cleanup()
        with self.connect(True) as db:
            cutoff = (datetime.fromisoformat(self.clock()) - timedelta(hours=24)).isoformat()
            db.execute(
                "DELETE FROM chat_searches WHERE created_at<=? AND NOT EXISTS "
                "(SELECT 1 FROM chat_sessions WHERE search_id=chat_searches.id)",
                (cutoff,),
            )
            count = db.execute(
                "DELETE FROM records WHERE state='trash' AND purge_at<=?", (self.clock(),)
            ).rowcount
            if count:
                self.bump(db)
        if count:
            self.checkpoint()
        return count

    def checkpoint(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            db.close()

    def retry(self, rid, expected_version=None):
        with self.connect(True) as db:
            r = self.require(db, rid, "active")
            if expected_version is not None and r["version"] != expected_version:
                raise AppError("RECORD_VERSION_CONFLICT", "최신 기억을 다시 확인해 주세요.", 409)
            if r["status"] == "archived":
                raise AppError(
                    "INVALID_RECORD_STATE", "보관된 기억을 먼저 다시 활성화해 주세요.", 409
                )
            rev = db.execute(
                "SELECT id FROM revisions WHERE record_id=? AND version=?", (rid, r["version"])
            ).fetchone()[0]
            active = db.execute(
                "SELECT id FROM jobs WHERE revision_id=? AND status IN ('queued','running')", (rev,)
            ).fetchone()
            if active:
                job = active[0]
            else:
                self.invalidate(db, rid, keep_chunks=True)
                job = self.queue(db, rev)
                db.execute("UPDATE records SET status='queued' WHERE id=?", (rid,))
        return dict(record_id=rid, version=r["version"], job_id=job, status="queued")

    def failed_jobs(self):
        with self.connect() as db:
            rows = db.execute(
                "SELECT j.id AS job_id,v.record_id,v.version,v.text,j.error_code,j.updated_at,j.metadata "
                "FROM records r JOIN revisions v ON v.record_id=r.id AND v.version=r.version "
                "JOIN jobs j ON j.id=(SELECT k.id FROM jobs k WHERE k.revision_id=v.id "
                "ORDER BY k.rowid DESC LIMIT 1) "
                "WHERE r.state='active' AND r.status='failed' AND j.status='failed' "
                "ORDER BY j.updated_at DESC,j.id DESC"
            ).fetchall()
            items = []
            for row in rows:
                item = dict(row)
                item["diagnostic"] = json.loads(item.pop("metadata") or "null")
                item["history"] = [
                    dict(j, diagnostic=json.loads(j["metadata"] or "null"))
                    for j in db.execute(
                        "SELECT j.status,j.error_code,j.updated_at,j.metadata FROM jobs j JOIN revisions v ON v.id=j.revision_id WHERE v.record_id=? AND v.version=? ORDER BY j.rowid DESC",
                        (item["record_id"], item["version"]),
                    )
                ]
                for entry in item["history"]:
                    entry.pop("metadata", None)
                items.append(item)
            return items

    def retry_failed(self, job_ids):
        """Only retry the failed versions shown to the caller, atomically and once."""
        queued, skipped = [], []
        with self.connect(True) as db:
            for jid in dict.fromkeys(job_ids):
                row = db.execute(
                    "SELECT v.id AS revision_id,r.id AS record_id FROM jobs j "
                    "JOIN revisions v ON v.id=j.revision_id JOIN records r ON r.id=v.record_id "
                    "WHERE j.id=? AND j.status='failed' AND r.state='active' "
                    "AND r.status='failed' AND r.version=v.version "
                    "AND j.id=(SELECT k.id FROM jobs k WHERE k.revision_id=v.id "
                    "ORDER BY k.rowid DESC LIMIT 1)",
                    (jid,),
                ).fetchone()
                if row is None:
                    skipped.append(jid)
                    continue
                self.invalidate(db, row["record_id"], keep_chunks=True)
                self.queue(db, row["revision_id"])
                db.execute("UPDATE records SET status='queued' WHERE id=?", (row["record_id"],))
                queued.append(row["record_id"])
        return {"queued": len(queued), "skipped": len(skipped)}

    def recover(self):
        with self.connect(True) as db:
            db.execute("UPDATE jobs SET status='queued',token=NULL WHERE status='running'")
            db.execute("UPDATE records SET status='queued' WHERE status='processing'")

    def claim(self):
        with self.connect(True) as db:
            row = db.execute(
                "SELECT j.*,v.text,v.reference_time,v.record_id,v.version FROM jobs j JOIN revisions v ON v.id=j.revision_id JOIN records r ON r.id=v.record_id WHERE j.status='queued' AND r.state='active' AND r.version=v.version ORDER BY j.created_at,j.id LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            job, token = dict(row), identifier()
            db.execute(
                "UPDATE jobs SET status='running',token=?,attempts=attempts+1,updated_at=? WHERE id=?",
                (token, self.clock(), job["id"]),
            )
            db.execute("UPDATE records SET status='processing' WHERE id=?", (job["record_id"],))
            job["token"] = token
            return job

    def current_job(self, db, job):
        return (
            db.execute(
                "SELECT j.id FROM jobs j JOIN revisions v ON v.id=j.revision_id JOIN records r ON r.id=v.record_id WHERE j.id=? AND j.token=? AND j.status='running' AND r.state='active' AND r.version=v.version",
                (job["id"], job["token"]),
            ).fetchone()
            is not None
        )

    def publish(self, job, memories, vectors, model_key, metadata):
        from .models import normalized_vectors

        if len(memories) != len(vectors):
            raise ValueError("VECTOR_COUNT_MISMATCH")
        if memories:
            vectors = normalized_vectors(vectors, len(memories), len(vectors[0]))
        with self.connect(True) as db:
            if not self.current_job(db, job):
                return False
            for index, (m, vector) in enumerate(zip(memories, vectors)):
                mid = identifier()
                db.execute(
                    "INSERT INTO memories VALUES(?,?,?,?,?)",
                    (
                        mid,
                        job["revision_id"],
                        job["id"],
                        m["local_id"],
                        json.dumps(m, ensure_ascii=False),
                    ),
                )
                for i, e in enumerate(m["evidence"]):
                    start = job["text"].find(e["quote"])
                    provenance = metadata.get("provenance", [])
                    if index < len(provenance):
                        span = provenance[index]["evidence"][i]
                        start = span["start"]
                        if job["text"][start : span["end"]] != e["quote"]:
                            raise ValueError("INVALID_EVIDENCE")
                    if start < 0:
                        raise ValueError("INVALID_EVIDENCE")
                    db.execute(
                        "INSERT INTO evidence VALUES(?,?,?,?,?)",
                        (mid, i, e["quote"], start, start + len(e["quote"])),
                    )
                db.execute(
                    "INSERT INTO embeddings VALUES(?,?,?,?)",
                    (mid, model_key, len(vector), vector.astype("<f4").tobytes()),
                )
                self.project_memory(
                    db,
                    mid,
                    m,
                    job["text"],
                    job["reference_time"],
                    job["created_at"],
                    job["revision_id"],
                )
            db.execute(
                "UPDATE jobs SET status='succeeded',token=NULL,error_code=NULL,metadata=?,updated_at=? WHERE id=?",
                (json.dumps(metadata), self.clock(), job["id"]),
            )
            db.execute(
                "UPDATE records SET status=? WHERE id=?",
                ("ready" if memories else "ready_empty", job["record_id"]),
            )
            self.bump(db)
        return True

    def chunk_get(self, revision_id, key):
        with self.connect() as db:
            row = db.execute(
                "SELECT payload FROM extraction_chunks WHERE revision_id=? AND cache_key=?",
                (revision_id, key),
            ).fetchone()
            return json.loads(row[0]) if row else None

    def chunk_save(self, job, key, payload):
        with self.connect(True) as db:
            if not self.current_job(db, job):
                raise AppError("SOURCE_CHANGED", "원문이 변경되었습니다.", 409)
            db.execute(
                "INSERT OR REPLACE INTO extraction_chunks VALUES(?,?,?)",
                (job["revision_id"], key, json.dumps(payload, ensure_ascii=False)),
            )

    def fail(self, job, code, diagnostic=None):
        with self.connect(True) as db:
            if self.current_job(db, job):
                db.execute(
                    "UPDATE jobs SET status='failed',error_code=?,metadata=?,token=NULL,updated_at=? WHERE id=?",
                    (code, json.dumps(diagnostic) if diagnostic else None, self.clock(), job["id"]),
                )
                db.execute("UPDATE records SET status='failed' WHERE id=?", (job["record_id"],))

    def job(self, jid):
        with self.connect() as db:
            r = db.execute(
                "SELECT id,status,attempts,error_code,created_at,updated_at FROM jobs WHERE id=?",
                (jid,),
            ).fetchone()
            if not r:
                raise AppError("NOT_FOUND", "작업을 찾을 수 없습니다.", 404)
            return dict(r)

    def snapshot_for_owner(self, model_key, owner_id):
        return self.snapshot(model_key, owner_id=owner_id)

    def snapshot(self, model_key, *, owner_id=None):
        observation = _start_observation()
        with self.connect() as db:
            generation = db.execute("SELECT generation FROM metadata WHERE id=1").fetchone()[0]
            rows = db.execute(
                # Materialize exclusions once rather than scanning captures twice
                # for every memory. Automatic join indexes require no schema change.
                "WITH archived AS MATERIALIZED ("
                "SELECT record_id,json_extract(payload,'$.record_version') AS version "
                "FROM captured_memories WHERE json_extract(payload,'$.lifecycle_status')='archived'), "
                "other_owners AS MATERIALIZED (SELECT DISTINCT record_id FROM captured_memories "
                "WHERE ? IS NOT NULL AND owner_id<>?) "
                "SELECT m.id,m.payload,e.vector,e.dimensions,v.record_id,v.version,v.text,"
                "v.reference_time,v.created_at,f.payload AS fact_payload "
                "FROM memories m JOIN embeddings e ON e.memory_id=m.id "
                "JOIN revisions v ON v.id=m.revision_id JOIN records r ON r.id=v.record_id "
                "LEFT JOIN facts f ON f.memory_id=m.id AND f.projection_version=? "
                "LEFT JOIN archived a ON a.record_id=r.id AND a.version=r.version "
                "LEFT JOIN other_owners o ON o.record_id=r.id "
                "WHERE r.state='active' AND r.status='ready' AND r.version=v.version "
                "AND a.record_id IS NULL AND o.record_id IS NULL "
                "AND e.model_key=? ORDER BY v.id,m.local_id",
                (owner_id, owner_id, FACT_VERSION, model_key),
            ).fetchall()
            # Keep the same read transaction and evidence ordering, but avoid one
            # SQL round trip per memory. Small batches also support SQLite builds
            # with the older 999-variable limit.
            evidence = {}
            for offset in range(0, len(rows), 500):
                ids = [row["id"] for row in rows[offset:offset + 500]]
                placeholders = ",".join("?" for _ in ids)
                for item in db.execute(
                    "SELECT memory_id,quote,start,end FROM evidence WHERE memory_id IN ("
                    + placeholders + ") ORDER BY memory_id,position", ids
                ):
                    evidence.setdefault(item["memory_id"], []).append(
                        {key: item[key] for key in ("quote", "start", "end")}
                    )
            result = []
            for row in rows:
                item = dict(row)
                item["memory"] = json.loads(item.pop("payload"))
                fact = item.pop("fact_payload")
                item["fact"] = json.loads(fact) if fact else None
                item["evidence"] = evidence.get(row["id"], [])
                result.append(item)
        _observe_read(Stage.SNAPSHOT, observation, result)
        return generation, result

    def project_memory(self, db, mid, memory, source, reference_time, recorded_at, revision_id):
        evidence = [
            dict(row)
            for row in db.execute(
                "SELECT quote,start,end FROM evidence WHERE memory_id=? ORDER BY position", (mid,)
            )
        ]
        fact = project(memory, source, reference_time, recorded_at, evidence=evidence)
        source_record = db.execute(
            "SELECT record_id FROM revisions WHERE id=?", (revision_id,)
        ).fetchone()[0]
        signature = fingerprint(
            [
                source_record,
                sorted(e["quote"] for e in memory["evidence"]),
                fact["actor"],
                fact["recipient"],
                fact["relation"],
                fact["object_key"],
            ]
        )
        db.execute("DELETE FROM memory_links WHERE left_id=? OR right_id=?", (mid, mid))
        db.execute(
            "INSERT OR REPLACE INTO facts VALUES(?,?,?,?,?,?,?)",
            (
                mid,
                FACT_VERSION,
                fact["actor"],
                fact["recipient"],
                fact["object_key"],
                json.dumps(fact, ensure_ascii=False),
                signature,
            ),
        )
        candidates = db.execute(
            "SELECT f.*,m.revision_id FROM facts f JOIN memories m ON m.id=f.memory_id WHERE f.object_key=? AND f.memory_id<>? AND (f.actor=? OR f.recipient=? OR f.actor=?) AND f.projection_version=? ORDER BY json_extract(f.payload,'$.event_time.start') DESC,f.signature LIMIT 100",
            (
                fact["object_key"],
                mid,
                fact["actor"],
                fact["actor"],
                fact["recipient"],
                FACT_VERSION,
            ),
        ).fetchall()
        for candidate in candidates:
            linked = connection(fact, json.loads(candidate["payload"]))
            if not linked:
                continue
            sig = fingerprint(sorted([signature, candidate["signature"]]) + [linked["kind"]])
            if db.execute("SELECT 1 FROM dismissed_links WHERE signature=?", (sig,)).fetchone():
                continue
            db.execute(
                "INSERT OR IGNORE INTO memory_links VALUES(?,?,?,?,?)",
                (sig, mid, candidate["memory_id"], sig, json.dumps(linked, ensure_ascii=False)),
            )

    def rebuild_facts(self, limit=50):
        """Resumable derived-only migration; no model calls or changes to source history."""
        with self.connect(True) as db:
            rows = db.execute(
                "SELECT m.id,m.payload,m.revision_id,v.text,v.reference_time,v.created_at FROM memories m JOIN revisions v ON v.id=m.revision_id LEFT JOIN facts f ON f.memory_id=m.id WHERE f.memory_id IS NULL OR f.projection_version<>? ORDER BY m.id LIMIT ?",
                (FACT_VERSION, limit),
            ).fetchall()
            if rows:
                backup = self.path.with_name(f"{self.path.name}.before-facts-v{FACT_VERSION}.bak")
                if not backup.exists():
                    temporary = backup.with_name(backup.name + "." + identifier() + ".tmp")
                    try:
                        # Read the last committed WAL snapshot through another connection;
                        # never back up the active write transaction itself.
                        with (
                            closing(sqlite3.connect(self.path)) as source,
                            closing(sqlite3.connect(temporary)) as target,
                        ):
                            source.backup(target)
                        temporary.rename(backup)
                    finally:
                        temporary.unlink(missing_ok=True)
            for row in rows:
                self.project_memory(
                    db,
                    row["id"],
                    json.loads(row["payload"]),
                    row["text"],
                    row["reference_time"],
                    row["created_at"],
                    row["revision_id"],
                )
            if rows:
                self.bump(db)
            return len(rows)

    def links(self, record_id=None, memory_ids=None):
        observation = _start_observation()
        selected_clause = ""
        selected_args = []
        observed_ids = None
        if memory_ids is not None:
            if not memory_ids:
                _observe_read(
                    Stage.RELATION_LOOKUP,
                    observation,
                    [],
                    selected_ids=[],
                    record_id=record_id,
                    executed=False,
                )
                return []
            selected_args = sorted(memory_ids)
            observed_ids = selected_args
            marks = ",".join("?" for _ in selected_args)
            selected_clause = f" AND l.left_id IN ({marks}) AND l.right_id IN ({marks})"
            selected_args = selected_args + selected_args
        with self.connect() as db:
            if record_id:
                self.require(db, record_id, "active")
            rows = db.execute(
                "SELECT l.*,a.revision_id AS left_revision,b.revision_id AS right_revision,va.record_id AS left_record,vb.record_id AS right_record,a.payload AS left_memory,b.payload AS right_memory FROM memory_links l JOIN memories a ON a.id=l.left_id JOIN memories b ON b.id=l.right_id JOIN revisions va ON va.id=a.revision_id JOIN revisions vb ON vb.id=b.revision_id JOIN facts fa ON fa.memory_id=a.id JOIN facts fb ON fb.memory_id=b.id WHERE fa.projection_version=? AND fb.projection_version=? AND (? IS NULL OR va.record_id=? OR vb.record_id=?)"
                + selected_clause
                + " ORDER BY l.id",
                (FACT_VERSION, FACT_VERSION, record_id, record_id, record_id, *selected_args),
            ).fetchall()
            result = [
                {
                    "id": row["id"],
                    **json.loads(row["payload"]),
                    "citations": [row["left_id"], row["right_id"]],
                    "records": [row["left_record"], row["right_record"]],
                    "evidence": [json.loads(row["left_memory"]), json.loads(row["right_memory"])],
                }
                for row in rows
            ]
        _observe_read(
            Stage.RELATION_LOOKUP,
            observation,
            result,
            selected_ids=observed_ids,
            record_id=record_id,
        )
        return result

    def dismiss_link(self, link_id):
        with self.connect(True) as db:
            row = db.execute(
                "SELECT l.signature,a.revision_id AS a,b.revision_id AS b FROM memory_links l JOIN memories a ON a.id=l.left_id JOIN memories b ON b.id=l.right_id WHERE l.id=?",
                (link_id,),
            ).fetchone()
            if not row:
                raise AppError("NOT_FOUND", "연결을 찾을 수 없습니다.", 404)
            db.execute("INSERT OR IGNORE INTO dismissed_links VALUES(?,?,?)", tuple(row))
            db.execute("DELETE FROM memory_links WHERE id=?", (link_id,))
            self.bump(db)

    def facts_pending(self):
        with self.connect() as db:
            return db.execute(
                "SELECT count(*) FROM memories m LEFT JOIN facts f ON f.memory_id=m.id AND f.projection_version=? WHERE f.memory_id IS NULL",
                (FACT_VERSION,),
            ).fetchone()[0]

    def assert_generation(self, generation):
        with self.connect() as db:
            if db.execute("SELECT generation FROM metadata WHERE id=1").fetchone()[0] != generation:
                raise AppError(
                    "SOURCE_CHANGED", "처리 중 기록이 변경되었습니다. 다시 질문하세요.", 409, True
                )

    def processing_progress(self):
        """Current active revisions only; never expose job tokens or model payloads."""
        with self.connect() as db:
            counts = dict(
                db.execute(
                    "SELECT status,count(*) FROM records WHERE state='active' GROUP BY status"
                ).fetchall()
            )
            rows = db.execute(
                "SELECT j.id,j.status,j.updated_at,j.error_code,v.record_id,"
                "substr(v.text,1,60) AS preview FROM jobs j "
                "JOIN revisions v ON v.id=j.revision_id "
                "JOIN records r ON r.id=v.record_id "
                "WHERE r.state='active' AND r.version=v.version "
                "AND j.status IN ('running','succeeded','failed') "
                "ORDER BY (j.status='running') DESC,j.updated_at DESC,j.id DESC LIMIT 8"
            ).fetchall()
            return {
                "remaining": counts.get("queued", 0) + counts.get("processing", 0),
                "queued": counts.get("queued", 0),
                "processing": counts.get("processing", 0),
                "completed": counts.get("ready", 0) + counts.get("ready_empty", 0),
                "failed": counts.get("failed", 0),
                "total": sum(counts.values()),
                "recent": [dict(row) for row in rows],
            }

    def stats(self):
        with self.connect() as db:
            return {
                r[0]: r[1]
                for r in db.execute("SELECT status,count(*) FROM records GROUP BY status")
            }

    def reindex_changed_model(self, model_key):
        """No mixed-index reads: changed models rebuild from current source revisions."""
        with self.connect(True) as db:
            rows = db.execute(
                "SELECT DISTINCT r.id,r.version FROM records r JOIN revisions v ON v.record_id=r.id AND v.version=r.version JOIN memories m ON m.revision_id=v.id JOIN embeddings e ON e.memory_id=m.id WHERE r.state='active' AND e.model_key<>?",
                (model_key,),
            ).fetchall()
            for row in rows:
                self.invalidate(db, row["id"])
                rev = db.execute(
                    "SELECT id FROM revisions WHERE record_id=? AND version=?",
                    (row["id"], row["version"]),
                ).fetchone()[0]
                self.queue(db, rev)
                db.execute("UPDATE records SET status='queued' WHERE id=?", (row["id"],))
            return len(rows)
