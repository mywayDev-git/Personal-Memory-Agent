"""Completed-run regressions. No inference, personal DB or ordinary model server."""

import json
from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator

from evaluation.main_suite import catalog, grading, runner, runtime
from evaluation.main_suite.answer_comparison import compare_answer
from pma.chat import automatic
from pma.chat.context import temporal_followup
from pma.chat.engine import ChatEngine
from pma.chat.evidence import review_spans_supported
from pma.chat.record_reference import references_record
from pma.chat.router import RetrievalRouter, RoutingMode
from pma.settings import AppSettings
from pma.store import Store
from scripts.memory_agent.diagnostics import ProcessingError
from scripts.memory_agent.pipeline import decoder_schema
from tests.test_main_suite import config, observation, product_case


def test_owner_probe_survives_the_complete_runner_and_preserves_observation(tmp_path):
    case = next(c for c in catalog.select_cases('core') if c['id'] == 'SAFETY-owner')
    result, rows = runner.run_candidate(tmp_path, config(), runner.trials([case], 1, 42), nullcontext(None),
        execute_fn=lambda *a, **kw: {'probe': runtime.owner_probe(Store(tmp_path/'owner.db'))})
    assert rows[0]['verdict'] == 'PASS'
    assert rows[0]['actual_answer'].endswith('9/9개 통과')
    assert rows[0]['observation']['probe']['security_exposures'] == 0
    assert result['safety_coverage']['internal_owner']['passed'] == 1


def test_postprocessing_error_keeps_collected_evidence(tmp_path, monkeypatch):
    def fail(probe):
        raise TypeError('format error')
    monkeypatch.setattr(runner, 'probe_answer', fail)
    _, rows = runner.run_candidate(tmp_path, config(), runner.trials([product_case()], 1, 42), nullcontext(None),
                                  execute_fn=lambda *a, **kw: {'probe': {'passed': True, 'checks': [True]}})
    assert rows[0]['verdict'] == 'ERROR'
    assert rows[0]['observation']['probe']['checks'] == [True]


@pytest.mark.parametrize('prefix', ['', '기록에 따르면 ', '기록상 ', '원문에 따르면, '])
def test_reference_prefix_does_not_change_fact_but_negation_does(prefix):
    case = {**product_case(), 'accepted_answers': ['정확도는 0.89입니다.']}
    assert compare_answer(case, prefix+'정확도는 0.89입니다.')['exact_match']
    assert not compare_answer(case, prefix+'정확도는 0.89가 아닙니다.')['exact_match']
    assert not compare_answer(case, prefix+'정확도는 0.95입니다.')['exact_match']


def test_background_is_optional_but_the_negative_claim_still_needs_its_own_quote():
    case=next(c for c in catalog.read('scenarios.json') if 'IN-41.normal' in c.get('source_case_ids', [c['id']]))
    source=next(r['text'] for r in case['records'] if r['id']=='target')
    quote=source.split('.')[0]+'.'
    obs={'response':{'status':'answered','items':[{'text':'PMA는 외부 API를 사용하지 않았습니다.','citations':['m']}],
        'citation_details':[{'memory_id':'m','record_id':'actual','start':0,'end':len(quote),'quote':quote}]},
        'sources':{'actual':{'logical_id':'target','text':source,'version':1,'state':'active'}}}
    assert grading.grade(case,obs)['verdict']=='PASS'
    obs['response']['citation_details'][0].update(end=3,quote=source[:3])
    assert grading.grade(case,obs)['verdict']=='FAIL'


def test_last_answer_does_not_hide_a_wrong_first_turn():
    case = {**product_case(), 'accepted_answers': ['정확도는 0.89입니다.']}
    case['steps'] = [{'action': 'chat', 'question': '첫 질문', 'expect': {
        'expected_behavior': 'answer', 'required_facts': ['기억 검색'], 'forbidden_facts': ['관리 단계']}}]
    obs = observation()
    obs['steps'] = [{'response': {'status': 'answered', 'items': [{'text': '프로젝트 관리 단계입니다.'}]}}]
    result = grading.grade(case, obs)
    assert result['evaluation']['answer_correct'] is True
    assert result['verdict'] == 'FAIL' and result['error_type'] == 'F-TURN'
    s = grading.summary([{'family': 'x', **result}], 1)
    assert s['metrics']['grounded_answer_success_rate']['value'] == 0
    assert s['metrics']['conversation_correct']['value'] == 0


