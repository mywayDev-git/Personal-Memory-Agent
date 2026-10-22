"""Explicit memory refusal applies before routing, preferences and context reuse."""

import re


def memory_disabled(question, mode="auto"):
    return mode == "general" or bool(
        re.search(
            r"(?:내\s*)?(?:기록|기억)(?:은|을|을은)?\s*(?:쓰지|사용하지|참조하지|조회하지|검색하지)|"
            r"(?:내\s*)?(?:기록|기억)\s*(?:말고|없이)|개인\s*(?:정보|기록|기억)\s*제외",
            question,
        )
    )


def private_context(session):
    """Keep current user-authored conversational context, never recalled assistant facts."""
    result = dict(session)
    result["context"] = {}
    result["evidence"] = []
    result["snapshot"] = {}
    result["messages"] = [
        {
            **m,
            "response": {
                "status": "answered",
                "items": [
                    i
                    for i in (m.get("response") or {}).get("items", [])
                    if i.get("source_type") == "general" and not i.get("citations")
                ],
                "conversation_type": "general",
            },
            "evidence": [],
            "snapshot": {},
        }
        for m in session.get("messages", [])
        if (
            m.get("mode") == "general"
            or (m.get("response") or {}).get("conversation_type") == "general"
            or (m.get("response") or {}).get("conversation_mode") == "general"
        )
        and not m.get("error_code")
    ]
    return result


def source_allowed(question, row):
    """Conservative topic gate for sensitive source excerpts, independent of model relevance."""
    text = row.get("source_text", "")
    categories = [
        (
            r"진단|진료|치료|질환|병원|건강\s*상담|정신\s*건강",
            r"건강|의료|진단|진료|치료|질환|병원|상담",
        ),
        # An expiry/error diagnosis is not a credential value. Keep actual token
        # declarations sensitive, including when a later sentence mentions expiry.
        (r"비밀번호|주민등록번호|인증\s*토큰(?!(?:이|의)?\s*(?:만료|오류|갱신|재발급|문제))|계좌번호", r"비밀번호|주민등록번호|인증|계좌"),
        (r"성생활|성적\s*지향", r"성생활|성적\s*지향"),
    ]
    employment = hospital_employment(question, text)
    return all(
        not re.search(source, text) or re.search(request, question)
        or (index == 0 and employment)
        for index, (source, request) in enumerate(categories)
    )


def hospital_employment(question, text):
    """A complete job introduction is not a patient's health history.

    Only a single, positive role/name/job sentence qualifies. Additional health
    facts, a patient label, instructions or other sensitive content cannot ride
    along with the employment exception.
    """
    from .evidence import asks_identity
    from .identity import ROLE
    if not (asks_identity(question) or re.search(r'(?:어떤|무슨)\s*일', question)):
        return False
    match = ROLE.match(text.strip())
    if not match:
        return False
    jobs = r'의사|약사|간호사|방사선사|임상병리사|치과위생사|물리치료사|작업치료사|응급구조사|행정직원|원무직원|접수직원|연구원|보안요원|미화원|조리사'
    return bool(re.fullmatch(
        re.escape(match.group()) + rf'(?:은|는|이|가)\s+(?:{jobs})(?:입니다|이다|다|이에요|예요)[.!?]?',
        text.strip(),
    ))
