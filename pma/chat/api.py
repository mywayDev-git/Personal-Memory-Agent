"""Chat routes use the host application's authentication and error middleware."""

from fastapi import APIRouter, Request, Response
from pydantic import Field, field_validator

from .schemas import ConversationMode


def router(input_type, query_type):
    class Selection(input_type):
        search_id: str | None = Field(default=None, min_length=1, max_length=128)
        selected_ids: list[str] = Field(default_factory=list, max_length=8)

    class Message(input_type):
        request_id: str = Field(min_length=1, max_length=128)
        question: str = Field(min_length=1, max_length=1000)
        mode: ConversationMode = ConversationMode.AUTO
        today: str | None = None
        context_message_id: str | None = Field(default=None, min_length=1, max_length=128)

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

    routes = APIRouter(prefix="/api/v1/chat")

    @routes.post("/searches")
    def search(data: query_type, request: Request):
        return request.app.state.chat.search(
            data.question, data.filters.model_dump() if data.filters else None, data.today
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
        return request.app.state.chat.message(
            sid, data.request_id, data.question, data.today, data.context_message_id, data.mode
        )

    @routes.get("/sessions/{sid}/requests/{request_id}")
    def progress(sid: str, request_id: str, request: Request):
        return request.app.state.chat.request_status(sid, request_id)

    @routes.post("/sessions/{sid}/requests/{request_id}/cancel")
    def cancel(sid: str, request_id: str, request: Request):
        request.app.state.chat.store.cancel(sid, request_id)
        return request.app.state.chat.request_status(sid, request_id)

    return routes
