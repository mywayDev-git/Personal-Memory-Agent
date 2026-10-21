import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from pma.chat.engine import ChatEngine
from pma.chat.models import ChatLocalModels
from pma.settings import AppSettings


def test_independent_identity_fixtures_remain_frozen():
    from evaluation.identity_followup_cases import manifest
    assert json.loads(Path('evaluation/identity_followup_manifest.json').read_text('utf-8')) == manifest()


def test_reference_rewrite_and_approving_model_cannot_override_user_role(monkeypatch):
    monkeypatch.setattr('pma.chat.engine.direct_statement', lambda *a, **kw: None)
    source = '동아리 친구 민수는 수학 교사다.'
    rows = [{'id': 'a', 'record_id': 'r', 'revision_id': 'v', 'source_text': source,
             'evidence': [{'quote': source, 'start': 0, 'end': len(source)}]}]
    engine = ChatEngine.__new__(ChatEngine)
    engine.service = SimpleNamespace(settings=AppSettings(), trace=lambda *a, **kw: None)
    # Deliberately broaden the downstream model interpretation and approve a
    # swapped role. The user scope must survive both model mistakes.
    engine.resolve = lambda *a, **kw: ({'question': '회사 동료 민수와 동아리 친구 민수의 직업은?',
        'needs_clarification': False}, 1)
    reviewed = []
    def review(question, evidence, response):
        reviewed.append(question)
        return {'fulfillment': 'direct', 'abstention': 'not_applicable', 'reason': '원문 확인',
            'items': [{'index': 0, 'support': 'supported', 'relevant': True, 'issue': 'none',
                       'answer_quote': response['items'][0]['text'],
                       'evidence': [{'id': 'a', 'quote': source}]}]}
    engine.models = SimpleNamespace(answer=lambda *a, **kw: {'status': 'answered',
        'items': [{'text': '회사 동료 민수는 수학 교사다.', 'citations': ['a']}]}, review=review)
    result = engine.generate('그 친구 직업은?', {'evidence': rows, 'messages': [
        {'state': 'completed', 'question': '동아리 친구 민수는 누구야?', 'response': {
            'status': 'answered', 'citation_details': [{'quote': source}]}}]}, '2026-10-21')
    assert result['status'] == 'insufficient_evidence'
    assert len(reviewed) == 2
    assert reviewed == ['동아리 친구 민수 직업은?'] * 2


@pytest.mark.parametrize('wrong_span', [True, False])
def test_review_checks_role_in_selected_sentence_not_whole_mixed_source(wrong_span):
    from pma.answer_review import accepted
    from pma.chat.review_sources import source_catalog
    source = '회사 동료 민수는 개발자다. 동아리 친구 민수는 수학 교사다.'
    evidence = [{'id': 'a', 'source_text': source}]
    _, catalog = source_catalog(evidence)
    span_id = next(key for key, value in catalog.items() if (
        '동아리' in value['quote'] if wrong_span else '회사' in value['quote']))
    model = ChatLocalModels.__new__(ChatLocalModels)
    model.structured = lambda *a, **kw: {'fulfillment': 'direct', 'abstention': 'not_applicable',
        'reason': '원문 확인', 'items': [{'index': 0, 'support': 'supported', 'relevant': True,
            'issue': 'none', 'evidence': [{'id': 'a', 'span_id': span_id}]}]}
    response = {'status': 'answered', 'items': [{'text': '수학 교사입니다.' if wrong_span else '개발자입니다.',
                                               'citations': ['a']}]}
    result = model.review('회사 동료 민수 직업은?', evidence, response)
    assert accepted(result, response) is (not wrong_span)
    if wrong_span:
        assert result['items'][0]['issue'] == 'person'
