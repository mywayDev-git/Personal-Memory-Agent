"""Lossless removal of identical model-input copies, not source truncation."""

from copy import deepcopy


def has_source_directives(evidence):
    from .review_sources import instruction_span, source_units
    return any(instruction_span(unit) for row in evidence
               for unit in source_units(row.get("source_text", row.get("source_context", ""))))


def deduplicate_sources(evidence):
    rows = deepcopy(evidence)
    # Formatting changes affected ambiguity handling on embedded commands in
    # real-model screening. Preserve the full legacy input for this class.
    if has_source_directives(rows):
        return rows
    for row in rows:
        source_key = "source_text" if "source_text" in row else "source_context"
        if source_key not in row:
            continue
        source = row[source_key]
        if not isinstance(source, str):
            continue
        fact = row.get("fact") or {}
        for inner, outer in (("evidence", "evidence"), ("event_time", "time"),
                             ("recorded_at", "recorded_at"), ("reference_time", "reference_time")):
            if inner in fact and fact[inner] == row.get(outer):
                fact.pop(inner)
        if row.get("content") == source:
            row.pop("content", None)
        for ref in row.get("evidence") or []:
            if ref.get("quote") == source:
                ref.pop("quote")
                ref["quote_from"] = source_key
    return rows
