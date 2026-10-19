"""Same-origin local API and static UI. No account or cloud service required."""

import logging
import secrets
import sqlite3
import threading
import time
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Literal

import requests
from fastapi import FastAPI, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .errors import AppError
from .lock import DataLock
from .models import LocalModels
from .service import Service
from .settings import AppSettings
from .store import Store, identifier

STATIC = Path(__file__).parent / "static"
log = logging.getLogger("pma")


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class RecordInput(Input):
    text: str = Field(min_length=1, max_length=4000)
    reference_time: str | None = None

    @field_validator("text")
    @classmethod
    def text_present(cls, v):
        if not v.strip():
            raise ValueError("empty text")
        return v

    @field_validator("reference_time")
    @classmethod
    def valid_time(cls, v):
        if v is not None:
            parsed = datetime.fromisoformat(v)
            if parsed.tzinfo is None:
                raise ValueError("timezone required")
            return parsed.isoformat()
        return v


class UpdateInput(RecordInput):
    expected_version: int = Field(ge=1)


class RevertInput(Input):
    expected_version: int = Field(ge=1)
    version: int = Field(ge=1)


class RetryFailedInput(Input):
    job_ids: list[str] = Field(min_length=1, max_length=1000)


class Filters(Input):
    date_from: str | None = None
    date_to: str | None = None

    @field_validator("date_from", "date_to")
    @classmethod
    def valid_date(cls, v):
        if v is not None:
            date.fromisoformat(v)
        return v

    @model_validator(mode="after")
    def ordered(self):
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("invalid range")
        return self


class QueryInput(Input):
    correction_enabled: bool = True
    question: str = Field(min_length=1, max_length=1000)
    filters: Filters | None = None
    today: str | None = None

    @field_validator("question")
    @classmethod
    def nonempty(cls, v):
        if not v.strip():
            raise ValueError("empty question")
        return v

    @field_validator("today")
    @classmethod
    def valid_date(cls, v):
        if v is not None:
            date.fromisoformat(v)
        return v


class SessionInput(Input):
    token: str = Field(min_length=32, max_length=128)


def error_response(code, message, status, request_id, retryable=False):
    return JSONResponse(
        {
            "error": {
                "code": code,
                "message": message,
                "retryable": retryable,
                "request_id": request_id,
            }
        },
        status_code=status,
    )


