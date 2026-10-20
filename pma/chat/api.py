"""Chat routes use the host application's authentication and error middleware."""

from fastapi import APIRouter, Query, Request, Response
from pydantic import AliasChoices, Field, field_validator

from .schemas import ConversationMode


def router(input_type, query_type):
    from ..web import Filters

    class Selection(input_type):
        search_id: str | None = Field(default=None, min_length=1, max_length=128)
        selected_ids: list[str] = Field(default_factory=list, max_length=8)

    class Message(input_type):
        correction_enabled: bool = True
        request_id: str = Field(min_length=1, max_length=128,
                                validation_alias=AliasChoices("request_id", "client_message_id"))
        question: str = Field(min_length=1, max_length=1000)
        mode: ConversationMode = Field(default=ConversationMode.AUTO, strict=False)
        today: str | None = None
        context_message_id: str | None = Field(default=None, min_length=1, max_length=128)
        filters: Filters | None = None

        @field_validator("question")
        @classmethod
        def nonempty(cls, value):
            if not value.strip():
                raise ValueError("empty question")
            return value

        @field_validator("today")
        @classmethod
        def valid_date(cls, value):
            from datetime import date

            if value is not None:
                date.fromisoformat(value)
            return value

    class ActionInput(input_type):
        request_id: str = Field(min_length=1, max_length=128)
        expected_context_version: int = Field(ge=0)

    routes = APIRouter(prefix="/api/v1/chat")

    @routes.post("/sessions/{sid}/actions/{action_id}")
    def execute_action(sid: str, action_id: str, data: ActionInput, request: Request):
        from .actions import ActionManager
        return ActionManager(request.app.state.chat).run(sid, action_id, data.request_id,
                                                       data.expected_context_version)

    @routes.post("/searches")
    def search(data: query_type, request: Request):
        return request.app.state.chat.search(
            data.question, data.filters.model_dump() if data.filters else None, data.today,
            **({"correction_enabled": False} if not data.correction_enabled else {})
        )

    @routes.post("/sessions", status_code=201)
    def create(data: Selection, request: Request):
        if data.search_id is None and not data.selected_ids:
            return request.app.state.chat.store.create_empty()
        return request.app.state.chat.store.create(data.search_id, data.selected_ids)

    @routes.get("/sessions")
    def listing(request: Request, q: str = ""):
        return request.app.state.chat.store.list(q[:1000])

    @routes.get("/sessions/{sid}")
    def detail(sid: str, request: Request):
        result = request.app.state.chat.store.get(sid)
        result["diagnostics_enabled"] = request.app.state.chat.service.settings.diagnostics
        return result

    @routes.delete("/sessions/{sid}", status_code=204)
    def delete(sid: str, request: Request):
        request.app.state.chat.store.delete(sid)
        return Response(status_code=204)

    @routes.post("/sessions/{sid}/messages")
    def message(sid: str, data: Message, request: Request):
        result = request.app.state.chat.message(
            sid, data.request_id, data.question, data.today, data.context_message_id, data.mode,
            **({"filters": data.filters.model_dump(exclude_unset=True)} if data.filters else {}),
            **({"correction_enabled": False} if not data.correction_enabled else {}),
        )
        from ..memory.api import natural_candidates

        try:
            result["memory_candidates"] = natural_candidates(
                request.app.state.chat.service.store,
                sid,
                result["message_id"],
                data.question,
                data.mode,
            )
        except Exception as exc:
            # Capture failure never invalidates a completed chat response.
            result["memory_candidates"] = []
            result["memory_capture_error"] = getattr(exc, "code", "CAPTURE_FAILED")
        return result

    @routes.get("/sessions/{sid}/messages")
    def messages(sid: str, request: Request, offset: int = Query(0, ge=0),
                 limit: int = Query(50, ge=1, le=100)):
        return request.app.state.chat.store.messages(sid, offset, limit)

    @routes.post("/sessions/{sid}/clarifications")
    def clarification(sid: str, data: Message, request: Request):
        from ..errors import AppError

        if not data.context_message_id:
            raise AppError("CONTEXT_REQUIRED", "확인할 질문을 선택하세요.", 422)
        session = request.app.state.chat.store.get(sid)
        anchor = next((m for m in session["messages"] if m["id"] == data.context_message_id), None)
        if (not anchor or anchor.get("error_code") or
                (anchor.get("response") or {}).get("status") != "needs_clarification"):
            raise AppError("CONTEXT_EXPIRED", "확인 질문이 만료되었습니다.", 409)
        return message(sid, data, request)

    @routes.get("/citations/{citation_id}")
    def citation(citation_id: str, request: Request):
        return request.app.state.chat.store.citation(citation_id)

    @routes.get("/sessions/{sid}/requests/{request_id}")
    def progress(sid: str, request_id: str, request: Request):
        return request.app.state.chat.request_status(sid, request_id)

    @routes.post("/sessions/{sid}/requests/{request_id}/cancel")
    def cancel(sid: str, request_id: str, request: Request):
        request.app.state.chat.store.cancel(sid, request_id)
        return request.app.state.chat.request_status(sid, request_id)

    return routes
