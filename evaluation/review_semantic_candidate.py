"""Evaluation candidate: source/answer comparisons before accepting a review.

Inherited answer generation and retrieval are unchanged. No production flag enabled.
"""
from copy import deepcopy

from pma.models import LocalModels
from scripts.memory_agent.validator import schema_errors

RULES = """
추가 검증 절차: 먼저 checks에서 원문이 허용하는 의미와 답변의 의미를 비교하고,
그 결과를 items와 fulfillment에 반영한다. 답변을 고치거나 다른 질문에 답하지 않는다.
passed는 의미 일치, failed는 의미 불일치 또는 질문의 값 누락,
not_applicable은 해당 현상이 원문·질문·답변에 없다는 뜻이다.
각 적용되는 검사에는 실제 제공된 원문 구절을 생략·변형 없이 인용한다.

time: 질문이 사건일인지 발언일인지 먼저 구별한다. 인용 밖 명시된 발언 날짜와
인용 속 상대 날짜를 함께 읽어 실제 사건일을 계산하고 source_interpretation에 적는다.
예: '2031-01-01에 어제 만났다고 말했다'의 만남 날짜는 2030-12-31이다.
발언 날짜는 2031-01-01이다. 질문이 사건일인데 발언일로 답하면 failed, issue=time이다.
사건 날짜를 묻는데 원문 발언만 되풀이하고 날짜 값을 답하지 않아도 failed이며
fulfillment=missing이다. 발언일 질문에 올바른 발언일을 답하면 passed다.
발화 날짜가 없으면 저장일·기록일로 대신 계산하지 않는다. 날짜 미확인을 정확히
설명하는 답변은 허용한다. 날짜 값은 실제 달력 기준으로 계산하며 월·연 경계도 처리한다.

correction: 인용한 기록만 보지 말고 제공된 다른 기록에서 같은 사건을 명시적으로
정정했는지 확인한다. 정정된 값을 묻는데 정정 전 값만 답하면 failed다.
예: '8일이라고 기록했다. 앞 날짜를 정정한다. 실제는 10일이다'에 실제 날짜 8일은
실패이고 10일은 통과다. 앞서 8일이라고 기록했지만 10일로 정정했다고 설명하는
답변도 통과다. 다른 사건의 정정으로 덮어쓰거나 단순 기록 순서를 정정으로 간주하지
않는다. 정정 관계 없는 서로 다른 기록은 상충을 유지하고 임의로 한쪽을 선택하지 않는다.

negation_scope: 부정이 행동의 실행에 걸리는지 결정·계획에 걸리는지 분리한다.
'주지 않았다'는 행동 미실행의 근거다. '주기로 하지 않았다'는 전달 결정을 하지
않았다는 기록일 뿐, 실제 주지 않았다는 뜻도 주지 않기로 결정했다는 뜻도 아니다.
따라서 이 기록만으로 '실제로 전달하지 않았다'고 답하면 failed, issue=negation이다.
'하기로 했고 아직 하지 않았다'면 현재 미실행을 답해도 passed다.
추측·계획·결정·취소만으로 실제 실행 여부를 단정하지 않는다. 확인된 결정 내용을
보존하면서 실제 실행은 미확인이라고 설명하면 passed다. 명시적 행동 부정까지
근거 부족으로 거절하지 않는다. 빈 답변도 관련 사실과 한계를 설명할 수 있는지 평가한다.

세 검사 중 failed가 하나라도 있으면 supported/issue=none/direct로 승인하지 않는다.
not_applicable을 오류 회피용으로 쓰지 않는다. 정확한 한계 설명과 상충 설명을 보존한다.
"""


def check_schema():
    ref = dict(type='object',additionalProperties=False,required=['id','quote'],properties={
        'id':dict(type='string'),'quote':dict(type='string',minLength=1)})
    one = dict(type='object',additionalProperties=False,
               required=['source_interpretation','answer_interpretation','evidence','status'],
               properties={
                   'source_interpretation':dict(type='string',maxLength=240),
                   'answer_interpretation':dict(type='string',maxLength=240),
                   'evidence':dict(type='array',maxItems=3,items=ref),
                   'status':dict(enum=['passed','failed','not_applicable'])})
    return dict(type='object',additionalProperties=False,
                required=['time','correction','negation_scope'],
                properties={key:deepcopy(one) for key in ('time','correction','negation_scope')})


def apply_checks(result, records):
    result=deepcopy(result)
    checks=result.pop('checks')
    if schema_errors(checks,check_schema()):
        raise ValueError('INVALID_SEMANTIC_CHECKS')
    sources={r['id']:r for r in records}
    failed=[]
    for name,check in checks.items():
        if check['status']!='not_applicable' and not check['evidence']:
            raise ValueError('SEMANTIC_CHECK_WITHOUT_SOURCE')
        for ref in check['evidence']:
            if ref['id'] not in sources:
                raise ValueError('SEMANTIC_CHECK_UNKNOWN_SOURCE')
            source=sources[ref['id']]
            texts=[source.get('source_context','')]+[e['quote'] for e in source.get('evidence',[])]
            if not any(ref['quote'] in text for text in texts):
                raise ValueError('SEMANTIC_CHECK_INVALID_QUOTE')
        if check['status']=='failed':failed.append(name)
    if failed:
        result['fulfillment']='missing'
        if result['abstention']!='not_applicable':result['abstention']='excessive'
        result['reason']=('의미 대조 실패: '+','.join(failed)+'; '+result['reason'])[:240]
    return result


class SemanticReviewModels(LocalModels):
    def structured(self,prompt,data,schema,max_tokens=None):
        if 'fulfillment' not in schema.get('properties',{}):
            return super().structured(prompt,data,schema,max_tokens=max_tokens)
        schema=deepcopy(schema)
        schema['properties']={'checks':check_schema(),**schema['properties']}
        schema['required']=['checks',*schema['required']]
        raw=super().structured(prompt+'\n'+RULES,data,schema,max_tokens=max_tokens)
        return apply_checks(raw,data['source_records'])
