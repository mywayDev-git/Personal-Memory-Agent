import copy
import unittest
from unittest.mock import Mock

from test_pipeline import memory, fake_output, REF
from scripts.memory_agent.extractor import extract_memories, sentence_units
from scripts.memory_agent.pipeline import extract_document
from scripts.memory_agent.temporal import normalize_time
from scripts.memory_agent.exceptions import ExtractionError
import json


class AccuracyTests(unittest.TestCase):
    def test_sentence_ids_round_trip_dates_quotes_and_newlines(self):
        text = '2026.10.13 오늘 "회의"했다.\n다음 주 발표한다! 가격은 3.14이다.'
        units = sentence_units(text)
        self.assertEqual(len(units), 3)
        session = Mock()
        item = memory(quote='unused')
        item['evidence'] = [{'sentence_id': 's1'}]
        session.post.return_value.ok = True
        session.post.return_value.json.return_value = {'choices': [{'message': {'content': json.dumps({'memories':[item]})}, 'finish_reason':'stop'}]}
        raw, _, _ = extract_memories(session, 'http://unused', None, '', text, {})
        self.assertEqual(raw['memories'][0]['evidence'], [{'quote': '다음 주 발표한다!'}])
        schema = session.post.call_args.kwargs['json']['json_schema']
        self.assertEqual(schema['$defs']['time']['properties']['start'], {'type':'null'})
        self.assertEqual(schema['$defs']['evidence_item']['properties']['sentence_id']['enum'], ['s0','s1','s2'])

    def test_invalid_sentence_id_rejected(self):
        session = Mock()
        item = memory()
        item['evidence'] = [{'sentence_id': 's999'}]
        session.post.return_value.ok = True
        session.post.return_value.json.return_value = {'choices': [{'message': {'content': json.dumps({'memories':[item]})}, 'finish_reason':'stop'}]}
        with self.assertRaisesRegex(ExtractionError, 'sentence_id'):
            extract_memories(session, 'http://unused', None, '', '회의했다.', {})

    def test_model_computed_date_is_replaced_before_validation(self):
        item = memory('다음 주 금요일', '다음 주 금요일에 발표한다.')
        item['time'].update(start='2026-10-14T00:00:00+09:00', precision='relative')
        result, _ = extract_document('다음 주 금요일에 발표한다.', source_id='x', reference_time=REF, extract_fn=fake_output([item]))
        self.assertEqual(result['memories'][0]['time']['start'], '2026-10-16')

    def test_utc_reference_uses_korean_calendar(self):
        item = memory('오늘', '오늘 회의했다.')
        self.assertEqual(normalize_time(item, '2026-10-12T16:00:00Z')['start'], '2026-10-13')

    def test_wrong_time_is_abstained_and_reported(self):
        item = memory('어제', '오늘 회의했다.')
        result, meta = extract_document('오늘 회의했다.', source_id='x', reference_time=REF, extract_fn=fake_output([item]))
        self.assertIsNone(result['memories'][0]['time']['start'])
        self.assertIsNone(result['memories'][0]['time']['raw'])
        self.assertEqual(meta['warnings'][0]['discarded_raw'], '어제')
        self.assertEqual(meta['warnings'][0]['code'], 'unsupported_time_raw')

    def test_independent_actions_and_negation_are_not_deduplicated(self):
        quote = '파일을 백업했지만 OS를 재설치하지 않았다.'
        first = memory(quote=quote, content='파일을 백업했다.')
        second = copy.deepcopy(first)
        second.update(content='OS를 재설치하지 않았다.', assertion_polarity='negated')
        result, _ = extract_document(quote, source_id='x', extract_fn=fake_output([first,second]))
        self.assertEqual(len(result['memories']), 2)
        self.assertEqual(result['memories'][1]['assertion_polarity'], 'negated')

    def test_unique_verbatim_content_repairs_wrong_sentence_and_date(self):
        quote = '오늘 지현과 카페에서 만나 오해를 풀었다.'
        unrelated = '책상에는 노트와 펜이 놓여 있었다.'
        item = memory('오늘', unrelated, '지현과 카페에서 만나 오해를 풀었다')
        result, meta = extract_document(quote+' '+unrelated, source_id='x', reference_time=REF, extract_fn=fake_output([item]))
        self.assertEqual(result['memories'][0]['evidence'], [{'quote':quote}])
        self.assertEqual(result['memories'][0]['time']['start'], '2026-10-10')
        self.assertEqual(meta['warnings'][0]['code'], 'evidence_realigned')

    def test_alignment_refuses_ambiguous_occurrences_or_missing_entities(self):
        from scripts.memory_agent.pipeline import align_verbatim_evidence
        quote = '오늘 지현과 카페에서 만나 오해를 풀었다.'
        item = memory('오늘', '다른 문장이다.', '지현과 카페에서 만나 오해를 풀었다')
        self.assertIsNone(align_verbatim_evidence(item, quote+' '+quote))
        item['object'] = {'kind':'entity','value':'민수','value_type':'string'}
        self.assertIsNone(align_verbatim_evidence(item, quote))
