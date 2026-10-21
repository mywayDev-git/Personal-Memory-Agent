"""Check explicit identifiers against current active originals, without inference."""

import re


def identifiers(question):
    tokens = re.findall(r"(?<![\w])(?:[A-Za-z][A-Za-z0-9_*+.#:/-]*|[가-힣]{2,15}(?=에서|의\s))", question)
    common = {"i", "a", "an", "the", "my", "your", "our", "it", "this", "that", "who", "what", "where", "when",
              "how", "why", "is", "was", "are", "were", "did", "does", "do", "of", "in", "on", "to", "for", "and"}
    return list(dict.fromkeys(t for t in tokens if t.casefold() not in common))


def contains_identifier(text, token):
    return bool(re.search(r"(?<![A-Za-z0-9_])" + re.escape(token) + r"(?![A-Za-z0-9_])", text, re.I))


def scoped_evidence(question, evidence):
    # Only an identifier actually present in originals can narrow the set.
    # Do not let expanded searches introduce a different project into ambiguity.
    tokens = [t for t in identifiers(question) if re.search(r"[A-Za-z]", t)]
    def positive(text, token):
        without_exclusions = re.sub(re.escape(token) + r"(?:와|과)는?\s*(?:다른|별개)|" +
                                    re.escape(token) + r"(?:가|이)\s*아닌", "", text, flags=re.I)
        return contains_identifier(without_exclusions, token)
    present = [t for t in tokens if any(positive(r["source_text"], t) for r in evidence)]
    if present:
        evidence = [r for r in evidence if any(positive(r["source_text"], t) for t in present)]
    if re.search(r"내가|나는|나의|내\s", question) and re.search(r"선호|좋아|취향", question):
        evidence = [r for r in evidence if not (
            re.match(r"(?:회사\s*)?(?:동료|친구|선배|후배)", r["source_text"])
            and not re.search(r"나는|내가|나의|사용자", r["source_text"]))]
    return evidence


def previously_supported(evidence):
    """Rescue a contradictory second selection only with a prior checked excerpt.

    This selects candidates, never approves an answer. Independent answer review
    and citation validation still run.
    """
    selected = []
    for row in evidence:
        assessment = row.get("search_explanation", {}).get("model_assessment") or {}
        quote = assessment.get("quote", "")
        if assessment.get("category") in {"direct_answer", "conflicting_evidence"} and quote and quote in row["source_text"]:
            selected.append(row["id"])
    return selected


def references_record(question, store):
    if not re.search(r"누구|담당|정확도|바뀌|변경|파일|경로|주소|문구|회의|어떤|뭐|무엇|요약|완료|원인|상태|선호|가격|RAM|기록|선택|방식|알려|코드|프로젝트|기간|학습|공부|효과|성능|조건|"
                     r"\b(?:who|what|where|when|accuracy|owner|file|path|changed|status|summary)\b", question, re.I):
        return False
    tokens = identifiers(question)
    korean_head = re.match(r"([가-힣]{2,15})(?:\s|의|에서)", question)
    if korean_head and korean_head[1] not in {"일반적으로", "일반적인", "오늘", "어제", "이번", "지난", "어떤", "무엇", "누구"}:
        tokens.append(korean_head[1])
    tokens += re.findall(r"['\"‘“]([^'\"’”]{3,80})['\"’”]", question)
    if not tokens:
        return False
    with store.connect() as db:
        for token in tokens:
            rows = db.execute(
                "SELECT v.text FROM records r JOIN revisions v ON v.record_id=r.id AND v.version=r.version "
                "WHERE r.state='active' AND instr(lower(v.text),lower(?))>0", (token,))
            pattern = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(token) + r"(?![A-Za-z0-9_])", re.I)
            if any(pattern.search(row["text"]) for row in rows):
                return True
    return False
