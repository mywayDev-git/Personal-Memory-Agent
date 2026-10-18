"""Sentence provenance and conservative event-time normalization."""

import re
from datetime import datetime, timedelta, timezone

from .temporal import normalize_time as normalize_expression

DATE = re.compile(
    r"(?<!\d)(\d{4})(?:[-.]\s*|년\s*)(\d{1,2})(?:[-.]\s*|월\s*)(\d{1,2})(?:일)?(?!\d)"
)
REL = re.compile(r"그저께|그제|어제|오늘|내일")


def sentences(text):
    # Decimal numbers and dates are not sentence boundaries.
    units = [
        dict(id=f"s{i}", start=m.start(), end=m.end(), text=m.group())
        for i, m in enumerate(re.finditer(r"[^\n]+?(?:[.!?](?=\s|$)|(?=\n|$))", text))
        if m.group().strip()
    ]
    header = None
    anchor = None
    previous_end = 0
    for unit in units:
        if "\n\n" in text[previous_end : unit["start"]]:
            anchor = None
        found = list(DATE.finditer(unit["text"]))
        if len(found) == 1 and unit["text"].strip().rstrip(".") == found[0].group():
            header = found[0].group()
        unit["date_header"] = header
        unit["previous_date"] = anchor
        if len(found) == 1:
            anchor = found[0].group()
        elif len(found) > 1:
            anchor = None
        previous_end = unit["end"]
    return units


def normalize_time(memory, units, reference_time):
    prior = dict(memory.get("time") or {})
    result = dict(raw=None, start=None, end=None, precision="unknown", certainty="uncertain")
    raw = prior.get("raw") or ""
    # Evidence is selected by sentence ID; only its own temporal expression applies.
    text = " ".join(u["text"] for u in units)
    if raw and raw not in text:
        memory["time"] = result
        return dict(
            status="unresolved",
            rule="unsupported_time_raw",
            source_ids=[u["id"] for u in units],
            changed=prior != result,
        )
    if raw:
        # Existing Korean week/month/year rules apply only to the exact selected
        # expression. Keep the team's date-header and next-day logic below.
        normalized = normalize_expression(
            dict(time=prior, evidence=[{"quote": u["text"]} for u in units]), reference_time
        )
        if (
            normalized["start"]
            and not DATE.search(raw)
            and len(list(DATE.finditer(text))) + len(list(REL.finditer(text))) <= 1
            and not re.search(r"그날|다음\s*날", raw)
        ):
            memory["time"] = normalized
            return dict(
                status="verified",
                rule="explicit_expression",
                source_ids=[u["id"] for u in units],
                changed=prior != normalized,
            )
    dates = list(DATE.finditer(text))
    relative = list(REL.finditer(text))
    inherited = False
    if not dates and not relative:
        headers = {u.get("date_header") for u in units if u.get("date_header")}
        if len(headers) == 1:
            dates = list(DATE.finditer(next(iter(headers))))
            inherited = True
    candidates = []
    for match in dates:
        try:
            candidates.append(
                (match.group(), datetime(*map(int, match.groups())).date(), "explicit")
            )
        except ValueError:
            pass
    if reference_time:
        base = (
            datetime.fromisoformat(reference_time).astimezone(timezone(timedelta(hours=9))).date()
        )
        for match in relative:
            delta = {"그저께": -2, "그제": -2, "어제": -1, "오늘": 0, "내일": 1}[match.group()]
            candidates.append((match.group(), base + timedelta(days=delta), "inferred"))
    # A booking statement can mention both its recording date and an unresolved appointment.
    unresolved = bool(re.search(r"[월화수목금토일]요일|그날|다음\s*날|지난번|작년", raw))
    chosen = [c for c in candidates if c[0] == raw] if raw else []
    if raw in {"그날", "다음 날", "다음날"} and raw in text:
        anchors = {u.get("previous_date") for u in units if u.get("previous_date")}
        if len(anchors) == 1:
            match = DATE.fullmatch(next(iter(anchors)))
            if match:
                try:
                    day = datetime(*map(int, match.groups())).date() + timedelta(
                        days=int(raw != "그날")
                    )
                    chosen = [(raw, day, "inferred")]
                    unresolved = False
                except ValueError:
                    pass
    if not chosen and len(candidates) == 1 and not unresolved:
        chosen = candidates
    if len(candidates) > 1:
        chosen = []
    if len(chosen) == 1 and not unresolved:
        expression, day, certainty = chosen[0]
        result.update(raw=expression, start=day.isoformat(), precision="day", certainty=certainty)
    elif raw and raw in text:
        result.update(raw=raw, precision="relative")
        month = re.fullmatch(r"(\d{4})(?:년\s*|-)(\d{1,2})월?", raw)
        year = re.fullmatch(r"(\d{4})년?", raw)
        if month and 1 <= int(month[2]) <= 12:
            result.update(
                start=f"{int(month[1]):04}-{int(month[2]):02}",
                precision="month",
                certainty="explicit",
            )
        elif year:
            result.update(start=year[1], precision="year", certainty="explicit")
    memory["time"] = result
    return dict(
        status="verified" if result["start"] else "unresolved",
        rule="date_header" if inherited else "sentence_scope",
        source_ids=[u["id"] for u in units],
        changed=prior != result,
    )
