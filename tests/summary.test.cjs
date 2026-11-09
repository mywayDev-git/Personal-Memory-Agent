const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),http=require('node:http');
const {Store}=require('../local/store.cjs'),{Engine}=require('../local/engine.cjs'),{createApi}=require('../local/api.cjs'),{createSummaryApi}=require('../local/summary-api.cjs'),{parts,VERSION}=require('../local/summary.cjs'),{buildReview}=require('../local/review.cjs');
const root=path.resolve(__dirname,'..'),SENTINEL='ORIGINAL_ONLY_9472',SUMMARY='회의는 11월 7일 오후 3시로 변경됐다. 금액 30만원은 확정되지 않았다.';
class Runtime{
 constructor(){this.calls=[];this.version='SUMMARY_OFFLINE';this.states={generation:{status:'stopped'},embedding:{status:'stopped'}};}
 status(){return {version:this.version,states:this.states,models:[]};}
 allowStart(){} async ensure(role,id){this.calls.push({kind:'ensure',role,id});this.states[role]={status:'ready',model_id:id};}async stopAll(){}
 async tokenize(text){return Math.ceil(text.length/2);}
 async embed(text,query,signal){signal?.throwIfAborted();if(this.failEmbed)throw Error('embedding failed');this.calls.push({kind:'embed',text,query});return [1,text.length/100+1,2];}
 async chat(messages,schema,config,signal){signal?.throwIfAborted();this.calls.push({kind:'chat',messages});const payload=JSON.parse(messages[1].content);let parsed;
  if(schema.properties.summary){if(this.failSummary)throw Error('summary failed');if(this.invalid)parsed={summary:' '};else parsed={summary:this.summary||SUMMARY};}
  else{const e=payload.evidence[0];parsed={action:e?'answer':'abstain',answer:e?e.text:'요약에 정보가 없습니다.',citations:e?[{evidence_id:e.evidence_id,quote:e.text,occurrence:1}]:[]};}
  return {parsed,raw:JSON.stringify(parsed),usage:{prompt_tokens:10,completion_tokens:10},elapsed_ms:1};
 }
}
function fixture(datasets=false){const dir=fs.mkdtempSync(path.join(os.tmpdir(),'summary-memory-'));if(datasets)fs.cpSync(path.join(root,'datasets'),path.join(dir,'datasets'),{recursive:true});const store=new Store(dir),runtime=new Runtime(),engine=new Engine(dir,store,runtime),api=createSummaryApi(engine,runtime);return {dir,store,runtime,engine,api};}
const get=(f,route='/summary-memory')=>f.api.get(new URL('http://localhost'+route).pathname,new URL('http://localhost'+route));
const save=(f,text=SENTINEL+' 회의는 11월 7일로 변경. 30만원은 확정 아님.',extra={})=>f.api.post('/summary-memory/save',{text,...extra});
async function finish(f,body){const run=await f.engine.create(body);for(let i=0;i<600;i++){const r=f.store.run(run.id);if(!f.engine.busy)return r;await new Promise(r=>setTimeout(r,5));}throw Error('timeout');}

