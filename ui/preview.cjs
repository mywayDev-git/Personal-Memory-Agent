'use strict';
// A static-only preview: deliberately never imports local/api.cjs, Store, or Runtime.
const http=require('node:http'),fs=require('node:fs'),path=require('node:path');
const {handleUi}=require('./routes.cjs');
const root=path.resolve(__dirname,'..');
const assets=['baseline.js','baseline.css','summary.js','summary.css','summary-lab.js','app.js','style.css','timing.js','usage-ui.js','usage-ui.css','structured-lab.js','event-graph-viewer.js','event-graph-viewer.css','stage-review.js','stage-review.css','answer-evaluation.js','answer-evaluation.css'];
const files=new Map(assets.map(name=>['/'+name,name]));
for(const route of ['/baseline','/baseline/','/baseline.html'])files.set(route,'baseline.html');
for(const route of ['/summary','/summary.html'])files.set(route,'summary.html');
files.set('/ui/lab-preview.js','ui/lab-preview.js');files.set('/ui/lab-preview.css','ui/lab-preview.css');
files.set('/memorylab-preview','index.html');
function createPreviewServer(){return http.createServer((req,res)=>{
  const url=new URL(req.url,'http://127.0.0.1');
  if(url.pathname.startsWith('/api/')){res.writeHead(503,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'});res.end(JSON.stringify({error:'UI 미리보기입니다. AI·저장·검색·실험 실행은 연결하지 않았습니다.',code:'UI_PREVIEW_ONLY'}));return;}
  if(url.pathname!=='/memorylab-preview'&&handleUi(req,res,url,root))return;
  const name=files.get(url.pathname);
  if(!name||!['GET','HEAD'].includes(req.method)){res.writeHead(404);res.end('Not found');return;}
  const file=path.join(root,name);if(!fs.existsSync(file)){res.writeHead(404);res.end('Not found');return;}
  const html=name.endsWith('.html');
  res.writeHead(200,{'Content-Type':name.endsWith('.js')?'text/javascript; charset=utf-8':name.endsWith('.css')?'text/css; charset=utf-8':'text/html; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'none'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"});
  if(req.method==='HEAD'){res.end();return;}
  if(html){
    let body=fs.readFileSync(file,'utf8');
    body=body.replaceAll('http://127.0.0.1:4319/','/');
    if(name==='index.html')body=body.replace('<nav>','<nav><a class="nav" href="/#memorylab">← <span>서재로 돌아가기</span></a>');
    body=body.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,'');
    body=body.replace('</head>','<link rel="stylesheet" href="/ui/lab-preview.css"></head>');
    body=body.replace('</body>','<script src="/ui/lab-preview.js"></script></body>');
    res.end(body);
  }else{const stream=fs.createReadStream(file);stream.on('error',()=>res.destroy());stream.pipe(res);}
});}
if(require.main===module){
  const server=createPreviewServer(),port=Number(process.env.UI_PORT||4330);
  server.listen(port,'127.0.0.1',()=>console.log('UI preview: http://127.0.0.1:'+server.address().port+'/'));
  server.on('error',error=>{console.error(error.message);process.exitCode=1;});
  for(const signal of ['SIGINT','SIGTERM'])process.on(signal,()=>server.close());
}
module.exports={createPreviewServer};
