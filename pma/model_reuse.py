"""Request-local reuse of an identical relevance decision, never verification."""

import hashlib
import json
import os
from copy import deepcopy
from functools import wraps

from scripts.memory_agent.llm_client import check_request_active, current_request_budget
from scripts.memory_agent.performance import count


def reuse_selection(function):
    @wraps(function)
    def wrapped(self, question, evidence):
        budget = current_request_budget()
        settings = getattr(self, "settings", None)
        enabled = getattr(settings, "selection_reuse", None)
        if enabled is None:
            enabled = getattr(settings, "request_reuse", False)
        if budget is None or not enabled or not evidence:
            return function(self, question, evidence)
        check_request_active()
        # Match the complete model-visible data plus full immutable sources.
        # Rank/score/audit changes are not model inputs, so cannot change this policy.
        payload = [question, self.compact_evidence(evidence),
                   [row.get("search_explanation", {}).get("query_correction") for row in evidence
                    if row.get("search_explanation", {}).get("query_correction", {}).get("status") == "applied"],
                   [{k: row.get(k) for k in ("id", "record_id", "revision_id", "version", "source_text")}
                    for row in evidence], repr(settings), os.getenv("PMA_GENERATION_REVISION", "unconfigured")]
        key = (function, type(self), hashlib.sha256(json.dumps(
            payload, ensure_ascii=False, sort_keys=True, default=str
        ).encode()).digest())
        if key in budget.selection_decisions:
            budget.selection_decisions.move_to_end(key)
            count("selection_cache_hits")
            return deepcopy(budget.selection_decisions[key])
        result = function(self, question, evidence)
        # Exceptions, cancellation, and expired requests never populate the cache.
        check_request_active()
        if all(value.get("category") != "unverified_selection" for value in result.values()):
            budget.selection_decisions[key] = deepcopy(result)
            if len(budget.selection_decisions) > 64:
                budget.selection_decisions.popitem(last=False)
        return result
    return wrapped
