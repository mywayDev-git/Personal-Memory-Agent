const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');

const pages = new Map([
  ['/', ['index.html', 'text/html; charset=utf-8']],
  ['/diary-dates.js', ['../local/diary-dates.js', 'text/javascript; charset=utf-8']],
  ['/layout.js', ['layout.js', 'text/javascript; charset=utf-8']],
  ['/constellation.js', ['constellation.js', 'text/javascript; charset=utf-8']],
  ['/demo.js', ['demo.js', 'text/javascript; charset=utf-8']],
]);
const api = new Map([
  ['/api/baseline/bootstrap', 'GET'],
  ['/api/baseline/summary-memory', 'GET'],
  ['/api/baseline/summary-memory/intent', 'POST'],
  ['/api/baseline/summary-memory/save', 'POST'],
  ['/api/baseline/summary-memory/search', 'POST'],
]);
const originalRecord = /^\/api\/baseline\/summary-memory\/original\?key=[a-f0-9]{64}$/;

function errorResponse(response, status, message) {
  if (response.headersSent) {
    response.destroy();
    return;
  }
  response.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8' });
  response.end(JSON.stringify({ error: message }));
}

function createDemoServer(backendPort = 4319) {
  const backendHost = '127.0.0.1:' + backendPort;
  const server = http.createServer((request, response) => {
    const host = '127.0.0.1:' + server.address().port;
    if (request.headers.host !== host || (request.headers.origin && request.headers.origin !== 'http://' + host)) {
      errorResponse(response, 403, '시연 페이지의 로컬 주소로 접속해 주세요.');
      return;
    }
    response.setHeader('Cache-Control', 'no-store');
    response.setHeader('X-Content-Type-Options', 'nosniff');

    const page = pages.get(request.url);
    if (request.method === 'GET' && page) {
      const [file, type] = page;
      response.setHeader('Content-Type', type);
      response.setHeader('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'");
      const stream = fs.createReadStream(path.join(__dirname, file));
      stream.on('error', () => errorResponse(response, 500, '시연 화면 파일을 읽지 못했습니다.'));
      stream.pipe(response);
      return;
    }
    const allowedMethod = api.get(request.url) || (originalRecord.test(request.url) ? 'GET' : null);
    if (allowedMethod !== request.method) {
      errorResponse(response, 404, '시연에서 사용할 수 없는 경로입니다.');
      return;
    }

    const headers = { Host: backendHost };
    if (request.method === 'POST') {
      if (request.headers.origin !== 'http://' + host ||
          !request.headers['content-type']?.startsWith('application/json') ||
          !request.headers['x-memory-lab-token']) {
        errorResponse(response, 403, '시연 화면에서 다시 요청해 주세요.');
        return;
      }
      headers.Origin = 'http://' + backendHost;
      headers['Content-Type'] = 'application/json';
      headers['X-Memory-Lab-Token'] = request.headers['x-memory-lab-token'];
    }
    const upstream = http.request({
      hostname: '127.0.0.1',
      port: backendPort,
      path: request.url,
      method: request.method,
      headers,
    }, result => {
      response.writeHead(result.statusCode, { 'Content-Type': 'application/json; charset=utf-8' });
      result.on('error', () => response.destroy());
      result.pipe(response);
    });
    upstream.on('error', () => {
      errorResponse(response, 502, 'Memory Lab 백엔드에 연결하지 못했습니다. 4319번 서버를 확인해 주세요.');
    });
    response.on('close', () => {
      if (!response.writableFinished) upstream.destroy();
    });
    request.pipe(upstream);
  });
  return server;
}

if (require.main === module) {
  const server = createDemoServer();
  server.on('error', error => {
    console.error('시연 서버 시작 실패:', error.message);
    process.exitCode = 1;
  });
  server.listen(4320, '127.0.0.1', () => console.log('시연 화면: http://127.0.0.1:4320/'));
}

module.exports = { createDemoServer };
