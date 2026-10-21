"""Conservative vetoes for explicitly scoped occupation answers.

These checks cannot approve an answer. A fresh model review remains mandatory.
"""

import re

from .identity import ROLE, canonical_label, positive_labels


LIMIT = re.compile(r"확인.{0,12}(?:없|않)|알\s*수\s*없|제공.{0,8}않|명시.{0,8}않|기록.{0,8}없|미상|불명|모르")
ATTRIBUTE = re.compile(r"키(?:가|는|은|\s)|\d\s*(?:cm|㎝|kg|세|살)|몸무게|혈액형|생일|출생|거주")


def occupation_target(question):
    targets = positive_labels(question)
    if len(set(targets)) != 1:
        return None
    target = targets[0]
    tail = question[question.find(target) + len(target):].strip()
    if not re.fullmatch(
        r"(?:은|는|의)?\s*(?:직업(?:은|이)?\s*(?:뭐야|뭐예요|뭔가요|무엇인가요)?|"
        r"(?:어떤|무슨)\s*일(?:을)?\s*(?:해|해요|하나요|합니까|하세요))\s*[?.!]*", tail
    ):
        return None
    return target


def same_role(target, label):
    left, right = canonical_label(target), canonical_label(label)
    return left.endswith(right) or right.endswith(left)


def target_text(target, text):
    return any(same_role(target, match.group()) for match in ROLE.finditer(text))


def plain_occupation(target, text):
    """Only unqualified, explicit copular statements; never infer a job."""
    from .review_sources import source_units, instruction_span
    for unit in source_units(text):
        if instruction_span(unit) or re.search(r"계획|예정|않|아니|미상|불명|과거|예전|이전|그만|추측|전언", unit):
            continue
        for match in ROLE.finditer(unit):
            if not same_role(target, match.group()):
                continue
            tail = unit[match.end():].strip().rstrip(".!?")
            if ATTRIBUTE.search(tail):
                continue
            found = re.fullmatch(r"(?:은|는|이|가)\s+([가-힣A-Za-z ·-]{1,40}?)(?:입니다|이다|다|이에요|예요)", tail)
            if found:
                return found[1]
    return None


def enforce_answer_integrity(question, evidence, response, review):
    target = occupation_target(question)
    if not target:
        return
    target_rows = [row for row in evidence if target_text(target, row['source_text'])]
    known_jobs = [job for row in target_rows if (job := plain_occupation(target, row['source_text']))]
    for checked in review['items']:
        claim = response['items'][checked['index']]
        selected = checked['evidence']
        # Every chosen span must belong to this person when it declares a role.
        # A model's approval of the whole answer cannot excuse an extra ref.
        unrelated = any(any(not same_role(target, m.group()) for m in ROLE.finditer(ref['quote']))
                        and not target_text(target, ref['quote']) for ref in selected)
        cited = [row for row in evidence if row['id'] in claim['citations']]
        unrelated = unrelated or any(ROLE.search(row['source_text']) and not target_text(target, row['source_text'])
                                     for row in cited)
        if unrelated:
            checked.update(support='unsupported', relevant=False, issue='person')
            review['reason'] = '질문의 인물과 무관한 역할·인물의 인용이 포함됨'
        text = claim['text']
        limited = bool(re.search(r'직업|어떤\s*일|무슨\s*일', text) and LIMIT.search(text))
        # Height-only quotations are true but do not answer an occupation query.
        if (ATTRIBUTE.search(text) and not limited
                and not any(job in text for job in known_jobs)
                and not re.search(r'직업|일하|근무|종사', text)):
            checked['relevant'] = False
            review.update(fulfillment='missing', reason='직업 질문에 다른 속성만 답하고 직업 미확인을 설명하지 않음')
        if limited and known_jobs and not any(job in text for job in known_jobs):
            checked['relevant'] = False
            review.update(fulfillment='missing', reason='같은 역할의 별도 원문에 직업이 명시되어 있어 미확인 답변은 불충분함')


def occupation_limit_draft(question, evidence):
    """Repair a height-only answer without pretending absence in the whole DB."""
    target = occupation_target(question)
    if not target:
        return None
    rows = [row for row in evidence if target_text(target, row['source_text'])]
    if not rows or any(plain_occupation(target, row['source_text']) for row in rows):
        return None
    # Restrict the proposal to the observed height-only failure class. Other
    # attributes, free prose and conflicting sources keep normal generation.
    from .review_sources import source_units
    if not all(all(target_text(target, unit) and ATTRIBUTE.search(unit)
                   and not re.search(r'직업|일하|근무|종사|계획|예정|지시', unit)
                   for unit in source_units(row['source_text'])) for row in rows):
        return None
    return {'status': 'answered', 'items': [{
        'text': f'{target}의 직업은 현재 확인한 기록만으로는 알 수 없습니다.',
        'citations': [row['id'] for row in rows],
    }]}
