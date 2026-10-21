"""Deterministic comparison, with narrow exact-answer proof and explicit unknowns."""

import re
import unicodedata


def normalized(text):
    # Preserve numbers, identifiers and negation. Only presentation punctuation/spacing differs.
    text = re.sub(r"^(?:기록에 따르면|기록상|원문에 따르면)[,，: ]*", "", unicodedata.normalize("NFC", text or "").strip())
    return re.sub(r"\s+", " ", text).strip().rstrip("。.!?")


def compare_answer(case, answer):
    exact = bool(answer.strip()) and any(normalized(answer) == normalized(value)
                                        for value in case.get("accepted_answers", []))
    facts = [{"fact": fact, "status": "MATCH" if fact in answer else "MISSING"}
             for fact in case.get("required_facts", [])]
    forbidden = [{"fact": fact, "status": "MENTIONED" if fact in answer else "ABSENT"}
                 for fact in case.get("forbidden_facts", [])]
    return {"version": "answer-comparison-v1", "method": "exact_reference_and_fact_presence",
            "status": "EXACT_MATCH" if exact else "NO_ANSWER" if not answer.strip() else "REVIEW_REQUIRED",
            "expected_answer": case.get("expected_answer"), "exact_match": exact,
            "required_facts": facts, "forbidden_facts": forbidden,
            "coverage_scope": case.get("coverage_scope", "scenario_contract"),
            "coverage_gaps": case.get("coverage_gaps", []),
            "note": "필수 단어 일치와 금지 단어 언급은 사실 판정의 보조 정보입니다. 의미가 다른 문장은 일치로 확정하지 않습니다."}


def reference_behavior(case, answer):
    """A complete authored reference can prove intent; keywords alone cannot."""
    if compare_answer(case, answer)["exact_match"]:
        return case["expected_behavior"]
    return None
