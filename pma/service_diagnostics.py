"""Passive service observations. All preparation is guarded and request-local."""

import time
from contextlib import nullcontext
from contextvars import ContextVar
from functools import wraps

from .diagnostics import Reason, Source, Stage, Status, current_trace, start_trace

_OBSERVATION = ContextVar("pma_service_observation", default=None)
_EXCLUSIONS = {
    "facts_pending": Reason.FACT_MISSING,
    "requested_object": Reason.REQUESTED_OBJECT,
    "preference_change": Reason.PREFERENCE_CHANGE,
    "activity_state": Reason.ACTIVITY_STATE,
    "location": Reason.PLACE_MISMATCH,
    "explicit_named_person": Reason.PERSON_MISMATCH,
    "unknown_filtered_date": Reason.TIME_UNKNOWN,
    "date_range": Reason.TIME_MISMATCH,
}
_VALIDATION_REASONS = {
    "rejected": Reason.VERIFICATION_REJECTED,
    "rejected_attributes": Reason.UNSUPPORTED_ATTRIBUTES,
    "unresolved_time_anchor": Reason.UNRESOLVED_TIME_ANCHOR,
}


def capture(method, *args, **kwargs):
    observer = _OBSERVATION.get()
    if observer is not None:
        try:
            getattr(observer, method)(*args, **kwargs)
        except Exception:
            try:
                observer.trace.recording_failed = True
            except Exception:
                pass


def filter_reason(reason):
    capture("compatibility", reason)


def traced_request(function):
    @wraps(function)
    def wrapped(self, *args, **kwargs):
        existing = current_trace()
        enabled = getattr(self.settings, "diagnostics", False)
        if existing is None and not enabled:
            return function(self, *args, **kwargs)
        scope = (
            nullcontext(existing)
            if existing is not None
            else start_trace(enabled=True, path=getattr(self.settings, "diagnostics_path", None))
        )
        with scope as trace:
            try:
                observer = Observation(trace) if trace is not None else None
            except Exception:
                observer = None
            token = _OBSERVATION.set(observer)
            try:
                result = function(self, *args, **kwargs)
            except Exception as exc:
                capture("error", exc)
                raise
            else:
                capture("finish", result, function.__name__)
                return result
            finally:
                _OBSERVATION.reset(token)

    return wrapped


