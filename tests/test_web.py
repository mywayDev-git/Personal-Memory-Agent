import threading
import time
import unittest

import requests

from pma_web import Playground, make_server


class WebTests(unittest.TestCase):
    def setUp(self):
        self.release = threading.Event()

        def extract(text, **kwargs):
            self.release.wait(2)
            if text == 'failure':
                raise ValueError('Invalid extraction: evidence mismatch')
            return {'memories': []}, {'validation': {'valid': True}}

        self.app = Playground(extract_fn=extract)
        self.server = make_server(0, self.app)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        self.client = requests.Session()
        self.client.trust_env = False

    def tearDown(self):
        self.release.set()
        self.server.shutdown()
        self.server.server_close()
        self.client.close()

    def wait(self, key):
        for _ in range(100):
            job = self.client.get(self.url+'/api/jobs/'+key).json()
            if job['status'] != 'running':
                return job
            time.sleep(.01)
        self.fail('job did not finish')

    def test_async_busy_and_success(self):
        response = self.client.post(self.url+'/api/jobs', json={'text': '긴 글. '*3000})
        self.assertEqual(response.status_code, 202)
        self.assertEqual(self.client.post(self.url+'/api/jobs', json={'text': '중복'}).status_code, 409)
        self.release.set()
        job = self.wait(response.json()['id'])
        self.assertEqual(job['status'], 'done')
        self.assertEqual(job['input_text'], '긴 글. '*3000)

    def test_errors_and_input_validation(self):
        for payload in ({'text': ''}, {'text': 'x', 'chunk_bytes': -1}, {'text': 'x', 'reference_time': '2026-01-01'}, []):
            self.assertEqual(self.client.post(self.url+'/api/jobs', json=payload).status_code, 400)
        self.release.set()
        response = self.client.post(self.url+'/api/jobs', json={'text': 'failure'})
        job = self.wait(response.json()['id'])
        self.assertEqual(job['status'], 'error')
        self.assertIn('evidence mismatch', job['error'])

    def test_local_origin_and_page(self):
        self.assertIn('기억 추출 실험실', self.client.get(self.url).text)
        self.assertEqual(self.client.post(self.url+'/api/jobs', json={'text': 'x'}, headers={'Origin': 'https://example.com'}).status_code, 403)
        self.assertEqual(self.client.get(self.url, headers={'Host': 'example.com'}).status_code, 403)


if __name__ == '__main__':
    unittest.main()
