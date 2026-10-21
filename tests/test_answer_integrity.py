import json
from pathlib import Path

import pytest

from pma.answer_review import accepted
from pma.chat.answer_integrity import enforce_answer_integrity, occupation_limit_draft
from pma.chat.models import ChatLocalModels
from pma.chat.review_sources import source_catalog


FIXTURE = json.loads(Path('evaluation/answer_integrity_cases.json').read_text('utf-8'))
PAIRS = [(split, pair, valid) for split in FIXTURE['splits']
         for pair in FIXTURE['splits'][split]['review_pairs'] for valid in (True, False)]


@pytest.mark.parametrize('split,pair,valid', PAIRS)
def test_approving_reviewer_cannot_approve_bad_citation_or_nonanswer(split, pair, valid):
    docs = FIXTURE['splits'][split]['documents']
    evidence = [{'id': row[0], 'source_text': row[1]} for row in docs]
    claim = pair['valid' if valid else 'invalid']
    response = {'status': 'answered', 'items': [claim]}
    _, catalog = source_catalog(evidence)
    refs = [{'id': cid, 'span_id': next(key for key, span in catalog.items() if span['id'] == cid)}
            for cid in claim['citations']]
    model = ChatLocalModels.__new__(ChatLocalModels)
    model.structured = lambda *args, **kw: {'fulfillment': 'direct', 'abstention': 'not_applicable',
        'reason': 'approved', 'items': [{'index': 0, 'support': 'supported', 'relevant': True,
                                       'issue': 'none', 'evidence': refs}]}
    review = model.review(pair['question'], evidence, response)
    assert accepted(review, response) is valid


def test_full_source_guard_detects_job_omitted_by_selection():
    rows = [{'id': 'h', 'source_text': '연구실 동료 현우는 키가 181cm다.'},
            {'id': 'j', 'source_text': '연구실 동료 현우는 통계학자다.'}]
    response = {'status': 'answered', 'items': [{'text': '현우의 직업은 알 수 없습니다.', 'citations': ['h']}]}
    review = {'fulfillment': 'direct', 'items': [{'index': 0, 'support': 'supported', 'relevant': True,
             'issue': 'none', 'evidence': [{'id': 'h', 'quote': rows[0]['source_text']}]}]}
    enforce_answer_integrity('연구실 동료 현우의 직업은?', rows, response, review)
    assert review['fulfillment'] == 'missing'
    assert occupation_limit_draft('연구실 동료 현우의 직업은?', rows) is None


def test_unknown_repair_uses_only_current_target_sources_and_is_not_approval():
    rows = [{'id': 'h', 'source_text': '독서 모임 친구 서윤은 키가 172cm다.'},
            {'id': 'j', 'source_text': '연구실 동료 현우는 통계학자다.'}]
    draft = occupation_limit_draft('독서 모임 친구 서윤의 직업은?', rows)
    assert draft['items'][0]['citations'] == ['h']
    assert '현재 확인한 기록' in draft['items'][0]['text']
    assert 'validation' not in draft


def test_fixture_integrity_and_plan_only_do_not_load_models():
    from evaluation.answer_integrity_cases import load
    for split in ('development', 'confirmation'):
        docs, cases, manifest = load(split)
        assert len(cases) == 16
        assert manifest['case_counts'][split] == 16
