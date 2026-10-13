import copy
import hashlib
import json
import threading
import unittest
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import Mock

import requests

from config.settings import Settings, paths
from scripts.memory_agent.chunking import split_text
from scripts.memory_agent.llm_client import call_llm
from scripts.memory_agent.pipeline import PipelineOptions, extract_document
from scripts.memory_agent.temporal import normalize_time


REF = '2026-10-10T12:00:00+09:00'


def memory(raw=None, quote='회의했다.', content='회의했다.'):
    value = {'kind': 'unknown', 'value': None, 'value_type': 'none'}
    return dict(memory_type='event', content=content, subject=copy.deepcopy(value),
                predicate='회의하다', object=copy.deepcopy(value), target=None,
                time=dict(raw=raw, start=None, end=None, precision='unknown', certainty='uncertain'),
                assertion_polarity='affirmed', polarity='neutral', content_certainty='explicit',
                evidence=[{'quote': quote}])


def fake_output(memories):
    return lambda **kwargs: ({'memories': copy.deepcopy(memories)}, {'finish_reason': 'stop'}, 0.01)


class TemporalTests(unittest.TestCase):
    def test_distinct_event_and_plan_dates(self):
        a = normalize_time(memory('어제', '어제 회의했다.'), REF)
        b = normalize_time(memory('다음 주', '다음 주 결정한다.'), REF)
        self.assertEqual(a['start'], '2026-10-09')
        self.assertEqual((b['start'], b['end'], b['precision']), ('2026-10-12', '2026-10-18', 'range'))

    def test_missing_date_never_defaults(self):
        self.assertIsNone(normalize_time(memory(), REF)['start'])

    def test_missing_reference_preserves_relative(self):
        actual = normalize_time(memory('내일', '내일 회의'), None)
        self.assertEqual(actual['precision'], 'relative')
        self.assertIsNone(actual['start'])

    def test_absolute_without_reference(self):
        for raw in ('2024-02-29', '2024년 2월 29일'):
            self.assertEqual(normalize_time(memory(raw, raw), None)['start'], '2024-02-29')

    def test_precision(self):
        for raw, expected, precision in [('작년', '2025', 'year'), ('지난달', '2026-09', 'month'),
                                          ('2024년 2월', '2024-02', 'month')]:
            actual = normalize_time(memory(raw, raw), REF)
            self.assertEqual((actual['start'], actual['end'], actual['precision']), (expected, expected, precision))

    def test_unresolved_expressions_do_not_invent_dates(self):
        for raw in ('오전 10시', '그다음 날', '3년 동안', '3월', '2025년 2월 30일',
                    '2025-02-30', '내일 오전 10시', '내일 또는 모레'):
            with self.subTest(raw=raw):
                self.assertIsNone(normalize_time(memory(raw, raw), REF)['start'])

    def test_raw_requires_own_evidence(self):
        with self.assertRaisesRegex(ValueError, 'time.raw'):
            normalize_time(memory('어제', '오늘 회의'), REF)

    def test_year_rollover(self):
        self.assertEqual(normalize_time(memory('내일', '내일'), '2026-12-31T12:00:00+09:00')['start'], '2027-01-01')


class ChunkTests(unittest.TestCase):
    def test_lossless_unicode_and_bounds(self):
        text = ('첫 문단입니다. 🙂\n\n다음 문장입니다. ' * 200)
        chunks = split_text(text, 128, 20)
        seen = set()
        for chunk in chunks:
            self.assertEqual(chunk.text, text[chunk.start:chunk.end])
            self.assertLessEqual(len(chunk.text.encode('utf-8')), 128)
            seen.update(range(chunk.start, chunk.end))
        self.assertEqual(seen, set(range(len(text))))
        self.assertTrue(all(a.start < b.start for a, b in zip(chunks, chunks[1:])))

    def test_no_separators(self):
        chunks = split_text('한' * 2000, 100)
        self.assertGreater(len(chunks), 1)
        self.assertEqual(chunks[-1].end, 2000)

    def test_invalid_limits(self):
        for budget, overlap in [(0, 0), (31, 0), (100, -1)]:
            with self.assertRaises(ValueError):
                split_text('abc', budget, overlap)


