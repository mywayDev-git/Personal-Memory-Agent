import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from evaluation.latency_variants import configured
from pma.chat.source_completion import draft
from pma.settings import AppSettings

RAW=Path('evaluation/source_completion_cases.json').read_bytes()
DATA=json.loads(RAW)
CONTRACTS=[dict(r,split=k) for k,v in DATA['splits'].items() for r in v['probe_contracts']]


def settings():
    return configured(AppSettings(),['source_facts','source_dates','source_completion'])


def record(case):
    day=case['date']
    return {'id':'r','record_id':'record','revision_id':'revision','source_text':case['source'],
        'memory_type':'event','assertion_polarity':'affirmed','evidence':[{'quote':case['source'],'start':0,'end':len(case['source'])}],
        'fact':{'state':'observed','action_relation':'give','object':case['object'],
          'event_time':{'start':day,'end':None,'certainty':'explicit' if day else 'uncertain','precision':'day' if day else 'unknown'},
          'time_validation':{'status':'verified' if day else 'unresolved'},'warnings':[],'review_reasons':[]}}


def test_new_independent_sources_and_contracts_were_frozen_before_product_changes():
    from evaluation.answer_integrity_cases import load
    manifest=json.loads(Path('evaluation/source_completion_manifest.json').read_text('utf-8'))
    assert hashlib.sha256(RAW).hexdigest()==manifest['sha256']
    a,ca,_=load('source_development');b,cb,_=load('source_confirmation')
    assert len(ca)==len(cb)==16
    assert not {r[1] for r in a}&{r[1] for r in b}
    old=set()
    for split in ['development','confirmation','v2_development','v2_confirmation','v3_development','v3_confirmation']:
        rows,_,_=load(split);old.update(r[1] for r in rows)
    assert not ({r[1] for r in a}|{r[1] for r in b})&old


@pytest.mark.parametrize('case',CONTRACTS,ids=lambda c:c['split']+'_'+c['id'])
def test_frozen_literal_proposal_contracts(case):
    proposal=draft(case['question'],[record(case)],settings())
    assert bool(proposal) is case['eligible']
    if proposal:
        assert 'validation' not in proposal
        assert case['source'] in proposal['items'][0]['text']


def test_wrong_absolute_day_and_compound_or_second_matching_event_cannot_close_search():
    case=DATA['splits']['development']['probe_contracts'][0]
    row=record(case)
    assert draft('2026년 7월 20일 '+case['question'],[row],settings()) is None
    assert draft('2026년 7월 19일 '+case['question'],[row],settings()) is not None
    q=case['question']+' 그리고 그 이유는?'
    assert draft(q,[row],settings()) is None
    date_case=DATA['splits']['development']['probe_contracts'][1]
    other=record(date_case);other['id']='other';other['source_text']='유하에게 노란색 모자를 선물했다.'
    other['fact']['event_time'].update(start=None,certainty='uncertain',precision='unknown')
    assert draft(date_case['question'],[record(date_case),other],settings()) is None


@pytest.mark.parametrize('approve,fulfillment',[(True,'direct'),(False,'missing'),(True,'limited')])
def test_source_probe_requires_fresh_direct_review_and_cannot_call_interpretation_or_selection(approve,fulfillment):
    from pma.chat.engine import ChatEngine
    case=DATA['splits']['development']['probe_contracts'][0];row=record(case)
    calls=[]
    def review(q,e,response):
        calls.append('review')
        assert e[0]['source_text']==case['source']
        return {'fulfillment':fulfillment,'abstention':'not_applicable','reason':'fresh independent',
          'items':[{'index':0,'support':'supported' if approve else 'unsupported','relevant':True,
            'issue':'none' if approve else 'other','answer_quote':response['items'][0]['text'],
            'evidence':[{'id':'r','quote':case['source']}]}]}
    engine=ChatEngine.__new__(ChatEngine)
    engine.service=SimpleNamespace(settings=settings(),trace=lambda *a,**kw:None)
    engine.models=SimpleNamespace(review=review,select=lambda *a:pytest.fail('already retrieved complete pool'),
        answer=lambda *a,**kw:pytest.fail('already has literal proposal'))
    engine.resolve=lambda *a,**kw:pytest.fail('closed first lookup only')
    response=engine.generate(case['question'],{'messages':[],'evidence':[row]},'2026-10-22',_source_probe=draft(case['question'],[row],settings()))
    assert calls==['review']
    assert (response['status']=='answered') is (approve and fulfillment=='direct')


