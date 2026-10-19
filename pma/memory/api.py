"""Uses the application's existing local-account authentication and CSRF middleware."""

import json
from typing import Literal

from fastapi import APIRouter, Request, Response
from pydantic import Field, field_validator

from ..chat.memory_capture import capture_intent, classify, is_reference
from ..errors import AppError
from .manager import MemoryCaptureManager
from .provenance import message_snapshot, source_text
from .repository import MemoryRepository
from .schemas import MemoryType

OWNER = "local-account"


def from_messages(
    repo, sid, ids, source_type, selected_text=None, mode="general", capture_request_id=None
):
    with repo.store.connect() as db:
        messages = []
        for mid in ids:
            row = db.execute(
                "SELECT * FROM chat_messages WHERE session_id=? AND id=?", (sid, mid)
            ).fetchone()
            if not row or row["state"] != "completed" or row["error_code"]:
                raise AppError("INVALID_SOURCE", "저장할 메시지를 다시 선택해 주세요.", 409)
            messages.append(row)
        if not messages:
            raise AppError("INVALID_SOURCE", "저장할 메시지를 선택해 주세요.")
        if source_type == "user_message":
            content = "\n\n".join(m["question"] for m in messages)
        else:
            content = "\n\n".join(
                i["text"] for m in messages for i in json.loads(m["response"])["items"]
            )
        if selected_text is not None:
            if not selected_text.strip() or selected_text not in content:
                raise AppError("INVALID_SELECTION", "선택한 문장이 원문에 없습니다.")
            content = selected_text
        source_records = list(
            dict.fromkeys(
                r[0]
                for mid in ids
                for r in db.execute(
                    "SELECT record_id FROM chat_message_evidence WHERE message_id=?", (mid,)
                )
            )
        )
        snapshots = [
            message_snapshot(m, source_type, source_text(m, source_type)) for m in messages
        ]
    return repo.propose(
        OWNER,
        content=content,
        source_type=source_type,
        session_id=sid,
        message_ids=ids,
        source_record_ids=source_records,
        mode=mode,
        source_snapshots=snapshots,
        reference_time=snapshots[-1]["reference_date"],
        capture_request_id=capture_request_id,
    )


def natural_candidates(store, sid, mid, question, mode):
    if not capture_intent(question) and MemoryRepository(store).policy(OWNER) != "SUGGEST":
        return []
    repo = MemoryRepository(store)
    if not capture_intent(question) and (
        classify(question) == "user_statement" or question.rstrip().endswith("?")
    ):
        return []

    def capture(ids, source):
        return from_messages(
            repo, sid, ids, source, mode=mode, capture_request_id=f"{mid}:{source}:{ids[0]}"
        )

    if "이 대화" in question:
        with store.connect() as db:
            rows = db.execute(
                "SELECT id,question FROM chat_messages WHERE session_id=? AND id<>? "
                "AND state='completed' AND error_code IS NULL ORDER BY rowid DESC LIMIT 30",
                (sid, mid),
            ).fetchall()
        selected = [
            r
            for r in rows
            if "결정" not in question or classify(r["question"]) == "project_decision"
        ]
        return [capture([row["id"]], "user_message") for row in reversed(selected)]
    if not is_reference(question):
        return [capture([mid], "user_message")]
    with store.connect() as db:
        previous = db.execute(
            "SELECT id FROM chat_messages WHERE session_id=? AND id<>? "
            "AND state='completed' AND error_code IS NULL ORDER BY rowid DESC LIMIT 1",
            (sid, mid),
        ).fetchone()
    if not previous:
        return []
    # Ambiguous reference: expose both actual sources instead of choosing for the user.
    return [capture([previous["id"]], source) for source in ("user_message", "assistant_message")]


