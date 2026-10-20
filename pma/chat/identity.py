"""Narrow, source-backed role scope for immediate person follow-ups."""

import re

ROLE = re.compile(
    r"([가-힣]+(?:\s+[가-힣]+){0,2}\s+(?:동료|친구|동창|선배|후배))\s+"
    r"([가-힣]{2,5}?)(?=은|는|이|가|에게|와|과|의|[ .,! ?]|$)"
)
REFERENCE = re.compile(r"그\s*(?:사람|분)(?![가-힣])|그\s*(?:사람|분)(?=은|는|이|의|에게)|그녀|그는")


def labels(text):
    return [match.group() for match in ROLE.finditer(text)]


def scoped_followup(question, session):
    if not REFERENCE.search(question) or labels(question):
        return question
    messages = session.get("messages", [])
    if not messages:
        return question
    previous = messages[-1]
    response = previous.get("response") or {}
    if (previous.get("state") != "completed" or previous.get("error_code")
            or response.get("status") != "answered"):
        return question
    candidates = labels(previous["question"])
    if len(set(candidates)) != 1:
        return question
    label = candidates[0]
    # Assistant prose alone cannot establish a referent. Require a checked span.
    if not any(label in ref.get("quote", "") for ref in response.get("citation_details", [])):
        return question
    return REFERENCE.sub(label, question)


def identity_conflict(question, item, evidence):
    targets = labels(question)
    if len(set(targets)) != 1:
        return False
    target = targets[0]
    target_name = next(ROLE.finditer(target)).group(2)
    for row in evidence:
        if row["id"] not in item["citations"]:
            continue
        other = [m for m in ROLE.finditer(row["source_text"]) if m.group(2) == target_name]
        if other and all(m.group() != target for m in other):
            return True
    return False
