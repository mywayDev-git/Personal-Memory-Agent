"""Pin accepted claim citations to the exact frozen source revision and span."""

import re
from copy import deepcopy


def asks_identity(question):
    return bool(
        re.search(r"누구|어떤\s*사람|관계|(?:어떤|무슨)\s*사이|어떻게\s*아는|직업", question)
    )


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


def causal_claims_supported(question, response, evidence):
    """Conservative extra guard against turning a repeated event into its own cause."""
    if not re.search(r"왜|이유|원인", question):
        return True
    sources = {row["id"]: row["source_text"] for row in evidence}
    causal = r"때문|덕분|탓|느라|므로|어서|아서|여서|와서|워서|해서|라서|니까|위해"
    for item in response["items"]:
        if not re.search(causal + r"|려고|목적|이유|원인|확인.*없|알.*없", item["text"]):
            return False
        if re.search(causal, item["text"]) and not any(
            re.search(causal, sources[cid]) for cid in item["citations"]
        ):
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
            start = row["source_text"].find(ref["quote"])
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
    if not asks_identity(question) or re.search(r"둘|각각|비교|차이", question):
        return []
    groups = {}
    for row in evidence:
        pattern = r"([가-힣]+(?:\s+[가-힣]+){0,2}\s+(?:동료|친구|동창|선배|후배))\s+([가-힣]{2,5}?)(?=은|는|이|가|에게|와|과|[ .,!]|$)"
        for match in re.finditer(pattern, row["source_text"]):
            role, name = match.groups()
            if name not in question:
                continue
            groups.setdefault(name, {})[role] = {
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
    identity = re.search(r"([가-힣]{2,8}?)(?:이가|이는|가|는)?\s*누구", intent_question)
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
