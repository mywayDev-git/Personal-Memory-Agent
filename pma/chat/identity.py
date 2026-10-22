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


def ambiguity_reservations(question, candidates):
    """Keep eligible source-backed roles for clarification, never certify an answer.

    Call only after owner/version/date/structural filtering. A model selection
    must not erase the second person before the context ambiguity check runs.
    """
    if positive_labels(question):
        return set()
    from .evidence import identity_alternatives
    sources = [{'id': row['id'], 'source_text': row.get('source_text', row.get('text', ''))}
               for row in candidates]
    return {item['evidence_id'] for item in identity_alternatives(question, sources)}


def retain_ambiguity_rows(candidates, selected, reserved, limit):
    """Restore only protected eligible rows without increasing the evidence cap."""
    result = list(selected)
    present = {row['id'] for row in result}
    for row in candidates:
        if row['id'] in reserved and row['id'] not in present:
            from copy import deepcopy
            result.append(deepcopy(row))
            present.add(row['id'])
    while len(result) > limit:
        index = next((i for i in range(len(result)-1, -1, -1)
                      if result[i]['id'] not in reserved), None)
        if index is None:
            raise ValueError('IDENTITY_ALTERNATIVES_EXCEED_EVIDENCE_LIMIT')
        result.pop(index)
    return result


def identity_source_reservations(question, candidates):
    """An explicit occupation query also needs its own non-occupation records.

    Height is not an occupation answer, but it can support the carefully scoped
    statement that the requested occupation is not established in these sources.
    """
    from .answer_integrity import occupation_target, target_text, plain_occupation
    from .review_sources import source_units, instruction_span
    target = occupation_target(question)
    if not target:
        return set()
    matches = [row for row in candidates if any(target_text(target, unit)
               for unit in source_units(row.get('source_text', row.get('text', '')))
               if not instruction_span(unit))]
    # Reserve proof sources, not every mention. A known job must not disappear
    # behind many height records. All other candidates keep normal ranking.
    matches.sort(key=lambda row: not bool(plain_occupation(target, row.get('source_text', row.get('text', '')))))
    return {row['id'] for row in matches[:4]}


def identity_probe_candidate(question, evidence):
    """Identify a bounded original quote to try, never certify completion.

    Only a complete explicit role lookup with one plain original statement can
    try a fresh independent review. The role may be known while the requested
    attribute is absent: this predicate alone must never stop further search.
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
