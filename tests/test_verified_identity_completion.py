import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from pma.chat.engine import ChatEngine
from pma.chat.identity import identity_probe_candidate
from pma.errors import AppError
from pma.settings import AppSettings


@pytest.mark.parametrize('fulfillment', ['direct', 'limited', 'missing'])
def test_probe_requires_one_fresh_direct_review_and_never_regenerates(fulfillment):
    source = '회사 동료 민수는 개발자다.' if fulfillment == 'direct' else '회사 동료 민수는 키가 180cm다.'
    rows = [{'id': 'a', 'record_id': 'r', 'revision_id': 'v', 'source_text': source,
             'evidence': [{'quote': source, 'start': 0, 'end': len(source)}]}]
    engine = ChatEngine.__new__(ChatEngine)
    engine.service = SimpleNamespace(settings=AppSettings(), trace=lambda *a, **kw: None)
    engine.resolve = lambda q, *a, **kw: ({'question': q, 'needs_clarification': False}, 0)
    reviews = []
    def review(question, evidence, response):
        reviews.append(question)
        return {'fulfillment': fulfillment, 'abstention': 'not_applicable', 'reason': '원문 확인',
            'items': [{'index': 0, 'support': 'supported', 'relevant': True, 'issue': 'none',
                'answer_quote': response['items'][0]['text'], 'evidence': [{'id': 'a', 'quote': source}]}]}
    def forbidden(*a, **kw):
        raise AssertionError('A quote probe cannot introduce a model-generated answer or repair')
    engine.models = SimpleNamespace(answer=forbidden, review=review)
    result = engine.generate('회사 동료 민수 직업은?', {'evidence': rows, 'messages': []},
                             '2026-10-19', _direct_probe=True)
    assert len(reviews) == 1
    assert result['status'] == ('answered' if fulfillment == 'direct' else 'insufficient_evidence')
    assert result['validation'] == ('model_checked' if fulfillment == 'direct' else 'probe_rejected')


def setup_routing(monkeypatch, *, change_scope=False, reject_probe=False):
    from pma.chat import automatic, interpretation, planner, retrieval
    queries, generation = [], []
    source = '회사 동료 민수는 키가 180cm다.' if reject_probe else '회사 동료 민수는 개발자다.'
    first = {'id': 'a', 'record_id': 'r', 'version': 1, 'source_text': source, 'content': source,
             'search_explanation': {'final_selection': {'reason': 'relevant'}}}
    later = {**first, 'id': 'b', 'record_id': 'r2', 'source_text': '회사 동료 민수는 개발자다.'}
    def retrieve(service, query, **kw):
        queries.append(query)
        return None, {'results': [first] if len(queries) == 1 else [later],
                      'status': 'ok', 'filters': {}, 'query_plan': {}}
    monkeypatch.setattr(retrieval, 'retrieve', retrieve)
    monkeypatch.setattr(automatic, 'structured', lambda *a, **kw: {'query': ''})
    monkeypatch.setattr(automatic, 'combine', lambda batches: list({r['id']:r for b in batches for r in b}.values()))
    monkeypatch.setattr(interpretation, 'analyze', lambda *a: {'observations': []})
    monkeypatch.setattr(planner, 'prepare', lambda *a: {})
    def grounded(engine, question, session, today, **kw):
        generation.append((kw.get('_direct_probe', False), session['evidence']))
        if kw.get('_direct_probe') and reject_probe:
            return {'status': 'insufficient_evidence', 'items': [], 'validation': 'probe_rejected'}
        return {'status': 'answered', 'validation': 'model_checked',
                'items': [{'text': session['evidence'][-1]['source_text'], 'citations': [session['evidence'][-1]['id']]}]}
    monkeypatch.setattr(automatic, 'grounded', grounded)
    freezes = []
    def freeze(rows):
        freezes.append(1)
        return [{**r, 'version': len(freezes) if change_scope else r['version']} for r in rows]
    engine = SimpleNamespace(service=SimpleNamespace(settings=SimpleNamespace(embedding_key='test',
        intermediate_planning=False, scoped_identity_search=True), trace=lambda *a, **kw: None),
        store=SimpleNamespace(freeze=freeze))
    return automatic, engine, queries, generation


def test_incomplete_attribute_keeps_discovery_and_uses_later_occupation_source(monkeypatch):
    automatic, engine, queries, generation = setup_routing(monkeypatch, reject_probe=True)
    assert identity_probe_candidate('회사 동료 민수 직업은?',
        [{'id': 'height', 'source_text': '회사 동료 민수는 키가 180cm다.'}])
    response, evidence, _ = automatic.run(engine, '회사 동료 민수 직업은?',
        {'messages': [], 'context': {}}, '2026-10-19', 'memory')
    assert queries == ['회사 동료 민수 직업은?', '나의 지인들과 어떤 관계인지 알려줘']
    assert [probe for probe, _ in generation] == [True, False]
    assert {r['id'] for r in evidence} == {'a', 'b'}
    assert response['items'][0]['citations'] == ['b']


@pytest.mark.parametrize('change_scope', [False, True])
def test_verified_completion_is_forwarded_only_for_exact_current_scope(monkeypatch, change_scope):
    automatic, engine, queries, generation = setup_routing(monkeypatch, change_scope=change_scope)
    response, _, _ = automatic.run(engine, '회사 동료 민수 직업은?',
        {'messages': [], 'context': {}}, '2026-10-19', 'memory')
    assert len(queries) == 1
    assert [probe for probe, _ in generation] == ([True, False] if change_scope else [True])
    assert response['validation'] == 'model_checked'


@pytest.mark.parametrize('code', ['CANCELLED', 'CHAT_TIMEOUT', 'SOURCE_CHANGED'])
def test_probe_cannot_swallow_cancellation_deadline_or_changed_source(monkeypatch, code):
    automatic, engine, _, _ = setup_routing(monkeypatch)
    def failed(*a, **kw):
        raise AppError(code, 'test', 409)
    monkeypatch.setattr(automatic, 'grounded', failed)
    with pytest.raises(AppError) as exc:
        automatic.run(engine, '회사 동료 민수 직업은?', {'messages': [], 'context': {}}, '2026-10-19', 'memory')
    assert exc.value.code == code


def test_third_independent_set_is_frozen_and_unknown_occupation_is_not_a_height_answer():
    from evaluation.identity_completion_cases import CASES, manifest
    from evaluation.response_latency import quality
    assert json.loads(Path('evaluation/identity_completion_manifest.json').read_text('utf-8')) == manifest()
    case = CASES['complete_unknown_attribute']
    source = '독서 모임 친구 서윤은 키가 172cm다.'
    evidence = [{'id': 'a', 'record_id': 'r', 'source_text': source}]
    reference = {'memory_id': 'a', 'record_id': 'r', 'quote': source, 'start': 0, 'end': len(source)}
    response = {'status': 'insufficient_evidence', 'items': []}
    assert quality(case, response, evidence, {'r':'height'})['passed']
    response = {'status': 'answered', 'validation': 'model_checked', 'citation_details': [reference],
                'items': [{'text': '원문에는 키만 있고 직업은 확인할 수 없습니다.', 'citations': ['a']}]}
    assert quality(case, response, evidence, {'r':'height'})['passed']
    response['items'][0]['text'] = source
    assert not quality(case, response, evidence, {'r':'height'})['passed']
