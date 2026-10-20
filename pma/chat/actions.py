"""Authenticated, versioned UI actions. Model-authored executable instructions are forbidden."""

import json

from ..errors import AppError
from .planner import ACTION_TYPES, FOLLOWUPS
from .store import encode


def persist_states(db, message, context_version):
    response = message.get("response")
    if not response:
        return
    for action in response.get("ui_actions", []):
        row = db.execute(
            "SELECT state,context_version FROM chat_ui_actions WHERE id=?", (action["action_id"],)
        ).fetchone()
        action["state"] = row["state"] if row else "EXPIRED"
        if (
            row
            and row["state"] == "ACTIVE"
            and (row["context_version"] != context_version or message.get("error_code"))
        ):
            action["state"] = "EXPIRED"


class ActionManager:
    def __init__(self, chat):
        self.chat = chat
        self.store = chat.store

    def run(self, sid, aid, request_id, expected_context_version):
        payload = None
        with self.store.store.connect(True) as db:
            self.store.require(db, sid)
            row = db.execute(
                "SELECT * FROM chat_ui_actions WHERE id=? AND session_id=?", (aid, sid)
            ).fetchone()
            if not row:
                raise AppError("NOT_FOUND", "선택 항목을 찾을 수 없습니다.", 404)
            payload = json.loads(row["payload"])
            if payload["type"] not in ACTION_TYPES:
                raise AppError("INVALID_ACTION", "지원하지 않는 선택입니다.", 422)
            # Even a cached result must not resurrect deleted/changed source text.
            invalid = False
            for rid, version in payload["source_versions"].items():
                source = db.execute(
                    "SELECT version,state FROM records WHERE id=?", (rid,)
                ).fetchone()
                invalid |= not source or source["state"] != "active" or source["version"] != version
            message = db.execute(
                "SELECT error_code FROM chat_messages WHERE id=?", (row["message_id"],)
            ).fetchone()
            invalid |= not message or bool(message["error_code"])
            completed = db.execute(
                "SELECT id,state,error_code FROM chat_messages WHERE session_id=? AND request_id=?",
                (sid, "action:" + aid),
            ).fetchone()
            if invalid:
                db.execute(
                    "UPDATE chat_ui_actions SET state='EXPIRED',result=NULL WHERE id=?", (aid,)
                )
            elif row["state"] == "RESOLVED":
                if row["request_id"] != request_id:
                    raise AppError("ACTION_RESOLVED", "이미 처리한 선택입니다.", 409)
                return json.loads(row["result"])
            elif (
                row["request_id"] == request_id
                and completed
                and completed["state"] == "completed"
                and not completed["error_code"]
            ):
                result = {
                    "effect": "conversation",
                    "message_id": completed["id"],
                    "state": "RESOLVED",
                }
                db.execute(
                    "UPDATE chat_ui_actions SET state='RESOLVED',result=? WHERE id=?",
                    (encode(result), aid),
                )
                return result
            elif (
                row["state"] == "EXPIRED"
                or row["context_version"] != expected_context_version
                or self.store.context_in(db, sid).version != row["context_version"]
            ):
                invalid = True
                db.execute("UPDATE chat_ui_actions SET state='EXPIRED' WHERE id=?", (aid,))
            elif row["state"] == "LOADING":
                if row["request_id"] != request_id:
                    raise AppError("ACTION_BUSY", "선택한 작업을 처리 중입니다.", 409, True)
                completed = db.execute(
                    "SELECT id,state,error_code FROM chat_messages WHERE session_id=? AND request_id=?",
                    (sid, "action:" + aid),
                ).fetchone()
                if completed and completed["state"] == "completed" and not completed["error_code"]:
                    result = {
                        "effect": "conversation",
                        "message_id": completed["id"],
                        "state": "RESOLVED",
                    }
                    db.execute(
                        "UPDATE chat_ui_actions SET state='RESOLVED',result=? WHERE id=?",
                        (encode(result), aid),
                    )
                    return result
                raise AppError("ACTION_BUSY", "선택한 작업을 처리 중입니다.", 409, True)
            else:
                duplicate = db.execute(
                    "SELECT id FROM chat_ui_actions WHERE session_id=? AND request_id=?",
                    (sid, request_id),
                ).fetchone()
                if duplicate and duplicate["id"] != aid:
                    raise AppError("REQUEST_CONFLICT", "다른 선택에 사용한 요청 ID입니다.", 409)
                db.execute(
                    "UPDATE chat_ui_actions SET state='LOADING',request_id=? WHERE id=?",
                    (request_id, aid),
                )
        if invalid:
            raise AppError(
                "ACTION_EXPIRED",
                "대화 또는 기록이 바뀌었습니다. 현재 내용으로 다시 질문해 주세요.",
                409,
            )
        try:
            result = self.execute(sid, payload, expected_context_version)
            with self.store.store.connect(True) as db:
                # A successful follow-up intentionally advances the context version.
                self.store.require(db, sid)
                db.execute(
                    "UPDATE chat_ui_actions SET state='RESOLVED',result=? WHERE id=? AND request_id=?",
                    (encode({**result, "state": "RESOLVED"}), aid, request_id),
                )
            return {**result, "state": "RESOLVED"}
        except Exception:
            with self.store.store.connect(True) as db:
                db.execute(
                    "UPDATE chat_ui_actions SET state='ACTIVE',request_id=NULL WHERE id=? AND state='LOADING'",
                    (aid,),
                )
            raise

    def execute(self, sid, payload, version):
        kind = payload["type"]
        aid, mid = payload["action_id"], payload["message_id"]
        session = self.store.get(sid)
        anchor = next(m for m in session["messages"] if m["id"] == mid)
        if kind == "DISMISS":
            return {"effect": "dismiss"}
        if kind in {
            "SHOW_EVIDENCE",
            "SHOW_HISTORY",
            "COMPARE",
            "CONFIRM_PROGRESS",
            "CORRECT_RECORD",
        }:
            return {
                "effect": {
                    "SHOW_EVIDENCE": "evidence",
                    "SHOW_HISTORY": "history",
                    "COMPARE": "compare",
                    "CONFIRM_PROGRESS": "record_preview",
                    "CORRECT_RECORD": "record_preview",
                }[kind],
                "message_id": mid,
                "record_ids": list(payload["source_versions"]),
                "source_versions": payload["source_versions"],
            }
        if kind == "SAVE_PROGRESS":
            from ..memory.api import from_messages
            from ..memory.repository import MemoryRepository

            candidate = from_messages(
                MemoryRepository(self.store.store),
                sid,
                [mid],
                "user_message",
                mode=anchor.get("mode", "auto"),
                capture_request_id="action:" + aid,
            )
            return {"effect": "save_preview", "candidates": [candidate]}
        if kind in FOLLOWUPS:
            question = FOLLOWUPS[kind] + "\n대상: " + anchor["question"]
        elif kind in {"CHOOSE_TARGET", "CHOOSE_DATE"}:
            question = payload["query"]
        elif kind in {"RETRY_SEARCH", "EXPAND_SCOPE"}:
            question = anchor["question"]
        else:
            raise AppError("INVALID_ACTION", "지원하지 않는 선택입니다.", 422)
        result = self.chat.message(
            sid,
            "action:" + aid,
            question[:1000],
            anchor.get("request_today"),
            mid,
            anchor.get("mode", "auto"),
            **({"filters": {"date_from": None, "date_to": None}} if kind == "EXPAND_SCOPE" else {}),
            expected_context_version=version,
        )
        return {"effect": "conversation", "message_id": result["message_id"]}