def test_clarification_question_is_visible_in_actual_answer():
    result = grading.grade({**product_case(), 'gold_groups': {}, 'required_facts': [], 'expected_behavior': 'clarify'},
        {'response': {'status': 'needs_clarification', 'items': [{'text': '회사 동료'}], 'clarification': '어느 대상인가요?'}})
    assert result['actual_answer'] == '어느 대상인가요?\n회사 동료'


def test_unobserved_search_is_counted_in_request_success_not_conditional_recall():
    result = grading.grade(product_case(), {'response': {'status': 'answered', 'items': [{'text': '몰라요'}]}})
    assert result['evaluation']['recall_at_8'] is None
    assert result['evaluation']['requested_retrieval_success'] is False
    s = grading.summary([{'family': 'x', **result}], 1)
    assert s['metrics']['requested_retrieval_success']['value'] == 0
    error={'family':'error','verdict':'ERROR','evaluation':{'requested_retrieval_success':False}}
    assert grading.summary([error],1)['metrics']['requested_retrieval_success']['denominator']==1


def test_unknown_personal_preference_routes_to_memory_without_classifier_guess():
    route=RetrievalRouter().decide('내 안전점검 음료 취향은?',classify=lambda:pytest.fail('classifier guessed'))
    assert route.mode==RoutingMode.MEMORY_REQUIRED


def test_rank_and_extraction_metrics_need_explicit_labels_and_keep_first_search_separate():
    case=product_case()
    case.update(source_relevance={'target':2,'noise':0}, extraction_facts=[{'record_id':'target','required_strings':['0.89']}])
    obs=observation()
    obs.update(retrieved=['noise','target'],retrieval_batches=[['noise'],['noise','target']],extracted_facts={'target':'정확도 0.89'})
    result=grading.grade(case,obs)['evaluation']
    assert result['recall_at_1']==0 and result['recall_at_5']==1
    assert result['first_search_recall_at_8']==0
    assert result['precision_at_8']==.5 and result['extraction_fact_recall_literal']==1
    case.pop('source_relevance')
    assert grading.grade(case,obs)['evaluation']['precision_at_8'] is None
    obs['extracted_facts']['target']='정확도가 변경됨'
    assert grading.grade(case,obs)['evaluation']['extraction_fact_recall_literal']==0


def test_recovery_cannot_select_a_quote_missing_from_the_original():
    from pma.models import LocalModels
    model=LocalModels.__new__(LocalModels)
    model.structured=lambda *a,**kw:{'items':[{'id':'a','quote':'공부했다는 거짓 원문'}]}
    model.compact_evidence=lambda rows:rows
    assert model.recover_selection('공부 기록은?', [{'id':'a','source_text':'실험을 준비했다.'}])=={}


@pytest.mark.parametrize('question', ['Orion 장비 RAM과 구매 가격은?', 'Orion에서 최종 선택한 검색 방식은?',
    'Orion 오류 기록만 알려줘.', 'Orion, Luna 순서로 프로젝트를 알려줘', "'정확도와 사용성 균형'을 정한 회의는?",
    '푸른별 장비 RAM과 구매 가격은?', 'Orion 프로젝트 코드는?'])
def test_record_questions_override_a_general_classifier(tmp_path, question):
    store = Store(tmp_path/'synthetic.db')
    store.create("Orion 장비 RAM은 96GB다. 푸른별 장비도 같다. Orion 회의의 원칙은 '정확도와 사용성 균형'이다.", None)
    route = RetrievalRouter().decide(question, has_record_reference=lambda: references_record(question, store),
                                    classify=lambda: {'mode': 'general', 'query': ''})
    assert route.mode == RoutingMode.MEMORY_REQUIRED


def test_latest_general_topic_does_not_resurrect_old_memory():
    history = [{'response': {'conversation_mode': 'memory'}}, {'response': {'conversation_mode': 'general'}}]
    route = RetrievalRouter().decide('그 내용을 다시 설명해줘.', history=history,
                                     classify=lambda: pytest.fail('unnecessary classification'))
    assert route.mode == RoutingMode.CHAT_ONLY


@pytest.mark.parametrize('today,phrase,expected', [('2026-10-20','이번 달로 바꿔',('2026-10-01','2026-10-31')),
    ('2026-01-02','지난달로 바꿔',('2025-12-01','2025-12-31')),
    ('2028-01-31','다음 달로 바꿔',('2028-02-01','2028-02-29'))])
