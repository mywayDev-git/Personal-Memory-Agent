"""Bounded, in-memory reuse of exact interpretation inputs, never answer reviews."""

import hashlib
import inspect
import json
import os
import re
import time
from collections import OrderedDict
from functools import wraps
from threading import Lock

from scripts.memory_agent.llm_client import check_request_active
from scripts.memory_agent.performance import count

MAX_BYTES = 512 * 1024
MAX_ENTRIES = 64
TTL_SECONDS = 1800
_entries = OrderedDict()
_bytes = 0
_lock = Lock()


def context_history(messages):
    """The exact history read by the resolver, excluding transport/request state."""
    return [{"question": m["question"], "response": m["response"]} for m in messages
            if m["state"] == "completed" and m["response"] and not m.get("error_code")][-6:]


def clear_interpretations():
    global _bytes
    with _lock:
        _entries.clear()
        _bytes = 0


def cache_info():
    with _lock:
        return {"entries": len(_entries), "value_bytes": _bytes,
                "max_value_bytes": MAX_BYTES, "ttl_seconds": TTL_SECONDS}


def reuse_interpretation(kind):
    """Only validated interpretations/proposals; never answers or reviews."""
    if kind not in {"question", "context", "proposal"}:
        raise ValueError("INVALID_INTERPRETATION_KIND")

    def decorate(function):
        signature = inspect.signature(function)

        @wraps(function)
        def wrapped(self, *args, **kwargs):
            global _bytes
            settings = self.settings if kind == "question" else self.service.settings
            revision = os.getenv("PMA_GENERATION_REVISION", "unconfigured")
            # A server-default alias alone cannot identify a model replacement.
            if (not getattr(settings, "interpretation_reuse", False)
                    or not re.fullmatch(r"[a-fA-F0-9]{64}", revision)
                    or settings.llm.temperature != 0):
                return function(self, *args, **kwargs)
            check_request_active()
            bound = signature.bind(self, *args, **kwargs)
            bound.apply_defaults()
            inputs = dict(bound.arguments)
            inputs.pop(next(iter(signature.parameters)))
            if kind in {"context", "proposal"}:
                session = inputs["session"]
                # These are all session fields read by resolve; never use a
                # conversation ID alone as a substitute for its actual contents.
                inputs["session"] = {"history": context_history(session["messages"]),
                                     "evidence": session["evidence"]}
                inputs["scope"] = [session.get("owner"), session.get("owner_id")]
                if kind == "proposal":
                    from .chat.engine import RESOLVE_PROMPT, RESOLVE_SCHEMA
                    from .chat.automatic import NEXT_PROMPT
                    policy = [RESOLVE_PROMPT, RESOLVE_SCHEMA, NEXT_PROMPT,
                              repr(getattr(self.models, "settings", None))]
                else:
                    policy = [self.models.__class__.__module__, self.models.__class__.__qualname__,
                          repr(getattr(self.models, "settings", None)),
                          function.__globals__["RESOLVE_PROMPT"], function.__globals__["RESOLVE_SCHEMA"],
                          function.__globals__["AMBIGUITY_PROMPT"], function.__globals__["AMBIGUITY_SCHEMA"]]
            else:
                policy = [self.__class__.__module__, self.__class__.__qualname__]
            # Hash full inputs, immutable source versions, user data-directory
            # scope, model configuration and policy. No prompts/sources in keys.
            key = hashlib.sha256(json.dumps(
                [kind, function.__module__, function.__qualname__, inspect.getsource(function),
                 repr(settings), revision, policy, inputs], ensure_ascii=False,
                sort_keys=True, default=str).encode()).digest()
            now = time.monotonic()
            with _lock:
                for old_key, (created, value) in list(_entries.items()):
                    if now - created >= TTL_SECONDS:
                        _bytes -= len(value)
                        del _entries[old_key]
                entry = _entries.get(key)
                if entry is not None:
                    _entries.move_to_end(key)
                    value = json.loads(entry[1])
            if entry is not None:
                # JSON round-trip makes every caller's result independent.
                count(f"{kind}_interpretation_cache_hits")
                check_request_active()
                return (value[0], value[1]) if kind == "context" else value
            count(f"{kind}_interpretation_cache_misses")
            result = function(self, *args, **kwargs)
            check_request_active()
            # Ambiguity needs its normal clarification path, never a cached
            # approval. Failures, cancellations and invalid results are not saved.
            if kind == "context" and result[0].get("needs_clarification"):
                return result
            if kind == "proposal" and (result is None or result["context"].get("needs_clarification")):
                return result
            encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode()
            if len(encoded) > MAX_BYTES // 4:
                return result
            with _lock:
                prior = _entries.pop(key, None)
                if prior is not None:
                    _bytes -= len(prior[1])
                _entries[key] = (time.monotonic(), encoded)
                _bytes += len(encoded)
                while _bytes > MAX_BYTES or len(_entries) > MAX_ENTRIES:
                    _, (_, value) = _entries.popitem(last=False)
                    _bytes -= len(value)
            return result

        return wrapped
    return decorate
