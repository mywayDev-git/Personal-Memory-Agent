"""Search provenance and deterministic, corpus-wide evidence selection."""

import os
import re
from copy import deepcopy
from functools import lru_cache

from .search_expressions import (
    ALIASES,
    PARTICLES,
    TOKEN,
    alias_parts,
    canonical_word,
    fold,
)
from .search_expressions import (
    canonical_query as canonical_query,
)
from .search_expressions import (
    keyword_weight as keyword_weight,
)

STOP = {"언제", "어디", "누구", "무엇", "어떤", "어떻게", "왜", "알려줘", "했어", "있어", "기록", "검색"}
VERBS = {
    "갔다": "가다",
    "갔어": "가다",
    "갔던": "가다",
    "갔는지": "가다",
    "취소했다": "취소하다",
    "취소했어": "취소하다",
    "취소한": "취소하다",
    "달렸다": "달리다",
    "달렸어": "달리다",
    "달린": "달리다",
    "받았다": "받다",
    "받았어": "받다",
    "받은": "받다",
    "줬다": "주다",
    "줬어": "주다",
    "주었다": "주다",
    "좋아한다": "좋아하다",
    "좋아해": "좋아하다",
}


def normalize(word, vocabulary):
    word = fold(word)
    equivalent = canonical_word(word)
    if equivalent != word or word in ALIASES:
        return equivalent
    if word in VERBS:
        return VERBS[word]
    for suffix in PARTICLES:
        if word.endswith(suffix):
            stem = word[: -len(suffix)]
            # Single-character particles are ambiguous (e.g. 고양이).
            if len(stem) >= 2 and (len(suffix) > 1 or stem in vocabulary):
                return stem
    return word


def keyword_query(question, rows):
    vocabulary = {fold(t) for t in TOKEN.findall(question)}
    for row in rows:
        vocabulary.update(fold(t) for t in TOKEN.findall(row["text"] + " " + row["memory"]["content"]))
    vocabulary.update(normalize(token, set()) for token in list(vocabulary))
    tokens = [fold(t) for t in TOKEN.findall(question)]
    terms = sorted({
        token for index, token in enumerate(tokens)
        if token not in STOP
        # The dependent noun in "알 수 있나요" is not a topic keyword.
        # Keep standalone 수 and other meaningful one-character words searchable.
        and not (
            token == "수" and index + 1 < len(tokens)
            and tokens[index + 1].startswith(("있", "없"))
        )
    })
    specs, seen = [], set()
    for term in terms:
        normalized = normalize(term, vocabulary)
        if normalized in seen:
            continue
        seen.add(normalized)
        specs.append({"text": alias_parts(term)[0] or term, "normalized": normalized})
    return specs, vocabulary


def keyword_matches(row, terms, vocabulary, *, normalization_cache=None):
    # Vocabulary is fixed for a single retrieval pass. The caller must provide a
    # fresh cache for another vocabulary (including the corrected-query pass).
    def normalized(word):
        if normalization_cache is None:
            return normalize(word, vocabulary)
        key = fold(word)
        value = normalization_cache.get(key)
        if value is None:
            value = normalize(key, vocabulary)
            if len(normalization_cache) < 16384:
                normalization_cache[key] = value
        return value

    matches = []
    for field, text in (("source_text", row["text"]), ("content", row["memory"]["content"])):
        tokens = list(TOKEN.finditer(text))
        for term in terms:
            exact = [match for match in tokens if fold(match.group()) == term["text"]]
            for match in exact:
                matches.append(
                    {
                        "term": term["text"],
                        "kind": "exact",
                        "field": field,
                        "start": match.start(),
                        "end": match.end(),
                        "quote": match.group(),
                    }
                )
            if not exact:
                for match in tokens:
                    if normalized(match.group()) == term["normalized"]:
                        matches.append(
                            {
                                "term": term["text"],
                                "kind": "normalized",
                                "field": field,
                                "start": match.start(),
                                "end": match.end(),
                                "quote": match.group(),
                            }
                        )
    return matches


def python_keyword_matches_batch(rows, terms, vocabulary):
    cache = {}
    return [keyword_matches(row, terms, vocabulary, normalization_cache=cache) for row in rows]


@lru_cache(maxsize=1)
def _native_matcher():
    try:
        try:
            from . import _keyword_native_expressions as module
        except ImportError:
            from . import _keyword_native as module
        return module.match_batch if getattr(module, "TOKENIZER_VERSION", 0) >= 2 else None
    except (ImportError, OSError):
        # The optional binary is interpreter/platform specific. Source-only and
        # CPU-only installations keep the same Python matching implementation.
        return None


