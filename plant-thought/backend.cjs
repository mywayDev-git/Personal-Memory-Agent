'use strict';
const http=require('node:http');
const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const {createApi}=require(path.join(root,'local/api.cjs'));
const {Runtime}=require(path.join(root,'local/runtime.cjs'));
const {Store}=require(path.join(root,'local/store.cjs'));
const {createConversationUx}=require('./conversation-ux.cjs');

async function installedModelDirectory(){
  if(process.env.PLANT_MODEL_DIR)return path.resolve(process.env.PLANT_MODEL_DIR);
  if(fs.existsSync(path.join(root,'.models')))return path.join(root,'.models');
  try{
    const response=await fetch('http://127.0.0.1:4319/api/baseline/bootstrap',{signal:AbortSignal.timeout(2500)});
    const {runtime}=await response.json();
    const present=runtime?.models?.filter(model=>model.present&&path.basename(model.path)===model.file)||[];
    const directories=[...new Set(present.map(model=>path.dirname(model.path)))];
    if(directories.length===1&&present.every(model=>fs.existsSync(model.path)))return directories[0];
  }catch{}
  return path.join(root,'.models');
}
async function start(){
  const runtime=new Runtime(__dirname,{modelDirectory:await installedModelDirectory(),ports:{generation:18501,embedding:18502}});
  const api=createApi(root,{runtime,store:new Store(__dirname),wrapSummaryApi:createConversationUx});
  const port=Number(process.env.PLANT_BACKEND_PORT||4321);
  // Reuse the branch's static asset map for its separate model-management screen.
  const source=fs.readFileSync(path.join(root,'server.cjs'),'utf8');
  const mapText=source.match(/const staticFiles=new Map\((\[.*?\])\);/s)?.[1];
  if(!mapText)throw Error('브랜치의 관리 화면 구성을 확인하지 못했습니다.');
  const staticFiles=new Map(JSON.parse(mapText.replaceAll("'",'"')));
  const server=http.createServer(async(req,res)=>{
    res.setHeader('X-Plant-Backend','conversation-ux-v1');
    const url=new URL(req.url,'http://127.0.0.1:'+port);
    if(await api.handle(req,res,url))return;
    const file=staticFiles.get(url.pathname);
    if(!file||req.method!=='GET'){res.writeHead(404);res.end('Not found');return;}
    res.writeHead(200,{'Content-Type':file.endsWith('.js')?'text/javascript; charset=utf-8':file.endsWith('.css')?'text/css; charset=utf-8':'text/html; charset=utf-8','Cache-Control':'no-cache','X-Content-Type-Options':'nosniff','Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"});
    const stream=fs.createReadStream(path.join(root,file));stream.on('error',()=>res.destroy());stream.pipe(res);
  });
  let closing=false;
  async function close(){if(closing)return;closing=true;server.close();await api.close();}
  process.on('SIGINT',()=>void close());process.on('SIGTERM',()=>void close());
  server.on('error',error=>{console.error(error.message);void close();process.exitCode=1;});
  await new Promise((resolve,reject)=>{
    server.once('error',reject);
    server.listen(port,'127.0.0.1',()=>{console.log('Plant Thought 기억 서버: http://127.0.0.1:'+port+'/baseline');resolve();});
  });
  return {server,close};
}
if(require.main===module)start().catch(error=>{console.error(error.message);process.exitCode=1;});
module.exports={installedModelDirectory,start};
