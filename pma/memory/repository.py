"""Approval + provenance + existing durable jobs in a single SQLite transaction.

The host is a single local account. owner_id is supplied by trusted host code,
never by API input. Separate owner values remain isolated in repository callers.
"""

import json
from datetime import datetime, timedelta

from ..chat.memory_capture import classify
from ..errors import AppError
from ..store import identifier
from .deduplication import compare
from .provenance import corpus_digest, digest, review_input, source_text
from .schemas import MemoryCandidate, MemoryRecord

DDL = """
CREATE TABLE IF NOT EXISTS capture_candidates (
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS captured_memories (
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL,
 record_id TEXT NOT NULL REFERENCES records(id) ON DELETE CASCADE,
 payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS captured_owner ON captured_memories(owner_id);
CREATE TABLE IF NOT EXISTS capture_requests (
 owner_id TEXT NOT NULL, request_id TEXT NOT NULL, candidate_id TEXT NOT NULL,
 memory_id TEXT NOT NULL REFERENCES captured_memories(id) ON DELETE CASCADE,
 request_input TEXT NOT NULL,
 PRIMARY KEY(owner_id,request_id));
CREATE TABLE IF NOT EXISTS capture_reviews (
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, candidate_id TEXT NOT NULL
 REFERENCES capture_candidates(id) ON DELETE CASCADE, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS capture_policies (
 owner_id TEXT PRIMARY KEY, policy TEXT NOT NULL CHECK(policy IN ('MANUAL','SUGGEST')));
CREATE TABLE IF NOT EXISTS capture_session_owners (
 session_id TEXT PRIMARY KEY REFERENCES chat_sessions(id) ON DELETE CASCADE, owner_id TEXT NOT NULL);
INSERT OR IGNORE INTO capture_session_owners SELECT id,'local-account' FROM chat_sessions;
"""


def encode(value):
    return json.dumps(value, ensure_ascii=False)


def fail(code, status=409):
    messages = {
        "APPROVAL_REQUIRED": "내용을 확인하고 저장을 승인해 주세요.",
        "EXACT_DUPLICATE": "같은 기억이 이미 있습니다. 기존 기억을 확인하거나 저장을 취소해 주세요.",
        "COMPARISON_REQUIRED": "관련 기록을 비교한 후 기존 기억 유지·별도 추가 또는 정정을 선택해 주세요.",
        "CANDIDATE_EXPIRED": "후보의 유효기간이 지났습니다. 원문에서 다시 선택해 주세요.",
        "SOURCE_CHANGED": "원본 대화가 바뀌었거나 삭제되었습니다. 원문을 다시 확인해 주세요.",
        "AI_SOURCE_TYPE": "AI 답변은 제안·가설·대화 요약으로 저장할 수 있습니다.",
        "RECORD_VERSION_CONFLICT": "기억이 변경되었습니다. 최신 내용을 열어 다시 확인해 주세요.",
        "CORRECTION_APPROVAL_REQUIRED": "기존 기억의 새 버전으로 정정할지 확인해 주세요.",
        "REVIEW_STALE": "비교한 기록이 변경되었습니다. 다시 비교한 뒤 승인해 주세요.",
        "REVIEW_CHANGED": "내용 또는 유형이 바뀌었습니다. 다시 비교한 뒤 승인해 주세요.",
        "REVIEW_INCOMPLETE": "의미 비교를 완료하지 못했습니다. 모델 연결을 확인하고 다시 비교해 주세요.",
        "SEMANTIC_DUPLICATE": "같은 의미의 기억이 있습니다. 기존 기억을 확인해 주세요.",
    }
    raise AppError(code, messages.get(code, "기억과 출처, 버전을 다시 확인해 주세요."), status)


