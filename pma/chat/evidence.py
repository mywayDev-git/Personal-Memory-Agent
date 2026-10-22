"""Pin accepted claim citations to the exact frozen source revision and span."""

import re
from copy import deepcopy

from scripts.memory_agent.meaning import meaning_conflict

from ..relevance import study_topic, topic_supported

CAUSAL_CUES = r"때문|덕분|탓|느라|므로|어서|아서|여서|와서|워서|해서|라서|니까|위해|(?:으?로)\s*인(?:해|하여|한)"


def quoted_topic_answer(question, evidence):
    """A bounded repair draft: exact source quotes, never an opposite paraphrase.

    This draft must still pass the normal independent answer review. It is used
    only after a failed meaning check for an explicit topic, not as acceptance.
    """
    if not study_topic(question):
        return None
    from .semantics import stop_record_draft

    focused = stop_record_draft(question, evidence)
    if focused:
        return focused
    items, seen = [], set()
    for row in evidence:
        if not topic_supported(question, row):
            continue
        for ref in row.get("evidence", []):
            quote = ref.get("quote", "")
            key = (row.get("record_id"), quote)
            if quote and quote in row["source_text"] and key not in seen:
                seen.add(key)
                items.append({"text": "기록 원문: “" + quote + "”", "citations": [row["id"]]})
                if len(items) == 8:
                    break
        if len(items) == 8:
            break
    return {"status": "answered", "items": items} if items else None


def asks_identity(question):
    return bool(
        re.search(r"누구|어떤\s*사람|관계|(?:어떤|무슨)\s*사이|어떻게\s*아는|직업", question)
    )


def preserve_overview(question, resolved):
    """A named overview is not a request to infer identity or a relationship."""
    overview = re.search(r"(?:에\s*대해|에\s*관해|관련해서).*(?:이야기|알려|설명|정리)", question)
    dependent = re.search(r"그\s*(?:사람|분|것|거)|그녀|그때|그날|저\s*사람", question)
    return question if overview and not dependent else resolved


def selected_alternative(question, labels):
    """Match a unique explicitly named candidate, including a shortened role.

    Selection is interpretation only, and still requires fresh retrieval/review.
    A bare shared name or a negated option cannot select a candidate.
    """
    if re.search(r"말고|아니|아닌|제외", question):
        return None
    compact = re.sub(r"\s+", "", question)
    words = [set(label.split()) for label in labels]
    matches = []
    for index, label in enumerate(labels):
        other = set().union(*(w for j, w in enumerate(words) if j != index))
        unique = words[index] - other
        if label.split()[-1] in compact and any(w in compact for w in unique):
            matches.append(label)
    return matches[0] if len(matches) == 1 else None


def causal_claims_supported(question, response, evidence, *, require_coverage=True):
    """Conservative extra guard against turning a repeated event into its own cause."""
    if not re.search(r"왜|이유|원인", question):
        return True
    sources = {row["id"]: row["source_text"] for row in evidence}
    from .identity import canonical_label, positive_labels
    from .questions import question_parts

    parts = question_parts(question)
    identity_sources = set()
    if parts:
        label = canonical_label(positive_labels(parts[0])[0])
        identity_sources = {row["id"] for row in evidence
                            if label in canonical_label(row["source_text"])}
    identity_seen = cause_seen = False
    causal = CAUSAL_CUES
    for item in response["items"]:
        identity_item = bool(set(item["citations"]) & identity_sources)
        identity_seen = identity_seen or identity_item
        causal_text = re.search(causal + r"|려고|목적|이유|원인|확인.*없|알.*없", item["text"])
        if parts and identity_item and not causal_text:
            continue
        if not causal_text:
            # A supported event may accompany its actual cause. Completeness is
            # checked across the answer, not independently for every sentence.
            continue
        cause_seen = True
        if re.search(causal, item["text"]) and not any(
            re.search(causal, sources[cid]) for cid in item["citations"]
        ):
            return False
    if not require_coverage or not response['items']:
        return True
    return cause_seen and (not parts or identity_seen)


