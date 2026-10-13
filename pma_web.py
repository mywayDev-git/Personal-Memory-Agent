"""Local extraction playground. Run: python pma_web.py (http://127.0.0.1:8766)."""
import argparse
import copy
import json
import threading
import time
import uuid
from dataclasses import replace
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import requests

from config.settings import Settings
from scripts.memory_agent.pipeline import PipelineOptions, extract_document


class Playground:
    def __init__(self, settings=None, extract_fn=extract_document):
        self.settings = settings or replace(Settings.from_env(), timeout=1800)
        self.extract_fn = extract_fn
        self.lock = threading.Lock()
        self.jobs = {}
        self.active = False

    def submit(self, data):
        if not isinstance(data, dict):
            raise ValueError('JSON 객체가 필요합니다.')
        text = data.get('text')
        if not isinstance(text, str) or not text.strip() or len(text) > 50000:
            raise ValueError('원문은 1~50,000자로 입력하세요.')
        ref = data.get('reference_time') or None
        if ref is not None:
            if not isinstance(ref, str) or datetime.fromisoformat(ref.replace('Z', '+00:00')).tzinfo is None:
                raise ValueError('기준 시각에는 시간대가 필요합니다.')
        size = data.get('chunk_bytes', 6000)
        if type(size) is not int or not 500 <= size <= 6000:
            raise ValueError('분할 크기는 500~6000 바이트입니다.')
        with self.lock:
            if self.active:
                raise RuntimeError('추출이 진행 중입니다. 완료 후 다시 실행하세요.')
            self.active = True
            key = uuid.uuid4().hex
            # Bounded in-memory history; nothing is written to disk.
            while len(self.jobs) >= 20:
                del self.jobs[next(iter(self.jobs))]
            self.jobs[key] = dict(id=key, status='running', started=time.time(), responses=[], input_text=text)
        threading.Thread(target=self.run, args=(key, text, ref, size), daemon=True).start()
        return key

    def snapshot(self, key):
        with self.lock:
            return copy.deepcopy(self.jobs.get(key))

    def run(self, key, text, ref, size):
        app = self

        class Recorder(requests.Session):
            def post(self, *args, **kwargs):
                response = super().post(*args, **kwargs)
                try:
                    body = response.json()
                except ValueError:
                    body = response.text[:100000]
                with app.lock:
                    app.jobs[key]['responses'].append(body)
                return response

        try:
            with Recorder() as session:
                session.trust_env = False
                result, metadata = self.extract_fn(
                    text, source_id=f'web-{key}', reference_time=ref,
                    settings=self.settings, session=session,
                    options=PipelineOptions(chunk_bytes=size))
            update = dict(status='done', result=result, metadata=metadata)
        except Exception as exc:
            update = dict(status='error', error=str(exc))
        finally:
            with self.lock:
                self.jobs[key].update(update, elapsed_seconds=round(time.time()-self.jobs[key]['started'], 2))
                self.active = False


def make_server(port=8766, app=None):
    app = app or Playground()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send(self, status, data, content_type='application/json; charset=utf-8'):
            body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(body)

        def allowed(self):
            host = self.headers.get('Host')
            expected = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
            origin = self.headers.get('Origin')
            return host in expected and (origin is None or origin == f'http://{host}')

        def do_GET(self):
            if not self.allowed():
                return self.send(403, {'error': 'Local requests only'})
            if self.path == '/':
                return self.send(200, Path(__file__).with_name('web_test.html').read_bytes(), 'text/html; charset=utf-8')
            if self.path == '/api/health':
                try:
                    endpoint = urlsplit(app.settings.endpoint)
                    with requests.Session() as session:
                        session.trust_env = False
                        response = session.get(f'{endpoint.scheme}://{endpoint.netloc}/health', timeout=2)
                    ready = response.ok
                except requests.RequestException:
                    ready = False
                return self.send(200, {'ready': ready, 'model': app.settings.model})
            if self.path == '/api/evaluations':
                rows = []
                root = Path(__file__).resolve().parent / 'results'
                filenames = ('local_accuracy_final.json',) if (root/'local_accuracy_final.json').exists() else ('local_accuracy_replay.json', 'local_accuracy_continued.json')
                for name in filenames:
                    path = root / name
                    if not path.exists():
                        continue
                    try:
                        saved = json.loads(path.read_text(encoding='utf-8'))
                    except (ValueError, OSError):
                        continue
                    for row in saved if isinstance(saved, list) else [saved]:
                        if row['status'] == 'running':
                            continue
                        if row['name'] == 'previous_long' and name == 'local_accuracy_replay.json':
                            continue
                        rows.append(dict(id=row['name'], status='done' if row['status']=='ok' else 'error',
                            input_text=row['source'], elapsed_seconds=row.get('seconds', 0),
                            result=row.get('result'), metadata=row.get('metadata'), error=row.get('error'),
                            responses=row.get('responses', []), checks=row.get('checks'),
                            evaluation_type=row.get('evaluation_type')))
                return self.send(200, rows)
            if self.path.startswith('/api/jobs/'):
                job = app.snapshot(self.path.removeprefix('/api/jobs/'))
                return self.send(200 if job else 404, job or {'error': '작업을 찾을 수 없습니다.'})
            self.send(404, {'error': 'Not found'})

        def do_POST(self):
            if not self.allowed():
                return self.send(403, {'error': 'Local requests only'})
            if self.path != '/api/jobs':
                return self.send(404, {'error': 'Not found'})
            try:
                if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                    raise ValueError('application/json required')
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 400000:
                    raise ValueError('요청 크기가 올바르지 않습니다.')
                self.connection.settimeout(10)
                data = json.loads(self.rfile.read(length))
                key = app.submit(data)
                self.send(202, {'id': key})
            except RuntimeError as exc:
                self.send(409, {'error': str(exc)})
            except (ValueError, TypeError, OSError) as exc:
                self.send(400, {'error': str(exc)})

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8766)
    args = parser.parse_args()
    server = make_server(args.port)
    print(f'PMA playground: http://127.0.0.1:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