class MemoryRepository:
    def __init__(self, store):
        self.store = store

    @staticmethod
    def require(db, table, owner, key):
        row = db.execute(
            f"SELECT * FROM {table} WHERE id=? AND owner_id=?", (key, owner)
        ).fetchone()
        if not row:
            if (
                table == "captured_memories"
                and owner == "local-account"
                and key.startswith("record:")
            ):
                rid, _, requested_version = key.removeprefix("record:").partition("@")
                if db.execute(
                    "SELECT 1 FROM captured_memories WHERE record_id=? AND owner_id<>?",
                    (rid, owner),
                ).fetchone():
                    fail("NOT_FOUND", 404)
                old = db.execute(
                    "SELECT r.*,v.text FROM records r JOIN revisions v "
                    "ON v.record_id=r.id AND v.version=r.version WHERE r.id=?",
                    (rid,),
                ).fetchone()
                if old and (not requested_version or requested_version == str(old["version"])):
                    captured = db.execute(
                        "SELECT payload FROM captured_memories WHERE record_id=? AND owner_id=? "
                        "AND json_extract(payload,'$.record_version')=? ORDER BY rowid DESC LIMIT 1",
                        (rid, owner, old["version"]),
                    ).fetchone()
                    if captured:
                        return json.loads(captured[0])
                    return dict(
                        memory_id=key,
                        record_id=rid,
                        owner_id=owner,
                        content=old["text"],
                        record_version=old["version"],
                        lifecycle_status="active" if old["state"] == "active" else "deleted",
                        memory_type="user_statement",
                        source_type="imported_document",
                        epistemic_status="unverified",
                        source_record_ids=[rid],
                        provenance={"source_record_ids": [rid]},
                        created_at=old["created_at"],
                        updated_at=old["updated_at"],
                    )
            fail("NOT_FOUND", 404)
        return json.loads(row["payload"])

    def sources(self, db, candidate):
        sid = candidate["session_id"]
        if not sid:
            if candidate["message_ids"]:
                fail("INVALID_SOURCE")
            return
        ownership = db.execute(
            "SELECT owner_id FROM capture_session_owners WHERE session_id=?", (sid,)
        ).fetchone()
        if (ownership[0] if ownership else "local-account") != candidate["owner_id"]:
            fail("SOURCE_OWNER_MISMATCH")
        if not db.execute("SELECT 1 FROM chat_sessions WHERE id=?", (sid,)).fetchone():
            fail("SOURCE_CHANGED")
        for mid in candidate["message_ids"]:
            row = db.execute(
                "SELECT * FROM chat_messages WHERE id=? AND session_id=?", (mid, sid)
            ).fetchone()
            if not row or row["state"] != "completed" or row["error_code"]:
                fail("SOURCE_CHANGED")
            for snapshot in candidate.get("source_snapshots", []):
                if (
                    snapshot["message_id"] == mid
                    and digest(source_text(row, snapshot["source_type"])) != snapshot["fingerprint"]
                ):
                    fail("SOURCE_CHANGED")

    def propose(
        self,
        owner,
        *,
        content,
        source_type="user_message",
        session_id=None,
        message_ids=None,
        mode="general",
        memory_type=None,
        source_record_ids=None,
        supersedes=None,
        expected_version=None,
        source_snapshots=None,
        reference_time=None,
        project_scope=None,
        event_time=None,
        capture_request_id=None,
        epistemic_status=None,
    ):
        ts = self.store.clock()
        kind = classify(content, source_type)
        if source_type == "assistant_message" and memory_type not in (
            None,
            "proposal",
            "hypothesis",
            "conversation_summary",
        ):
            fail("AI_SOURCE_TYPE")
        candidate = MemoryCandidate(
            candidate_id=identifier(),
            owner_id=owner,
            content=content,
            memory_type=memory_type or kind,
            epistemic_status=epistemic_status
            or (
                "ai_proposed"
                if source_type == "assistant_message"
                else "unverified"
                if source_type in ("conversation_summary", "imported_document")
                else "user_reported"
            ),
            source_type=source_type,
            conversation_mode=mode,
            session_id=session_id,
            message_ids=message_ids or [],
            source_record_ids=source_record_ids or [],
            created_at=ts,
            expires_at=(datetime.fromisoformat(ts) + timedelta(hours=24)).isoformat(),
            supersedes_memory_id=supersedes,
            expected_version=expected_version,
            source_snapshots=source_snapshots or [],
            reference_time=reference_time,
            project_scope=project_scope,
            event_time=event_time,
            capture_request_id=capture_request_id,
        ).model_dump()
        with self.store.connect(True) as db:
            self.sources(db, candidate)
            if capture_request_id:
                prior = db.execute(
                    "SELECT payload FROM capture_candidates WHERE owner_id=? "
                    "AND json_extract(payload,'$.capture_request_id')=?",
                    (owner, capture_request_id),
                ).fetchone()
                if prior:
                    previous = json.loads(prior[0])
                    if previous["content"] != content or previous["session_id"] != session_id:
                        fail("REQUEST_CONFLICT")
                    return dict(previous, comparisons=self.comparisons(db, owner, content))
            if supersedes:
                previous = self.detail(db, owner, supersedes)
                if previous["lifecycle_status"] != "active":
                    fail("INVALID_RECORD_STATE")
                if previous["record_version"] != expected_version:
                    fail("RECORD_VERSION_CONFLICT")
                candidate["source_record_ids"] = [previous["record_id"]]
                candidate["supersedes_memory_id"] = previous["memory_id"]
            db.execute(
                "INSERT INTO capture_candidates VALUES(?,?,?)",
                (candidate["candidate_id"], owner, encode(candidate)),
            )
            candidate["comparisons"] = self.comparisons(db, owner, content)
        return candidate

    def corpus(self, db, owner):
        rows = [
            json.loads(row[0])
            for row in db.execute(
                "SELECT c.payload FROM captured_memories c JOIN records r ON r.id=c.record_id "
                "WHERE c.owner_id=? AND r.state='active' "
                "AND r.version=json_extract(c.payload,'$.record_version')",
                (owner,),
            )
        ]
        rows = [r for r in rows if r.get("lifecycle_status") == "active"]
        current = {r["record_id"] for r in rows}
        for row in db.execute(
            "SELECT r.id,r.version FROM records r WHERE r.state='active' AND r.status<>'archived' "
            "AND NOT EXISTS(SELECT 1 FROM captured_memories c WHERE c.record_id=r.id AND c.owner_id<>?) "
            "AND (?='local-account' OR EXISTS(SELECT 1 FROM captured_memories c WHERE c.record_id=r.id AND c.owner_id=?))",
            (owner, owner, owner),
        ):
            if row["id"] not in current:
                legacy = self.require(
                    db, "captured_memories", owner, f"record:{row['id']}@{row['version']}"
                )
                if legacy["lifecycle_status"] == "active":
                    rows.append(legacy)
        return rows

    def comparisons(self, db, owner, content):
        return compare(content, self.corpus(db, owner))

    def commit(
        self,
        owner,
        cid,
        *,
        approved,
        request_id,
        resolution="add",
        candidate_version=1,
        content=None,
        memory_type=None,
        review_id=None,
        link_memory_ids=None,
        require_review=False,
        project_scope=None,
        event_time=None,
    ):
        if approved is not True:
            fail("APPROVAL_REQUIRED")
        request_input = encode(
            dict(
                candidate_version=candidate_version,
                content=content,
                memory_type=memory_type,
                resolution=resolution,
                project_scope=project_scope,
                event_time=event_time,
                review_id=review_id,
                link_memory_ids=link_memory_ids or [],
            )
        )
        with self.store.connect(True) as db:
            cached = db.execute(
                "SELECT * FROM capture_requests WHERE owner_id=? AND request_id=?",
                (owner, request_id),
            ).fetchone()
            if cached:
                if cached["candidate_id"] != cid or cached["request_input"] != request_input:
                    fail("REQUEST_CONFLICT")
                return self.detail(db, owner, cached["memory_id"])
            candidate = self.require(db, "capture_candidates", owner, cid)
            if candidate["lifecycle_status"] != "pending":
                fail("INVALID_CANDIDATE_STATE")
            if candidate["expires_at"] <= self.store.clock():
                fail("CANDIDATE_EXPIRED")
            if candidate["candidate_version"] != candidate_version:
                fail("CANDIDATE_VERSION_CONFLICT")
            self.sources(db, candidate)
            if content is not None:
                candidate["content"] = content
            if memory_type is not None:
                candidate["memory_type"] = memory_type
            if project_scope is not None:
                candidate["project_scope"] = project_scope or None
            if event_time is not None:
                candidate["event_time"] = event_time or None
            candidate = MemoryCandidate.model_validate(candidate).model_dump()
            if candidate["epistemic_status"] == "ai_proposed" and candidate["memory_type"] not in (
                "proposal",
                "hypothesis",
                "conversation_summary",
            ):
                fail("AI_SOURCE_TYPE")
            comparisons = self.comparisons(db, owner, candidate["content"])
            if require_review and not review_id and self.corpus(db, owner):
                fail("REVIEW_REQUIRED")
            if review_id:
                review = self.require(db, "capture_reviews", owner, review_id)
                if review["candidate_id"] != cid or review["input_hash"] != review_input(candidate):
                    fail("REVIEW_CHANGED")
                if review["corpus_hash"] != corpus_digest(self.corpus(db, owner)):
                    fail("REVIEW_STALE")
                if review["status"] != "complete":
                    fail("REVIEW_INCOMPLETE")
                comparisons = review["comparisons"]
            if any(c["relation"] == "semantic_duplicate" for c in comparisons):
                fail("SEMANTIC_DUPLICATE")
            if any(c["relation"] == "exact_duplicate" for c in comparisons):
                fail("EXACT_DUPLICATE")
            if any(c["relation"] != "unrelated" for c in comparisons) and resolution not in (
                "add_confirmed",
                "correct",
            ):
                fail("COMPARISON_REQUIRED")
            old_id = candidate["supersedes_memory_id"]
            if resolution == "correct" and not old_id:
                fail("CORRECTION_TARGET_REQUIRED")
            related = []
            for linked in dict.fromkeys(link_memory_ids or []):
                target = self.detail(db, owner, linked)
                relation = next((c for c in comparisons if c["memory_id"] == linked), None)
                if (
                    target["lifecycle_status"] != "active"
                    or not relation
                    or relation["relation"]
                    not in ("supporting", "complementary", "temporal_update")
                ):
                    fail("INVALID_MEMORY_LINK")
                related.append(
                    dict(
                        memory_id=linked,
                        record_version=target["record_version"],
                        relation=relation["relation"],
                    )
                )
            version, rid = 1, identifier()
            ts, rev, mid = self.store.clock(), identifier(), identifier()
            if old_id:
                if resolution != "correct":
                    fail("CORRECTION_APPROVAL_REQUIRED")
                old = self.detail(db, owner, old_id)
                if old["lifecycle_status"] != "active":
                    fail("RECORD_VERSION_CONFLICT")
                old.pop("index_status", None)
                rid = old["record_id"]
                record = self.store.require(db, rid, "active")
                if record["version"] != candidate["expected_version"]:
                    fail("RECORD_VERSION_CONFLICT")
                version = record["version"] + 1
                self.store.invalidate(db, rid)
                old["lifecycle_status"] = "superseded"
                db.execute(
                    "INSERT INTO captured_memories VALUES(?,?,?,?) "
                    "ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                    (old_id, owner, rid, encode(old)),
                )
                db.execute(
                    "UPDATE records SET version=?,status='queued',updated_at=? WHERE id=?",
                    (version, ts, rid),
                )
            else:
                db.execute(
                    "INSERT INTO records VALUES(?,1,'active','queued',?,?,NULL,NULL)", (rid, ts, ts)
                )
            # Approval is explicitly distinct from factual verification in the searchable source.
            text = (
                f"[대화 기억 / 유형: {candidate['memory_type']} / 출처: {candidate['source_type']} / "
                f"사실 상태: {candidate['epistemic_status']} / 사용자 저장 승인, 객관적 검증 아님]\n"
                + candidate["content"]
            )
            db.execute(
                "INSERT INTO revisions VALUES(?,?,?,?,?,?)",
                (rev, rid, version, text, candidate.get("reference_time"), ts),
            )
            job = self.store.queue(db, rev)
            saved = dict(
                candidate,
                memory_id=mid,
                record_id=rid,
                record_version=version,
                lifecycle_status="active",
                created_at=ts,
                updated_at=ts,
                valid_at=None,
                provenance=dict(
                    source_type=candidate["source_type"],
                    session_id=candidate["session_id"],
                    message_ids=candidate["message_ids"],
                    source_record_ids=candidate["source_record_ids"],
                    original_content=self.require(db, "capture_candidates", owner, cid)["content"],
                    source_snapshots=candidate.get("source_snapshots", []),
                    reviewed_relations=comparisons,
                ),
                job_id=job,
                related_memories=related,
            )
            db.execute(
                "INSERT INTO captured_memories VALUES(?,?,?,?)",
                (mid, owner, rid, encode(MemoryRecord.model_validate(saved).model_dump())),
            )
            candidate["lifecycle_status"] = "active"
            db.execute(
                "UPDATE capture_candidates SET payload=? WHERE id=?", (encode(candidate), cid)
            )
            db.execute(
                "INSERT INTO capture_requests VALUES(?,?,?,?,?)",
                (owner, request_id, cid, mid, request_input),
            )
            self.store.bump(db)
            return self.detail(db, owner, mid)

    def detail(self, db, owner, mid):
        item = self.require(db, "captured_memories", owner, mid)
        row = self.store.require(db, item["record_id"])
        if row["state"] == "trash":
            item["lifecycle_status"] = "deleted"
        elif item["record_version"] != row["version"]:
            item["lifecycle_status"] = "superseded"
        elif row["status"] == "archived":
            item["lifecycle_status"] = "archived"
        item["index_status"] = {
            "queued": "committed",
            "processing": "indexing",
            "ready": "searchable",
            "ready_empty": "index_failed",
            "failed": "index_failed",
        }.get(row["status"], "indexing")
        if item["lifecycle_status"] != "active":
            item["index_status"] = "inactive"
        return item

    def get(self, owner, mid):
        with self.store.connect() as db:
            return self.detail(db, owner, mid)

    def list(self, owner, include_inactive=False):
        with self.store.connect() as db:
            items = [
                self.detail(db, owner, row[0])
                for row in db.execute(
                    "SELECT id FROM captured_memories WHERE owner_id=? ORDER BY rowid DESC",
                    (owner,),
                )
            ]
            known = {i["memory_id"] for i in items}
            items.extend(
                self.detail(db, owner, r["memory_id"])
                for r in self.corpus(db, owner)
                if r["memory_id"] not in known
            )
        return {
            "items": [i for i in items if include_inactive or i["lifecycle_status"] == "active"],
            "policy": self.policy(owner),
        }

    def correct(self, owner, mid, content, expected_version):
        previous = self.get(owner, mid)
        if previous["lifecycle_status"] != "active":
            fail("INVALID_RECORD_STATE")
        return self.propose(
            owner,
            content=content,
            source_type="existing_record",
            memory_type=(
                previous["memory_type"]
                if previous["memory_type"]
                in ("preference", "plan", "project_decision", "proposal", "hypothesis")
                else "correction"
            ),
            supersedes=mid,
            expected_version=expected_version,
            epistemic_status=previous["epistemic_status"],
            project_scope=previous.get("project_scope"),
            event_time=previous.get("event_time"),
            reference_time=previous.get("reference_time"),
        )

    def history(self, owner, mid):
        with self.store.connect() as db:
            item = self.detail(db, owner, mid)
            captured = [
                self.detail(db, owner, r[0])
                for r in db.execute(
                    "SELECT id FROM captured_memories WHERE owner_id=? AND record_id=? ORDER BY rowid DESC",
                    (owner, item["record_id"]),
                )
            ]
            versions = {i["record_version"] for i in captured}
            for row in db.execute(
                "SELECT * FROM revisions WHERE record_id=? ORDER BY version DESC",
                (item["record_id"],),
            ):
                if row["version"] not in versions:
                    captured.append(
                        dict(
                            item,
                            content=row["text"],
                            record_version=row["version"],
                            lifecycle_status="superseded",
                            index_status="inactive",
                        )
                    )
            return sorted(captured, key=lambda i: i["record_version"], reverse=True)

    def pending(self, owner):
        with self.store.connect() as db:
            items = [
                json.loads(r[0])
                for r in db.execute(
                    "SELECT payload FROM capture_candidates WHERE owner_id=? ORDER BY rowid DESC",
                    (owner,),
                )
            ]
        return {
            "items": [
                i
                for i in items
                if i["lifecycle_status"] == "pending" and i["expires_at"] > self.store.clock()
            ]
        }

    def candidate(self, owner, cid):
        with self.store.connect() as db:
            return self.require(db, "capture_candidates", owner, cid)

    def policy(self, owner):
        with self.store.connect() as db:
            row = db.execute(
                "SELECT policy FROM capture_policies WHERE owner_id=?", (owner,)
            ).fetchone()
            return row[0] if row else "MANUAL"

    def set_policy(self, owner, policy):
        if policy not in ("MANUAL", "SUGGEST"):
            fail("AUTO_DISABLED", 422)
        with self.store.connect(True) as db:
            db.execute(
                "INSERT INTO capture_policies VALUES(?,?) ON CONFLICT(owner_id) DO UPDATE SET policy=excluded.policy",
                (owner, policy),
            )
        return {"policy": policy, "auto_enabled": False}

    def cleanup(self):
        cutoff = (datetime.fromisoformat(self.store.clock()) - timedelta(days=30)).isoformat()
        with self.store.connect(True) as db:
            return db.execute(
                "DELETE FROM capture_candidates WHERE json_extract(payload,'$.expires_at')<?",
                (cutoff,),
            ).rowcount

    def archive(self, owner, mid, expected_version):
        with self.store.connect(True) as db:
            item = self.detail(db, owner, mid)
            if item["lifecycle_status"] != "active" or item["record_version"] != expected_version:
                fail("RECORD_VERSION_CONFLICT")
            self.store.invalidate(db, item["record_id"])
            item.pop("index_status", None)
            item["lifecycle_status"] = "archived"
            db.execute(
                "INSERT INTO captured_memories VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                (mid, owner, item["record_id"], encode(item)),
            )
            db.execute(
                "UPDATE records SET status='archived',updated_at=? WHERE id=?",
                (self.store.clock(), item["record_id"]),
            )
        return self.get(owner, mid)

    def unarchive(self, owner, mid, expected_version):
        with self.store.connect(True) as db:
            item = self.detail(db, owner, mid)
            if item["lifecycle_status"] != "archived" or item["record_version"] != expected_version:
                fail("RECORD_VERSION_CONFLICT")
            revision = db.execute(
                "SELECT id FROM revisions WHERE record_id=? AND version=?",
                (item["record_id"], expected_version),
            ).fetchone()[0]
            self.store.queue(db, revision)
            item.pop("index_status", None)
            item["lifecycle_status"] = "active"
            db.execute("UPDATE captured_memories SET payload=? WHERE id=?", (encode(item), mid))
            db.execute("UPDATE records SET status='queued' WHERE id=?", (item["record_id"],))
            self.store.bump(db)
        return self.get(owner, mid)

    def preferences(self, owner):
        with self.store.connect() as db:
            return [
                json.loads(row[0])["content"]
                for row in db.execute(
                    "SELECT c.payload FROM captured_memories c JOIN records r ON r.id=c.record_id "
                    "WHERE c.owner_id=? AND r.state='active' AND r.version=json_extract(c.payload,'$.record_version') "
                    "AND json_extract(c.payload,'$.lifecycle_status')='active' "
                    "AND json_extract(c.payload,'$.memory_type')='preference' "
                    "AND json_extract(c.payload,'$.epistemic_status')='user_reported' "
                    "ORDER BY c.rowid DESC LIMIT 8",
                    (owner,),
                )
            ]

    def reject(self, owner, cid):
        with self.store.connect(True) as db:
            candidate = self.require(db, "capture_candidates", owner, cid)
            if candidate["lifecycle_status"] != "pending":
                fail("INVALID_CANDIDATE_STATE")
            candidate["lifecycle_status"] = "rejected"
            db.execute(
                "UPDATE capture_candidates SET payload=? WHERE id=?", (encode(candidate), cid)
            )

    def delete(self, owner, mid, expected_version):
        with self.store.connect(True) as db:
            item = self.detail(db, owner, mid)
            record = self.store.require(db, item["record_id"], "active")
            if item["lifecycle_status"] != "active" or record["version"] != expected_version:
                fail("RECORD_VERSION_CONFLICT")
            self.store.invalidate(db, item["record_id"])
            ts = self.store.clock()
            expiry = (datetime.fromisoformat(ts) + timedelta(days=30)).isoformat()
            db.execute(
                "UPDATE records SET state='trash',status='trashed',deleted_at=?,purge_at=?,updated_at=? WHERE id=?",
                (ts, expiry, ts, item["record_id"]),
            )

    def retry(self, owner, mid):
        item = self.get(owner, mid)
        if item["lifecycle_status"] != "active":
            fail("INVALID_RECORD_STATE")
        self.store.retry(item["record_id"], expected_version=item["record_version"])
        return self.get(owner, mid)
