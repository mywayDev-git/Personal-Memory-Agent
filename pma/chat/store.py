"""Chat persistence. All source checks and state transitions share write transactions."""

import json
from datetime import datetime, timedelta

from ..errors import AppError
from ..store import identifier


def encode(value):
    return json.dumps(value, ensure_ascii=False)


def changed():
    return AppError("SOURCE_CHANGED", "근거 기록이 변경되었습니다. 다시 시도해 주세요.", 409, True)


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

    def create_empty(self):
        sid, ts = identifier(), self.store.clock()
        with self.store.connect(True) as db:
            db.execute(
                "INSERT INTO chat_sessions VALUES(?,NULL,?,'active',?,?)", (sid, "새 대화", ts, ts)
            )
        return self.get(sid)

    def freeze(self, rows):
        """Resolve exact revisions before inference without persisting drafts."""
        with self.store.connect() as db:
            self.check_sources(db, rows)
            frozen = []
            for row in rows:
                revision = db.execute(
                    "SELECT id,text FROM revisions WHERE record_id=? AND version=?",
                    (row["record_id"], row["version"]),
                ).fetchone()
                if not revision or revision["text"] != row["source_text"]:
                    raise changed()
                for ref in row["evidence"]:
                    if (
                        not (0 <= ref["start"] < ref["end"] <= len(revision["text"]))
                        or revision["text"][ref["start"] : ref["end"]] != ref["quote"]
                    ):
                        raise ValueError("INVALID_SOURCE_SPAN")
                frozen.append({**row, "revision_id": revision["id"]})
            return frozen

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
            snapshot = db.execute(
                "SELECT payload FROM chat_snapshots WHERE session_id=?", (sid,)
            ).fetchone()
            result["snapshot"] = json.loads(snapshot[0]) if snapshot else {}
            result["messages"] = []
            for row in db.execute(
                "SELECT * FROM chat_messages WHERE session_id=? ORDER BY created_at,rowid", (sid,)
            ):
                message = dict(row)
                request_input = message.pop("request_input")
                message["request_today"] = (
                    json.loads(request_input)["today"] if request_input else None
                )
                message["context_message_id"] = (
                    json.loads(request_input).get("context_message_id") if request_input else None
                )
                message["mode"] = (
                    json.loads(request_input).get("mode", "auto") if request_input else "auto"
                )
                message["response"] = (
                    json.loads(message["response"]) if message["response"] else None
                )
                message["evidence"] = [
                    json.loads(r[0])
                    for r in db.execute(
                        "SELECT payload FROM chat_message_evidence WHERE message_id=? ORDER BY rowid",
                        (message["id"],),
                    )
                ]
                snapshot = db.execute(
                    "SELECT payload FROM chat_message_snapshots WHERE message_id=?",
                    (message["id"],),
                ).fetchone()
                message["snapshot"] = json.loads(snapshot[0]) if snapshot else {}
                result["messages"].append(message)
            result["mode"] = result["messages"][-1]["mode"] if result["messages"] else "auto"
            return result

    def list(self, query=""):
        with self.store.connect() as db:
            return {
                "items": [
                    dict(r)
                    for r in db.execute(
                        "SELECT s.* FROM chat_sessions s WHERE ?='' OR instr(lower(s.title),lower(?))>0 "
                        "OR EXISTS(SELECT 1 FROM chat_messages m WHERE m.session_id=s.id AND "
                        "(instr(lower(m.question),lower(?))>0 OR "
                        "(m.state='completed' AND m.error_code IS NULL AND EXISTS "
                        "(SELECT 1 FROM json_each(m.response,'$.items') i "
                        "WHERE instr(lower(json_extract(i.value,'$.text')),lower(?))>0)))) "
                        "ORDER BY s.updated_at DESC,s.id DESC",
                        (query, query, query, query),
                    )
                ]
            }

    def delete(self, sid):
        with self.store.connect(True) as db:
            self.require(db, sid)
            db.execute("DELETE FROM chat_sessions WHERE id=?", (sid,))

    def begin(self, sid, request_id, question, today=None, context_message_id=None, mode="auto"):
        inputs = {"question": question, "today": today}
        if context_message_id is not None:
            inputs["context_message_id"] = context_message_id
        if mode != "auto":
            inputs["mode"] = mode
        request_input = encode(inputs)
        with self.store.connect(True) as db:
            session = self.require(db, sid)
            previous = db.execute(
                "SELECT * FROM chat_messages WHERE session_id=? AND request_id=?", (sid, request_id)
            ).fetchone()
            if previous and previous["question"] != question:
                raise AppError("REQUEST_CONFLICT", "같은 요청 ID의 질문이 다릅니다.", 409)
            if (
                previous
                and previous["request_input"] is not None
                and previous["request_input"] != request_input
            ):
                raise AppError("REQUEST_CONFLICT", "같은 요청 ID의 입력 조건이 다릅니다.", 409)
            if previous and previous["state"] == "completed":
                return previous["id"], (
                    json.loads(previous["response"])
                    if previous["response"]
                    else {"status": "insufficient_evidence", "items": [], "source_state": "deleted"}
                )
            if context_message_id is not None:
                anchor = db.execute(
                    "SELECT * FROM chat_messages WHERE session_id=? AND id=?",
                    (sid, context_message_id),
                ).fetchone()
                if not anchor or anchor["state"] != "completed" or anchor["error_code"]:
                    raise AppError(
                        "CONTEXT_EXPIRED",
                        "이전 대화의 근거가 변경되었거나 선택이 만료되었습니다. 다시 질문해 주세요.",
                        409,
                    )
                if json.loads(anchor["response"])["status"] == "needs_clarification":
                    latest = db.execute(
                        "SELECT id FROM chat_messages WHERE session_id=? AND state='completed' "
                        "ORDER BY created_at DESC,rowid DESC LIMIT 1",
                        (sid,),
                    ).fetchone()
                    if latest["id"] != context_message_id:
                        raise AppError(
                            "CONTEXT_EXPIRED",
                            "이미 이어진 대화의 선택입니다. 현재 기록으로 다시 질문해 주세요.",
                            409,
                        )
            if session["state"] != "active":
                raise changed()
            if db.execute(
                "SELECT 1 FROM chat_messages WHERE session_id=? AND state='running'", (sid,)
            ).fetchone():
                raise AppError("CHAT_BUSY", "이 대화의 답변을 작성 중입니다.", 409, True)
            mid = previous["id"] if previous else identifier()
            if previous:
                db.execute(
                    "UPDATE chat_messages SET state='running',error_code=NULL,created_at=?,request_input=? WHERE id=?",
                    (self.store.clock(), request_input, mid),
                )
            else:
                db.execute(
                    "INSERT INTO chat_messages(id,session_id,request_id,question,state,created_at,request_input) "
                    "VALUES(?,?,?,?,'running',?,?)",
                    (mid, sid, request_id, question, self.store.clock(), request_input),
                )
            return mid, None

    def finish(self, sid, mid, response, rows=None, metadata=None, *, budget=None):
        with self.store.connect(True) as db:
            session = self.require(db, sid)
            state = db.execute(
                "SELECT state FROM chat_messages WHERE id=? AND session_id=?", (mid, sid)
            ).fetchone()
            if not state or state["state"] != "running":
                raise AppError("CANCELLED", "요청을 중단했습니다.", 409)
            rows = self.evidence(db, sid) if rows is None else rows
            if session["state"] != "active":
                raise changed()
            self.check_sources(db, rows)
            for row in rows:
                db.execute(
                    "INSERT INTO chat_message_evidence VALUES(?,?,?,?,?)",
                    (mid, row["id"], row["record_id"], row["version"], encode(row)),
                )
            db.execute(
                "INSERT INTO chat_message_snapshots VALUES(?,?)", (mid, encode(metadata or {}))
            )
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
                        ref["record_id"] != source["record_id"]
                        or ref["revision_id"] != source["revision_id"]
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
            db.execute(
                "UPDATE chat_sessions SET updated_at=?,title=CASE WHEN title='새 대화' THEN (SELECT substr(question,1,100) FROM chat_messages WHERE id=?) ELSE title END WHERE id=?",
                (ts, mid, sid),
            )
            if budget is not None:
                budget.remaining()  # Raise inside the transaction so all draft writes roll back.

    def fail(self, mid, code):
        with self.store.connect(True) as db:
            db.execute(
                "UPDATE chat_messages SET state='failed',error_code=? WHERE id=? AND state='running'",
                (code, mid),
            )

    def cancel(self, sid, request_id):
        with self.store.connect(True) as db:
            self.require(db, sid)
            if not db.execute(
                "SELECT 1 FROM chat_messages WHERE session_id=? AND request_id=?", (sid, request_id)
            ).fetchone():
                raise AppError(
                    "REQUEST_PENDING",
                    "요청이 아직 접수되지 않았습니다. 잠시 후 다시 중단해 주세요.",
                    409,
                    True,
                )
            db.execute(
                "UPDATE chat_messages SET state='failed',error_code='CANCELLED' "
                "WHERE session_id=? AND request_id=? AND state='running'",
                (sid, request_id),
            )

    def request_state(self, sid, request_id):
        with self.store.connect() as db:
            self.require(db, sid)
            row = db.execute(
                "SELECT state,error_code FROM chat_messages WHERE session_id=? AND request_id=?",
                (sid, request_id),
            ).fetchone()
            return dict(row) if row else {"state": "pending", "error_code": None}
