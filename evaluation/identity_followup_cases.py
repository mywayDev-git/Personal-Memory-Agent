"""Version 1 independent cases frozen before the referent repair.

These are final confirmation data, not development examples. Keep the original
first-response fixtures unchanged. Gold comes from authored synthetic records.
"""

import hashlib
import json

DOCUMENTS = [
    ("club", "사진 동아리 친구 은호는 도예가다.", "도예가다", "은호"),
    ("office", "회사 동료 은호는 회계사다.", "회계사다", "은호"),
    ("school", "학교 동창 소영은 수의사다.", "수의사다", "소영"),
    ("team", "배구 모임 친구 소영은 번역가다.", "번역가다", "소영"),
    ("gift", "2026년 8월 14일 혜원에게 보라색 모자를 선물했다.", "선물했다", "보라색 모자"),
    ("negative", "도윤에게는 초대장을 보내지 않았다.", "보내지 않았다", "초대장"),
    ("plan", "박물관 자료는 2026년 12월 9일까지 반납할 계획이다.", "반납할 계획이다", "박물관 자료"),
    ("cause", "춘천 여행은 취소했다. 폭설 때문이다.", "취소했다", "춘천 여행"),
]

CASES = {
    "scope_friend": {"question": "그 친구는 어떤 일을 해?", "anchor": "사진 동아리 친구 은호는 누구야?", "gold": ["club"], "allowed_sources": ["club"], "answer_patterns": ["도예"]},
    "scope_friend_possessive": {"question": "그 친구의 직업은 뭐야?", "anchor": "배구 모임 친구 소영은 누구야?", "gold": ["team"], "allowed_sources": ["team"], "answer_patterns": ["번역"]},
    "scope_person": {"question": "그 사람은 무슨 일을 해?", "anchor": "회사 동료 은호는 누구야?", "gold": ["office"], "allowed_sources": ["office"], "answer_patterns": ["회계"]},
    "scope_polite": {"question": "그분의 직업은?", "anchor": "학교 동창 소영은 누구야?", "gold": ["school"], "allowed_sources": ["school"], "answer_patterns": ["수의"]},
    "scope_female": {"question": "그녀의 직업은 뭐야?", "anchor": "학교 동창 소영은 누구야?", "gold": ["school"], "allowed_sources": ["school"], "answer_patterns": ["수의"]},
    "scope_switch": {"question": "회사 동료 은호 말고 사진 동아리 친구 은호의 직업은?", "gold": ["club"], "allowed_sources": ["club"], "answer_patterns": ["도예"]},
    "scope_explicit": {"question": "학교 동창 소영은 무슨 일을 해?", "gold": ["school"], "allowed_sources": ["school"], "answer_patterns": ["수의"]},
    "scope_ambiguous": {"question": "은호 직업은 뭐야?", "gold": ["club", "office"], "clarification": True},
    "control_fact": {"question": "혜원에게 어떤 색 모자를 선물했어?", "gold": ["gift"], "answer_patterns": ["보라|자주", "모자"]},
    "control_date": {"question": "혜원에게 모자를 선물한 날짜는?", "gold": ["gift"], "answer_patterns": ["8월|08-", "14"]},
    "control_negation": {"question": "도윤에게 초대장을 보냈어?", "gold": ["negative"], "answer_patterns": ["않|안.*보|부정"]},
    "control_plan": {"question": "박물관 자료를 실제 반납했어?", "gold": ["plan"], "answer_patterns": ["계획|예정", "확인|불명|알.*없|실제"]},
    "control_cause": {"question": "춘천 여행을 취소한 이유는?", "gold": ["cause"], "answer_patterns": ["폭설|눈"]},
    "control_absent": {"question": "도윤의 혈액형은?", "gold": [], "absent": True},
    "control_compound": {"question": "회사 동료 은호의 직업과 춘천 여행을 취소한 이유는?", "gold": ["office", "cause"], "allowed_sources": ["office", "cause"], "answer_patterns": ["회계", "폭설|눈"]},
    "control_other_role": {"question": "학교 동창 말고 배구 모임 친구 소영의 직업은?", "gold": ["team"], "allowed_sources": ["team"], "answer_patterns": ["번역"]},
}


def manifest():
    encoded = json.dumps({"documents": DOCUMENTS, "cases": CASES}, ensure_ascii=False, sort_keys=True).encode()
    return {"sha256": hashlib.sha256(encoded).hexdigest(), "cases": list(CASES),
            "gold_origin": "hand_authored_synthetic_sources", "version": 1,
            "purpose": "independent confirmation frozen before identity follow-up repair"}
