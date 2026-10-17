import copy
from unittest.mock import patch

import pytest
import requests

from evaluation.fixed_answer_replay import Journal, TransportStop, evaluate, read
from pma.answer_review import answer_found


def fixture():
    quote='민수는 부산에 살고 있다.'
    nodes=[dict(id='m1',content=quote,source_text=quote,evidence=[dict(quote=quote)],
                fact=dict(relation='other',state='observed',review_reasons=[],distance_m=[]))]
    response=dict(status='answered',items=[dict(text=quote,citations=['m1'])])
    review=dict(fulfillment='direct',abstention='not_applicable',reason='원문 일치',
                items=[dict(index=0,support='supported',relevant=True,issue='none',
                            answer_quote=quote,evidence=[dict(id='m1',quote=quote)])])
    return dict(question='민수는 어디 살아?',evidence=nodes),response,review


class Models:
    def __init__(self, failures=0, disconnect=None):
        self.payload,self.response,self.review_result=fixture()
        self.calls=[]
        self.failures,self.disconnect=failures,disconnect

    def answer(self,q,nodes,feedback=None):
        self.calls.append(('repair' if feedback else 'draft',q,copy.deepcopy(nodes),copy.deepcopy(feedback)))
        return copy.deepcopy(self.response)

    def verify(self,q,nodes,items):
        self.calls.append(('legacy_verify',q,copy.deepcopy(nodes),copy.deepcopy(items)))
        return True

    def review(self,q,nodes,response):
        self.calls.append(('review',q,copy.deepcopy(nodes),copy.deepcopy(response)))
        if self.disconnect:
            raise self.disconnect
        result=copy.deepcopy(self.review_result)
        if self.failures:
            self.failures-=1
            result['fulfillment']='missing'
        return result


def journal(tmp_path,models,identity='one'):
    return Journal(tmp_path/'stage.json',identity,models)


def test_shared_inputs_draft_review_and_cache(tmp_path):
    m=Models(failures=1)
    before=copy.deepcopy(m.payload)
    result=evaluate(m.payload,m,m,journal(tmp_path,m))
    assert [c[0] for c in m.calls]==['draft','legacy_verify','review','repair','review']
    assert result['B']['draft']==result['C']['draft']==result['D']['draft']
    assert result['C']['review']==result['D']['review']
    assert all(c[2]==before['evidence'] for c in m.calls)
    assert m.payload==before
    assert result['D']['decision']=='repaired'
    count=len(m.calls)
    assert evaluate(m.payload,m,m,journal(tmp_path,m))==result
    assert len(m.calls)==count


@pytest.mark.parametrize('failures',[0,1,2])
def test_matches_existing_model_path_without_structured_shortcut(tmp_path,failures):
    m=Models(failures=failures)
    result=evaluate(m.payload,m,m,journal(tmp_path,m))
    for label,repair in [('C',False),('D',True)]:
        other=Models(failures=failures)
        with patch('pma.grounding.grounded_response',return_value=None):
            expected=answer_found(other,m.payload['question'],dict(results=m.payload['evidence'],query_plan={}),lambda *a,**k:None,repair=repair)
        assert result[label]['response']=={k:expected[k] for k in ('status','items')}
    assert sum(c[0]=='repair' for c in m.calls)<=1


def test_disconnect_resumes_only_failed_stage(tmp_path):
    m=Models(disconnect=requests.ConnectionError())
    with pytest.raises(TransportStop):
        evaluate(m.payload,m,m,journal(tmp_path,m))
    saved=read(tmp_path/'stage.json')
    assert set(saved['stages'])=={'draft','legacy_verify'}
    assert saved['attempts'][-1]['status']=='transport_error'
    m.disconnect=None
    count=len(m.calls)
    result=evaluate(m.payload,m,m,journal(tmp_path,m))
    assert [c[0] for c in m.calls[count:]]==['review']
    assert result['D']['response']['status']=='answered'


def test_protocol_failure_is_not_semantic_abstention_or_resampled(tmp_path):
    m=Models(disconnect=ValueError('INVALID_REVIEW_SOURCE_QUOTE'))
    result=evaluate(m.payload,m,m,journal(tmp_path,m))
    assert result['B']['status']=='complete'
    assert result['C']['status']==result['D']['status']=='processing_error'
    assert result['C']['response'] is None
    count=len(m.calls)
    evaluate(m.payload,m,m,journal(tmp_path,m))
    assert len(m.calls)==count


def test_cache_isolation_and_input_change_rejected(tmp_path):
    m=Models()
    evaluate(m.payload,m,m,journal(tmp_path,m))
    with pytest.raises(AssertionError,match='IDENTITY'):
        journal(tmp_path,m,identity='different_code')
    altered=copy.deepcopy(m.payload)
    altered['question']='다른 질문'
    with pytest.raises(AssertionError,match='INPUT'):
        evaluate(altered,m,m,journal(tmp_path,m))


def test_only_selected_candidate_executes_during_expansion(tmp_path):
    m=Models()
    result=evaluate(m.payload,m,m,journal(tmp_path,m),conditions=('C',))
    assert set(result)=={'C'}
    assert [c[0] for c in m.calls]==['draft','review']


def test_empty_draft_is_reviewed_and_can_be_repaired(tmp_path):
    m=Models()
    m.response=dict(status='insufficient_evidence',items=[])
    m.review_result=dict(fulfillment='missing',abstention='excessive',reason='답변 가능',items=[])
    result=evaluate(m.payload,m,m,journal(tmp_path,m))
    assert result['B']['decision']=='accepted'
    assert result['C']['decision']=='verifier_rejected'
    assert result['D']['decision']=='repair_rejected'
    assert [c[0] for c in m.calls]==['draft','review','repair','review']
