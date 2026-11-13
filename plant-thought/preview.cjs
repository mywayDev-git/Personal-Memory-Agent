'use strict';
const http=require('node:http');
const fs=require('node:fs');
const path=require('node:path');
const files=new Map([
  ['/', ['index.html','text/html; charset=utf-8']],
  ['/index.html',['index.html','text/html; charset=utf-8']],
  ['/memory.js',['memory.js','text/javascript; charset=utf-8']],
  ['/conversation-ux.js',['conversation-ux.js','text/javascript; charset=utf-8']],
  ['/diary-dates.js',['diary-dates.js','text/javascript; charset=utf-8']],
]);
const routes=new Map([
  ['/api/baseline/bootstrap','GET'],
  ['/api/baseline/summary-memory','GET'],
  ['/api/baseline/summary-memory/intent','POST'],
  ['/api/baseline/summary-memory/save','POST'],
  ['/api/baseline/summary-memory/search','POST'],
  ...['plan','save','delete','commit','search','status','cancel','access'].map(action=>['/api/baseline/summary-memory/ux/'+action,'POST']),
  ['/api/baseline/summary-memory/ux/info','GET'],
]);
const readOnly=/^\/api\/baseline\/summary-memory\/(?:original\?key=[a-f0-9]{64}|progress\?id=[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12})$/;
function createPlantServer({backendPort=4321}={}){
  return http.createServer((req,res)=>{
    const host='127.0.0.1:'+res.socket.localPort;
    const error=(status,message)=>{
      if(res.headersSent){res.destroy();return;}
      res.writeHead(status,{'Content-Type':'application/json; charset=utf-8'});res.end(JSON.stringify({error:message}));
    };
    if(req.headers.host!==host||(req.headers.origin&&req.headers.origin!=='http://'+host)){
      error(403,'페이지의 로컬 주소로 접속해 주세요.');return;
    }
    res.setHeader('Cache-Control','no-store');res.setHeader('X-Content-Type-Options','nosniff');
    const page=files.get(req.url);
    if(req.method==='GET'&&page){
      res.setHeader('Content-Type',page[1]);
      res.setHeader('Content-Security-Policy',"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'");
      const stream=fs.createReadStream(path.join(__dirname,page[0]));stream.on('error',()=>error(500,'화면 파일을 읽지 못했습니다.'));stream.pipe(res);return;
    }
    const method=routes.get(req.url)||(readOnly.test(req.url)?'GET':null);
    if(method!==req.method){error(404,'사용할 수 없는 경로입니다.');return;}
    const headers={Host:'127.0.0.1:'+backendPort};
    if(req.method==='POST'){
      if(req.headers.origin!=='http://'+host||!req.headers['content-type']?.startsWith('application/json')||!req.headers['x-memory-lab-token']){
        error(403,'이 화면에서 다시 요청해 주세요.');return;
      }
      Object.assign(headers,{Origin:'http://127.0.0.1:'+backendPort,'Content-Type':'application/json','X-Memory-Lab-Token':req.headers['x-memory-lab-token']});
    }
    const upstream=http.request({hostname:'127.0.0.1',port:backendPort,path:req.url,method:req.method,headers},result=>{
      res.writeHead(result.statusCode,{'Content-Type':'application/json; charset=utf-8'});result.on('error',()=>res.destroy());result.pipe(res);
    });
    upstream.on('error',()=>error(502,'기억 서버에 연결하지 못했습니다. start-local.ps1로 실행하거나 4321번 백엔드를 확인해 주세요.'));
    res.on('close',()=>{if(!res.writableFinished)upstream.destroy();});req.pipe(upstream);
  });
}
if(require.main===module){
  const server=createPlantServer({backendPort:Number(process.env.PLANT_BACKEND_PORT||4321)});
  server.on('error',error=>{console.error(error.message);process.exitCode=1;});
  server.listen(Number(process.env.PLANT_PORT||4180),'127.0.0.1',()=>console.log('Plant Thought: http://127.0.0.1:'+server.address().port));
}
module.exports={createPlantServer};
