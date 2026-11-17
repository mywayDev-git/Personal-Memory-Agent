'use strict';
const http=require('node:http'),fs=require('node:fs'),path=require('node:path');
const {handleUi}=require('./routes.cjs'),{createChatApi}=require('./chat-api.cjs'),{createReadinessApi}=require('./archive-readiness.cjs');
const {createLibraryApi}=require('./library.cjs');
const root=path.resolve(__dirname,'..'),port=Number(process.env.UI_PORT||4330),readiness=createReadinessApi(root);
const library=createLibraryApi(root),chat=createChatApi(root,{resume:data=>{const thread=library.library.read().threads.find(t=>t.id===data.thread_id&&!t.deletedAt);const message=thread?.messages.find(m=>m.kind==='assistant'&&!m.archived&&m.submission.request_id===data.request_id&&m.result?.parts);return message?{submission:message.submission,parts:message.result.parts}:null;}});
const names=['baseline.js','baseline.css','summary.js','summary.css','summary-lab.js','app.js','style.css','timing.js','usage-ui.js','usage-ui.css','structured-lab.js','event-graph-viewer.js','event-graph-viewer.css','stage-review.js','stage-review.css','answer-evaluation.js','answer-evaluation.css'];
const files=new Map(names.map(name=>['/'+name,name]));
for(const route of ['/baseline','/baseline/','/baseline.html'])files.set(route,'baseline.html');
for(const route of ['/summary','/summary.html'])files.set(route,'summary.html');
const server=http.createServer(async(req,res)=>{
  try{
    const url=new URL(req.url,'http://127.0.0.1:'+port),host=req.headers.host||'';
    if(!['127.0.0.1:'+port,'localhost:'+port].includes(host)||(req.headers.origin&&req.headers.origin!=='http://'+host)){res.writeHead(403);res.end('Local origin required');return;}
    if(await library.handle(req,res,url))return;
    if(await chat.handle(req,res,url))return;
    if(await readiness.handle(req,res,url))return;
    if(url.pathname.startsWith('/api/baseline/')){
      // The browser still uses same-origin CSRF tokens; only the fixed local upstream is permitted.
      const upstream=http.request({hostname:'127.0.0.1',port:4319,path:url.pathname+url.search,method:req.method,headers:{...req.headers,host:'127.0.0.1:4319',...(req.headers.origin?{origin:'http://127.0.0.1:4319'}:{})}},response=>{res.writeHead(response.statusCode,response.headers);response.pipe(res);});
      upstream.on('error',()=>{if(!res.headersSent)res.writeHead(503,{'Content-Type':'application/json; charset=utf-8'});res.end(JSON.stringify({error:'기존 AI 서버에 연결할 수 없습니다. start-local.ps1을 실행해 주세요.'}));});req.pipe(upstream);return;
    }
    if(handleUi(req,res,url,root,{connected:true}))return;
    const name=files.get(url.pathname);
    if(!name||!['GET','HEAD'].includes(req.method)){res.writeHead(404);res.end('Not found');return;}
    res.writeHead(200,{'Content-Type':name.endsWith('.js')?'text/javascript; charset=utf-8':name.endsWith('.css')?'text/css; charset=utf-8':'text/html; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"});
    if(req.method==='HEAD'){res.end();return;}const stream=fs.createReadStream(path.join(root,name));stream.on('error',()=>res.destroy());stream.pipe(res);
  }catch{if(!res.headersSent)res.writeHead(500);res.end('요청을 처리하지 못했습니다.');}
});
if(require.main===module){server.listen(port,'127.0.0.1',()=>console.log('AI connected: http://127.0.0.1:'+port+'/#chat'));server.on('error',error=>{console.error(error.message);process.exitCode=1;});for(const signal of ['SIGINT','SIGTERM'])process.on(signal,()=>server.close());}
module.exports={server};
server.on('close',()=>{library.close();chat.close?.();readiness.close?.();});
