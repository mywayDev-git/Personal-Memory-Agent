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
            "response": {"status": "answered", "items": [], "conversation_type": "general"},
            "evidence": [],
            "snapshot": {},
        }
        for m in session.get("messages", [])
        if m.get("mode") == "general" and not m.get("error_code")
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
        (r"비밀번호|주민등록번호|인증\s*토큰|계좌번호", r"비밀번호|주민등록번호|인증|계좌"),
        (r"성생활|성적\s*지향", r"성생활|성적\s*지향"),
    ]
    return all(
        not re.search(source, text) or re.search(request, question)
        for source, request in categories
    )
