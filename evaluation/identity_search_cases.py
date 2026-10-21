"""Second independent confirmation frozen before scoped-search optimization.

Authored substitutions give new sources, people, roles, occupations and dates.
The identity lookup cases also test the initial conversation preparation query.
No results from this set may be used to tune its answer rules.
"""

from copy import deepcopy
import hashlib
import json

from .identity_followup_cases import DOCUMENTS as ORIGINAL_DOCUMENTS, CASES as ORIGINAL_CASES

SUBSTITUTIONS = [
    ('사진 동아리 친구', '동네 친구'), ('회사 동료', '연구실 동료'),
    ('학교 동창', '대학교 선배'), ('배구 모임 친구', '축구 모임 친구'),
    ('은호', '다은'), ('소영', '준서'), ('혜원', '나영'), ('도윤', '가온'),
    ('도예가', '제빵사'), ('도예', '제빵'), ('회계사', '물리학자'), ('회계', '물리학'),
    ('수의사', '약사'), ('수의', '약'), ('번역가', '건축가'), ('번역', '건축'),
    ('2026년 8월 14일', '2026년 6월 11일'), ('8월|08-', '6월|06-'), ('14', '11'),
    ('보라|자주', '빨간|빨강'), ('보라색', '빨간색'), ('모자', '가방'),
    ('초대장', '엽서'), ('박물관 자료', '연구실 도서'),
    ('춘천 여행', '속초 캠핑'), ('폭설|눈', '태풍|강풍'), ('폭설', '태풍'),
]


def authored_text(value):
    for old, new in SUBSTITUTIONS:
        value = value.replace(old, new)
    return value


DOCUMENTS = [tuple(authored_text(value) for value in row) for row in ORIGINAL_DOCUMENTS]
CASES = json.loads(authored_text(json.dumps(deepcopy(ORIGINAL_CASES), ensure_ascii=False)))
CASES['scope_explicit'] = {'question': '연구실 동료 다은은 누구야?', 'gold': ['office'],
    'allowed_sources': ['office'], 'answer_patterns': ['물리학']}
CASES['control_other_role'] = {'question': '동네 친구 다은은 누구야?', 'gold': ['club'],
    'allowed_sources': ['club'], 'answer_patterns': ['제빵']}
CASES = {'search2_' + key: value for key, value in CASES.items()}


def manifest():
    encoded = json.dumps({'documents': DOCUMENTS, 'cases': CASES}, ensure_ascii=False, sort_keys=True).encode()
    return {'sha256': hashlib.sha256(encoded).hexdigest(), 'cases': list(CASES),
        'version': 2, 'gold_origin': 'hand_authored_synthetic_sources',
        'purpose': 'independent scoped-search confirmation frozen before call-structure change'}
