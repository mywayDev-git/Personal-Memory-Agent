"""Narrow, source-backed role scope for immediate person follow-ups."""

import re

QUALIFIER = r"(?!(?:그|이|저|어느|어떤|무슨|다른|말고|아닌|아니라|아니고|그리고|또는|하지만|제외한)\b)[가-힣]+"
ROLE = re.compile(
    rf"(?<![가-힣])({QUALIFIER}(?:\s+{QUALIFIER}){{0,2}}\s+(?:동료|친구|동창|선배|후배))\s+"
    r"([가-힣]{2,5}?)(?=은|는|이|가|에게|와|과|의|[ .,! ?]|$)"
)
REFERENCE = re.compile(
    r"(?<![가-힣])그\s*(?:사람|분|친구)(?![가-힣])|"
    r"(?<![가-힣])그\s*(?:사람|분|친구)(?=은|는|이|가|의|에게|한테|와|과|도)|"
    r"(?<![가-힣])그녀(?=$|[^가-힣]|의|는|가|에게)|(?<![가-힣])그는(?=$|[^가-힣])"
)


def labels(text):
    return [match.group() for match in ROLE.finditer(text)]


def positive_labels(text):
    return [match.group() for match in ROLE.finditer(text) if not re.match(
        r"\s*(?:은|는|이|가)?\s*(?:말고|아닌|아니라|아니고|제외)", text[match.end():]
    )]


def canonical_label(text):
    compact = re.sub(r"\s+", "", text)
    return re.sub(r"(회사|동아리|학교|대학|대학교|팀|직장|모임|연구실)의", r"\1", compact)


def scoped_followup(question, session):
    messages = session.get("messages", [])
    # ChatStore.begin has already appended the current in-flight user turn.
    if messages and messages[-1].get("state") == "running" and messages[-1].get("question") == question:
        messages = messages[:-1]
    return _scoped_followup(question, messages, 0)


def _scoped_followup(question, messages, depth):
    if not REFERENCE.search(question) or labels(question):
        return question
    if not messages or depth >= 6:
        return question
    previous = messages[-1]
    response = previous.get("response") or {}
    if (previous.get("state") != "completed" or previous.get("error_code")
            or response.get("status") != "answered"):
        return question
    prior_question = previous["question"]
    if REFERENCE.search(prior_question) and not labels(prior_question):
        prior_question = _scoped_followup(prior_question, messages[:-1], depth + 1)
    candidates = positive_labels(prior_question)
    if len(set(candidates)) != 1:
        return question
    label = candidates[0]
    # Assistant prose alone cannot establish a referent. Require a checked span.
    checked_sources = [{"source_text": ref.get("quote", "")}
                       for ref in response.get("citation_details", [])]
    # A question about this person's friend introduces a new possible referent.
    # Only a complete identity/profession lookup can anchor this narrow shortcut.
    if not explicit_person_lookup(prior_question, checked_sources):
        return question
    return REFERENCE.sub(label, question)


def identity_conflict(question, item, evidence):
    targets = positive_labels(question)
    if len(set(targets)) != 1:
        return False
    target = targets[0]
    target_name = next(ROLE.finditer(target)).group(2)
    compact_target = canonical_label(target)
    def matches(label):
        compact = canonical_label(label)
        return compact.endswith(compact_target) or compact_target.endswith(compact)
    if any(m.group(2) == target_name and not matches(m.group())
           for m in ROLE.finditer(item["text"])):
        return True
    for row in evidence:
        if row["id"] not in item["citations"]:
            continue
        other = [m for m in ROLE.finditer(row["source_text"]) if m.group(2) == target_name]
        if other and all(not matches(m.group()) for m in other):
            return True
    return False


def explicit_person_lookup(question, evidence):
    targets = labels(question)
    if len(set(targets)) != 1:
        return False
    tail = question.replace(targets[0], "", 1).strip()
    return bool(re.fullmatch(
        r"(?:은|는|의)?\s*(?:누구(?:야|예요|인가요|입니까)?|직업(?:은|이)?\s*(?:뭐야|뭐예요|뭔가요|무엇인가요)?|"
        r"(?:어떤|무슨)\s*일(?:을)?\s*(?:해|해요|하나요|합니까|하세요))\s*[?.!]*",
        tail
    )) and any(canonical_label(targets[0]) in canonical_label(row["source_text"]) for row in evidence)


def identity_discovery_redundant(question, evidence):
    """A model's empty next query needs no forced generic relationship lookup.

    Only a complete explicit role lookup with one plain original statement can
    use this shortcut. It neither approves that statement nor drops sources.
    Unknown, ambiguous, conditional, conflicting and directive cases defer.
    """
    if not explicit_person_lookup(question, evidence):
        return False
    selected = [row for row in evidence if explicit_person_lookup(question, [row])]
    from .review_sources import instruction_span, source_units
    if any(row.get('warnings') or any(instruction_span(unit) for unit in source_units(row['source_text']))
           or re.search(r'계획|예정|않|아니|불명|미상|충돌|전언|가정|취소', row['source_text']) for row in selected):
        return False
    from .evidence import direct_statement
    return direct_statement(question, selected) is not None