def router(input_type):
    class ContentInput(input_type):
        @field_validator("content", check_fields=False)
        @classmethod
        def not_blank(cls, value):
            if value is not None and not value.strip():
                raise ValueError("empty content")
            return value

    class Capture(input_type):
        session_id: str = Field(min_length=1, max_length=128)
        message_ids: list[str] = Field(min_length=1, max_length=30)
        source_type: Literal["user_message", "assistant_message"]
        selected_text: str | None = Field(default=None, min_length=1, max_length=3500)

    class Commit(ContentInput):
        approved: bool
        request_id: str = Field(min_length=1, max_length=128)
        candidate_version: int = Field(default=1, ge=1)
        content: str | None = Field(default=None, min_length=1, max_length=3500)
        memory_type: MemoryType | None = None
        project_scope: str | None = Field(default=None, max_length=200)
        event_time: str | None = Field(default=None, max_length=100)
        resolution: Literal["add", "add_confirmed", "correct"] = "add"
        review_id: str | None = None
        link_memory_ids: list[str] = Field(default_factory=list, max_length=8)

    class Review(ContentInput):
        content: str | None = Field(default=None, min_length=1, max_length=3500)
        memory_type: MemoryType | None = None
        project_scope: str | None = Field(default=None, max_length=200)
        event_time: str | None = Field(default=None, max_length=100)
        candidate_version: int = Field(default=1, ge=1)

    class Policy(input_type):
        policy: Literal["MANUAL", "SUGGEST"]

    class Version(ContentInput):
        expected_version: int = Field(ge=1)

    class Target(Version):
        memory_id: str
        content: str = Field(min_length=1, max_length=3500)

    class Extract(input_type):
        session_id: str

    class Correction(ContentInput):
        content: str = Field(min_length=1, max_length=3500)
        expected_version: int = Field(ge=1)

    routes = APIRouter(prefix="/api/v1/memory")

    def repo(request):
        return MemoryRepository(request.app.state.store)

    def manager(request):
        return MemoryCaptureManager(
            request.app.state.store, getattr(request.app.state, "service", None)
        )

    @routes.get("/policy")
    def policy(request: Request):
        return {"policy": repo(request).policy(OWNER), "auto_enabled": False}

    @routes.put("/policy")
    def set_policy(data: Policy, request: Request):
        return repo(request).set_policy(OWNER, data.policy)

    @routes.post("/candidates/{cid}/review")
    def review(cid: str, data: Review, request: Request):
        return manager(request).review(OWNER, cid, **data.model_dump())

    @routes.post("/candidates/{cid}/target", status_code=201)
    def target(cid: str, data: Target, request: Request):
        repository = repo(request)
        candidate = repository.candidate(OWNER, cid)
        if (
            candidate["lifecycle_status"] != "pending"
            or candidate["expires_at"] <= repository.store.clock()
        ):
            raise AppError("CANDIDATE_EXPIRED", "원문에서 다시 저장 후보를 만들어 주세요.", 409)
        previous = repository.get(OWNER, data.memory_id)
        if (
            candidate["epistemic_status"] == "ai_proposed"
            and previous["epistemic_status"] != "ai_proposed"
        ):
            raise AppError("SOURCE_TYPE_MISMATCH", "출처가 다른 기억은 별도로 저장해 주세요.", 409)
        return repository.propose(
            OWNER,
            content=data.content,
            source_type=candidate["source_type"],
            session_id=candidate["session_id"],
            message_ids=candidate["message_ids"],
            source_snapshots=candidate["source_snapshots"],
            memory_type=candidate["memory_type"],
            epistemic_status=candidate["epistemic_status"],
            reference_time=candidate["reference_time"],
            mode=candidate["conversation_mode"],
            supersedes=data.memory_id,
            expected_version=data.expected_version,
        )

    @routes.post("/extract")
    def extract(data: Extract, request: Request):
        return manager(request).extract(OWNER, data.session_id)

    @routes.post("/candidates", status_code=201)
    def candidates(data: Capture, request: Request):
        with repo(request).store.connect() as db:
            row = db.execute(
                "SELECT request_input FROM chat_messages WHERE id=? AND session_id=?",
                (data.message_ids[-1], data.session_id),
            ).fetchone()
            mode = json.loads(row[0] or "{}").get("mode", "auto") if row else "auto"
        return from_messages(
            repo(request),
            data.session_id,
            list(dict.fromkeys(data.message_ids)),
            data.source_type,
            data.selected_text,
            mode,
        )

    @routes.post("/candidates/{cid}/commit", status_code=202)
    def commit(cid: str, data: Commit, request: Request):
        return manager(request).commit(OWNER, cid, **data.model_dump())

    @routes.get("/candidates")
    def pending(request: Request):
        return repo(request).pending(OWNER)

    @routes.post("/candidates/{cid}/reject", status_code=204)
    def reject(cid: str, request: Request):
        repo(request).reject(OWNER, cid)
        return Response(status_code=204)

    @routes.get("")
    def listing(request: Request, include_inactive: bool = False):
        return repo(request).list(OWNER, include_inactive)

    @routes.post("/{mid}/archive")
    def archive(mid: str, data: Version, request: Request):
        return repo(request).archive(OWNER, mid, data.expected_version)

    @routes.post("/{mid}/unarchive", status_code=202)
    def unarchive(mid: str, data: Version, request: Request):
        return repo(request).unarchive(OWNER, mid, data.expected_version)

    @routes.get("/{mid}")
    def detail(mid: str, request: Request):
        return repo(request).get(OWNER, mid)

    @routes.get("/{mid}/history")
    def history(mid: str, request: Request):
        return {"items": repo(request).history(OWNER, mid)}

    @routes.patch("/{mid}", status_code=201)
    @routes.post("/{mid}/corrections", status_code=201)
    def correct(mid: str, data: Correction, request: Request):
        return repo(request).correct(OWNER, mid, data.content, data.expected_version)

    @routes.delete("/{mid}", status_code=204)
    def delete(mid: str, request: Request, expected_version: int):
        repo(request).delete(OWNER, mid, expected_version)
        return Response(status_code=204)

    @routes.post("/{mid}/retry", status_code=202)
    def retry(mid: str, request: Request):
        return repo(request).retry(OWNER, mid)

    return routes
