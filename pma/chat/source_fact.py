"""Narrow extractive drafts. These are proposals, never accepted evidence checks."""

import re

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
