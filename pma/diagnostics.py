"""Opt-in, fail-open search traces containing only allowlisted metadata.

No model, database, settings, or application imports. Callers pass observations
from their existing execution path; this module never re-runs search or filters.
elapsed_ms is time since trace creation; duration_ms is an optional measured
stage duration. Neither denotes model latency unless the caller measured it.
"""

import json
import math
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

SCHEMA_VERSION = "pma.search_trace.v1"


class Stage(StrEnum):
    TRACE_SUMMARY = "trace_summary"
    QUERY_UNDERSTANDING = "query_understanding"
    QUERY_PLAN = "query_plan"
    QUERY_CONDITION = "query_condition"
    DATE_PARSING = "date_parsing"
    FACT_COMPARISON = "fact_comparison"
    GROUNDING_CHECK = "grounding_check"
    REVIEW_CHECK = "review_check"
    ANSWER_POLICY = "answer_policy"
    HTTP_REQUEST = "http_request"
    SNAPSHOT = "snapshot"
    SOURCE_VALIDATION = "source_validation"
    STRUCTURE_FILTER = "structure_filter"
    VECTOR_RETRIEVAL = "vector_retrieval"
    KEYWORD_RETRIEVAL = "keyword_retrieval"
    RANK_FUSION = "rank_fusion"
    EVIDENCE_SELECTION = "evidence_selection"
    EVIDENCE_SELECTION_BATCH = "evidence_selection_batch"
    EVIDENCE_SELECTION_MERGE = "evidence_selection_merge"
    MODEL_UNDERSTANDING = "model_understanding"
    MODEL_ANSWER = "model_answer"
    MODEL_REVIEW = "model_review"
    MODEL_VERIFY = "model_verify"
    RELATION_LOOKUP = "relation_lookup"
    ANSWER_GENERATION = "answer_generation"
    ANSWER_VALIDATION = "answer_validation"
    FINAL_DECISION = "final_decision"


class Reason(StrEnum):
    FACT_MISSING = "fact_missing"
    RELATION_MISMATCH = "relation_mismatch"
    PERSON_MISMATCH = "person_mismatch"
    PLACE_MISMATCH = "place_mismatch"
    TIME_UNKNOWN = "time_unknown"
    TIME_MISMATCH = "time_mismatch"
    QUANTITY_MISMATCH = "quantity_mismatch"
    STATUS_MISMATCH = "status_mismatch"
    REQUESTED_OBJECT = "requested_object"
    PREFERENCE_CHANGE = "preference_change"
    ACTIVITY_STATE = "activity_state"
    CANDIDATE_LIMIT = "candidate_limit"
    EVIDENCE_LIMIT = "evidence_limit"
    MODEL_NOT_SELECTED = "model_not_selected"
    INVALID_RESPONSE = "invalid_response"
    MODEL_ERROR = "model_error"
    INVALID_CITATION = "invalid_citation"
    UNSUPPORTED_ATTRIBUTES = "unsupported_attributes"
    VERIFICATION_REJECTED = "verification_rejected"
    UNRESOLVED_TIME_ANCHOR = "unresolved_time_anchor"
    UNSUPPORTED_INTENT = "unsupported_intent"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    RETRIEVAL_NOT_EXECUTED = "retrieval_not_executed"
    NOT_OBSERVED = "not_observed"
    UNKNOWN = "unknown"
    INVALID_DATE_RANGE = "invalid_date_range"
    SOURCE_CHANGED = "source_changed"
    MODEL_BUSY = "model_busy"
    CONDITION_PRESENT = "condition_present"
    CONDITION_ABSENT = "condition_absent"
    CONDITION_MATCHED = "condition_matched"
    HINT_ONLY = "hint_only"
    COMPARISON_BYPASS = "comparison_bypass"
    INCOMPLETE_ANSWER = "incomplete_answer"
    EXCESSIVE_ABSTENTION = "excessive_abstention"