def create_app(settings=None, models=None, run_worker=True, console_test=False):
    settings = settings or AppSettings.from_env()
    settings.validate()
    bootstrap = secrets.token_urlsafe(32)
    auth_lock = threading.Lock()
    auth = {"bootstrap": bootstrap, "session": None, "csrf": None, "expires": 0}

    @asynccontextmanager
    async def lifespan(app):
        with DataLock(settings.data_dir / "app.lock"):
            store = Store(settings.data_dir / "memory.db")
            sink = None
            if console_test:
                from .console_trace import ConsoleTrace

                sink = ConsoleTrace()
                sink.intro(settings.data_dir / "memory.db")
            service = Service(store, models or LocalModels(settings), settings, diagnostic_sink=sink)
            app.state.store, app.state.service = store, service
            from .chat.engine import ChatEngine

            app.state.chat = ChatEngine(service)
            app.state.chat.store.recover()
            if run_worker:
                service.start()
            else:
                store.expire()
                store.recover()
            try:
                yield
            finally:
                service.stop()
                store.checkpoint()

    app = FastAPI(
        title="Personal Memory Agent",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.bootstrap_token = bootstrap
    app.state.settings = settings

    from .evaluation_api import install

    install(app, settings, STATIC)

    @app.middleware("http")
    async def security(request, call_next):
        rid = identifier()
        request.state.request_id = rid
        host = request.headers.get("host", "")
        if host != f"127.0.0.1:{settings.port}":
            return error_response("INVALID_HOST", "허용하지 않은 접근입니다.", 403, rid)
        origin = request.headers.get("origin")
        if origin and origin != settings.origin:
            return error_response("INVALID_ORIGIN", "허용하지 않은 출처입니다.", 403, rid)
        if request.headers.get("sec-fetch-site") == "cross-site":
            return error_response("INVALID_ORIGIN", "허용하지 않은 출처입니다.", 403, rid)
        modifying = request.method not in {"GET", "HEAD"}
        api = request.url.path.startswith("/api/")
        if api and modifying and origin != settings.origin:
            return error_response("INVALID_ORIGIN", "로컬 화면에서 요청해 주세요.", 403, rid)
        if api and not (request.url.path == "/api/v1/session" and request.method == "POST"):
            with auth_lock:
                valid = (
                    auth["session"] is not None
                    and time.monotonic() < auth["expires"]
                    and secrets.compare_digest(
                        request.cookies.get("pma_session", ""), auth["session"]
                    )
                )
                csrf = auth["csrf"]
            if not valid:
                return error_response(
                    "SESSION_REQUIRED", "실행기에서 앱을 다시 열어 주세요.", 401, rid
                )
            if modifying and not secrets.compare_digest(
                request.headers.get("x-csrf-token", ""), csrf
            ):
                return error_response("CSRF_REQUIRED", "요청을 확인할 수 없습니다.", 403, rid)
        if api and modifying:
            if (
                request.method != "DELETE"
                and request.headers.get("content-type", "").split(";")[0] != "application/json"
            ):
                return error_response("JSON_REQUIRED", "JSON 요청이 필요합니다.", 422, rid)
            chunks, size = [], 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > 65536:
                    return error_response("INPUT_TOO_LARGE", "입력이 너무 큽니다.", 422, rid)
                chunks.append(chunk)
            request._body = b"".join(chunks)
        started = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            log.error("request_failed request_id=%s", rid)
            response = error_response(
                "INTERNAL_ERROR", "처리하지 못했습니다. 다시 시도하세요.", 500, rid
            )
        response.headers.update(
            {
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "Referrer-Policy": "no-referrer",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
                "X-Request-ID": rid,
            }
        )
        log.info(
            "request request_id=%s status=%s elapsed=%.3f",
            rid,
            response.status_code,
            time.monotonic() - started,
        )
        return response

    @app.exception_handler(AppError)
    async def app_error(request, exc):
        return error_response(
            exc.code, exc.message, exc.status, request.state.request_id, exc.retryable
        )

    @app.exception_handler(RequestValidationError)
    async def input_error(request, exc):
        return error_response(
            "INVALID_INPUT",
            "입력 길이·날짜·필수 항목을 확인해 주세요.",
            422,
            request.state.request_id,
        )

    @app.exception_handler(ValueError)
    async def model_error(request, exc):
        return error_response(
            "MODEL_INVALID_RESPONSE",
            "AI 응답을 검증하지 못했습니다. 다시 시도하세요.",
            503,
            request.state.request_id,
            True,
        )

    @app.exception_handler(requests.RequestException)
    async def network_error(request, exc):
        timeout = isinstance(exc, requests.Timeout)
        return error_response(
            "MODEL_TIMEOUT" if timeout else "MODEL_UNAVAILABLE",
            "로컬 AI 서버 연결 상태를 확인해 주세요.",
            504 if timeout else 503,
            request.state.request_id,
            True,
        )

    @app.exception_handler(sqlite3.Error)
    async def storage_error(request, exc):
        return error_response(
            "STORAGE_UNAVAILABLE",
            "저장소를 사용할 수 없습니다.",
            503,
            request.state.request_id,
            True,
        )

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.post("/api/v1/session")
    def session(data: SessionInput, response: Response):
        with auth_lock:
            if not auth["bootstrap"] or not secrets.compare_digest(data.token, auth["bootstrap"]):
                raise AppError("INVALID_TOKEN", "실행기에서 앱을 다시 열어 주세요.", 401)
            auth.update(
                bootstrap=None,
                session=secrets.token_urlsafe(32),
                csrf=secrets.token_urlsafe(32),
                expires=time.monotonic() + 43200,
            )
            response.set_cookie(
                "pma_session", auth["session"], httponly=True, samesite="strict", max_age=43200
            )
            return {"csrf": auth["csrf"]}

    @app.get("/api/v1/session")
    def current_session():
        return {"csrf": auth["csrf"], "evaluation_enabled": settings.evaluation_enabled}

    @app.get("/api/v1/health")
    def health():
        return {
            "app": "ready",
            "database": "ready",
            "models": app.state.service.models.health(),
            "records": app.state.store.stats(),
            "facts_pending": app.state.store.facts_pending(),
        }

    @app.get("/api/v1/records")
    def records(state: Literal["active", "trash"] = "active", cursor: str | None = None):
        app.state.store.expire()
        return app.state.store.list(state, cursor)

    @app.get("/api/v1/failures")
    def failures():
        return {"items": app.state.store.failed_jobs()}

    @app.post("/api/v1/failures/retry", status_code=202)
    def retry_failures(data: RetryFailedInput):
        return app.state.store.retry_failed(data.job_ids)

    @app.get("/api/v1/processing")
    def processing():
        result = app.state.store.processing_progress()
        result["worker_paused"] = app.state.service.worker_paused
        current = app.state.service.processing_status
        result["current"] = (
            {
                "job_id": current["job_id"],
                "phase": current["phase"],
                "elapsed_seconds": max(0, int(time.monotonic() - current["started"])),
                "chunks_total": current.get("chunks_total"),
                "chunks_completed": current.get("chunks_completed"),
                "chunk": current.get("chunk"),
            }
            if current
            else None
        )
        return result

    @app.post("/api/v1/records", status_code=202)
    def create(data: RecordInput):
        result = app.state.store.create(data.text, data.reference_time)
        app.state.service.trace("record_saved", text=data.text, **result)
        return result

    @app.get("/api/v1/records/{rid}")
    def get(rid: str):
        app.state.store.expire()
        return app.state.store.get(rid)

    @app.patch("/api/v1/records/{rid}", status_code=202)
    def update(rid: str, data: UpdateInput):
        return app.state.store.update(rid, data.expected_version, data.text, data.reference_time)

    @app.get("/api/v1/records/{rid}/revisions")
    def revisions(rid: str):
        app.state.store.expire()
        return {"items": app.state.store.revisions(rid)}

    @app.post("/api/v1/records/{rid}/revert", status_code=202)
    def revert(rid: str, data: RevertInput):
        return app.state.store.update(rid, data.expected_version, revert_version=data.version)

    @app.delete("/api/v1/records/{rid}", status_code=204)
    def trash(rid: str):
        app.state.store.trash(rid)

    @app.post("/api/v1/records/{rid}/restore", status_code=202)
    def restore(rid: str):
        return app.state.store.restore(rid)

    @app.delete("/api/v1/records/{rid}/purge", status_code=204)
    def purge(rid: str):
        app.state.store.purge(rid)

    @app.post("/api/v1/records/{rid}/retry", status_code=202)
    def retry(rid: str):
        return app.state.store.retry(rid)

    @app.get("/api/v1/jobs/{jid}")
    def job(jid: str):
        return app.state.store.job(jid)

    @app.get("/api/v1/relations")
    def relations(record_id: str | None = None):
        return {"items": app.state.store.links(record_id)}

    @app.delete("/api/v1/relations/{link_id}", status_code=204)
    def dismiss_relation(link_id: str):
        app.state.store.dismiss_link(link_id)

    @app.post("/api/v1/search")
    def search(data: QueryInput):
        return app.state.service.search(
            data.question, data.filters.model_dump() if data.filters else None, data.today,
            **({"correction_enabled": False} if not data.correction_enabled else {})
        )

    from .chat.api import router as chat_router

    app.include_router(chat_router(Input, QueryInput))
    from .memory.api import router as memory_router

    app.include_router(memory_router(Input))

    @app.post("/api/v1/answers")
    def answer(data: QueryInput):
        return app.state.service.answer(
            data.question, data.filters.model_dump() if data.filters else None, data.today,
            **({"correction_enabled": False} if not data.correction_enabled else {})
        )

    from .web_diagnostics import DiagnosticMiddleware

    app.add_middleware(DiagnosticMiddleware, settings=settings)
    return app