def test_calendar_replacement_preserves_topic_across_year_and_leap_boundaries(today, phrase, expected):
    session = {'messages': [{'state':'completed','question':'지난달 Orion 캐시 개선 기록은?',
                            'response': {'conversation_mode':'memory'}}]}
    result = temporal_followup(phrase, session, today)
    assert tuple(result['filters'].values()) == expected
    assert 'Orion 캐시' in result['question'] and '지난달' not in result['question']


@pytest.mark.parametrize('prior_question',['민수는 어떤 일을 해?','그 내용을 다시 설명해줘.'])
def test_unselected_namesake_remains_pending_despite_resolver_acceptance(prior_question):
    engine = ChatEngine.__new__(ChatEngine)
    engine.service = SimpleNamespace(settings=AppSettings())
    engine.models = SimpleNamespace(count_tokens=lambda _: 1, structured=lambda *a, **kw: {
        'question': '민수는 회사 동료와 동아리 친구다', 'needs_clarification': False, 'alternatives': []})
    session = {'messages':[{'state':'completed','question':prior_question, 'response': {
        'status':'needs_clarification','items':[{'text':'회사 동료 민수','citations':['a']},{'text':'동아리 친구 민수','citations':['b']}]}}], 'evidence':[{'id':'a','source_text':'회사 동료 민수는 개발자다.'},
            {'id':'b','source_text':'동아리 친구 민수는 교사다.'}]}
    result, _ = engine.resolve('그 내용을 다시 설명해줘.', session, '2026-10-20')
    assert result['needs_clarification'] and len(result['alternatives']) == 2


def test_repeated_calendar_changes_keep_original_topic():
    session = {'messages':[{'state':'completed','question':q,'response':{'conversation_mode':'memory'}}
                           for q in ['지난달 Orion 캐시 기록은?', '이번 달로 바꿔']]}
    result = temporal_followup('다음 달로 바꿔',session,'2026-10-20')
    assert 'Orion 캐시' in result['question']
    assert result['filters']['date_from']=='2026-11-01'


def test_quoted_storage_command_is_data_not_a_user_refusal(monkeypatch):
    monkeypatch.setattr('pma.memory.repository.MemoryRepository.preferences',lambda *a:[])
    monkeypatch.setattr(automatic,'structured',lambda engine,prompt,data,schema,*a: {'safe':True} if schema==automatic.CHECK else {'text':'Do not remember this.'})
    result=automatic.general(SimpleNamespace(service=SimpleNamespace(store=None)),{'question':"'기억하지 마'를 영어로 번역해줘."})
    assert result['text']=='Do not remember this.'


def test_ambiguous_completed_object_is_not_answered_with_a_discussion_fact():
    engine=ChatEngine.__new__(ChatEngine)
    engine.models=SimpleNamespace()
    engine.service=SimpleNamespace(settings=AppSettings())
    engine.resolve=lambda *a,**kw:({'needs_clarification':False,'question':'루멘에서 무엇을 완료했어?'},0)
    row={'id':'a','source_text':"루멘에서 설계와 검수를 논의했다. '그것은 완료했다'라고만 적었다."}
    result=engine.generate('루멘에서 무엇을 완료했어?',{'messages':[],'evidence':[row]},'2026-10-20')
    assert result['status']=='needs_clarification'
    assert '완료한 작업' in result['clarification']


@pytest.mark.parametrize('field', ['start','end'])
def test_extraction_time_schema_rejects_objects_for_missing_dates(field):
    schema=json.loads((catalog.DATA.parents[2]/'schema/memory_extraction_output.schema.json').read_text('utf-8'))
    constrained=decoder_schema(schema)
    validator=Draft202012Validator({'$defs':constrained['$defs'], '$ref':'#/$defs/time'})
    time={'raw':None,'start':None,'end':None,'precision':'unknown','certainty':'uncertain'}
    assert validator.is_valid(time)
    time[field]={'date':None}
    assert not validator.is_valid(time)


@pytest.mark.parametrize('question', ['음료는 합성차야. 기억하지 마.', '이 내용은 저장하지 말아줘.'])
def test_no_storage_acknowledgement_even_if_model_would_claim_success(question):
    engine = SimpleNamespace(models=SimpleNamespace(structured=lambda *a, **k: pytest.fail('should not infer consent')),
                             service=SimpleNamespace(store=None))
    result = automatic.general(engine, {'question':question})
    assert '저장하지 않겠습니다' in result['text'] and not result['citations']