def semantic_issue(question, item, evidence):
    """Reject narrow, checkable meaning changes even if the model approves them."""
    from .identity import identity_conflict
    from .semantics import denies_stopping

    if identity_conflict(question, item, evidence):
        return "person"
    cited = [row["source_text"] for row in evidence if row["id"] in item["citations"]]
    text = item["text"]
    def units(value):
        return {("stage" if label == "단계" else "part", str(int(number)))
                for label, number in re.findall(r"(?i)(part|파트|단계)\s*(\d+)", value)}
    if not units(text) <= units("\n".join(cited)):
        return "other"
    if re.search(r"날짜|시각", text) and re.search(r"명시되지|확인되지|모르|불명|미상|없", text):
        if any(units(text) & units(sentence) and re.search(r"\d{4}-\d{2}-\d{2}", sentence)
               and re.search(r"(?i)(?:part|파트|단계)\s*\d+(?:을|를|은|는)?\s*(?:완료했다|완료했습니다|마쳤다|끝냈다)[.!]?$", sentence)
               for source in cited for sentence in re.split(r"(?<=[.!?])\s+|\n", source)):
            return "time"
    if denies_stopping(question, text, cited):
        return "negation"
    if meaning_conflict(text, "\n".join(cited)):
        return "other"
    if not causal_claims_supported(question, {"items": [item]}, evidence, require_coverage=False):
        return "cause"
    if re.search(r"때문|덕분|탓으로|원인이|이유로", text) and not any(
        re.search(CAUSAL_CUES, source)
        for source in cited
    ):
        if not re.search(r"확인.*없|알.*없|단정.*없|불명", text):
            return "cause"
    for source in cited:
        for match in re.finditer(r"(?<![가-힣])([가-힣]+?)기로\s*하지\s*않", source):
            stronger = re.escape(match[1]) + r"지\s*않기로"
            absence = r"(?:계획|의도)[이가은는]*\s*없(?:다|습니다|어요)[.!?]?$"
            if re.search(stronger, text) and not any(re.search(stronger, s) for s in cited):
                if not re.search(r"뜻.*아니|의미.*아니|단정.*없", text):
                    return "negation"
            if re.search(absence, text) and not any(re.search(absence, s) for s in cited):
                return "negation"
    return None


def unrecorded_cause_draft(question, evidence):
    """Repair inferred causality with a bounded source quote and explicit limit.

    Only a unique short cancellation record with no stated causal cue qualifies.
    This is a proposal for fresh independent review, never an approval or a
    claim that the entire database contains no reason.
    """
    from .questions import question_parts
    from .review_sources import instruction_span
    if (not re.search(r'왜|이유|원인', question) or '취소' not in question
            or question_parts(question) or asks_identity(question) or len(evidence) != 1):
        return None
    row = evidence[0]
    source = row['source_text'].strip()
    key = (row.get('fact') or {}).get('object_key') or ''
    compact = lambda value: re.sub(r'\s+', '', value)
    if (len(source) > 300 or row.get('warnings') or instruction_span(source)
            or re.search(CAUSAL_CUES + r'|이유|원인|목적|가정|예정|계획', source)
            or not re.search(r'취소(?:했|하지\s*않)', source)
            or len(key) < 2 or compact(key) not in compact(question) or compact(key) not in compact(source)):
        return None
    return {'status': 'answered', 'items': [{
        'text': '기록 원문: “' + source + '” 이 기록만으로는 질문하신 이유를 확인할 수 없습니다.',
        'citations': [row['id']],
    }]}


def review_spans_supported(response, review, evidence, *, question=None):
    """A true conclusion cannot cover uncited ancillary people, dates or plans."""
    rows = {r['id']: r for r in evidence}
    from .review_sources import factual_quote_span, instruction_span, verbatim_instruction_report
    for checked in review.get('items', []):
        text = response['items'][checked['index']]['text']
        for ref in checked['evidence']:
            if factual_quote_span(ref['quote'], rows[ref['id']]['source_text']) is None:
                if not (instruction_span(ref['quote']) and verbatim_instruction_report(
                        question or '', text, [ref['quote']])):
                    return False
        quote = '\n'.join(ref['quote'] for ref in checked['evidence'])
        sources = [rows[ref['id']] for ref in checked['evidence']]
        full = '\n'.join(r['source_text'] for r in sources)
        facts = [r.get('fact') or {} for r in sources]
        names = {f.get(key) for f in facts for key in ('actor', 'recipient', 'counterparty')} - {None, '', 'self'}
        tokens = names | set(re.findall(r'\d+(?:\.\d+)?|[월화수목금토일]요일', text))
        if any(token in text and token in full and token not in quote for token in tokens):
            return False
        if re.search(r'예정|계획', text) and re.search(r'예정|계획', full) and not re.search(r'예정|계획', quote):
            return False
    return True


def reviewed_citations(response, review, evidence):
    result = deepcopy(response)
    sources = {row["id"]: row for row in evidence}
    details = []
    for checked in review["items"]:
        index = checked["index"]
        refs = checked["evidence"]
        allowed = {ref["id"] for ref in refs}
        result["items"][index]["citations"] = [
            cid for cid in result["items"][index]["citations"] if cid in allowed
        ]
        for ref in refs:
            row = sources[ref["id"]]
            from .review_sources import factual_quote_span, instruction_span
            span = factual_quote_span(ref['quote'], row['source_text'])
            start = span[0] if span else (row['source_text'].find(ref['quote'])
                                         if instruction_span(ref['quote']) else -1)
            if start < 0:
                raise ValueError("INVALID_SOURCE_SPAN")
            details.append(
                {
                    "item_index": index,
                    "memory_id": row["id"],
                    "record_id": row["record_id"],
                    "revision_id": row["revision_id"],
                    "quote": ref["quote"],
                    "start": start,
                    "end": start + len(ref["quote"]),
                }
            )
    result["citation_details"] = details
    return result


