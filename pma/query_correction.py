"""Bounded retrieval-only spelling edits. Never infer entities from search hits."""

import re

from .facts import query_plan

# Deliberately small: unknown words are not automatically declared misspelled.
NOUNS = frozenset("내용 회의 기록 여행 일정 약속 예약 자료 문서 업무 프로젝트 보고서 음식 운동".split())
EDIT_SCHEMA = {
    "type": "array", "maxItems": 2,
    "items": {
        "type": "object", "additionalProperties": False,
        "required": ["start", "end", "before", "after", "kind"],
        "properties": {
            "start": {"type": "integer", "minimum": 0},
            "end": {"type": "integer", "minimum": 1},
            "before": {"type": "string", "minLength": 1, "maxLength": 40},
            "after": {"type": "string", "minLength": 1, "maxLength": 40},
            "kind": {"enum": ["spelling", "spacing"]},
        },
    },
}


def near(a, b):
    """At most one syllable edit (including an adjacent transposition)."""
    if a == b:
        return False
    if len(a) == len(b):
        changed = [i for i in range(len(a)) if a[i] != b[i]]
        return len(changed) == 1 or (len(changed) == 2 and
            changed[1] == changed[0] + 1 and
            a[changed[0]:changed[1] + 1] == b[changed[0]:changed[1] + 1][::-1])
    short, long = sorted((a, b), key=len)
    return len(long) == len(short) + 1 and any(
        long[:i] + long[i + 1:] == short for i in range(len(long)))


def validate(question, edits, understood, today, rows, *, enabled=True):
    result = {"status": "none", "query": question, "edits": [], "reason": None}
    if not enabled:
        return {**result, "reason": "disabled"}
    if not edits:
        return result

    def reject(reason):
        return {**result, "status": "rejected", "reason": reason}

    if not isinstance(edits, list) or len(edits) > 2:
        return reject("invalid_edits")
    protected = set()
    for row in rows:
        fact = row.get("fact") or {}
        protected.update(v for v in (fact.get("actor"), fact.get("recipient"),
            fact.get("counterparty"), *fact.get("participants", [])) if v and v != "self")
        if fact.get("relation") == "visit" and fact.get("object_key"):
            protected.add(fact["object_key"])
    for role in ("actor", "recipient"):
        value = (understood.get(role) or {}).get("value")
        if value:
            protected.add(value)
    previous = 0
    for edit in edits:
        if not isinstance(edit, dict):
            return reject("invalid_edits")
        start, end = edit.get("start"), edit.get("end")
        before, after = edit.get("before"), edit.get("after")
        if (type(start) is not int or type(end) is not int or
            not previous <= start < end <= len(question) or
            not isinstance(before, str) or not isinstance(after, str) or
            question[start:end] != before):
            return reject("invalid_span")
        previous = end
        # Whole whitespace-delimited words only: do not edit names or suffixes inside words.
        if ((start and question[start - 1].isalnum()) or
            (end < len(question) and question[end].isalnum())):
            return reject("partial_word")
        if any(v in before or v in after for v in protected):
            return reject("protected_entity")
        if not re.fullmatch(r"[가-힣 ]+", before + after):
            return reject("protected_expression")
        if edit.get("kind") == "spelling":
            if before in NOUNS or after not in NOUNS or len(before) < 2 or not near(before, after):
                return reject("unverified_word")
        elif edit.get("kind") == "spacing":
            if (before == after or before.replace(" ", "") != after.replace(" ", "") or
                not all(w in NOUNS for w in after.split())):
                return reject("unverified_spacing")
        else:
            return reject("invalid_kind")
    corrected = question
    for edit in reversed(edits):
        corrected = corrected[:edit["start"]] + edit["after"] + corrected[edit["end"]:]
    original_plan = query_plan(question, understood, today)
    corrected_plan = query_plan(corrected, understood, today)
    if {k: v for k, v in original_plan.items() if k != "question"} != {
        k: v for k, v in corrected_plan.items() if k != "question"
    }:
        return reject("changed_constraints")
    # Location extraction is also a hard constraint outside query_plan.
    pattern = r"([가-힣A-Za-z]+?)(?:에서|(?:에\s*)?\s+가서)"
    if re.findall(pattern, question) != re.findall(pattern, corrected):
        return reject("changed_constraints")
    return {"status": "applied", "query": corrected, "edits": edits, "reason": None}


def fuse(original, corrected):
    """One contribution per retrieval method; a second query is not corroboration."""
    values = {i: 1 / (60 + rank) for rank, i in enumerate(original, 1)}
    for rank, i in enumerate(corrected, 1):
        values[i] = max(values.get(i, 0), 0.8 / (60 + rank))
    return values
