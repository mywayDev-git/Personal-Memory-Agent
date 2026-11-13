const fs=require('node:fs'),path=require('node:path'),net=require('node:net'),os=require('node:os'),crypto=require('node:crypto'),{spawn,spawnSync}=require('node:child_process');
const {chatRequest,requestBudget}=require('./token-budget.cjs');
const diagnostics=require('./request-diagnostics.cjs');
const models=require('./model-registry.cjs'),{fileHash}=require('./download.cjs'),{hash,schemaIssues}=require('./core.cjs');
const {processControl}=require('./process-control.cjs');
const delay=ms=>new Promise(r=>setTimeout(r,ms));
const retryWait=require('node:timers/promises').setTimeout;
const TOKEN_COUNT_ENDPOINTS=new Set(['/tokenize','/v1/chat/completions/input_tokens']);
const TOKEN_COUNT_RETRY_CODES=new Set(['ECONNRESET','ECONNREFUSED','EPIPE','UND_ERR_SOCKET','UND_ERR_CONNECT_TIMEOUT']);
async function freePort(port){return new Promise((resolve,reject)=>{const s=net.createServer();s.once('error',()=>reject(Error(`전용 포트 ${port}가 이미 사용 중입니다. 기존 서버는 재사용하거나 종료하지 않습니다.`)));s.listen(port,'127.0.0.1',()=>s.close(resolve));});}
class Runtime{
 constructor(root,options={}){this.root=root;this.modelDirectory=options.modelDirectory||path.join(root,'.models');this.ports=options.ports||{generation:18491,embedding:18492};this.shutdownEpoch=0;this.stopRequested=false;this.terminating=false;this.last_process_check=null;this.exe='C:\\llama.cpp\\llama-server.exe';this.states={generation:{status:'stopped'},embedding:{status:'stopped'}};this.children={};this.keys={};this.verified=new Map();this.pending={};this.logDir=path.join(root,'.local','baseline','runtime');fs.mkdirSync(this.logDir,{recursive:true});const version=fs.existsSync(this.exe)?spawnSync(this.exe,['--version'],{windowsHide:true,encoding:'utf8',timeout:10000}):null;this.version=version?((version.stdout||'')+(version.stderr||'')).trim():'llama-server 없음';this.hardware={node:process.version,platform:process.platform,arch:process.arch,cpu:os.cpus()[0]?.model,logical_cpus:os.cpus().length,ram_bytes:os.totalmem()};}
 catalog(){return models.map(m=>({...m,path:path.join(this.modelDirectory,m.file),present:fs.existsSync(path.join(this.modelDirectory,m.file))&&fs.statSync(path.join(this.modelDirectory,m.file)).size===m.bytes}));}
 status(){return {executable:this.exe,version:this.version,hardware:this.hardware,states:this.states,models:this.catalog(),process_check:this.last_process_check,terminating:this.terminating};}
 allowStart(){if(this.terminating)throw Error('프로세스 종료 확인 중입니다.');this.stopRequested=false;}
 async inspectProcesses(){try{const report=await (this.processController||processControl)(this.root,this.exe,models,'inspect');this.last_process_check=report;return report;}catch(e){this.last_process_check={verified:false,checked_at:new Date().toISOString(),error:e.message};throw e;}}
 async forceStop(){
  if(this.terminating)throw Error('이미 프로세스 종료 확인 중입니다.');this.terminating=true;this.stopRequested=true;this.shutdownEpoch++;
  try{await this.stopAll().catch(()=>{});const report=await (this.processController||processControl)(this.root,this.exe,models,'terminate');this.last_process_check=report;if(report.remaining.length)throw Error('모델 프로세스 '+report.remaining.length+'개가 남아 있습니다.');await Promise.allSettled(Object.values(this.pending));this.children={};this.states={generation:{status:'stopped'},embedding:{status:'stopped'}};return report;}catch(e){this.last_process_check={verified:false,checked_at:new Date().toISOString(),error:e.message};throw e;}finally{this.terminating=false;}
 }
 async ensure(role,id,signal){
  if(this.stopRequested||this.terminating||signal?.aborted)throw Error('사용자 요청으로 모델 실행이 중단됐습니다.');
  const m=models.find(m=>m.id===id&&m.role===role);if(!m)throw Error('등록되지 않은 모델: '+id);
  if(this.states[role].status==='ready'&&this.states[role].model_id===id)return;
  if(this.pending[role]){await this.pending[role];if(this.states[role].model_id===id&&this.states[role].status==='ready')return;}
  this.pending[role]=this.start(role,m,signal);try{await this.pending[role];}finally{delete this.pending[role];}
 }
 async start(role,m,signal){
  const epoch=this.shutdownEpoch;const assertActive=()=>{if(this.stopRequested||this.terminating||epoch!==this.shutdownEpoch||signal?.aborted)throw Error('사용자 요청으로 모델 실행이 중단됐습니다.');};assertActive();
  if(!fs.existsSync(this.exe))throw Error('C:\\llama.cpp\\llama-server.exe를 찾을 수 없습니다.');
  if(signal?.aborted)throw Error('실행 취소');
  await this.stop(role);const file=path.join(this.modelDirectory,m.file);
  if(!fs.existsSync(file))throw Error('먼저 모델을 다운로드하세요: '+m.name);
  this.states[role]={status:'verifying',model_id:m.id};
  const stat=fs.statSync(file),fingerprint=stat.size+':'+stat.mtimeMs;
  if(this.verified.get(file)!==fingerprint){if(stat.size!==m.bytes||await fileHash(file)!==m.sha256){this.states[role].status='error';throw Error('모델 파일 해시 검증 실패');}this.verified.set(file,fingerprint);}
  assertActive();const port=this.ports[role];await freePort(port);assertActive();
  const logPath=path.join(this.logDir,role+'.log'),fd=fs.openSync(logPath,'a');
  this.keys[role]=crypto.randomBytes(32).toString('hex');const keyFile=path.join(this.logDir,role+'.key');fs.writeFileSync(keyFile,this.keys[role]);
  const args=['-m',file,'--host','127.0.0.1','--port',String(port),'-c','8192','-np','1','--no-warmup','--api-key-file',keyFile,'--cors-origins','http://127.0.0.1:'+(process.env.PORT||4319),'--no-cors-credentials'];
  if(role==='generation')args.push('-b','512','-ub','256','-ngl','99','--reasoning','off','--cache-ram','0');
  else args.push('-b','8192','-ub','8192','-ngl','0','--embedding','--pooling','last');
  if(m.stop_token)args.push('--reverse-prompt',m.stop_token);
  const child=spawn(this.exe,args,{cwd:path.dirname(this.exe),windowsHide:true,stdio:['ignore',fd,fd]});fs.closeSync(fd);
  this.children[role]=child;this.states[role]={status:'loading',model_id:m.id,pid:child.pid,port,log_file:logPath,args,runtime_hash:hash({version:this.version,args,model_sha256:m.sha256})};
  let spawnError;child.once('error',e=>{spawnError=e;this.states[role]={...this.states[role],status:'error',error:e.message};});
  child.once('exit',(code,exitSignal)=>{if(this.children[role]===child){delete this.children[role];this.states[role]={...this.states[role],status:code===0?'stopped':'error',exit_code:code,signal_code:exitSignal,exited_at:new Date().toISOString()};}});
  try{for(let i=0;i<180;i++){
   assertActive();if(spawnError)throw spawnError;if(child.exitCode!==null)throw Error('모델 서버가 종료됐습니다. 로그를 확인하세요: '+logPath);
   try{const r=await fetch(`http://127.0.0.1:${port}/health`,{headers:{Authorization:'Bearer '+this.keys[role]},signal:AbortSignal.timeout(1500)});if(r.ok){this.states[role].status='ready';return;}this.states[role].last_health_status=r.status;}catch(e){this.states[role].last_health_error=e.cause?.code||e.message;}
   await delay(1000);
  }throw Error('모델 로드 시간 초과: '+logPath);}catch(e){await this.stop(role);this.states[role]={...this.states[role],status:'error',model_id:m.id,error:e.message};throw e;}
 }
 async stop(role){const c=this.children[role];if(c&&c.exitCode===null&&!c.signalCode){const exited=new Promise(r=>c.once('exit',r));c.kill();await Promise.race([exited,delay(4000)]);if(c.exitCode===null&&!c.signalCode){this.states[role]={...this.states[role],status:'error',error:'프로세스 종료 미확인'};throw Error('프로세스 종료를 확인하지 못했습니다.');}}delete this.children[role];this.states[role]={status:'stopped'};}
 async stopAll(){await Promise.all(['generation','embedding'].map(r=>this.stop(r)));}
 async request(role,endpoint,body,signal,requestInfo={}){
  const maxAttempts=TOKEN_COUNT_ENDPOINTS.has(endpoint)?3:1;
  for(let attempt=1;attempt<=maxAttempts;attempt++){
   try{return await this.requestOnce(role,endpoint,body,signal,{...requestInfo,retry_attempt:attempt,max_attempts:maxAttempts});}
   catch(error){
    const d=error.error_details;
    const retryable=maxAttempts>1&&attempt<maxAttempts&&!signal?.aborted&&!this.stopRequested&&!this.terminating&&this.states[role]?.status==='ready'&&d&&!d.user_cancelled&&!d.timeout_expired&&['send_request','read_response'].includes(d.phase)&&(d.causes||[]).some(c=>TOKEN_COUNT_RETRY_CODES.has(c.code));
    if(!retryable)throw error;
    try{await retryWait(attempt===1?200:600,undefined,{signal});}catch(cancelError){diagnostics.failure(cancelError,{role,endpoint,operation:diagnostics.operation(endpoint),phase:'retry_backoff',retry_attempt:attempt,max_attempts:maxAttempts,user_cancelled:!!signal?.aborted},{logDir:this.logDir,secrets:Object.values(this.keys||{})});throw cancelError;}
   }
  }
 }
 async requestOnce(role,endpoint,body,signal,requestInfo={}){
  const started=performance.now(),before=diagnostics.memory(),serverBefore=diagnostics.server(this,role),timeout=AbortSignal.timeout(diagnostics.TIMEOUT_MS);let phase='before_request',httpStatus=null,requestBytes=0,responseBytes=0;
  try{
   signal?.throwIfAborted();
   if(this.states[role]?.status!=='ready')throw Error(role+' 모델 서버가 준비되지 않았습니다.');
   const encoded=JSON.stringify(body);requestBytes=Buffer.byteLength(encoded);phase='send_request';
   const response=await fetch(`http://127.0.0.1:${this.states[role].port}${endpoint}`,{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+this.keys[role],...(requestInfo.retry_attempt>1?{Connection:'close'}:{})},body:encoded,signal:AbortSignal.any([timeout,...(signal?[signal]:[])])});
   httpStatus=response.status;phase='read_response';const text=await response.text();responseBytes=Buffer.byteLength(text);
   if(!response.ok)throw Error('모델 요청 HTTP '+response.status);
   phase='parse_response';try{return JSON.parse(text);}catch{const error=Error('모델 서버 응답을 JSON으로 읽지 못했습니다.');error.name='SyntaxError';throw error;}
  }catch(error){diagnostics.failure(error,{context:{...diagnostics.context(),...(requestInfo.purpose?{purpose:requestInfo.purpose}:{})},role,endpoint,operation:diagnostics.operation(endpoint),retry_attempt:requestInfo.retry_attempt,max_attempts:requestInfo.max_attempts,phase,http_status:httpStatus,elapsed_ms:performance.now()-started,timeout_ms:diagnostics.TIMEOUT_MS,user_cancelled:!!signal?.aborted,timeout_expired:timeout.aborted,request_bytes:requestBytes,response_bytes:responseBytes,server_before:serverBefore,server_after:diagnostics.server(this,role),memory_before:before},{logDir:this.logDir,secrets:Object.values(this.keys||{})});throw error;}
 }
 async tokenize(text,signal){const d=await this.request('generation','/tokenize',{content:text},signal);if(!Array.isArray(d.tokens))throw Error('토큰 개수 조회 실패');return d.tokens.length;}
 contextLimit(){const args=this.states.generation.args||[],at=args.indexOf('-c');const limit=at>=0?Number(args[at+1]):8192;if(!Number.isInteger(limit)||limit<=0)throw Error('서버 문맥 한도를 확인할 수 없습니다.');return limit;}
 async countChatTokens(messages,schema,config,signal){const d=await this.request('generation','/v1/chat/completions/input_tokens',chatRequest(messages,schema,config),signal);if(!Number.isInteger(d.input_tokens)||d.input_tokens<0)throw Error('실제 요청 토큰 계산 실패. 모델을 실행하지 않습니다.');return d.input_tokens;}
 async chat(messages,schema,config,signal){const budget=await requestBudget(this,messages,schema,config,signal);if(!budget.eligible)throw Object.assign(Error(`전체 요청 ${budget.input_tokens}토큰이 입력 한도 ${budget.input_limit}을 초과했습니다. 원문을 자르지 않습니다.`),{token_budget:budget});const start=performance.now();const data=await this.request('generation','/v1/chat/completions',chatRequest(messages,schema,config),signal);const choice=data.choices?.[0],raw=choice?.message?.content;if(choice?.finish_reason==='length')throw Object.assign(Error('모델 출력 한도 초과; 잘린 출력을 정답으로 사용하지 않습니다.'),{raw,usage:data.usage,input_tokens:budget.input_tokens});if(typeof raw!=='string')throw Object.assign(Error('모델 텍스트 응답 누락'),{usage:data.usage,input_tokens:budget.input_tokens});let parsed;try{parsed=JSON.parse(raw);}catch{throw Object.assign(Error('모델 응답 JSON 파싱 실패'),{raw,usage:data.usage,input_tokens:budget.input_tokens});}const issues=schemaIssues(parsed,schema);if(issues.length)throw Object.assign(Error('모델 출력 스키마 검증 실패: '+issues.slice(0,5).join('; ')),{raw,usage:data.usage,input_tokens:budget.input_tokens});return {parsed,raw,usage:data.usage,elapsed_ms:performance.now()-start,input_tokens:budget.input_tokens,request_budget:budget};}
 async embed(text,query=false,signal){const input=(query?'Instruct: Retrieve personal memory passages relevant to the question, preserving names, negation, time and identifiers.\nQuery: ':'')+text+'<|endoftext|>';const d=await this.request('embedding','/v1/embeddings',{input,encoding_format:'float'},signal,{purpose:query?'query_embedding':'document_embedding'});const vector=d.data?.[0]?.embedding;if(!Array.isArray(vector)||!vector.length||!vector.every(Number.isFinite)||vector.every(v=>v===0))throw Error('유효하지 않은 임베딩');Object.defineProperty(vector,'token_usage',{value:d.usage||null,enumerable:false});return vector;}
}
module.exports={Runtime,freePort};