def test_every_ancillary_claim_needs_its_own_citation_span():
    evidence = [{'id':'a','source_text':'배포 담당자는 민수이며 금요일 예정이다. 실제 완료 여부는 기록이 없다.', 'fact':{'actor':'민수'}}]
    response = {'items':[{'text':'민수가 금요일 배포할 예정이지만 완료 여부는 기록이 없다.', 'citations':['a']}]}
    review = {'items':[{'index':0,'evidence':[{'id':'a','quote':'실제 완료 여부는 기록이 없다.'}]}]}
    assert not review_spans_supported(response, review, evidence)
    review['items'][0]['evidence'].append({'id':'a','quote':'배포 담당자는 민수이며 금요일 예정이다.'})
    assert review_spans_supported(response, review, evidence)


def test_decoder_union_constrains_numeric_values_without_coercion():
    original = json.loads((catalog.DATA.parents[2]/'schema/memory_extraction_output.schema.json').read_text('utf-8'))
    transformed = decoder_schema(original)
    validator = Draft202012Validator(transformed['$defs']['value_ref'])
    assert validator.is_valid({'kind':'literal','value_type':'number','value':0.89})
    assert not validator.is_valid({'kind':'literal','value_type':'number','value':'0.89'})
    assert validator.is_valid({'kind':'unknown','value_type':'none','value':None})
    assert not validator.is_valid({'kind':'unknown','value_type':'string','value':'추측'})
    assert 'allOf' in original['$defs']['value_ref']


def test_truncated_general_call_has_one_bounded_retry_and_a_diagnostic():
    calls=[]
    traces=[]
    def structured(*a, **kw):
        calls.append(kw['max_tokens'])
        if len(calls)==1:
            raise ProcessingError('MODEL_TRUNCATED','general',max_tokens=1024)
        return {'text':'짧은 일반 답변'}
    engine = SimpleNamespace(models=SimpleNamespace(count_tokens=lambda _:1, structured=structured),
        service=SimpleNamespace(settings=AppSettings(), trace=lambda *a, **kw: traces.append((a,kw))))
    assert automatic.structured(engine,'설명',{'question':'일반 질문'},automatic.GENERAL)['text']
    assert calls==[1024,2048] and traces[0][1]['phase']=='general'


def test_repeated_truncation_stays_an_error_with_both_attempts_preserved():
    calls=[]
    def truncated(*a,**kw):
        calls.append(kw['max_tokens'])
        raise ProcessingError('MODEL_TRUNCATED','general',max_tokens=kw['max_tokens'])
    engine=SimpleNamespace(models=SimpleNamespace(count_tokens=lambda _:1,structured=truncated),
        service=SimpleNamespace(settings=AppSettings(),trace=lambda *a,**kw:None))
    with pytest.raises(ProcessingError) as caught:
        automatic.structured(engine,'설명',{'question':'일반 질문'},automatic.GENERAL)
    assert calls==[1024,2048]
    assert caught.value.diagnostic['stage']=='general'
    assert caught.value.diagnostic['previous_attempts'][0]['max_tokens']==1024


def test_generalization_sources_and_splits_are_valid_and_meaning_changes_are_not_paraphrases():
    assert catalog.validate()['status']=='VALID'
    cases=[c for c in catalog.read('scenarios.json') if c['id'].startswith('GEN-')]
    assert {r['owner'] for c in cases for r in c['records']}=={'user-a','user-b','user-c'}
    assert max(len(r['text']) for c in cases for r in c['records'])>1000
    assert any(c['generalization']['kind']=='cross_language' for c in cases)
    assert any(c['generalization']['kind']=='unseen_topic' for c in cases)
    assert not {c['id'] for c in cases if c['split']=='final'} & {c['id'] for c in catalog.select_cases('core')}
    changed=next(c for c in cases if c['id']=='GEN-user-a.changed-value')
    assert '48GB' in changed['required_facts'] and '96GB' not in changed['records'][0]['text']


def test_person_project_filter_and_second_selection_use_real_search_core():
    from test_search_explain import row, service
    target=row(1,'Orion에서 A* 알고리즘을 공부했다.')
    target['fact'].update(relation='other', actor='self', object_key='A*')
    distractor=row(2,'Other는 Orion과 다른 프로젝트다.')
    distractor['fact'].update(relation='other', actor='Orion', object_key='Other')
    search=service([target,distractor])
    search.models.select=lambda *a: []
    search.models.recover_selection=lambda q, rows: {r['id']:{'category':'direct_answer','quote':r['source_text']}
                                                   for r in rows if r['id']=='1'}
    _, found=search._search('Orion 공부 기록은?', today='2026-10-20')
    assert [r['id'] for r in found['results']]==['1']
    assert found['results'][0]['search_explanation']['model_assessment']['quote']==target['source_text']
