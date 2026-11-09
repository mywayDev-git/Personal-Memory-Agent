const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),vm=require('node:vm');
const {Runtime}=require('../local/runtime.cjs'),diag=require('../local/request-diagnostics.cjs'),{Store}=require('../local/store.cjs'),{Engine}=require('../local/engine.cjs'),{buildAnswerEvaluation}=require('../local/answer-evaluation.cjs');
function fixture(){const root=fs.mkdtempSync(path.join(os.tmpdir(),'pma-diagnostic-')),runtime=Object.create(Runtime.prototype);runtime.logDir=path.join(root,'runtime');runtime.states={generation:{status:'ready',model_id:'FAKE',pid:99,port:18491},embedding:{status:'ready',model_id:'FAKE-EMBED',pid:100,port:18492}};runtime.children={};runtime.keys={generation:'SECRET-KEY-123',embedding:'SECRET-EMBED-123'};return {root,runtime,log:()=>fs.readFileSync(path.join(runtime.logDir,'request-errors.jsonl'),'utf8'),cleanup(){assert.ok(path.resolve(root).startsWith(path.resolve(os.tmpdir())+path.sep));fs.rmSync(root,{recursive:true,force:true});}};}
async function withFetch(fetcher,fn){const previous=global.fetch;global.fetch=fetcher;try{return await fn();}finally{global.fetch=previous;}}
const networkError=(code='ECONNRESET')=>new TypeError('fetch failed',{cause:Object.assign(Error('socket failure SECRET-KEY-123 Bearer SECRET-EMBED-123'),{code,syscall:'read'})});
test('failed transport preserves role, endpoint, phase, nested cause, timing and server/memory observations without bodies or keys',async()=>{
 const f=fixture();try{let calls=0;await withFetch(async()=>{calls++;throw networkError();},()=>diag.withContext({run_id:'RUN',question_id:'Q',stage:'answer'},async()=>{
  await assert.rejects(()=>f.runtime.request('generation','/v1/chat/completions',{messages:[{content:'PRIVATE-INPUT-SENTINEL'}]}),e=>{const d=e.error_details;assert.equal(d.category,'CONNECTION_CLOSED');assert.equal(d.cause_code,'ECONNRESET');assert.equal(d.context.question_id,'Q');assert.equal(d.role,'generation');assert.equal(d.phase,'send_request');assert.equal(d.operation,'generation');assert.equal(d.server_before.pid,99);assert.ok(d.elapsed_ms>=0);assert.ok(d.memory_before.web_rss_bytes>0);assert.equal(d.timeout_ms,300000);return true;});
 }));assert.equal(calls,1);const text=f.log();for(const forbidden of ['PRIVATE-INPUT-SENTINEL','SECRET-KEY-123','SECRET-EMBED-123','Authorization'])assert.ok(!text.includes(forbidden));assert.equal(text.trim().split('\n').length,1);
 }finally{f.cleanup();}
});
test('HTTP status, body-read failures, malformed JSON and server-not-ready have distinct diagnoses',async()=>{
 for(const [fetcher,category,phase]of [
  [async()=>({status:503,ok:false,text:async()=>'{"secret":"PRIVATE-RESPONSE"}'}),'HTTP_ERROR','read_response'],
  [async()=>({status:200,ok:true,text:async()=>{throw Object.assign(Error('body read failed'),{code:'UND_ERR_BODY_TIMEOUT'});}}),'BODY_TIMEOUT','read_response'],
  [async()=>({status:200,ok:true,text:async()=>'PRIVATE-RESPONSE'}),'RESPONSE_JSON_INVALID','parse_response']]){
  const f=fixture();try{await withFetch(fetcher,()=>assert.rejects(()=>f.runtime.request('embedding','/v1/embeddings',{input:'PRIVATE-INPUT'}),e=>{assert.equal(e.error_details.category,category);assert.equal(e.error_details.phase,phase);return true;}));assert.ok(!f.log().includes('PRIVATE-RESPONSE'));}finally{f.cleanup();}
 }
 const f=fixture();try{f.runtime.states.generation.status='stopped';await withFetch(async()=>{throw Error('must not send');},()=>assert.rejects(()=>f.runtime.request('generation','/tokenize',{}),e=>{assert.equal(e.error_details.category,'SERVER_NOT_READY');return true;}));}finally{f.cleanup();}
});
test('timeouts, user cancellation, connection refusal and confirmed OS failures are classified without inferring OOM from low RAM',()=>{
 for(const [code,info,expected]of [['ECONNREFUSED',{},'CONNECTION_REFUSED'],['UND_ERR_CONNECT_TIMEOUT',{},'CONNECT_TIMEOUT'],['UND_ERR_HEADERS_TIMEOUT',{},'HEADERS_TIMEOUT'],['ENOMEM',{},'OS_MEMORY_ERROR'],['ENOSPC',{},'OS_STORAGE_ERROR'],['UNKNOWN',{timeout_expired:true},'REQUEST_TIMEOUT'],['UNKNOWN',{user_cancelled:true,timeout_expired:true},'USER_CANCELLED'],['UNKNOWN',{memory_after:{available_system_ram_bytes:1}},'TRANSPORT_UNKNOWN']])assert.equal(diag.failure(networkError(code),{endpoint:'/tokenize',...info}).category,expected);
});
test('success preserves the request and writes no diagnostic file; a failed diagnostic write never replaces the primary error',async()=>{
 const f=fixture();try{const body={input:'UNCHANGED INPUT'};let sent;await withFetch(async(url,options)=>{sent=JSON.parse(options.body);return {status:200,ok:true,text:async()=>' {"tokens":[1,2]} '};},async()=>assert.deepEqual(await f.runtime.request('generation','/tokenize',body),{tokens:[1,2]}));assert.deepEqual(sent,body);assert.equal(fs.existsSync(f.runtime.logDir),false);
  fs.writeFileSync(f.runtime.logDir,'not a directory');await withFetch(async()=>{throw networkError();},()=>assert.rejects(()=>f.runtime.request('generation','/tokenize',body),e=>{assert.equal(e.message,'fetch failed');assert.equal(e.error_details.diagnostic_log_saved,false);assert.ok(e.error_details.diagnostic_log_error_code);return true;}));
 }finally{f.cleanup();}
});
test('concurrent contexts stay isolated and summary/document versus question embedding are distinguishable',async()=>{
 const f=fixture();try{await withFetch(async()=>{await new Promise(r=>setImmediate(r));throw networkError('ECONNREFUSED');},async()=>{
  await Promise.all(['Q1','Q2'].map((qid,i)=>diag.withContext({run_id:'R',question_id:qid,source_id:'S'+i,stage:'retrieval'},()=>assert.rejects(()=>f.runtime.embed('TEXT',i===0),e=>{assert.equal(e.error_details.context.question_id,qid);assert.equal(e.error_details.context.source_id,'S'+i);assert.equal(e.error_details.context.purpose,i===0?'query_embedding':'document_embedding');return true;}))));
 });assert.equal(f.log().trim().split('\n').length,2);assert.deepEqual(diag.context(),{});
 }finally{f.cleanup();}
});
test('a server exit observed while the request fails is recorded without restarting or probing the server',async()=>{
 const f=fixture();try{await withFetch(async()=>{f.runtime.states.generation={...f.runtime.states.generation,status:'error',exit_code:7,signal_code:'SIGTERM'};throw networkError();},()=>assert.rejects(()=>f.runtime.request('generation','/tokenize',{}),e=>{assert.equal(e.error_details.server_before.status,'ready');assert.equal(e.error_details.server_after.exit_code,7);assert.equal(e.error_details.server_after.signal_code,'SIGTERM');return true;}));}finally{f.cleanup();}
});
test('failed question diagnostics survive storage and export views while old run and review payloads are preserved',async()=>{
 const f=fixture();fs.cpSync(path.join(__dirname,'../datasets'),path.join(f.root,'datasets'),{recursive:true});const store=new Store(f.root);
 try{const old={id:'OLD',created_at:'2026-01-01',status:'COMPLETED',config:{},question_ids:[],results:[]};store.putRun(old);store.review('OLD','Q',{verdict:'FAIL',notes:'OLD REVIEW'});const before=JSON.stringify([store.run('OLD'),store.reviews('OLD')]);
  const runtime={version:'MOCK ONLY',status:()=>({states:{generation:{status:'ready'},embedding:{status:'stopped'}},models:[]}),ensure:async()=>{},stop:async()=>{},tokenize:async()=>100,countChatTokens:async()=>100,chat:async()=>{throw networkError('ECONNREFUSED');}};
  const engine=new Engine(f.root,store,runtime),run=await engine.create({config:{route:'R0-Full'},question_ids:['F02-Q1']});for(let n=0;n<200&&engine.busy;n++)await new Promise(r=>setTimeout(r,5));assert.equal(engine.busy,null);const saved=store.run(run.id),r=saved.results[0];assert.equal(r.status,'ERROR');assert.equal(r.error,'fetch failed');assert.equal(r.error_details.cause_code,'ECONNREFUSED');assert.equal(r.error_details.context.question_id,'F02-Q1');assert.equal(r.error_details.context.stage,'answer');assert.equal(saved.config.request_diagnostics_version,diag.VERSION);
  const view=buildAnswerEvaluation(saved,store,'F02-Q1');assert.equal(view.detail.has_answer,false);assert.equal(view.detail.error_details.event_id,r.error_details.event_id);assert.equal(JSON.stringify([store.run('OLD'),store.reviews('OLD')]),before);
 }finally{store.db.close();f.cleanup();}
});
test('failed summary attempts retain the source, part and nested cause independently of run storage',async()=>{
 const f=fixture(),store=new Store(f.root);try{const runtime={version:'MOCK',chat:async()=>{throw networkError('ECONNREFUSED');}},engine=new Engine(f.root,store,runtime),source={id:'SOURCE',revision:1,text:'합성 원문',metadata:{owner_id:'synthetic'}};await assert.rejects(()=>engine.summary.save('test',source,{model:'qwen35-4b-q4'}),/fetch failed/);const row=JSON.parse(store.db.prepare('SELECT payload FROM summary_attempts').get().payload);assert.equal(row.error_details.context.source_id,'SOURCE');assert.equal(row.error_details.context.summary_part,1);assert.equal(row.error_details.cause_code,'ECONNREFUSED');assert.equal(row.error_details.category,'CONNECTION_REFUSED');
 }finally{store.db.close();f.cleanup();}
});
test('the UI explains detailed errors and explicitly leaves old errors without invented causes',()=>{
 const ctx=vm.createContext({document:{querySelector:()=>null,querySelectorAll:()=>[],addEventListener(){}},console,setTimeout,clearTimeout,MemoryTiming:{format:()=>''}});vm.runInContext(fs.readFileSync(path.join(__dirname,'../baseline.js'),'utf8').replace('\ninitialize();','\n').replace('\ninitializeSelectionGuide();','\n'),ctx);
 assert.match(vm.runInContext('errorDetailsHTML(null)',ctx),/이전 실행에는 세부 원인이 저장되지/);ctx.detail=diag.failure(networkError(),{role:'generation',endpoint:'/tokenize',operation:'token_count',phase:'send_request',elapsed_ms:5,server_after:{status:'error',pid:9,port:18491},context:{question_id:'<unsafe>'}});const html=vm.runInContext('errorDetailsHTML(detail)',ctx);for(const text of ['연결 끊김','본문 토큰 계산','ECONNRESET','&lt;unsafe&gt;','메모리 부족으로 확정하지'])assert.ok(html.includes(text));assert.ok(!html.includes('<unsafe>'));
});
