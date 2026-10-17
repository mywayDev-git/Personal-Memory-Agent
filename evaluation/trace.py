"""Bounded, allowlisted diagnostics; source text never enters the collector."""

import json


class TraceCollector:
    def __init__(self, max_bytes=262144):
        self.max_bytes = max_bytes
        self.bytes_used = 0
        self.events = []
        self.truncated = False

    def __call__(self, event):
        try:
            safe = {"stage": str(event["stage"]), "status": event.get("status", "completed")}
            for key in ("ids", "selected_ids", "excluded_ids", "id", "supported", "duration_ms"):
                if key in event:
                    safe[key] = event[key]
            if "candidates" in event:
                safe["candidates"] = [
                    {k: c[k] for k in ("id", "rank", "score") if k in c}
                    for c in event["candidates"]
                ]
            size = len(json.dumps(safe, allow_nan=False).encode())
            if self.bytes_used + size > self.max_bytes:
                self.truncated = True
                return
            self.events.append(safe)
            self.bytes_used += size
        except ValueError, TypeError, KeyError:
            self.truncated = True
