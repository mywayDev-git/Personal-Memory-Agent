"""Narrow extractive drafts. These are proposals, never accepted evidence checks."""

import re
from datetime import date

from scripts.memory_agent.provenance import sentences


def source_fact_draft(question, evidence):
    if len(evidence) != 1 or not re.search(r"무엇|뭐|어떤", question):
        return None
    if not re.search(r"선물|줬|주었|준", question):
        return None
    if re.search(r"왜|이유|언제|날짜|누가|누구|어디|몇|가장|처음|마지막|모두|전부|계획|예정|않|안\s|실제|때문|어떻게|순서|비교|받|그리고|각각|했고|했으며|또", question):
        return None
    row = evidence[0]
    fact = row.get("fact") or {}
    if (row.get("assertion_polarity") != "affirmed" or row.get("memory_type") != "event"
            or fact.get("state") != "observed" or fact.get("action_relation") != "give"
            or fact.get("warnings") or fact.get("review_reasons")):
        return None
    source = row.get("source_text", "").strip()
    obj = fact.get("object")
    if (not source or len(source) > 240 or len(sentences(source)) != 1
            or not isinstance(obj, str) or not obj.strip()
            or re.sub(r"\s+", "", obj) not in re.sub(r"\s+", "", source)):
        return None
    return {"status": "answered", "items": [{
        "text": "기록에 이렇게 남아 있습니다: “" + source + "”", "citations": [row["id"]],
    }]}


def _single_source_date_draft(question, evidence):
    """One explicit observed event date as a quote, never a reviewed answer."""
    from ..facts import COLORS, relation
    from ..search_expressions import entity_overlap
    from .models import asks_record_time
    from .questions import question_parts
    if (len(evidence) != 1 or not re.search(r"언제|날짜|며칠", question)
            or asks_record_time(question) or question_parts(question)
            or re.search(r"왜|이유|원인|최초|처음|마지막|최근|모두|각각|비교|순서|전후|실제|실행|계획|예정", question)):
        return None
    row = evidence[0]
    fact = row.get("fact") or {}
    source = row.get("source_text", "").strip()
    event = fact.get("event_time") or {}
    if (row.get("memory_type") != "event" or row.get("assertion_polarity") != "affirmed"
            or fact.get("state") != "observed" or fact.get("warnings") or fact.get("review_reasons")
            or (fact.get("time_validation") or {}).get("status") != "verified"
            or event.get("certainty") != "explicit" or event.get("precision") != "day" or event.get("end")
            or not source or len(source) > 240 or len(sentences(source)) != 1
            or re.search(r"계획|예정|정했다|변경|취소|말했다|그리고|했고|했으며|이후|전후|반면|지만", source)):
        return None
    matches = list(re.finditer(r"(\d{4})(?:년\s*|-)(\d{1,2})(?:월\s*|-)(\d{1,2})(?:일)?", source))
    if len(matches) != 1:
        return None
    try:
        explicit = date(*(int(value) for value in matches[0].groups())).isoformat()
    except ValueError:
        return None
    if event.get("start") != explicit:
        return None
    obj = fact.get("object")
    if not isinstance(obj, str):
        return None
    colors = "|".join(re.escape(key) for key in sorted(set(COLORS) | set(COLORS.values()), key=len, reverse=True))
    noun = re.sub(r"\s+", " ", re.sub(colors, "", obj)).strip()
    if not noun or not entity_overlap(question, noun) or not entity_overlap(source, noun):
        return None
    actions = re.findall(r"선물|시작|중단|그만|입사|퇴사|구매|구입|반납|회의|여행", question)
    if not actions or any(action not in source for action in actions):
        return None
    requested = relation(question)
    if requested in {"give", "receive", "visit"} and fact.get("action_relation") != requested:
        return None
    return {"status": "answered", "items": [{"text": "기록 원문: “" + source + "”", "citations": [row["id"]]}]}


def source_date_draft(question, evidence):
    """A uniquely dated target event; keep the complete pool for review."""
    from ..facts import COLORS
    from ..search_expressions import entity_overlap
    proposals = [(row, _single_source_date_draft(question, [row])) for row in evidence]
    proposals = [(row, result) for row, result in proposals if result is not None]
    if len(proposals) != 1:
        return None
    row, result = proposals[0]
    colors = "|".join(re.escape(key) for key in sorted(set(COLORS) | set(COLORS.values()), key=len, reverse=True))
    noun = re.sub(r"\s+", " ", re.sub(colors, "", row["fact"]["object"])).strip()
    actions = re.findall(r"선물|시작|중단|그만|입사|퇴사|구매|구입|반납|회의|여행", question)
    for other in evidence:
        if other is row:
            continue
        source = other.get("source_text", "")
        # An undated/negated/uncertain second mention of the same target still
        # prevents the shortcut. Do not discard a potentially conflicting fact.
        if entity_overlap(source, noun) and all(action in source for action in actions):
            return None
    return result