def keyword_matches_batch(rows, terms, vocabulary):
    backend = os.environ.get("PMA_KEYWORD_BACKEND", "auto").strip().lower()
    if backend not in {"auto", "python", "cpp"}:
        raise ValueError("PMA_KEYWORD_BACKEND must be auto, python, or cpp")
    if backend != "python":
        matcher = _native_matcher()
        if matcher is not None:
            return matcher(rows, terms, vocabulary, normalize)
        if backend == "cpp":
            raise RuntimeError("C++ keyword matcher is unavailable; build it or use PMA_KEYWORD_BACKEND=python")
    return python_keyword_matches_batch(rows, terms, vocabulary)


def condition_matches(row, plan, applied, locations, names, objects):
    fact = row["fact"]
    checks = []

    def add(key, value):
        checks.append({"condition": key, "status": "matched", "value": value})

    if plan["relation"] != "other" and plan["kind"] not in {"compare", "change"}:
        add("relation", fact["relation"])
    if locations:
        add(
            "place",
            [loc for loc in locations if loc in row["memory"]["content"] or loc in row["text"]],
        )
    if names:
        roles = {fact.get("actor"), fact.get("recipient"), fact.get("counterparty"), *fact.get("participants", [])}
        checks.append(
            {
                "condition": "person",
                "status": "needs_review" if fact.get("review_reasons") or not names & roles else "matched",
                "value": sorted(
                    names & roles
                )
                or sorted(n for n in names if n in row["text"]),
            }
        )
    if applied.get("date_from") or applied.get("date_to"):
        add("time", fact["event_time"])
    if plan["distance_m"] is not None:
        add("quantity", fact.get("distance_m", []))
    if plan["relation"] == "visit" and objects:
        add("object", fact["object_key"])
    if not fact.get("review_reasons") and (
        plan.get("event_listing") or (plan["relation"] == "run" and not plan.get("execution_check"))
    ):
        add("state", fact["state"])
    if (
        not fact.get("review_reasons")
        and plan["self"]
        and plan["relation"] in {"run", "give", "receive"}
    ):
        add("self", "self")
    return checks


def failed_condition(reason, plan, applied, names, locations, objects):
    """Store the requested constraint, never values copied from excluded records."""
    constraints = {
        "relation_mismatch": ("relation", plan["relation"]),
        "person_mismatch": ("self", "self"),
        "explicit_named_person": ("person", sorted(names)),
        "location": ("place", locations),
        "place_mismatch": ("place", locations),
        "requested_object": ("object", sorted(objects)),
        "preference_change": ("relation", ["prefer", "desire", "give"]),
        "activity_state": ("state", "실행된 활동"),
        "status_mismatch": ("state", "planned" if plan.get("planned") and not plan.get("event_listing") else "observed"),
        "quantity_mismatch": ("quantity", {"amount": plan.get("distance_m"), "operator": plan.get("operator", "eq")}),
    }
    if reason in {"unknown_filtered_date", "date_range", "time_unknown", "time_mismatch"}:
        key, expected = "time", {"start": applied.get("date_from"), "end": applied.get("date_to")}
    elif reason in constraints:
        key, expected = constraints[reason]
    else:
        return []
    return [{"condition": key, "status": "failed", "expected": expected, "reason": reason}]


def select_evidence(rows, limit=8, prefer_recent=False):
    """Compare all candidates; penalize repeated source/state evidence, not late batches."""
    unique = {}
    for row in rows:
        key = row["id"]
        if key not in unique or row.get("score", 0) > unique[key].get("score", 0):
            unique[key] = deepcopy(row)
    pending = list(unique.values())
    selected, seen_sources, covered = [], set(), set()
    while pending and len(selected) < limit:

        def priority(row):
            fact = row.get("fact") or {}
            coverage = (fact.get("relation"), fact.get("state"))
            assessment = (row.get("search_explanation", {}).get("model_assessment") or {}).get(
                "category"
            )
            base = row.get("score", 0) * {
                "direct_answer": 1.4,
                "conflicting_evidence": 1.4,
                "supporting_context": 0.8,
            }.get(assessment, 1)
            # Same source and same event state contributes less new evidence.
            adjusted = base * (
                0.55 if row["record_id"] in seen_sources and coverage in covered else 1
            )
            event = (row.get("time") or fact.get("event_time") or {}).get("start") or ""
            digits = re.sub(r"[^0-9]", "", event)[:8].ljust(8, "0")
            recent = int(digits) if prefer_recent else 0
            return (-recent, -adjusted, row.get("content", ""), row["record_id"], row["id"])

        pending.sort(key=priority)
        row = pending.pop(0)
        fact = row.get("fact") or {}
        coverage = (fact.get("relation"), fact.get("state"))
        reason = (
            "event_time_order"
            if prefer_recent
            else "coverage_and_rank"
            if selected and coverage not in covered
            else "combined_rank"
        )
        row.setdefault("search_explanation", {})["final_selection"] = {
            "status": "selected",
            "reason": reason,
        }
        selected.append(row)
        seen_sources.add(row["record_id"])
        covered.add(coverage)
    return selected