class Status(StrEnum):
    COMPLETED = "completed"
    RUNNING = "running"
    INCLUDED = "included"
    EXCLUDED = "excluded"
    SELECTED = "selected"
    NOT_SELECTED = "not_selected"
    NOT_EXECUTED = "not_executed"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    UNKNOWN = "unknown"
    ANSWER = "answer"
    CLARIFICATION = "clarification"
    ABSTENTION = "abstention"


class Source(StrEnum):
    RULE = "rule"
    LLM = "llm"
    EXPLICIT_INPUT = "explicit_input"
    UNKNOWN = "unknown"


_CURRENT = ContextVar("pma_search_trace", default=None)
_WRITE_LOCK = threading.Lock()  # In-process threads only; not an inter-process file lock.
_COUNTS = frozenset(
    {"input_count", "output_count", "retry_count", "batch_index", "top_k", "http_status"}
)
_FLAGS = frozenset(
    {
        "executed",
        "passed",
        "supported",
        "parse_succeeded",
        "needs_time_anchor",
        "has_entity_condition",
        "has_time_condition",
        "has_relation_condition",
        "has_quantity_condition",
        "has_person_condition",
        "has_place_condition",
        "has_negation_condition",
        "has_status_condition",
        "regenerated",
        "model_called",
        "batched",
        "date_certain",
        "truncated",
        "applied",
        "present",
        "negation_present",
    }
)
_CANDIDATE_FLAGS = frozenset({"has_fact", "has_embedding", "has_record"})
_LABELS = {
    "policy_path": frozenset({"legacy", "review", "structured"}),
    "condition": frozenset(
        {
            "relation",
            "time",
            "date_from",
            "date_to",
            "time_anchor",
            "person",
            "place",
            "object",
            "quantity",
            "state",
            "negation",
            "role_hint",
            "requested_slots",
            "intent",
        }
    ),
    "relation_type": frozenset(
        {
            "desire",
            "give",
            "receive",
            "prefer",
            "run",
            "visit",
            "eat",
            "conflict",
            "cancel",
            "other",
        }
    ),
    "query_kind": frozenset(
        {"why", "change", "compare", "when", "current", "recall", "activities"}
    ),
    "operator": frozenset({"ge", "gt", "le", "lt", "eq"}),
    "phase": frozenset({"generated", "resolved", "compared"}),
}
_COMPONENTS = ("vector", "keyword", "role", "structure")
_VALIDATIONS = frozenset(
    {
        "schema",
        "citation",
        "attributes",
        "quantity",
        "color",
        "role",
        "relation",
        "rule",
        "llm",
        "structured",
        "unknown",
    }
)


def _enum(value, enum):
    if not isinstance(value, (str, enum)):
        return None
    try:
        return enum(value).value
    except ValueError:
        return None


def _number(value, *, nonnegative=False):
    # Do not call arbitrary __float__/__str__ methods on model or source objects.
    if type(value) not in (int, float) or not math.isfinite(value):
        return None
    return value if not nonnegative or value >= 0 else None


