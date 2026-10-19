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
from .facts import compatible, mentions_person, query_plan
from .models import ANSWER_SCHEMA, QUERY_SCHEMA, normalized_vectors
from .processing import extract_record
from .query_correction import fuse as fuse_queries
from .query_correction import validate as validate_correction
from .search_explain import (
    condition_matches,
    failed_condition,
    keyword_matches_batch,
    keyword_query,
    keyword_weight,
    select_evidence,
)
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
        self.slot_condition = threading.Condition()
        self.foreground_waiters = 0
        self.worker_gate = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = None
        self.processing_status = None
        self.worker_paused = False
        self.worker_phase = "idle"
        self.diagnostic_sink = diagnostic_sink
        # A single bounded entry: no query text or model outputs are retained.
        self.vector_cache_bytes = 64 * 1024 * 1024
        self._vector_cache = None
        self._vector_cache_lock = threading.Lock()
    def trace(self, stage, **data):
        capture("legacy", stage, data)
        if self.diagnostic_sink is not None:
            try:
                self.diagnostic_sink(deepcopy({"stage": stage, **data}))
            except Exception:
                log.warning("diagnostic_sink_failed stage=%s", stage)

    @contextmanager
    def model_slot(self, wait=None, *, background=False, cancelled=None):
        if wait is None and not background:
            wait = getattr(getattr(self.settings, "llm", None), "timeout", 5)
        deadline = None if wait is None else time.monotonic() + wait
        with self.slot_condition:
            if not background:
                self.foreground_waiters += 1
            try:
                while True:
                    if (background and self.stop_event.is_set()) or (cancelled and cancelled()):
                        raise AppError("CANCELLED", "요청을 중단했습니다.", 409)
                    if not (background and self.foreground_waiters) and self.gate.acquire(False):
                        break
                    remaining = None if deadline is None else deadline - time.monotonic()
                    if remaining is not None and remaining <= 0:
                        raise AppError("MODEL_BUSY", "AI가 다른 기록을 처리 중입니다. 잠시 후 다시 시도하세요.", 429, True)
                    self.slot_condition.wait(0.1 if remaining is None else min(remaining, 0.1))
            finally:
                if not background:
                    self.foreground_waiters -= 1
                self.slot_condition.notify_all()
        try:
            yield
        finally:
            with self.slot_condition:
                self.gate.release()
                self.slot_condition.notify_all()



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
        with self.worker_gate:
            with self.model_slot(wait=0, background=True):
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
                extracted = False
                for attempt in range(2):
                    try:
                        context = make_source_context(job["record_id"], job["reference_time"])
                        self.processing_status = dict(self.processing_status, phase="extract")
                        if not extracted:
                            extract_started = time.monotonic()
                            try:
                                result, metadata = extract_record(self, job, context)
                            finally:
                                self.processing_metric("extract", time.monotonic() - extract_started)
                            extracted = True
                        self.processing_status = dict(self.processing_status, phase="embed")
                        self.trace("embedding_start", memories=result["memories"])
                        with self.background_model_slot():
                            embed_started = time.monotonic()
                            self.processing_metric("embed", embed_calls=1)
                            try:
                                vectors = self.models.embed([m["content"] for m in result["memories"]])
                            finally:
                                self.processing_metric("embed", time.monotonic() - embed_started)
                        if len(result["memories"]):
                            vectors = normalized_vectors(
                                vectors, len(result["memories"]), self.settings.embedding_dimensions
                            )
                        break
                    except (requests.ConnectionError, requests.Timeout) as exc:
                        # A timed-out extraction has not made progress on this
                        # chunk. Leave recovery to an explicit retry/config change.
                        if isinstance(exc, requests.ReadTimeout) and not extracted:
                            raise
                        if attempt or self.stop_event.wait(1):
                            raise
                        self.processing_metric("retry", retries=1)
                if self.stop_event.is_set():
                    return False
                self.processing_status = dict(self.processing_status, phase="save")
                save_started = time.monotonic()
                # Publishing changes the search generation: do not invalidate a
                # foreground answer that acquired its snapshot between calls.
                with self.background_model_slot():
                    self.store.publish(
                        job, result["memories"], vectors, self.settings.embedding_key, metadata
                    )
                self.processing_metric("save", time.monotonic() - save_started)
                self.trace("processing_done", count=len(result["memories"]),
                           record_id=job["record_id"])
                log.info(
                    "job_finished job_id=%s elapsed=%.3f", job["id"], time.monotonic() - started
                )
            except Exception as exc:
                if self.stop_event.is_set():
                    return False
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
                log.info("job_performance job_id=%s metrics=%s", job["id"],
                         (self.processing_status or {}).get("performance", {}))
                self.processing_status = None
            return True

    def _search(self, question, filters=None, today=None, *, defer_limit=False, selection_question=None, correction_enabled=True):
        today = today or datetime.now(timezone.utc).astimezone().date().isoformat()
        capture("begin", Stage.QUERY_UNDERSTANDING)
        try:
            understood = self.models.understand(question, today)
            understood = dict(understood)
            if schema_errors(understood, QUERY_SCHEMA):
                raise ValueError("INVALID_QUERY")
        except (TypeError, ValueError, requests.RequestException, AppError) as exc:
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
        if hasattr(self.store, "snapshot_for_owner"):
            generation, rows = self.store.snapshot_for_owner(self.settings.embedding_key, "local-account")
        else:
            generation, rows = self.store.snapshot(self.settings.embedding_key)
        correction = validate_correction(question, understood.get("corrections"), understood,
                                         today, rows, enabled=correction_enabled)
        correction.update(original_query=question, searched=False)
        corrected = correction["query"] if correction["status"] == "applied" else None
        if understood["intent"] == "aggregate" and re.search(
            r"총|몇\s*번|횟수|가장|최초|최후|제일|처음|마지막", question
        ):
            correction["reason"] = "unsupported_intent"
            return generation, {"status": "unsupported_intent", "filters": applied, "results": [],
                                "query_correction": correction}
        capture("begin", Stage.STRUCTURE_FILTER)
        candidates = []
        exclusions = []
        def excluded(row, reason):
            reason = str(reason)
            exclusions.append({
                "id": row["id"], "record_id": row["record_id"], "version": row["version"],
                "status": "excluded", "reason": reason,
                "conditions": failed_condition(reason, plan, applied, known_names, locations, requested_objects),
                "stages": {
                    "conditions": {"status": "not_run" if reason == "facts_pending" else "failed", "reason": reason},
                    "selection": {"status": "not_run"},
                    "answer": {"status": "not_run"},
                },
            })

        locations = [m[1] for m in re.finditer(r"([가-힣A-Za-z]+?)(?:에서|에\s+가서)", question)]
        known_names = {
            value
            for r in rows
            if r["fact"]
            for value in (r["fact"]["actor"], r["fact"]["recipient"], r["fact"].get("counterparty"), *r["fact"].get("participants", []))
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
            failure_reasons = []
            def record_failure(reason):
                failure_reasons.append(reason)
                filter_reason(reason)
            if not fact or not compatible(
                fact, plan, on_exclude=record_failure, diagnostic_id=row["id"]
            ):
                self.trace(
                    "excluded",
                    id=row["id"],
                    reason="facts_pending" if not fact else "relation_state_or_quantity",
                )
                excluded(row, failure_reasons[0] if failure_reasons else "facts_pending")
                continue
            if (
                plan["relation"] == "visit"
                and requested_objects
                and fact["object_key"] not in requested_objects
            ):
                self.trace("excluded", id=row["id"], reason="requested_object")
                excluded(row, "requested_object")
                continue
            if (
                plan["kind"] == "change"
                and re.search(r"취향|선호|좋아", question)
                and fact["relation"] not in {"prefer", "desire", "give"}
            ):
                self.trace("excluded", id=row["id"], reason="preference_change")
                excluded(row, "preference_change")
                continue
            if plan["kind"] == "activities" and fact["state"] in {
                "planned",
                "desire",
                "preference",
                "uncertain",
            }:
                self.trace("excluded", id=row["id"], reason="activity_state")
                excluded(row, "activity_state")
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
                    excluded(row, "location")
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
                    roles.update(fact.get("participants", []))
                source_review = fact.get("review_reasons") and any(
                    n in row["text"] for n in known_names
                )
                if plan["relation"] == "other":
                    source_review = source_review or any(
                        mentions_person(row["memory"]["content"], n)
                        and any(mentions_person(e["quote"], n) for e in row["evidence"])
                        for n in known_names
                    )
                if not known_names & roles and not source_review:
                    self.trace("excluded", id=row["id"], reason="explicit_named_person")
                    excluded(row, "explicit_named_person")
                    continue
                capture("condition_pass", "person", row["id"])
            t = fact["event_time"]
            a, b = temporal_bounds(t.get("start")), temporal_bounds(t.get("end"))
            if start or end:
                if not a or t.get("certainty") == "uncertain":
                    self.trace("excluded", id=row["id"], reason="unknown_filtered_date")
                    excluded(row, "unknown_filtered_date")
                    continue
                low, high = a[0], b[1] if b else a[1]
                if (start and low < start) or (end and high > end):
                    self.trace("excluded", id=row["id"], reason="date_range")
                    excluded(row, "date_range")
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
        term_specs, vocabulary = keyword_query(question, candidates)
        if not candidates:
            capture("begin", Stage.SOURCE_VALIDATION)
            self.store.assert_generation(generation)
            return generation, {
                "status": "ok",
                "filters": applied,
                "results": [],
                "query_plan": plan,
                "query_correction": correction,
                "search_keywords": [term["text"] for term in term_specs],
                "keyword_terms": term_specs,
                "search_audit": {"candidates": exclusions[:100], "excluded_count": len(exclusions), "truncated": len(exclusions) > 100},
                "facts_pending": pending,
                "connections": [],
            }
        capture("begin", Stage.VECTOR_RETRIEVAL)
        queries = [question]
        def query_index(text):
            if text not in queries:
                queries.append(text)
            return queries.index(text)
        corrected_index = query_index(corrected) if corrected else None
        try:
            query_vectors = normalized_vectors(
                self.models.embed(queries), len(queries), self.settings.embedding_dimensions
            )
        except (ValueError, requests.RequestException, AppError):
            if len(queries) == 1:
                raise
            if corrected:
                correction = {"status": "rejected", "query": question, "edits": [],
                              "reason": "embedding_failed", "original_query": question, "searched": False}
            corrected = None
            query_vectors = normalized_vectors(
                self.models.embed([question]), 1, self.settings.embedding_dimensions
            )
        query = query_vectors[0]
        matrix = self._candidate_matrix(generation, candidates)
        scores = matrix @ query
        vector_order = np.argsort(-scores, kind="stable")[:20].tolist()
        capture("retrieval", Stage.VECTOR_RETRIEVAL, candidates, vector_order, scores)
        capture("begin", Stage.KEYWORD_RETRIEVAL)
        terms = {term["text"] for term in term_specs}
        matches = keyword_matches_batch(candidates, term_specs, vocabulary)
        keyword = [sum(max((keyword_weight(m) for m in found if m["term"] == term), default=0) for term in terms) for found in matches]
        keyword_order = sorted(
            (i for i, score in enumerate(keyword) if score),
            key=lambda i: (-keyword[i], candidates[i]["id"]),
        )[:20]
        self.trace("search_methods", terms=sorted(terms), vectors=len(vector_order),
                   keywords=len(keyword_order))
        capture("retrieval", Stage.KEYWORD_RETRIEVAL, candidates, keyword_order, keyword)
        capture("begin", Stage.RANK_FUSION)
        corrected_vector_order, corrected_keyword_order = [], []
        corrected_matches = [[] for _ in candidates]
        corrected_scores = None
        corrected_keyword = [0 for _ in candidates]
        if corrected:
            correction["searched"] = True
            corrected_scores = matrix @ query_vectors[corrected_index]
            corrected_vector_order = np.argsort(-corrected_scores, kind="stable")[:20].tolist()
            corrected_terms, corrected_vocab = keyword_query(corrected, candidates)
            corrected_matches = keyword_matches_batch(candidates, corrected_terms, corrected_vocab)
            corrected_keyword = [sum(max((keyword_weight(m)
                for m in found if m["term"] == term["text"]), default=0)
                for term in corrected_terms) for found in corrected_matches]
            corrected_keyword_order = sorted((i for i, score in enumerate(corrected_keyword) if score),
                key=lambda i: (-corrected_keyword[i], candidates[i]["id"]))[:20]
        ranks = {}
        contributions = {}
        for component, order in (("vector", vector_order), ("keyword", keyword_order)):
            alternate = corrected_vector_order if component == "vector" else corrected_keyword_order
            merged = fuse_queries(order, alternate)
            contributions[component] = merged
            for i, contribution in merged.items():
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
                    "search_explanation": {
                        "query": question,
                        "query_correction": correction,
                        "corrected_retrieval": {
                            "query": corrected,
                            "keyword_matches": corrected_matches[i],
                            "semantic_rank": corrected_vector_order.index(i) + 1 if i in corrected_vector_order else None,
                            "keyword_rank": corrected_keyword_order.index(i) + 1 if i in corrected_keyword_order else None,
                            "semantic_score": float(corrected_scores[i]) if corrected_scores is not None else None,
                            "keyword_score": corrected_keyword[i],
                            "contributed": any(i in alt and (i not in orig or
                                0.8 / (61 + alt.index(i)) > 1 / (61 + orig.index(i)))
                                and 0.8 / (61 + alt.index(i)) == contributions[component].get(i)
                                for component, orig, alt in (("vector", vector_order, corrected_vector_order), ("keyword", keyword_order, corrected_keyword_order))),
                        },
                        "conditions": condition_matches(row, plan, applied, locations, known_names, requested_objects),
                        "keyword_matches": matches[i],
                        "methods": [name for name, ranking in (("keyword", keyword_order), ("semantic", vector_order)) if i in ranking] + (["structure"] if plan["relation"] != "other" or known_names else []),
                        "ranks": {"keyword": keyword_order.index(i) + 1 if i in keyword_order else None, "semantic": vector_order.index(i) + 1 if i in vector_order else None, "combined": order.index(i) + 1},
                        "scores": {"keyword": keyword[i], "semantic": float(scores[i]), "combined": ranks[i]},
                        "selection": {"status": "candidate", "reason": "combined_rank"},
                    },
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
        selection_pool = list(results)
        model_selected = None
        model_decisions = {}
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
            if hasattr(self.models, "select_explained"):
                model_decisions = self.models.select_explained(selection_question or question, results)
                selected = [mid for mid, decision in model_decisions.items() if decision["category"] not in {"irrelevant", "unverified_selection"}]
                for row in results:
                    row["search_explanation"]["model_assessment"] = model_decisions.get(row["id"])
            else:
                selected = self.models.select(selection_question or question, results)
            allowed = {r["id"] for r in results}
            if not set(selected) <= allowed:
                raise ValueError("INVALID_SELECTION")
            model_selected = set(selected)
            results = [r for r in results if r["id"] in selected]
            self.trace(
                "selection", selected_ids=selected, excluded_ids=sorted(allowed - set(selected))
            )
        capture("limit_input", results)
        evidence_limit = 24 if defer_limit else 8
        if plan["kind"] in {"current", "change", "compare"}:
            results = results[:evidence_limit]
            selection_reason = "event_time_order"
        else:
            results = select_evidence(results, limit=evidence_limit)
            selection_reason = "combined_rank"
        selected_ids = {r["id"] for r in results}
        audit_candidates = []
        for row in selection_pool:
            reason = "model_not_selected" if model_selected is not None and row["id"] not in model_selected else "evidence_limit" if row["id"] not in selected_ids else "model_selected" if model_selected is not None else selection_reason
            if row["id"] in model_decisions and reason in {"model_selected", "model_not_selected"}:
                reason = model_decisions[row["id"]]["category"]
            decision = {"status": "selected" if row["id"] in selected_ids else "excluded", "reason": reason}
            row["search_explanation"]["selection"] = decision
            for chosen in results:
                if chosen["id"] == row["id"]:
                    chosen["search_explanation"]["selection"] = decision
            audit_candidates.append({"id": row["id"], "record_id": row["record_id"], "version": row["version"], **decision, "methods": row["search_explanation"]["methods"], "ranks": row["search_explanation"]["ranks"], "conditions": [{"condition": c["condition"], "status": c["status"]} for c in row["search_explanation"]["conditions"]]})
        for candidate in audit_candidates:
            candidate["stages"] = {
                "conditions": {"status": "needs_review" if any(
                    c["status"] == "needs_review" for c in candidate["conditions"]
                ) else "passed"},
                "selection": {"status": candidate["status"], "reason": candidate["reason"], "limit": evidence_limit},
                "answer": {"status": "not_run"},
            }
        capture("selected", results, evidence_limit)
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
            "query_correction": correction,
            "search_keywords": sorted(terms),
            "keyword_terms": term_specs,
            "search_audit": {"candidates": audit_candidates + exclusions[:100], "excluded_count": len(exclusions), "truncated": len(exclusions) > 100, "eligible_count": len(candidates), "candidate_limit_count": max(0, len(order) - 24)},
            "facts_pending": pending,
            "connections": links,
        }

    @traced_request
    def search(self, question, filters=None, today=None, *, correction_enabled=True):
        with self.model_slot():
            response = self._search(question, filters, today, correction_enabled=correction_enabled)[1]
            self.trace("result", response=response)
            return response


    @traced_request
    def answer(self, question, filters=None, today=None, *, correction_enabled=True):
        response = self._answer(question, filters, today, correction_enabled=correction_enabled)
        self.trace("result", response=response)
        return response

    def _answer(self, question, filters=None, today=None, *, correction_enabled=True):
        with self.model_slot():
            generation, found = self._search(question, filters, today, correction_enabled=correction_enabled)
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
                return {**found, "status": "insufficient_evidence", "items": [],
                        **({"clarification": "질문의 이름이나 검색 표현을 다시 확인해 주세요."}
                           if found.get("query_correction", {}).get("status") == "rejected" else {})}
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

    def search_in_model_slot(self, question, filters=None, today=None, *,
                             defer_limit=False, selection_question=None, correction_enabled=True):
        """Search adapter for orchestrators already holding model_slot().

        Does not acquire a second semaphore; uses exactly the public search core.
        """
        return self._search(question, filters, today, defer_limit=defer_limit,
                            selection_question=selection_question, correction_enabled=correction_enabled)


    @contextmanager
    def background_model_slot(self):
        started = time.monotonic()
        with self.model_slot(background=True):
            self.processing_metric("model_wait", time.monotonic() - started)
            yield


    def processing_metric(self, stage, seconds=0, **counts):
        status = self.processing_status
        if status is None:
            return
        metrics = status.setdefault("performance", {})
        metrics[stage + "_seconds"] = metrics.get(stage + "_seconds", 0) + seconds
        for key, value in counts.items():
            metrics[key] = metrics.get(key, 0) + value


    def _candidate_matrix(self, generation, candidates):
        key = (generation, self.settings.embedding_key, self.settings.embedding_dimensions,
               tuple(row["id"] for row in candidates))
        with self._vector_cache_lock:
            if self._vector_cache is not None and self._vector_cache[0] == key:
                return self._vector_cache[1]
            # Release the old generation/subset before allocating a replacement.
            self._vector_cache = None
            matrix = np.stack([np.frombuffer(row["vector"], dtype="<f4") for row in candidates])
            matrix = normalized_vectors(matrix, len(candidates), self.settings.embedding_dimensions)
            # Include a conservative allowance for retained candidate identifiers.
            if matrix.nbytes + len(candidates) * 128 <= self.vector_cache_bytes:
                matrix.setflags(write=False)
                self._vector_cache = (key, matrix)
            return matrix

