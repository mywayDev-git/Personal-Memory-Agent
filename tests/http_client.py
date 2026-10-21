"""Real in-process ASGI requests without Windows loopback socketpair startup.

Python's Windows Proactor loop normally creates a TCP socketpair just to wake
the loop from other threads. Some isolated Windows environments block that
connection before any HTTP request reaches the ASGI app. These tests need no
network I/O. A short timer wakes the normal Proactor scheduler instead; the
ASGI transport, lifespan, middleware, workers and response handling stay real.
"""

import asyncio
import sys

from fastapi.testclient import TestClient as StarletteTestClient

if sys.platform == "win32":
    class InProcessLoop(asyncio.ProactorEventLoop):
        def _make_self_pipe(self):
            self._ssock = self._csock = None

        def _loop_self_reading(self, future=None):
            pass

        def _close_self_pipe(self):
            # No socket or self-reader was created by this test loop.
            pass

        def _write_to_self(self):
            # call_soon_threadsafe still appends to the normal ready queue.
            # The next bounded timer tick dispatches it, without a TCP wakeup.
            pass

        def __init__(self):
            super().__init__()
            self.call_soon(self._tick)

        def _tick(self):
            self.call_later(.005, self._tick)


class TestClient(StarletteTestClient):
    __test__ = False

    def __init__(self, *args, **kwargs):
        if sys.platform == "win32" and kwargs.get("backend", "asyncio") == "asyncio":
            options = dict(kwargs.get("backend_options") or {})
            options.setdefault("loop_factory", InProcessLoop)
            kwargs["backend_options"] = options
        super().__init__(*args, **kwargs)
