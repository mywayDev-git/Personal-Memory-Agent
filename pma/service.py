import calendar
import logging
import re
import threading
import time
from contextlib import contextmanager
from copy import deepcopy
from datetime import date, datetime, timezone

import numpy as np
import requests

from scripts.memory_agent.diagnostics import failure
from scripts.memory_agent.postprocess import make_source_context
from scripts.memory_agent.validator import schema_errors

from .diagnostics import Stage
from .errors import AppError
from .facts import compatible, query_plan
from .models import ANSWER_SCHEMA, QUERY_SCHEMA, normalized_vectors
from .processing import extract_record
from .service_diagnostics import capture, filter_reason, traced_request

log = logging.getLogger("pma")


def temporal_bounds(value):
    """Conservative interval for a known time; never invent an event date."""
    if not value:
        return None
    try:
        if len(value) == 4:
            return date(int(value), 1, 1), date(int(value), 12, 31)
        if len(value) == 7:
            y, m = map(int, value.split("-"))
            return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])
        d = date.fromisoformat(value[:10])
        return d, d
    except TypeError, ValueError:
        return None


class Service:
    def __init__(self, store, models, settings, diagnostic_sink=None):
        self.store, self.models, self.settings = store, models, settings
        self.gate = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = None
        self.processing_status = None
        self.worker_paused = False
        self.worker_phase = "idle"
        self.diagnostic_sink = diagnostic_sink

    def trace(self, stage, **data):
        capture("legacy", stage, data)
        if self.diagnostic_sink is not None:
            try:
                self.diagnostic_sink(deepcopy({"stage": stage, **data}))
            except Exception:
                log.warning("diagnostic_sink_failed stage=%s", stage)

    @contextmanager
    def model_slot(self, wait=5):
        if not self.gate.acquire(timeout=wait):
            raise AppError(
                "MODEL_BUSY", "AI가 다른 기록을 처리 중입니다. 잠시 후 다시 시도하세요.", 429, True
            )
        try:
            yield
        finally:
            self.gate.release()

    def start(self):
        self.store.expire()
        self.store.recover()
        self.store.reindex_changed_model(self.settings.embedding_key)
        self.thread = threading.Thread(target=self.loop, name="pma-worker", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=self.settings.llm.timeout * 3 + 5)

    def loop(self):
        maintenance = 0
        while not self.stop_event.is_set():
            try:
                if self.worker_paused:
                    self.worker_phase = "health"
                    health = self.models.health()
                    if any(value != "ready" for value in health.values()):
                        self.stop_event.wait(5)
                        continue
                    self.worker_paused = False
                if time.monotonic() >= maintenance:
                    self.worker_phase = "maintenance"
                    self.store.expire()
                    maintenance = time.monotonic() + 3600
                self.run_one()
            except Exception as exc:
                # Contention is normal: leave queued work intact and try next iteration.
                if not (isinstance(exc, AppError) and exc.code == "MODEL_BUSY"
                        and self.worker_phase == "model_wait"):
                    from .worker_errors import describe_failure

                    details = describe_failure(exc, self.worker_phase)
                    log.error("worker_iteration_failed phase=%s code=%s type=%s",
                              self.worker_phase, details["code"], details["exception_type"])
                    self.trace("worker_failed", **details)
            self.stop_event.wait(0.5)

    def run_one(self):
        self.worker_phase = "model_wait"
        with self.model_slot(wait=0):
            self.worker_phase = "rebuild"
            self.store.rebuild_facts()
            self.worker_phase = "claim"
            job = self.store.claim()
            if not job:
                return False
            self.trace("processing_start", record_id=job["record_id"], text=job["text"])
            started = time.monotonic()
            self.processing_status = {"job_id": job["id"], "phase": "extract", "started": started}
            try:
                for attempt in range(2):
                    try:
                        context = make_source_context(job["record_id"], job["reference_time"])
                        self.processing_status = dict(self.processing_status, phase="extract")
                        result, metadata = extract_record(self, job, context)
                        self.processing_status = dict(self.processing_status, phase="embed")
                        self.trace("embedding_start", memories=result["memories"])
                        vectors = self.models.embed([m["content"] for m in result["memories"]])
                        if len(result["memories"]):
                            vectors = normalized_vectors(
                                vectors, len(result["memories"]), self.settings.embedding_dimensions
                            )
                        break
                    except requests.ConnectionError, requests.Timeout:
                        if attempt or self.stop_event.wait(1):
                            raise
                if self.stop_event.is_set():
                    return False
                self.processing_status = dict(self.processing_status, phase="save")
                self.store.publish(
                    job, result["memories"], vectors, self.settings.embedding_key, metadata
                )
                self.trace("processing_done", count=len(result["memories"]),
                           record_id=job["record_id"])
                log.info(
                    "job_finished job_id=%s elapsed=%.3f", job["id"], time.monotonic() - started
                )
            except Exception as exc:
                code, diagnostic = failure(
                    exc, (self.processing_status or {}).get("phase", "unknown")
                )
                diagnostic["elapsed_seconds"] = round(time.monotonic() - started, 3)
                diagnostic["processing"] = {
                    k: v
                    for k, v in (self.processing_status or {}).items()
                    if k not in {"started", "job_id"}
                }
                self.worker_phase = "failure_save"
                self.store.fail(job, code, diagnostic)
                from .worker_errors import describe_failure

                self.trace("processing_failed", record_id=job["record_id"],
                           **describe_failure(exc, diagnostic["stage"]))
                if code in {"MODEL_UNAVAILABLE", "MODEL_TIMEOUT", "MODEL_HTTP_ERROR"}:
                    self.worker_paused = True
                log.warning("job_failed job_id=%s code=%s", job["id"], code)
            finally:
                self.processing_status = None
            return True

    def _search(self, question, filters=None, today=None):
        today = today or datetime.now(timezone.utc).astimezone().date().isoformat()
        capture("begin", Stage.QUERY_UNDERSTANDING)
        try:
            understood = self.models.understand(question, today)
            if schema_errors(understood, QUERY_SCHEMA):
                raise ValueError("INVALID_QUERY")
        except (ValueError, requests.RequestException, AppError) as exc:
            understood = {"intent": "recall", "date_from": None, "date_to": None}
            self.trace("understand_fallback", error=type(exc).__name__)
        plan = query_plan(question, understood, today)
        self.trace("question", question=question, understood=understood, plan=plan)
        applied = dict(plan["filters"])
        if re.search(r"기준|당시|까지|이전", question) and applied["date_to"]:
            applied["date_from"] = None
        if filters is not None:
            applied.update(filters)
            if applied.get("date_to"):
                plan["needs_time_anchor"] = False
        capture("plan", plan, applied, filters)
        capture("begin", Stage.STRUCTURE_FILTER)
        start = date.fromisoformat(applied["date_from"]) if applied["date_from"] else None
        end = date.fromisoformat(applied["date_to"]) if applied["date_to"] else None
        if start and end and start > end:
            raise AppError("INVALID_DATE_RANGE", "시작일은 종료일보다 늦을 수 없습니다.")
        capture("begin", Stage.SNAPSHOT)
        generation, rows = self.store.snapshot(self.settings.embedding_key)
        if understood["intent"] == "aggregate" and re.search(
            r"총|몇\s*번|횟수|가장|최초|최후|제일|처음|마지막", question
        ):
            return generation, {"status": "unsupported_intent", "filters": applied, "results": []}
        capture("begin", Stage.STRUCTURE_FILTER)
        candidates = []
        locations = re.findall(r"([가-힣A-Za-z]+?)(?:에서|(?:에\s*)?\s+가서)", question)
        known_names = {
            value
            for r in rows
            if r["fact"]
            for value in (r["fact"]["actor"], r["fact"]["recipient"], r["fact"].get("counterparty"))
            if value and value != "self" and value in question
        }
        pending = sum(r["fact"] is None for r in rows)
        requested_objects = {
            r["fact"]["object_key"]
            for r in rows
            if r["fact"]
            and len(r["fact"]["object_key"]) >= 2
            and r["fact"]["object_key"] in question
        }
        capture("constraints", plan, locations, known_names, requested_objects)
        for row in rows:
            fact = row["fact"]
            if not fact or not compatible(
                fact, plan, on_exclude=filter_reason, diagnostic_id=row["id"]
            ):
                self.trace(
                    "excluded",
                    id=row["id"],
                    reason="facts_pending" if not fact else "relation_state_or_quantity",
                )
                continue
            if (
                plan["relation"] == "visit"
                and requested_objects
                and fact["object_key"] not in requested_objects
            ):
                self.trace("excluded", id=row["id"], reason="requested_object")
                continue
            if (
                plan["kind"] == "change"
                and re.search(r"취향|선호|좋아", question)
                and fact["relation"] not in {"prefer", "desire", "give"}
            ):
                self.trace("excluded", id=row["id"], reason="preference_change")
                continue
            if plan["kind"] == "activities" and fact["state"] in {
                "planned",
                "desire",
                "preference",
                "uncertain",
            }:
                self.trace("excluded", id=row["id"], reason="activity_state")
                continue
            if locations:
                parent = re.search(
                    r"([가-힣A-Za-z]+?)(?:에\s*(?:갔|다녀|가서)|\s*여행)", row["text"]
                )
                if not any(
                    loc in row["memory"]["content"] or (parent and loc == parent.group(1))
                    for loc in locations
                ):
                    self.trace("excluded", id=row["id"], reason="location")
                    continue
                capture("condition_pass", "place", row["id"])
            if known_names:
                roles = (
                    {fact["actor"]}
                    if plan["relation"] in {"desire", "prefer", "run"}
                    else {fact["actor"], fact["recipient"]}
                )
                if plan["kind"] in {"compare", "change"}:
                    roles = {fact["actor"], fact["recipient"]}
                if plan["relation"] not in {"desire", "prefer", "run"}:
                    roles.add(fact.get("counterparty"))
                source_review = fact.get("review_reasons") and any(
                    n in row["text"] for n in known_names
                )
                if not known_names & roles and not source_review:
                    self.trace("excluded", id=row["id"], reason="explicit_named_person")
                    continue
                capture("condition_pass", "person", row["id"])
            t = fact["event_time"]
            a, b = temporal_bounds(t.get("start")), temporal_bounds(t.get("end"))
            if start or end:
                if not a or t.get("certainty") == "uncertain":
                    self.trace("excluded", id=row["id"], reason="unknown_filtered_date")
                    continue
                low, high = a[0], b[1] if b else a[1]
                if (start and low < start) or (end and high > end):
                    self.trace("excluded", id=row["id"], reason="date_range")
                    continue
                capture("condition_pass", "time", row["id"])
            candidates.append(row)
        candidates.sort(
            key=lambda r: (
                r["memory"]["content"],
                r["fact"]["event_time"].get("start") or "",
                r["text"],
            )
        )
        self.trace("search_scope", total=len(rows), count=len(candidates), filters=applied)
        capture("filtered", rows, candidates, locations, known_names)
        if not candidates:
            capture("begin", Stage.SOURCE_VALIDATION)
            self.store.assert_generation(generation)
            return generation, {
                "status": "ok",
                "filters": applied,
                "results": [],
                "query_plan": plan,
                "facts_pending": pending,
                "connections": [],
            }
        capture("begin", Stage.VECTOR_RETRIEVAL)
        query = normalized_vectors(
            self.models.embed([question]), 1, self.settings.embedding_dimensions
        )[0]
        matrix = np.stack([np.frombuffer(r["vector"], dtype="<f4") for r in candidates])
        matrix = normalized_vectors(matrix, len(candidates), self.settings.embedding_dimensions)
        scores = matrix @ query
        vector_order = np.argsort(-scores, kind="stable")[:20].tolist()
        capture("retrieval", Stage.VECTOR_RETRIEVAL, candidates, vector_order, scores)
        capture("begin", Stage.KEYWORD_RETRIEVAL)
        terms = set(re.findall(r"[\w가-힣]+", question.casefold()))
        keyword = [
            sum(t in (r["memory"]["content"] + " " + r["text"]).casefold() for t in terms)
            for r in candidates
        ]
        keyword_order = sorted(
            (i for i, score in enumerate(keyword) if score),
            key=lambda i: (-keyword[i], candidates[i]["id"]),
        )[:20]
        self.trace("search_methods", terms=sorted(terms), vectors=len(vector_order),
                   keywords=len(keyword_order))
        capture("retrieval", Stage.KEYWORD_RETRIEVAL, candidates, keyword_order, keyword)
        capture("begin", Stage.RANK_FUSION)
        ranks = {}
        for component, order in (("vector", vector_order), ("keyword", keyword_order)):
            for rank, i in enumerate(order, 1):
                contribution = 1 / (60 + rank)
                ranks[i] = ranks.get(i, 0) + contribution
                capture("component", i, component, contribution)
        for i in ranks:
            bonus = sum(
                1 / 600
                for role, hint in plan["role_hints"].items()
                if candidates[i]["fact"].get(role) == hint["value"]
            )
            ranks[i] += bonus
            capture("component", i, "role", bonus)
        results = []
        # Structural matches are eligible independently of dense top-k. Stable ties
        # use content/time, never newly generated UUIDs or insertion order.
        if plan["relation"] != "other" or known_names:
            for i in range(len(candidates)):
                ranks[i] = ranks.get(i, 0) + 1 / 60
                capture("component", i, "structure", 1 / 60)
        order = sorted(
            ranks,
            key=lambda i: (
                -ranks[i],
                candidates[i]["memory"]["content"],
                candidates[i]["fact"]["event_time"].get("start") or "",
            ),
        )
        capture("fusion", candidates, order, ranks)
        for i in order[:24]:
            row = candidates[i]
            results.append(
                {
                    "id": row["id"],
                    "record_id": row["record_id"],
                    "version": row["version"],
                    "content": row["memory"]["content"],
                    "time": row["fact"]["event_time"],
                    "evidence": row["evidence"],
                    "fact": row["fact"],
                    "subject": row["memory"]["subject"],
                    "predicate": row["memory"]["predicate"],
                    "object": row["memory"]["object"],
                    "target": row["memory"]["target"],
                    "memory_type": row["memory"]["memory_type"],
                    "assertion_polarity": row["memory"]["assertion_polarity"],
                    "source_text": row["text"],
                    "reference_time": row["reference_time"],
                    "recorded_at": row["created_at"],
                    "score": ranks[i],
                }
            )
        if self.diagnostic_sink is not None:
            self.trace(
                "retrieval_merge",
                candidates=[
                    {"id": r["id"], "rank": i + 1, "score": r["score"]}
                    for i, r in enumerate(results)
                ],
            )
        capture("selection_input", results)
        if plan["kind"] in {"current", "change", "compare"}:
            results.sort(key=lambda r: (r["time"].get("start") or "", r["content"]), reverse=True)
        elif (
            plan["kind"] != "activities"
            and not (
                plan["relation"] == "visit"
                and requested_objects
                and all(r["fact"]["state"] in {"planned", "negated"} for r in results)
            )
            and plan["relation"]
            not in {
                "desire",
                "give",
                "receive",
                "prefer",
                "run",
                "conflict",
            }
            and hasattr(self.models, "select")
        ):
            capture("selecting")
            selected = self.models.select(question, results)
            allowed = {r["id"] for r in results}
            if not set(selected) <= allowed:
                raise ValueError("INVALID_SELECTION")
            results = [r for r in results if r["id"] in selected]
            self.trace(
                "selection", selected_ids=selected, excluded_ids=sorted(allowed - set(selected))
            )
        capture("limit_input", results)
        results = results[:8]
        capture("selected", results)
        selected_ids = {r["id"] for r in results}
        self.trace("evidence", ids=sorted(selected_ids))
        capture("begin", Stage.RELATION_LOOKUP)
        links = self.store.links(memory_ids=selected_ids)
        capture("relations", selected_ids, links)
        capture("begin", Stage.SOURCE_VALIDATION)
        self.store.assert_generation(generation)
        return generation, {
            "status": "ok",
            "filters": applied,
            "results": results,
            "query_plan": plan,
            "facts_pending": pending,
            "connections": links,
        }

    @traced_request
    def search(self, question, filters=None, today=None):
        with self.model_slot():
            response = self._search(question, filters, today)[1]
            self.trace("result", response=response)
            return response

    @traced_request
    def answer(self, question, filters=None, today=None):
        response = self._answer(question, filters, today)
        self.trace("result", response=response)
        return response

    def _answer(self, question, filters=None, today=None):
        with self.model_slot():
            generation, found = self._search(question, filters, today)
            if found.get("query_plan", {}).get("needs_time_anchor"):
                return {
                    **found,
                    "status": "insufficient_evidence",
                    "items": [],
                    "clarification": "당시가 어느 날짜나 사건을 뜻하는지 알려주세요.",
                    "validation": "unresolved_time_anchor",
                }
            if found["status"] == "unsupported_intent":
                return {**found, "items": []}
            if not found["results"]:
                return {**found, "status": "insufficient_evidence", "items": []}
            from .grounding import claims_supported, grounded_response

            self.trace("generation_start", status="running")
            capture(
                "policy", bool(hasattr(self.models, "review") and self.settings.answer_validation)
            )

            if hasattr(self.models, "review") and self.settings.answer_validation:
                from .answer_review import answer_found

                response = answer_found(self.models, question, found, self.trace)
                structured_answer = response.get("validation") == "structured"
            else:
                # Compatibility with existing injected gateways using verify()->bool.
                response = grounded_response(found)
                structured_answer = response is not None
                if response is None:
                    response = self.models.answer(question, found["results"])
                self.trace("answer", structured=structured_answer, response=response)
                if schema_errors(response, ANSWER_SCHEMA):
                    capture("validation", "schema", False)
                    raise ValueError("INVALID_ANSWER")
                capture("validation", "schema", True)
                allowed = {r["id"] for r in found["results"]}
                if (response["status"] == "answered" and not response["items"]) or any(
                    cid not in allowed for item in response["items"] for cid in item["citations"]
                ):
                    capture("validation", "citation", False, found["results"])
                    raise ValueError("INVALID_CITATION")
                capture("validation", "citation", True, found["results"])
                if response["status"] == "insufficient_evidence" and response["items"]:
                    raise ValueError("INVALID_ANSWER_STATE")
                attributes_supported = True
                if response["status"] == "answered":
                    attributes_supported = claims_supported(
                        response["items"], found["results"], found["query_plan"]
                    )
                    capture("validation", "attributes", attributes_supported, found["results"])
                if response["status"] == "answered" and not attributes_supported:
                    response = {
                        "status": "insufficient_evidence",
                        "items": [],
                        "validation": "rejected_attributes",
                    }
                if response["status"] == "answered" and not structured_answer:
                    try:
                        verified = hasattr(self.models, "verify") and self.models.verify(
                            question, found["results"], response["items"]
                        )
                    except (ValueError, requests.RequestException, AppError) as exc:
                        verified = False
                        self.trace(
                            "verification_error",
                            error=type(exc).__name__,
                            code=getattr(exc, "code", None),
                        )
                    self.trace("verification", supported=verified)
                    if not verified and (
                        hasattr(self.models, "verify") or found["query_plan"]["kind"] == "why"
                    ):
                        response = {
                            "status": "insufficient_evidence",
                            "items": [],
                            "validation": "rejected",
                        }
            # Extra fields are appended after the legacy answer schema validation.
            for item in response["items"]:
                item["claim_kind"] = "record"
                item["relation_ids"] = []
                if found["query_plan"]["kind"] == "compare":
                    linked = [
                        link["id"]
                        for link in found["connections"]
                        if link["kind"] == "desire_action"
                        and set(link["citations"]) <= set(item["citations"])
                    ]
                    if linked:
                        item["claim_kind"] = "inference"
                        item["relation_ids"] = linked
            response.setdefault(
                "validation", "structured" if structured_answer else "model_checked"
            )
            capture("begin", Stage.SOURCE_VALIDATION)
            self.store.assert_generation(generation)
            return {**found, **response}
