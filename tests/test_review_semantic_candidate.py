from copy import deepcopy
from unittest.mock import patch

import pytest

from evaluation.review_semantic_candidate import SemanticReviewModels, apply_checks
from pma.answer_review import accepted, REVIEW_SCHEMA
from pma.models import LocalModels


def data():
    response = {'status': 'answered', 'items': [{'text': '8일이다', 'citations': ['a']}]}
    review = dict(fulfillment='direct', abstention='not_applicable', reason='일치', items=[])
    review['checks'] = {k: dict(source_interpretation='', answer_interpretation='',
                               evidence=[], status='not_applicable')
                        for k in ('time', 'correction', 'negation_scope')}
    records = [dict(id='a', source_context='앞 기록을 정정한다. 실제는 10일이다.', evidence=[])]
    return response, review, records


@pytest.mark.parametrize('name', ['time', 'correction', 'negation_scope'])
def test_failed_semantic_comparison_cannot_be_approved(name):
    response, review, records = data()
    review['checks'][name].update(status='failed', evidence=[dict(id='a', quote='실제는 10일이다.')])
    before = deepcopy(review)
    result = apply_checks(review, records)
    assert not accepted(result, response)
    assert name in result['reason']
    assert review == before


def test_passed_comparison_preserves_existing_review():
    _, review, records = data()
    review['checks']['time'].update(status='passed', evidence=[dict(id='a', quote='10일')])
    expected = {k: v for k, v in review.items() if k != 'checks'}
    assert apply_checks(review, records) == expected


@pytest.mark.parametrize('evidence,message', [([], 'WITHOUT_SOURCE'),
    ([dict(id='absent', quote='10일')], 'UNKNOWN_SOURCE'),
    ([dict(id='a', quote='unseen')], 'INVALID_QUOTE')])
def test_check_requires_real_delivered_source(evidence, message):
    _, review, records = data()
    records[0]['source_text'] = 'unseen'  # Full record unavailable to verifier.
    review['checks']['correction'].update(status='failed', evidence=evidence)
    with pytest.raises(ValueError, match=message):
        apply_checks(review, records)


def test_counterevidence_need_not_be_cited_by_wrong_answer():
    response, review, records = data()
    records.append(dict(id='b', source_context='정정한다', evidence=[]))
    review['checks']['correction'].update(status='failed', evidence=[dict(id='b', quote='정정한다')])
    assert not accepted(apply_checks(review, records), response)


def test_generation_unchanged_review_only_extended():
    model = object.__new__(SemanticReviewModels)
    schema = {'properties': {'answer': {}}, 'required': ['answer']}
    with patch.object(LocalModels, 'structured', return_value={'answer': 1}) as call:
        assert model.structured('prompt', {'x': 1}, schema, 99) == {'answer': 1}
        call.assert_called_once_with('prompt', {'x': 1}, schema, max_tokens=99)
    _, review, records = data()
    original = deepcopy(REVIEW_SCHEMA)
    with patch.object(LocalModels, 'structured', return_value=review) as call:
        result = model.structured('prompt', {'source_records': records}, REVIEW_SCHEMA, 2048)
        assert 'checks' not in result
        assert next(iter(call.call_args.args[2]['properties'])) == 'checks'
        assert call.call_args.kwargs['max_tokens'] == 2048
    assert REVIEW_SCHEMA == original


def test_imported_draft_and_legacy_stage_are_reused(tmp_path):
    from evaluation.fixed_answer_replay import Journal, evaluate, write
    from test_fixed_answer_replay import Models
    old = Models()
    first = Journal(tmp_path/'old.json', 'old', old)
    baseline = evaluate(old.payload, old, old, first)
    candidate = Models(failures=1)
    replay = Journal(tmp_path/'new.json', 'new', candidate)
    replay.data['stages'] = {k: deepcopy(first.data['stages'][k]) for k in ('draft', 'legacy_verify')}
    replay.data['imported_stages'] = ['draft', 'legacy_verify']
    write(replay.path, replay.data)
    result = evaluate(candidate.payload, candidate, candidate, replay)
    assert result['B'] == baseline['B']
    assert all(result[c]['draft'] == baseline[c]['draft'] for c in 'BCD')
    assert [x[0] for x in candidate.calls] == ['review', 'repair', 'review']
    assert len(replay.data['attempts']) == 3
