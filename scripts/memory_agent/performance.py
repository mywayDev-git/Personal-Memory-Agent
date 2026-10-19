"""Content-free, request-local latency measurements with exclusive stage times."""

import time
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps

_profile = ContextVar("latency_profile", default=None)


class Profile:
    def __init__(self):
        self.started = time.perf_counter()
        self.stack = []
        self.stages = {}
        self.counts = {}

    def snapshot(self, outcome="completed"):
        now = time.perf_counter()
        stages = {name: dict(row) for name, row in self.stages.items()}
        for index, (started, children, name) in enumerate(self.stack):
            elapsed = now - started
            active_child = now - self.stack[index + 1][0] if index + 1 < len(self.stack) else 0
            row = stages.setdefault(name, {
                "calls": 0, "failures": 0, "inclusive_seconds": 0.0, "exclusive_seconds": 0.0,
            })
            row["calls"] += 1
            row["inclusive_seconds"] += elapsed
            row["exclusive_seconds"] += max(0.0, elapsed - children - active_child)
        return {
            "schema_version": 1,
            "outcome": outcome,
            "elapsed_seconds": round(time.perf_counter() - self.started, 6),
            "stages": {name: {key: round(value, 6) if isinstance(value, float) else value
                              for key, value in row.items()}
                       for name, row in stages.items()},
            "counts": dict(self.counts),
        }


@contextmanager
def profile_request():
    profile = Profile()
    token = _profile.set(profile)
    try:
        yield profile
    finally:
        _profile.reset(token)


def count(name, amount=1):
    profile = _profile.get()
    if profile is not None:
        profile.counts[name] = profile.counts.get(name, 0) + amount


def current_snapshot():
    profile = _profile.get()
    return profile.snapshot() if profile is not None else None


@contextmanager
def measure(name):
    profile = _profile.get()
    if profile is None:
        yield
        return
    frame = [time.perf_counter(), 0.0, name]
    profile.stack.append(frame)
    failed = False
    try:
        yield
    except BaseException:
        failed = True
        raise
    finally:
        elapsed = time.perf_counter() - frame[0]
        profile.stack.pop()
        if profile.stack:
            profile.stack[-1][1] += elapsed
        row = profile.stages.setdefault(name, {
            "calls": 0, "failures": 0, "inclusive_seconds": 0.0, "exclusive_seconds": 0.0,
        })
        row["calls"] += 1
        row["failures"] += int(failed)
        row["inclusive_seconds"] += elapsed
        row["exclusive_seconds"] += max(0.0, elapsed - frame[1])


def measured(name):
    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            with measure(name):
                return function(*args, **kwargs)
        return wrapped
    return decorate
