"""ASGI request scope outside authentication; no request/response bodies are read."""

from time import perf_counter

from .diagnostics import Reason, Stage, start_trace


class DiagnosticMiddleware:
    def __init__(self, app, settings):
        self.app, self.settings = app, settings

    async def __call__(self, scope, receive, send):
        if (
            not self.settings.diagnostics
            or scope["type"] != "http"
            or scope.get("method") != "POST"
            or scope.get("path") not in {"/api/v1/search", "/api/v1/answers"}
        ):
            return await self.app(scope, receive, send)
        with start_trace(enabled=True, path=self.settings.diagnostics_path) as trace:
            started = perf_counter()
            status = None
            completed = False

            async def observed_send(message):
                nonlocal status, completed
                if message["type"] == "http.response.start":
                    status = message["status"]
                await send(message)
                if message["type"] == "http.response.body" and not message.get("more_body", False):
                    completed = True

            try:
                return await self.app(scope, receive, observed_send)
            finally:
                if trace is not None:
                    try:
                        trace.record_event(
                            Stage.HTTP_REQUEST,
                            status="completed" if completed and status < 400 else "error",
                            http_status=status,
                            executed=True,
                            reason=Reason.UNKNOWN if not completed else None,
                            duration_ms=(perf_counter() - started) * 1000,
                        )
                    except Exception:
                        trace.recording_failed = True