test('originals are archived separately; only summaries reach lexical, vector and answer inputs',async()=>{
 const f=fixture();try{
  const {memory}=await save(f),original=await get(f,'/summary-memory/original?key='+memory.memory_key);assert.ok(original.source.text.includes(SENTINEL));assert.equal(memory.summary,SUMMARY);
  const archived=f.store.readArtifact(memory.summary_artifact_id);assert.equal(JSON.stringify(archived).includes(SENTINEL),false);assert.ok(!archived.original_artifact_id);
  const originalReader=f.engine.summary.original;f.engine.summary.original=()=>{throw Error('Search read an original');};
  const lexical=f.engine.lexical.bind(f.engine);f.engine.lexical=(items,text)=>{assert.ok(items.every(i=>i.origin==='summary'&&!i.text.includes(SENTINEL)));return lexical(items,text);};
  const result=await f.api.post('/summary-memory/search',{query:'회의 일정',answer:true});assert.equal(result.retrieval.kind,VERSION);assert.equal(result.retrieval.source_snapshots.length,0);assert.equal(result.retrieval.metrics.span_groups_fully_covered,null);assert.equal(result.answer.citation_errors.length,0);assert.ok(result.answer.citations.every(c=>c.basis==='summary'&&c.summary_id===memory.summary_artifact_id));
  assert.ok(f.runtime.calls.filter(c=>c.kind==='embed').every(c=>!c.text.includes(SENTINEL)));const request=f.runtime.calls.filter(c=>c.kind==='chat').at(-1);assert.ok(!JSON.stringify(request).includes(SENTINEL));assert.deepEqual(JSON.parse(request.messages[1].content).conversation,[]);
  assert.equal(f.store.list().length,0);f.engine.summary.original=originalReader;
 }finally{f.store.db.close();}
});
test('persisted summaries survive restart and search does not summarize again',async()=>{
 const f=fixture();try{await save(f);const count=f.runtime.calls.filter(c=>c.kind==='chat').length;await f.api.post('/summary-memory/search',{query:'회의',answer:false});assert.equal(f.runtime.calls.filter(c=>c.kind==='chat').length,count);f.store.db.close();f.store=new Store(f.dir);f.engine=new Engine(f.dir,f.store,f.runtime);f.api=createSummaryApi(f.engine,f.runtime);assert.equal((await get(f)).memories.length,1);await f.api.post('/summary-memory/search',{query:'회의'});assert.equal(f.runtime.calls.filter(c=>c.kind==='chat').length,count);}finally{f.store.db.close();}
});
test('failed generation, empty output, embedding failure and cancellation keep the old active summary',async()=>{
 const f=fixture();try{const {memory:m}=await save(f);
  for(const mode of ['failSummary','invalid','failEmbed']){f.runtime[mode]=true;f.runtime.summary='변경된 요약 '+mode;await assert.rejects(()=>f.api.post('/summary-memory/resummarize',{key:m.memory_key,expected:m.summary_artifact_id}));assert.equal((await get(f)).memories[0].summary_artifact_id,m.summary_artifact_id);f.runtime[mode]=false;}
  const controller=new AbortController(),embed=f.runtime.embed.bind(f.runtime);f.runtime.summary='취소 대상 요약';f.runtime.embed=async(...args)=>{controller.abort();return embed(...args);};await assert.rejects(()=>f.engine.summary.save(m.namespace,f.engine.summary.original(m),f.engine.config({route:'M0'}),controller.signal,{force:true}));assert.equal((await get(f)).memories[0].summary_artifact_id,m.summary_artifact_id);assert.ok(f.store.db.prepare('SELECT count(*) n FROM summary_attempts').get().n>=4);
 }finally{f.store.db.close();}
});
test('edit replaces the active summary, stale writes fail, and deletion immediately excludes it',async()=>{
 const f=fixture();try{const {memory:m}=await save(f);f.runtime.summary='회의는 취소됐다.';const {memory:updated}=await save(f,'새 원본 취소 기록',{key:m.memory_key,expected:m.summary_artifact_id});assert.equal(updated.revision,2);assert.notEqual(updated.summary_artifact_id,m.summary_artifact_id);assert.equal((await get(f)).memories.length,1);
  await assert.rejects(()=>save(f,'오래된 화면 수정',{key:m.memory_key,expected:m.summary_artifact_id}),/변경/);const found=await f.api.post('/summary-memory/search',{query:'회의',answer:true});assert.ok(found.retrieval.evidence.every(e=>e.summary_id===updated.summary_artifact_id));assert.ok(!found.answer.answer.includes('30만원'));
  await f.api.post('/summary-memory/delete',{key:updated.memory_key,expected:updated.summary_artifact_id});assert.equal((await get(f)).memories.length,0);const deleted=await f.api.post('/summary-memory/search',{query:'회의',answer:true});assert.equal(deleted.retrieval.evidence.length,0);assert.equal(deleted.answer.action,'abstain');await assert.rejects(()=>get(f,'/summary-memory/original?key='+m.memory_key),/없습니다/);assert.ok(f.store.readArtifact(m.original_artifact_id));
 }finally{f.store.db.close();}
});
test('resummarization reads the preserved original and atomically activates a new summary',async()=>{
 const f=fixture();try{const {memory:m}=await save(f);f.runtime.summary='재요약된 회의 일정.';const {memory:newM}=await f.api.post('/summary-memory/resummarize',{key:m.memory_key,expected:m.summary_artifact_id});assert.notEqual(newM.summary_artifact_id,m.summary_artifact_id);const call=f.runtime.calls.filter(c=>c.kind==='chat').at(-1);assert.ok(call.messages[1].content.includes(SENTINEL));assert.equal((await get(f)).memories[0].summary,f.runtime.summary);}finally{f.store.db.close();}
});
test('summary cache invalidates for content, owner, model and guidance, while unchanged input is reused',async()=>{
 const f=fixture();try{const {memory:m}=await save(f),source=f.engine.summary.original(m),signal=new AbortController().signal,c=f.engine.config({route:'M0'});let count=f.runtime.calls.filter(c=>c.kind==='chat').length;
  const cached=await f.engine.summary.save(m.namespace,source,c,signal);assert.equal(cached.reused,true);assert.equal(f.runtime.calls.filter(c=>c.kind==='chat').length,count);
  for(const patch of [{summary_prompt_text:'날짜를 보존해 요약'},{model:'qwen35-2b-q4'}]){await f.engine.summary.save(m.namespace,source,f.engine.config({route:'M0',...patch}),signal);assert.equal(f.runtime.calls.filter(c=>c.kind==='chat').length,++count);}
  await f.engine.summary.save(m.namespace,{...source,text:source.text+' 추가 입력'},c,signal);assert.equal(f.runtime.calls.filter(c=>c.kind==='chat').length,++count);
  const other=await f.engine.summary.save(m.namespace,{...source,metadata:{...source.metadata,owner_id:'other'}},c,signal);assert.notEqual(other.memory_key,m.memory_key);assert.equal((await get(f)).memories.length,1);
 }finally{f.store.db.close();}
});
test('overlapping summary operations are rejected and cannot overwrite a newer memory',async()=>{
 const f=fixture();try{const {memory:m}=await save(f);const previous=f.engine.summary.original(m),chat=f.runtime.chat.bind(f.runtime);let release;const gate=new Promise(r=>release=r);f.runtime.chat=async(...args)=>{await gate;return chat(...args);};
  const active=f.api.post('/summary-memory/resummarize',{key:m.memory_key,expected:m.summary_artifact_id});await new Promise(r=>setImmediate(r));await assert.rejects(()=>save(f,'concurrent'),/진행 중/);release();await active;assert.equal(f.engine.busy,null);
  const fresh=f.engine.summary.get(m.memory_key);await assert.rejects(()=>f.engine.summary.save(m.namespace,previous,f.engine.config({route:'M0'}),new AbortController().signal,{force:true,expected:'stale'}),/변경/);assert.equal(f.engine.summary.get(m.memory_key).summary_artifact_id,fresh.summary_artifact_id);
 }finally{f.store.db.close();}
});
test('long inputs cover every character without breaking emoji; malformed/partial results never publish',async()=>{
 const text='가'.repeat(2199)+'😀'+'나'.repeat(10000),ps=parts(text);assert.equal(ps[0].start,0);assert.equal(ps.at(-1).end,text.length);for(let i=0;i<ps.length;i++){assert.equal(ps[i].text,text.slice(ps[i].start,ps[i].end));assert.ok(!/[\uD800-\uDBFF]$/.test(ps[i].text));assert.ok(!/^[\uDC00-\uDFFF]/.test(ps[i].text));if(i)assert.ok(ps[i].start<=ps[i-1].end);}
 const f=fixture();try{await save(f,text);assert.equal(f.runtime.calls.filter(c=>c.kind==='chat').length,ps.length);let calls=0;const chat=f.runtime.chat.bind(f.runtime);f.runtime.chat=async(...args)=>{if(++calls===2)throw Error('second part failed');return chat(...args);};await assert.rejects(()=>save(f,text),/second part/);assert.equal((await get(f)).memories.length,1);}finally{f.store.db.close();}
});
test('dataset M0 reuses summaries across runs, excludes owner/deleted inputs and never sends gold',async()=>{
 const f=fixture(true);try{const a=await finish(f,{config:{route:'M0',query_prompt:'query-context-v1'},question_ids:['F02-Q1','F02-Q2','F30-Q1','F28-Q2','F29-Q2']});assert.equal(a.status,'COMPLETED',JSON.stringify(a.results.map(r=>r.error)));assert.ok(a.results.every(r=>r.status==='PENDING_REVIEW'));
  assert.deepEqual(a.results[2].accessible_source_ids,['F30-A']);for(const r of a.results.slice(3))assert.equal(r.stages.retrieval.evidence.length,0);
  const calls=f.runtime.calls.filter(c=>c.kind==='chat').length;await finish(f,{config:{route:'M0'},stage:'extract',question_ids:['F02-Q1']});assert.equal(f.runtime.calls.filter(c=>c.kind==='chat').length,calls);
  for(const call of f.runtime.calls.filter(c=>c.kind==='chat'))for(const forbidden of ['"gold":','"required_claims":','"reference_answer":','"expected_state":','TEST-ONLY-582','합성차-882'])assert.ok(!JSON.stringify(call.messages).includes(forbidden));
  const ds=await f.engine.dataset();const review=buildReview(a,f.store,ds,'extraction');assert.ok(review.targets.some(t=>t.method==='summary'&&t.sources.length&&t.units[0].object===SUMMARY));
 }finally{f.store.db.close();}
});
test('raw/structured frozen artifacts cannot enter summary search or answers',async()=>{
 const f=fixture(true);try{const a=await finish(f,{config:{route:'R0'},question_ids:['F02-Q1']});const raw=a.results[0].stages.retrieval.artifact_id;const blocked=await finish(f,{config:{route:'M0'},stage:'answer',artifacts:[raw],question_ids:['F02-Q1']});assert.equal(blocked.results[0].status,'ERROR');assert.match(blocked.results[0].error,/서로 재사용/);
  const summarized=await finish(f,{config:{route:'M0'},question_ids:['F02-Q1']}),r=summarized.results[0].stages.retrieval,source=(await f.engine.dataset()).d.sources.records.find(s=>s.id===r.source_refs[0].source_id);const forged=structuredClone(r);forged.evidence[0].text=SENTINEL;assert.throws(()=>f.engine.summary.assertRetrieval(forged,[source]),/요약 이외/);
  const scope=structuredClone(source);scope.metadata.owner_id='other';assert.throws(()=>f.engine.summary.assertRetrieval(r,[scope]),/소유자/);const changed=structuredClone(source);changed.text+=' new content';assert.throws(()=>f.engine.summary.assertRetrieval(r,[changed]),/버전/);
 }finally{f.store.db.close();}
});
test('HTTP summary mutations require a token and same origin; GETs never start models',async()=>{
 const f=fixture(),api=createApi(f.dir,{store:f.store,runtime:f.runtime}),server=http.createServer((req,res)=>api.handle(req,res,new URL(req.url,'http://'+req.headers.host)));await new Promise(r=>server.listen(0,'127.0.0.1',r));const base='http://127.0.0.1:'+server.address().port+'/api/baseline';
 try{assert.equal((await fetch(base+'/summary-memory')).status,200);assert.equal(f.runtime.calls.length,0);const {token}=await(await fetch(base+'/bootstrap')).json();const post=(headers,body)=>fetch(base+'/summary-memory/save',{method:'POST',headers:{'Content-Type':'application/json',...headers},body:JSON.stringify(body)});
  assert.equal((await post({},{})).status,403);assert.equal((await post({'X-Memory-Lab-Token':token,Origin:'https://example.invalid'},{})).status,403);assert.equal((await post({'X-Memory-Lab-Token':token},{text:SENTINEL})).status,200);assert.equal((await(await fetch(base+'/summary-memory')).json()).memories.length,1);
 }finally{await new Promise(r=>server.close(r));await api.close();}
});