def identity_alternatives(question, evidence):
    """Only explicit role-qualified names can force a clarification."""
    if not (asks_identity(question) or re.search(r"어떤\s*일|무슨\s*일", question)) or re.search(r"둘|각각|비교|차이", question):
        return []
    from .identity import ROLE, canonical_label
    from .review_sources import source_units, instruction_span
    groups = {}
    for row in evidence:
        # Labels in a quoted instruction cannot establish a second person.
        text = '\n'.join(unit for unit in source_units(row['source_text']) if not instruction_span(unit))
        for match in ROLE.finditer(text):
            role, name = match.groups()
            if name not in question:
                continue
            groups.setdefault(name, {})[canonical_label(role)] = {
                "label": match.group(),
                "quote": match.group(),
                "evidence_id": row["id"],
            }
    for roles in groups.values():
        if len(roles) >= 2 and not selected_alternative(
            question, [value["label"] for value in roles.values()]
        ):
            return list(roles.values())[:4]
    return []


def direct_statement(question, evidence, intent_question=None):
    """Prefer one explicit original sentence for simple identity or causal lookups.

    This is only a candidate: the normal independent review and span validation
    still run. Multiple conflicting candidates fall back to normal generation.
    """
    intent_question = intent_question or question
    from .execution import execution_draft

    planned = execution_draft(intent_question, evidence)
    if planned:
        return planned
    from .identity import labels, positive_labels, explicit_person_lookup

    if labels(intent_question) and not positive_labels(intent_question):
        return None
    identity = re.search(
        r"([가-힣]{2,8}?)(?:이가|이는|가|는|의)?\s*(?:누구|직업)", intent_question
    )
    if identity is None and explicit_person_lookup(intent_question, evidence):
        identity = re.search(r"([가-힣]{2,5}?)(?:은|는|의)?\s*(?:어떤|무슨)\s*일", intent_question)
    if not identity and asks_identity(intent_question):
        # The current intent must ask identity/relationship. A resolved name is
        # only a target hint; the candidate fact still comes verbatim from sources.
        matches = re.finditer(
            r"([가-힣]{2,8}?)(?:이가|이는|가|는)?\s*(?:나와|저와|사용자와|어떤\s*사이|무슨\s*사이|관계)",
            question,
        )
        identity = next(
            (
                m
                for m in matches
                if m[1] not in {"사람", "그사람", "그분", "그녀", "누구"}
                and any(m[1] in r["source_text"] for r in evidence)
            ),
            None,
        )
    why = re.search(r"왜|이유|원인", intent_question)
    if identity and why:
        return None  # One identity sentence cannot fulfill two independent questions.
    uncertainty = (
        re.search(r"최종|확정", intent_question) and len({r["source_text"] for r in evidence}) == 1
    )
    if not identity and not why and not uncertainty:
        return None
    candidates = {}
    for row in evidence:
        actor = (row.get("fact") or {}).get("actor") or ""
        if (
            uncertainty
            and len(row["source_text"]) <= 300
            and len(actor) >= 2
            and actor in question
            and re.search(r"최종.{0,20}(?:확인되지|알 수 없|불명|미정)", row["source_text"])
        ):
            candidates[row["source_text"]] = row["id"]
        if not identity and not why:
            continue
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", row["source_text"]):
            sentence = sentence.strip()
            if not sentence or len(sentence) > 300:
                continue
            if identity:
                match = identity.group(1) in sentence and re.search(
                    r"(?:나의|내|나와|저의).*?(?:동창|친구|동료|선배|후배|형제|자매|동생)", sentence
                )
                qualified = re.match(
                    r"^([가-힣]+(?:\s+[가-힣]+){0,2}\s+(?:동료|친구|동창|선배|후배)\s+[가-힣]{2,5}?)(?=은|는|이|가)",
                    sentence,
                )
                if qualified and re.sub(r"\s+", "", qualified[1]) in re.sub(
                    r"\s+", "", intent_question
                ):
                    match = True
            else:
                key = (row.get("fact") or {}).get("object_key") or ""
                match = (
                    len(key) >= 2
                    and key in re.sub(r"\s+", "", question)
                    and re.search(
                        r"(?:이유|원인|목적).*(?:때문|위해|려고)|(?:때문|덕분)에", sentence
                    )
                )
            if match:
                candidates[sentence] = row["id"]
    if len(candidates) != 1:
        return None
    sentence, cid = next(iter(candidates.items()))
    return {
        "status": "answered",
        "items": [{"text": "기록에 이렇게 남아 있습니다: “" + sentence + "”", "citations": [cid]}],
    }
