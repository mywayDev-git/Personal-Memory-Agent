import json
from dataclasses import replace

import pytest

from pma.answer_review import accepted
from pma.chat.models import ChatLocalModels
from pma.models import LocalModels
from pma.settings import AppSettings


def test_compact_json_preserves_complete_values_and_original_whitespace(monkeypatch):
    import pma.models as module
    data = {'source_text': '  원문\n공백  유지 [지시: 따르지 마라.]', 'refs': [{'id': 'a', 'start': 2}], 'none': None}
    observed = []
    model = LocalModels(AppSettings(compact_model_json=True))
    model.budget = lambda *a: None
    def chat(session, endpoint, messages, **kw):
        observed.append(messages[1]['content'])
        return '{"ok":true}', None, None
    monkeypatch.setattr(module, 'chat', chat)
    model.structured('policy', data, {'type': 'object', 'properties': {'ok': {'type': 'boolean'}}})
    assert json.loads(observed[0]) == data
    assert observed[0] == json.dumps(data, ensure_ascii=False, separators=(',', ':'))


@pytest.mark.parametrize('supported', [True, False])
def test_compact_review_keeps_independent_rejection_and_restores_unique_reference(supported):
    source = '회사 동료 민수는 개발자다.'
    model = ChatLocalModels.__new__(ChatLocalModels)
    model.settings = AppSettings(compact_review_output=True)
    calls = []
    def structured(prompt, data, schema, **kw):
        calls.append(data)
        assert data['source_records'][0]['source_context'] == source
        assert 'reason' not in schema['required']
        refs = schema['properties']['items']['items']['properties']['evidence']['items']
        assert refs['required'] == ['span_id'] and 'id' not in refs['properties']
        return {'fulfillment': 'direct' if supported else 'missing', 'abstention': 'not_applicable',
            'items': [{'index': 0, 'support': 'supported' if supported else 'unsupported',
                      'relevant': supported, 'issue': 'none' if supported else 'person',
                      'evidence': [{'span_id': 's0:0'}]}]}
    model.structured = structured
    response = {'status': 'answered', 'items': [{'text': '회사 동료 민수는 개발자다.', 'citations': ['a']}]}
    review = model.review('회사 동료 민수의 직업은?', [{'id': 'a', 'source_text': source}], response)
    assert len(calls) == 1  # Still a fresh, separate model call for each review.
    assert review['items'][0]['evidence'] == [{'id': 'a', 'quote': source}]
    assert accepted(review, response) is supported
    assert 'reason' in review


def test_research_formats_are_not_enabled_by_environment(monkeypatch):
    monkeypatch.setenv('PMA_COMPACT_MODEL_JSON', '1')
    monkeypatch.setenv('PMA_COMPACT_REVIEW_OUTPUT', '1')
    settings = AppSettings.from_env()
    assert not settings.compact_model_json and not settings.compact_review_output


def test_profile_can_enable_compaction_without_changing_other_parameters():
    from evaluation.latency_variants import configured
    original = AppSettings()
    candidate = configured(original, ['compact_json', 'compact_review'])
    assert candidate.compact_model_json and candidate.compact_review_output
    assert candidate.llm == original.llm