class PipelineTests(unittest.TestCase):
    def test_team_schemas_and_prompt_are_unchanged(self):
        manifest = json.loads((paths.root / 'config/upstream.json').read_text(encoding='utf-8'))
        for path, expected in manifest['blobs'].items():
            content = (paths.root / path).read_bytes().replace(b'\r\n', b'\n')
            header = f'blob {len(content)}\0'.encode()
            self.assertEqual(hashlib.sha1(header + content).hexdigest(), expected, path)

    def test_schema_and_per_memory_times(self):
        text = '어제 회의했다. 다음 주 결정한다.'
        a, b = memory('어제', '어제 회의했다.'), memory('다음 주', '다음 주 결정한다.', '결정한다.')
        b['memory_type'] = 'plan'
        result, meta = extract_document(text, source_id='diary-1', reference_time=REF, extract_fn=fake_output([a, b]))
        self.assertEqual(set(result), {'schema_version', 'source_context', 'memories'})
        self.assertEqual([m['local_id'] for m in result['memories']], ['m1', 'm2'])
        self.assertEqual(result['memories'][1]['time']['start'], '2026-10-12')
        self.assertTrue(meta['validation']['valid'])

    def test_empty_memories_are_valid(self):
        result, _ = extract_document('특별한 내용 없음', source_id='x', extract_fn=fake_output([]))
        self.assertEqual(result['memories'], [])

    def test_invalid_evidence_fails_entire_document(self):
        with self.assertRaisesRegex(ValueError, 'quote'):
            extract_document('회의했다.', source_id='x', extract_fn=fake_output([memory(quote='없는 인용')]))

    def test_invalid_schema(self):
        item = memory()
        item['unexpected'] = True
        with self.assertRaisesRegex(ValueError, 'Additional properties'):
            extract_document('회의했다.', source_id='x', extract_fn=fake_output([item]))

    def test_bad_reference_rejected_before_request(self):
        fn = Mock()
        with self.assertRaises(ValueError):
            extract_document('회의했다.', source_id='x', reference_time='2026-10-10', extract_fn=fn)
        fn.assert_not_called()

    def test_context_budget_rejected_before_request(self):
        fn = Mock()
        with self.assertRaisesRegex(ValueError, 'Context budget'):
            extract_document('회의했다.', source_id='x', options=PipelineOptions(context_tokens=4096), extract_fn=fn)
        fn.assert_not_called()

    def test_truncated_output_is_split_and_no_text_lost(self):
        received = []
        def fake(**kwargs):
            text = kwargs['source_text']
            received.append(text)
            if len(text.encode()) > 120:
                raise ValueError('OUTPUT_TRUNCATED')
            return {'memories': []}, {}, 0.1
        text = '가나다라마바사' * 20
        _, meta = extract_document(text, source_id='x', extract_fn=fake)
        self.assertGreater(meta['request_count'], 1)
        self.assertTrue(any(c['status'] == 'truncated' for c in meta['calls']))
        coverage = set()
        for call in meta['calls']:
            if call['status'] == 'ok':
                coverage.update(range(call['start'], call['end']))
        self.assertEqual(coverage, set(range(len(text))))

    def test_repeated_truncation_stops(self):
        fn = Mock(side_effect=ValueError('OUTPUT_TRUNCATED'))
        with self.assertRaisesRegex(ValueError, 'remains truncated'):
            extract_document('a' * 300, source_id='x', extract_fn=fn,
                             options=PipelineOptions(max_split_depth=1))
        self.assertEqual(fn.call_count, 2)

    def test_overlap_dedup_requires_same_source_occurrence(self):
        text = 'a' * 78 + '회의했다.' + 'b' * 150
        def fake(**kwargs):
            items = [memory()] if '회의했다.' in kwargs['source_text'] else []
            return {'memories': items}, {}, 0.0
        result, meta = extract_document(text, source_id='x', extract_fn=fake,
                                       options=PipelineOptions(chunk_bytes=110, overlap_chars=30))
        self.assertGreater(meta['chunk_count'], 1)
        self.assertEqual(len(result['memories']), 1)

    def test_separate_occurrences_are_preserved(self):
        text = '회의했다.' + 'a' * 200 + '회의했다.'
        def fake(**kwargs):
            return {'memories': [memory()] if '회의했다.' in kwargs['source_text'] else []}, {}, 0.0
        result, _ = extract_document(text, source_id='x', extract_fn=fake,
                                     options=PipelineOptions(chunk_bytes=100, overlap_chars=0))
        self.assertEqual(len(result['memories']), 2)


class HTTPTests(unittest.TestCase):
    def test_real_http_request_contract(self):
        captured = []
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                captured.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                body = json.dumps({'choices': [{'message': {'content': json.dumps({'memories': [memory()]})},
                                                 'finish_reason': 'stop'}], 'model': 'Qwen3-8B-Q4_K_M'}).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(body)
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            settings = replace(Settings(), endpoint=f'http://127.0.0.1:{server.server_port}/v1/chat/completions')
            result, meta = extract_document('회의했다.', source_id='http-test', settings=settings)
            self.assertTrue(meta['validation']['valid'])
            self.assertEqual(captured[0]['model'], 'Qwen3-8B-Q4_K_M')
            self.assertIn('json_schema', captured[0])
            self.assertEqual(captured[0]['seed'], 42)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_client_rejects_length_even_valid_json(self):
        session = Mock()
        session.post.return_value.ok = True
        session.post.return_value.json.return_value = {'choices': [{'message': {'content': '{"memories":[]}'}, 'finish_reason': 'length'}]}
        with self.assertRaisesRegex(ValueError, 'OUTPUT_TRUNCATED'):
            call_llm(session, 'http://unused', None, '', '', {}, 1, 1, 0, 42, 1)


if __name__ == '__main__':
    unittest.main()