class Observation:
    def __init__(self, trace):
        self.trace = trace
        self.active_stage = None
        self.started = time.perf_counter()
        self.stage_started = self.started
        self.excluded = {}
        self.components = {}
        self.pool = []
        self.before_limit = set()
        self.model_limited = set()
        self.last_reason = Reason.UNKNOWN
        self.understood = True
        self.selection_called = False
        self.model_selected = None
        self.retrieved = False
        self.retry_count = 0
        self.link_start = 0
        self.query_start = 0

    def refs(self, ids):
        return [self.trace.memory_ref(mid) for mid in ids]

    def begin(self, stage):
        self.active_stage = stage
        self.stage_started = time.perf_counter()
        if stage == Stage.RELATION_LOOKUP:
            self.link_start = self.trace.event_count
        if stage == Stage.QUERY_UNDERSTANDING:
            self.query_start = self.trace.event_count

    def emit(self, stage, **fields):
        if stage == self.active_stage:
            fields.setdefault("duration_ms", (time.perf_counter() - self.stage_started) * 1000)
        self.trace.record_event(stage, **fields)

    def compatibility(self, reason):
        self.last_reason = reason

    def policy(self, review):
        self.emit(
            Stage.ANSWER_POLICY,
            status=Status.RUNNING,
            executed=True,
            policy_path="review" if review else "legacy",
            retry_count=0,
        )

    def condition_pass(self, name, mid):
        from .facts_diagnostics import condition

        condition(
            self.trace,
            Stage.QUERY_CONDITION,
            name,
            True,
            phase="compared",
            applied=True,
            passed=True,
            reason=Reason.CONDITION_MATCHED,
            source="unknown" if name == "time" else "rule",
            date_certain=True if name == "time" else None,
            candidates=[{"memory_ref": self.trace.memory_ref(mid), "status": "included"}],
        )

    def constraints(self, plan, locations, names, objects):
        from .facts_diagnostics import condition

        for name, present in (
            ("place", bool(locations)),
            ("person", bool(names)),
            ("object", plan["relation"] == "visit" and bool(objects)),
        ):
            condition(
                self.trace, Stage.QUERY_CONDITION, name, present, phase="resolved", applied=False
            )

    def legacy(self, stage, data):
        if stage == "understand_fallback":
            self.understood = False
        elif stage == "excluded":
            reason = (
                self.last_reason
                if data["reason"] == "relation_state_or_quantity"
                else _EXCLUSIONS[data["reason"]]
            )
            self.excluded.setdefault(data["id"], reason)
            condition_name = {
                "location": "place",
                "explicit_named_person": "person",
                "requested_object": "object",
                "unknown_filtered_date": "time",
                "date_range": "time",
                "preference_change": "state",
                "activity_state": "state",
            }.get(data["reason"])
            if condition_name:
                from .facts_diagnostics import condition

                condition(
                    self.trace,
                    Stage.QUERY_CONDITION,
                    condition_name,
                    True,
                    phase="compared",
                    applied=True,
                    passed=False,
                    reason=reason,
                    source="unknown" if condition_name == "time" else "rule",
                    candidates=[
                        {
                            "memory_ref": self.trace.memory_ref(data["id"]),
                            "status": "excluded",
                            "reason": reason,
                        }
                    ],
                )
        elif stage == "selection":
            self.model_selected = list(data["selected_ids"])
        elif stage == "generation_start":
            self.begin(Stage.ANSWER_GENERATION)
        elif stage in {"answer", "answer_repair"}:
            self.emit(
                Stage.ANSWER_GENERATION,
                model_called=not data.get("structured", False),
                retry_count=self.retry_count,
                citation_refs=self.citations(data["response"]),
            )
            self.begin(Stage.ANSWER_VALIDATION)
        elif stage == "verification":
            self.emit(
                Stage.ANSWER_VALIDATION,
                validation_type="llm",
                executed=True,
                supported=bool(data["supported"]),
                retry_count=data.get("attempt", 0),
                status=Status.PASSED if data["supported"] else Status.FAILED,
            )
        elif stage in {"verification_error", "answer_error"}:
            self.emit(
                Stage.ANSWER_VALIDATION
                if stage == "verification_error"
                else Stage.ANSWER_GENERATION,
                status=Status.ERROR,
                reason=Reason.MODEL_ERROR,
            )
        elif stage == "repair_start":
            self.retry_count = data["attempt"]
            self.begin(Stage.ANSWER_GENERATION)

    def plan(self, plan, applied, explicit):
        from .facts_diagnostics import resolved

        resolved(self.trace, plan, applied, explicit)
        from .facts_diagnostics import condition

        source = Source.RULE if not self.understood else Source.UNKNOWN
        if self.understood and any(
            event["stage"] == Stage.MODEL_UNDERSTANDING
            and event.get("model_called")
            and event["status"] == Status.COMPLETED
            for event in self.trace.events[self.query_start :]
        ):
            source = Source.LLM

        for name, key in (
            ("role_hint", "role_hints"),
            ("requested_slots", "requested_slots"),
            ("intent", "intent"),
        ):
            condition(
                self.trace,
                Stage.QUERY_CONDITION,
                name,
                bool(plan[key]),
                phase="resolved",
                applied=False,
                source=source,
                reason=Reason.HINT_ONLY
                if name != "intent" and plan[key]
                else Reason.CONDITION_PRESENT
                if plan[key]
                else Reason.CONDITION_ABSENT,
            )
        self.emit(
            Stage.QUERY_UNDERSTANDING,
            status=Status.COMPLETED if self.understood else Status.FAILED,
            parse_succeeded=self.understood,
            model_called=True,
            needs_time_anchor=bool(plan["needs_time_anchor"]),
            has_time_condition=bool(applied.get("date_from") or applied.get("date_to")),
            has_relation_condition=plan["relation"] != "other",
            has_quantity_condition=plan["distance_m"] is not None,
            has_entity_condition=bool(plan["role_hints"]),
            has_person_condition=bool(plan["self"] or plan["role_hints"]),
            # The aggregate combines sources; detailed condition events are separate.
            source=Source.UNKNOWN,
        )

    def filtered(self, rows, candidates, locations, names):
        self.emit(
            Stage.STRUCTURE_FILTER,
            input_count=len(rows),
            output_count=len(candidates),
            has_place_condition=bool(locations),
            has_person_condition=bool(names),
            candidates=[
                dict(
                    memory_ref=self.trace.memory_ref(r["id"]),
                    status=Status.EXCLUDED if r["id"] in self.excluded else Status.INCLUDED,
                    reason=self.excluded.get(r["id"]),
                )
                for r in rows
            ],
        )

    def retrieval(self, stage, rows, order, scores):
        self.retrieved = True
        self.emit(
            stage,
            input_count=len(rows),
            output_count=len(order),
            top_k=20,
            candidates=[
                dict(
                    memory_ref=self.trace.memory_ref(rows[i]["id"]),
                    rank=rank,
                    score=float(scores[i]),
                    status=Status.INCLUDED,
                )
                for rank, i in enumerate(order, 1)
            ],
        )

    def component(self, index, name, value):
        self.components.setdefault(index, dict(vector=0, keyword=0, role=0, structure=0))[name] = (
            value
        )

    def fusion(self, rows, order, ranks):
        self.emit(
            Stage.RANK_FUSION,
            input_count=len(order),
            output_count=min(24, len(order)),
            top_k=24,
            candidates=[
                dict(
                    memory_ref=self.trace.memory_ref(rows[i]["id"]),
                    rank=rank,
                    score=ranks[i],
                    score_components=self.components[i],
                    status=Status.INCLUDED if rank <= 24 else Status.EXCLUDED,
                    reason=None if rank <= 24 else Reason.CANDIDATE_LIMIT,
                )
                for rank, i in enumerate(order, 1)
            ],
        )

    def selection_input(self, results):
        self.pool = [r["id"] for r in results]
        self.begin(Stage.EVIDENCE_SELECTION)

    def selecting(self):
        self.selection_called = True

    def limit_input(self, results):
        self.before_limit = {r["id"] for r in results}

    def selection_limit(self, ids):
        self.model_limited.update(ids)

    def selected(self, results):
        ids = [r["id"] for r in results]
        selected = set(ids)
        self.emit(
            Stage.EVIDENCE_SELECTION,
            input_count=len(self.pool),
            output_count=len(ids),
            top_k=8,
            model_called=self.selection_called,
            evidence_refs=self.refs(self.pool),
            model_selected_refs=self.refs(self.model_selected)
            if self.model_selected is not None
            else None,
            candidates=[
                dict(memory_ref=self.trace.memory_ref(mid), status=Status.SELECTED) for mid in ids
            ]
            + [
                dict(
                    memory_ref=self.trace.memory_ref(mid),
                    status=Status.EXCLUDED,
                    reason=Reason.EVIDENCE_LIMIT
                    if mid in self.before_limit or mid in self.model_limited
                    else Reason.MODEL_NOT_SELECTED,
                )
                for mid in self.pool
                if mid not in selected
            ],
        )

    def relations(self, ids, links):
        # Store owns the event; injected gateways without instrumentation need a summary.
        if not self.trace.has_event(Stage.RELATION_LOOKUP, self.link_start):
            self.emit(
                Stage.RELATION_LOOKUP,
                input_count=len(ids),
                output_count=len(links),
                evidence_refs=self.refs(sorted(ids)),
                relation_refs=[self.trace.relation_ref(r["id"]) for r in links],
            )

    def validation(self, kind, passed, evidence=None):
        self.emit(
            Stage.ANSWER_VALIDATION,
            validation_type=kind,
            executed=True,
            passed=bool(passed),
            status=Status.PASSED if passed else Status.FAILED,
            evidence_refs=self.refs(r["id"] for r in evidence) if evidence is not None else None,
        )

    def citations(self, response):
        return self.refs(
            dict.fromkeys(
                cid for item in response.get("items", []) for cid in item.get("citations", [])
            )
        )

    def finish(self, response, operation):
        if not self.retrieved:
            for stage in (Stage.VECTOR_RETRIEVAL, Stage.KEYWORD_RETRIEVAL):
                self.trace.record_event(
                    stage, status=Status.NOT_EXECUTED, reason=Reason.RETRIEVAL_NOT_EXECUTED
                )
        reason = _VALIDATION_REASONS.get(response.get("validation"))
        if response["status"] == "unsupported_intent":
            reason = Reason.UNSUPPORTED_INTENT
        if operation == "search":
            status = Status.COMPLETED
        elif response.get("clarification"):
            status = Status.CLARIFICATION
        elif response["status"] == "answered":
            status = Status.ANSWER
        else:
            status = Status.ABSTENTION
            reason = reason or Reason.INSUFFICIENT_EVIDENCE
        if operation == "answer" and response.get("results") and not response.get("clarification"):
            self.emit(
                Stage.ANSWER_VALIDATION,
                status=Status.FAILED if reason else Status.COMPLETED,
                reason=reason,
                retry_count=self.retry_count,
                regenerated=self.retry_count > 0,
                citation_refs=self.citations(response),
            )
        self.trace.record_event(
            Stage.FINAL_DECISION,
            status=status,
            reason=reason,
            citation_refs=self.citations(response),
            duration_ms=(time.perf_counter() - self.started) * 1000,
        )

    def error(self, exc):
        code = getattr(exc, "code", None)
        if code is None and exc.args and type(exc.args[0]) is str:
            code = exc.args[0]
        reason = (
            {
                "INVALID_CITATION": Reason.INVALID_CITATION,
                "INVALID_ANSWER": Reason.INVALID_RESPONSE,
                "INVALID_ANSWER_STATE": Reason.INVALID_RESPONSE,
                "INVALID_SELECTION": Reason.INVALID_RESPONSE,
                "INVALID_DATE_RANGE": Reason.INVALID_DATE_RANGE,
                "SOURCE_CHANGED": Reason.SOURCE_CHANGED,
                "MODEL_BUSY": Reason.MODEL_BUSY,
            }.get(code, Reason.UNKNOWN)
            if type(code) is str
            else Reason.UNKNOWN
        )
        if self.active_stage:
            self.emit(self.active_stage, status=Status.ERROR, reason=reason)
        self.trace.record_event(
            Stage.FINAL_DECISION,
            status=Status.ERROR,
            reason=reason,
            duration_ms=(time.perf_counter() - self.started) * 1000,
        )