def test_probe_recomputes_proposal_instead_of_trusting_injected_answer():
    from pma.chat.engine import ChatEngine
    case=DATA['splits']['development']['probe_contracts'][0];row=record(case)
    engine=ChatEngine.__new__(ChatEngine)
    engine.service=SimpleNamespace(settings=settings(),trace=lambda *a,**kw:None)
    engine.models=SimpleNamespace(review=lambda *a:pytest.fail('tampered proposal'))
    response=engine.generate(case['question'],{'messages':[],'evidence':[row]},'2026-10-22',
        _source_probe={'status':'answered','items':[{'text':'다른 물건을 샀다.','citations':['r']}]})
    assert response['status']=='insufficient_evidence'


def test_default_environment_does_not_enable_source_completion(monkeypatch):
    monkeypatch.setenv('PMA_VERIFIED_SOURCE_SEARCH','1')
    assert not AppSettings.from_env().verified_source_search



def routing(monkeypatch,*,reject=False,change_scope=False,fail_code=None):
    from pma.chat import automatic,interpretation,planner,retrieval,record_reference
    monkeypatch.setattr(record_reference,'references_record',lambda *a:False)
    from pma.errors import AppError
    case=DATA['splits']['development']['probe_contracts'][0];row=record(case)
    row['search_explanation']={'final_selection':{'reason':'relevant'}}
    queries,generated,planned,freezes=[],[],[],[]
    def retrieve(*a,**kw):
        queries.append(a[1]);return None,{'results':[row],'status':'ok','filters':{},'query_plan':{}}
    monkeypatch.setattr(retrieval,'retrieve',retrieve)
    monkeypatch.setattr(automatic,'combine',lambda batches,**kw:list({r['id']:r for b in batches for r in b}.values()))
    def next_query(*a,**kw):planned.append(True);return {'query':''}
    monkeypatch.setattr(automatic,'structured',next_query)
    monkeypatch.setattr(interpretation,'analyze',lambda *a:{'observations':[]})
    monkeypatch.setattr(planner,'prepare',lambda *a:{})
    def grounded(engine,q,session,today,**kw):
        is_probe=kw.get('_source_probe') is not None
        generated.append(is_probe)
        if fail_code:raise AppError(fail_code,'test',409)
        if is_probe and reject:return {'status':'insufficient_evidence','items':[],'validation':'probe_rejected'}
        return {'status':'answered','validation':'model_checked','items':[{'text':case['source'],'citations':['r']}]}
    monkeypatch.setattr(automatic,'grounded',grounded)
    def freeze(rows):
        freezes.append(True)
        return [{**r,'version':len(freezes) if change_scope else 1} for r in rows]
    engine=SimpleNamespace(service=SimpleNamespace(settings=settings(),store=None,trace=lambda *a,**kw:None),
        store=SimpleNamespace(freeze=freeze))
    return automatic,engine,case,queries,generated,planned


@pytest.mark.parametrize('reject,change_scope',[(False,False),(True,False),(False,True)])
def test_source_completion_reuse_is_request_local_and_rejection_keeps_original_path(monkeypatch,reject,change_scope):
    automatic,engine,case,queries,generated,planned=routing(monkeypatch,reject=reject,change_scope=change_scope)
    response,_,_=automatic.run(engine,case['question'],{'messages':[],'context':{}},'2026-10-22','memory')
    assert len(queries)==1
    assert generated==([True,False] if reject or change_scope else [True])
    assert bool(planned) is reject
    assert response['validation']=='model_checked'


@pytest.mark.parametrize('code',['CANCELLED','CHAT_TIMEOUT','SOURCE_CHANGED'])
def test_source_probe_never_swallows_cancellation_deadline_or_source_change(monkeypatch,code):
    from pma.errors import AppError
    automatic,engine,case,_,_,_=routing(monkeypatch,fail_code=code)
    with pytest.raises(AppError) as exc:
        automatic.run(engine,case['question'],{'messages':[],'context':{}},'2026-10-22','memory')
    assert exc.value.code==code


def test_prior_conversation_never_uses_the_first_question_shortcut(monkeypatch):
    automatic,engine,case,_,generated,planned=routing(monkeypatch)
    session={'messages':[{'state':'completed','question':'이전에 물었던 내용',
                         'response':{'status':'answered','items':[]}}],'context':{}}
    automatic.run(engine,case['question'],session,'2026-10-22','memory')
    assert generated==[False]
    assert planned



def test_verified_metadata_cannot_replace_a_different_literal_source_day():
    case=DATA['splits']['development']['probe_contracts'][0]
    row=record(case)
    row['fact']['event_time']['start']='2026-07-20'
    assert draft('2026년 7월 20일 '+case['question'],[row],settings()) is None



def test_unrelated_second_candidate_is_retained_instead_of_discarded_for_a_shortcut():
    case=DATA['splits']['development']['probe_contracts'][1]
    first=record(case)
    other={**first,'id':'other','source_text':'다른 이웃에게 책을 선물했다.'}
    assert draft(case['question'],[first,other],settings()) is None
    assert other['source_text']=='다른 이웃에게 책을 선물했다.'
