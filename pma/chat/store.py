"""Chat persistence. All source checks and state transitions share write transactions."""

import json
from datetime import datetime, timedelta

from ..errors import AppError
from ..store import identifier


def encode(value):
    return json.dumps(value, ensure_ascii=False)


def changed():
    return AppError(
        "SOURCE_CHANGED", "근거 기록이 변경되었습니다. 새 검색으로 대화를 시작하세요.", 409
    )


class ChatStore:
    def __init__(self, store):
        self.store = store

    def recover(self):
        with self.store.connect(True) as db:
            db.execute(
                "UPDATE chat_messages SET state='failed',error_code='INTERRUPTED' "
                "WHERE state='running'"
            )

    @staticmethod
    def check_sources(db, rows):
        for row in rows:
            source = db.execute(
                "SELECT version,state FROM records WHERE id=?", (row["record_id"],)
            ).fetchone()
            if not source or source["state"] != "active" or source["version"] != row["version"]:
                raise changed()

    def save_search(self, found, metadata):
        sid = identifier()
        with self.store.connect(True) as db:
            self.check_sources(db, found["results"])
            db.execute(
                "INSERT INTO chat_searches VALUES(?,?,?)",
                (sid, self.store.clock(), encode(metadata)),
            )
            for row in found["results"]:
                db.execute(
                    "INSERT INTO chat_search_results VALUES(?,?,?,?,?)",
                    (sid, row["id"], row["record_id"], row["version"], encode(row)),
                )
        return {**found, "search_id": sid}

    def create(self, search_id, selected_ids):
        sid, ts = identifier(), self.store.clock()
        with self.store.connect(True) as db:
            search = db.execute("SELECT * FROM chat_searches WHERE id=?", (search_id,)).fetchone()
            if not search or datetime.fromisoformat(search["created_at"]) <= (
                datetime.fromisoformat(ts) - timedelta(hours=24)
            ):
                raise AppError(
                    "SEARCH_EXPIRED", "검색 결과가 만료되었습니다. 다시 검색하세요.", 409
                )
            available = {
                r["memory_id"]: json.loads(r["payload"])
                for r in db.execute(
                    "SELECT * FROM chat_search_results WHERE search_id=?", (search_id,)
                )
            }
            if (
                not 1 <= len(selected_ids) <= 8
                or len(set(selected_ids)) != len(selected_ids)
                or not set(selected_ids) <= available.keys()
            ):
                raise AppError("INVALID_SELECTION", "검색된 기억을 1~8개 선택하세요.", 422)
            rows = [available[mid] for mid in selected_ids]
            self.check_sources(db, rows)
            metadata = json.loads(search["payload"])
            metadata["connections"] = [
                link
                for link in metadata.get("connections", [])
                if set(link["citations"]) <= set(selected_ids)
            ]
            db.execute(
                "INSERT INTO chat_sessions VALUES(?,?,?,'active',?,?)",
                (sid, search_id, metadata["question"][:100], ts, ts),
            )
            db.execute("INSERT INTO chat_snapshots VALUES(?,?)", (sid, encode(metadata)))
            for row in rows:
                revision = db.execute(
                    "SELECT * FROM revisions WHERE record_id=? AND version=?",
                    (row["record_id"], row["version"]),
                ).fetchone()
                if not revision or revision["text"] != row["source_text"]:
                    raise changed()
                row["revision_id"] = revision["id"]
                for ref in row["evidence"]:
                    if (
                        not (0 <= ref["start"] < ref["end"] <= len(revision["text"]))
                        or revision["text"][ref["start"] : ref["end"]] != ref["quote"]
                    ):
                        raise ValueError("INVALID_SOURCE_SPAN")
                db.execute(
                    "INSERT INTO chat_snapshot_items VALUES(?,?,?,?,?)",
                    (sid, row["id"], row["record_id"], row["version"], encode(row)),
                )
        return self.get(sid)

    @staticmethod
    def require(db, sid):
        row = db.execute("SELECT * FROM chat_sessions WHERE id=?", (sid,)).fetchone()
        if not row:
            raise AppError("NOT_FOUND", "대화를 찾을 수 없습니다.", 404)
        return dict(row)

    @staticmethod
    def evidence(db, sid):
        return [
            json.loads(r[0])
            for r in db.execute(
                "SELECT payload FROM chat_snapshot_items WHERE session_id=? ORDER BY rowid", (sid,)
            )
        ]

    def get(self, sid):
        with self.store.connect() as db:
            result = self.require(db, sid)
            result["evidence"] = self.evidence(db, sid)
            result["snapshot"] = json.loads(
                db.execute(
                    "SELECT payload FROM chat_snapshots WHERE session_id=?", (sid,)
                ).fetchone()[0]
            )
            result["messages"] = []
            for row in db.execute(
                "SELECT * FROM chat_messages WHERE session_id=? ORDER BY created_at,rowid", (sid,)
            ):
                message = dict(row)
                message["response"] = (
                    json.loads(message["response"]) if message["response"] else None
                )
                result["messages"].append(message)
            return result

    def list(self):
        with self.store.connect() as db:
            return {
                "items": [
                    dict(r)
                    for r in db.execute(
                        "SELECT * FROM chat_sessions ORDER BY updated_at DESC,id DESC"
                    )
                ]
            }

    def delete(self, sid):
        with self.store.connect(True) as db:
            self.require(db, sid)
            db.execute("DELETE FROM chat_sessions WHERE id=?", (sid,))

    def begin(self, sid, request_id, question):
        with self.store.connect(True) as db:
            session = self.require(db, sid)
            previous = db.execute(
                "SELECT * FROM chat_messages WHERE session_id=? AND request_id=?", (sid, request_id)
            ).fetchone()
            if previous and previous["question"] != question:
                raise AppError("REQUEST_CONFLICT", "같은 요청 ID의 질문이 다릅니다.", 409)
            if previous and previous["state"] == "completed":
                return previous["id"], json.loads(previous["response"])
            if session["state"] != "active":
                raise changed()
            self.check_sources(db, self.evidence(db, sid))
            if db.execute(
                "SELECT 1 FROM chat_messages WHERE session_id=? AND state='running'", (sid,)
            ).fetchone():
                raise AppError("CHAT_BUSY", "이 대화의 답변을 작성 중입니다.", 409, True)
            mid = previous["id"] if previous else identifier()
            if previous:
                db.execute(
                    "UPDATE chat_messages SET state='running',error_code=NULL,created_at=? WHERE id=?",
                    (self.store.clock(), mid),
                )
            else:
                db.execute(
                    "INSERT INTO chat_messages(id,session_id,request_id,question,state,created_at) "
                    "VALUES(?,?,?,?,'running',?)",
                    (mid, sid, request_id, question, self.store.clock()),
                )
            return mid, None

    def finish(self, sid, mid, response):
        with self.store.connect(True) as db:
            session = self.require(db, sid)
            rows = self.evidence(db, sid)
            if session["state"] != "active":
                raise changed()
            self.check_sources(db, rows)
            sources = {r["id"]: r for r in rows}
            for index, item in enumerate(response["items"]):
                for cid in item["citations"]:
                    refs = [
                        ref
                        for ref in response.get("citation_details", [])
                        if ref["item_index"] == index and ref["memory_id"] == cid
                    ]
                    source = sources[cid]
                    if not refs or any(
                        ref["revision_id"] != source["revision_id"]
                        or not (0 <= ref["start"] < ref["end"] <= len(source["source_text"]))
                        or source["source_text"][ref["start"] : ref["end"]] != ref["quote"]
                        for ref in refs
                    ):
                        raise ValueError("INVALID_SOURCE_SPAN")
                    db.execute(
                        "INSERT INTO chat_citations VALUES(?,?,?,?)",
                        (mid, index, cid, encode(refs)),
                    )
            ts = self.store.clock()
            db.execute(
                "UPDATE chat_messages SET state='completed',response=?,completed_at=? WHERE id=?",
                (encode(response), ts, mid),
            )
            db.execute("UPDATE chat_sessions SET updated_at=? WHERE id=?", (ts, sid))

    def fail(self, mid, code):
        with self.store.connect(True) as db:
            db.execute(
                "UPDATE chat_messages SET state='failed',error_code=? WHERE id=? AND state='running'",
                (code, mid),
            )