class SearchTrace:
    """One request's safe event buffer and in-memory ID mapping.

    events returns a detached copy. Raw ID mappings are never serialized. A
    reference must have been issued by this trace and for the correct ID kind.
    Limits bound diagnostic memory; truncation means absence is not evidence of
    exclusion. Ordinary collector/storage errors are swallowed, never logged
    with source-containing exception messages.
    """

    def __init__(self, path=None, *, max_events=4096, max_bytes=4 * 1024 * 1024):
        self.trace_id = uuid4().hex
        self._started = time.perf_counter()
        self._path = path
        self._lock = threading.RLock()
        self._events = []
        self._ids = {"memory": {}, "record": {}, "relation": {}}
        self._refs = {"memory": set(), "record": set(), "relation": set()}
        self._max_events = max(1, max_events)
        self._max_bytes = max(1024, max_bytes)
        self._bytes = 0
        self._written = 0
        self._closed = False
        self.truncated = False
        self.recording_failed = False
        self.storage_failed = False

    @property
    def events(self):
        with self._lock:
            return deepcopy(self._events)

    @property
    def event_count(self):
        with self._lock:
            return len(self._events)

    def has_event(self, stage, after=0):
        with self._lock:
            return any(e["stage"] == stage for e in self._events[after:])

    def _reference(self, kind, raw_id):
        try:
            if type(raw_id) is not str or not raw_id or len(raw_id) > 1024:
                return None
            with self._lock:
                mapping = self._ids[kind]
                if raw_id in mapping:
                    return mapping[raw_id]
                if self._closed:
                    return None
                if len(mapping) >= 65536:
                    self._truncate()
                    return None
                ref = f"{kind}-{self.trace_id}-{len(mapping) + 1}"
                mapping[raw_id] = ref
                self._refs[kind].add(ref)
                return ref
        except Exception:
            self.recording_failed = True
            return None

    def memory_ref(self, memory_id):
        return self._reference("memory", memory_id)

    def lookup_ref(self, kind, raw_id):
        """Read-only evaluation binding lookup; never allocate an unseen identity."""
        with self._lock:
            return self._ids.get(kind, {}).get(raw_id)

    def record_ref(self, record_id):
        return self._reference("record", record_id)

    def relation_ref(self, relation_id):
        return self._reference("relation", relation_id)

    def _valid_ref(self, value, kind):
        return type(value) is str and value in self._refs[kind]

    def _candidate(self, candidate):
        if type(candidate) is not dict:
            return None
        safe = {}
        for kind in self._refs:
            key = f"{kind}_ref"
            if self._valid_ref(candidate.get(key), kind):
                safe[key] = candidate[key]
        if not safe:
            return None
        for key, enum in (("status", Status), ("reason", Reason)):
            value = _enum(candidate.get(key), enum)
            if value is not None:
                safe[key] = value
        rank = candidate.get("rank")
        if type(rank) is int and 0 < rank < 2**63:
            safe["rank"] = rank
        score = _number(candidate.get("score"))
        if score is not None:
            safe["score"] = score
        components = candidate.get("score_components")
        if type(components) is dict:
            safe["score_components"] = {
                key: value
                for key in _COMPONENTS
                if (value := _number(components.get(key))) is not None
            }
        for key in _CANDIDATE_FLAGS:
            if type(candidate.get(key)) is bool:
                safe[key] = candidate[key]
        return safe

    def _truncate(self):
        self.truncated = True
        if self._events:
            self._events[-1]["truncated"] = True

    def record_event(self, stage, **fields):
        try:
            stage = _enum(stage, Stage)
            if stage is None:
                return
            with self._lock:
                if self._closed:
                    return
                if len(self._events) >= self._max_events:
                    self._truncate()
                    return
                elapsed = _number(fields.get("elapsed_ms"), nonnegative=True)
                event = dict(
                    schema_version=SCHEMA_VERSION,
                    trace_id=self.trace_id,
                    stage=stage,
                    event_sequence=len(self._events) + 1,
                    status=_enum(fields.get("status", Status.COMPLETED), Status)
                    or Status.UNKNOWN.value,
                    elapsed_ms=elapsed
                    if elapsed is not None
                    else (time.perf_counter() - self._started) * 1000,
                )
                for key in _COUNTS:
                    value = fields.get(key)
                    if key in fields and (
                        value is None or type(value) is int and 0 <= value < 2**63
                    ):
                        event[key] = value
                if event["status"] == Status.NOT_EXECUTED:
                    event.update(input_count=None, output_count=None)
                for key in _FLAGS:
                    if type(fields.get(key)) is bool:
                        event[key] = fields[key]
                duration = _number(fields.get("duration_ms"), nonnegative=True)
                if duration is not None:
                    event["duration_ms"] = duration
                for key, enum in (
                    ("reason", Reason),
                    ("reason_code", Reason),
                    ("unobserved_reason", Reason),
                    ("source", Source),
                ):
                    value = _enum(fields.get(key), enum)
                    if value is not None:
                        event[key] = value
                value = fields.get("validation_type")
                if type(value) is str and value in _VALIDATIONS:
                    event["validation_type"] = value
                for key, allowed in _LABELS.items():
                    value = fields.get(key)
                    if type(value) is str and value in allowed:
                        event[key] = value
                for key, kind in (
                    ("citation_refs", "memory"),
                    ("evidence_refs", "memory"),
                    ("model_selected_refs", "memory"),
                    ("relation_refs", "relation"),
                    ("record_refs", "record"),
                ):
                    values = fields.get(key)
                    if key in fields and values is None:
                        event[key] = None
                    elif type(values) in (list, tuple):
                        event[key] = [v for v in values[:4096] if self._valid_ref(v, kind)]
                        if len(values) > 4096:
                            event["truncated"] = self.truncated = True
                candidates = fields.get("candidates")
                if type(candidates) in (list, tuple):
                    event["candidates"] = [
                        safe
                        for candidate in candidates[:4096]
                        if (safe := self._candidate(candidate)) is not None
                    ]
                    if len(candidates) > 4096:
                        event["truncated"] = self.truncated = True
                size = len(json.dumps(event, allow_nan=False).encode("utf-8"))
                if self._bytes + size > self._max_bytes:
                    self._truncate()
                    return
                self._bytes += size
                self._events.append(event)
        except Exception:
            self.recording_failed = True

    def write_jsonl(self):
        """Append unflushed events only; no path means no filesystem interaction.

        No directories are created. Parent path errors are handled as storage
        failures. The process-wide lock prevents concurrent thread interleaving.
        """
        try:
            if self._path is None or self._path == "":
                return True
            with self._lock:
                pending = self._events[self._written :]
                if not pending:
                    return True
                payload = "".join(json.dumps(e, allow_nan=False) + "\n" for e in pending)
                with _WRITE_LOCK, Path(self._path).open("a", encoding="utf-8") as stream:
                    stream.write(payload)
                self._written = len(self._events)
                return True
        except Exception:
            self.storage_failed = True
            return False

    def finish_trace(self):
        try:
            with self._lock:
                if self._closed:
                    return
                self._closed = True
                # One reserved summary beyond the buffer limit makes loss visible
                # even when the preceding event was already flushed (or none fit).
                if self.truncated or self.recording_failed:
                    self._events.append(
                        dict(
                            schema_version=SCHEMA_VERSION,
                            trace_id=self.trace_id,
                            stage=Stage.TRACE_SUMMARY.value,
                            event_sequence=len(self._events) + 1,
                            status=Status.UNKNOWN.value,
                            elapsed_ms=(time.perf_counter() - self._started) * 1000,
                            truncated=self.truncated,
                            recording_failed=self.recording_failed,
                        )
                    )
                self.write_jsonl()
        except Exception:
            self.storage_failed = True


def current_trace():
    return _CURRENT.get()


@contextmanager
def start_trace(*, enabled=False, path=None):
    """New isolated scope; nested disabled scopes temporarily suppress collection."""
    trace = None
    if enabled:
        try:
            trace = SearchTrace(path=path)
        except Exception:
            pass
    token = _CURRENT.set(trace)
    try:
        yield trace
    finally:
        _CURRENT.reset(token)
        if trace is not None:
            try:
                trace.finish_trace()
            except Exception:
                pass


def record_event(stage, **fields):
    trace = _CURRENT.get()
    if trace is not None:
        try:
            trace.record_event(stage, **fields)
        except Exception:
            pass


def record_candidates(stage, candidates, **fields):
    """Candidates must contain issued refs, never raw memory/record IDs."""
    if _CURRENT.get() is not None:
        record_event(stage, candidates=candidates, **fields)
