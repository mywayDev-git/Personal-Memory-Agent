const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),http=require('node:http');
const {sentences,locate,validateNative,validateCitations,schemaIssues,rrf,cosine}=require('../local/core.cjs'),prompts=require('../local/prompts.cjs'),{Store}=require('../local/store.cjs'),{Engine}=require('../local/engine.cjs'),{createApi}=require('../local/api.cjs');
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
class FakeRuntime{
 constructor(){this.version='OFFLINE_TEST_DOUBLE';this.calls=[];this.states={generation:{status:'stopped'},embedding:{status:'stopped'}};}
 status(){return {version:this.version,states:this.states,models:[]};}
 async ensure(role,id){this.calls.push({kind:'ensure',role,id});this.states[role]={status:'ready',model_id:id};}
 async stopAll(){}
 async tokenize(text){return Math.ceil(text.length/3);}
 async embed(text,query,signal){if(signal?.aborted)throw Error('cancelled');this.calls.push({kind:'embed',text,query});return [text.length/100+1,1,(text.charCodeAt(0)||1)/1000];}
 async chat(messages,schema){this.calls.push({kind:'chat',messages});const payload=JSON.parse(messages[1].content);let parsed;
  if(payload.sentences){const s=payload.sentences[0],q={polarity:'positive',status:'unknown',modality:'asserted',time:'',event_time:'',speech_time:'',valid_from:'',valid_to:'',condition:'',evidence:[{sentence_id:s.sentence_id,quote:s.text,occurrence:1}],mentions:[]};
   if(schema.properties.facts)parsed={facts:[{subject:'PMA',relation:'기록',object:s.text,...q}]};else if(schema.properties.events)parsed={events:[{actor:'민수',action:'기록',participants:[],object:s.text,...q}]};else parsed={entities:[{name:'PMA',kind:'project',attributes:[{relation:'기록',value:s.text,...q}]}],relationships:[]};
  }else{const e=payload.evidence[0];parsed={action:e?'answer':'abstain',answer:e?'테스트 더블: '+e.text:'테스트 더블: 근거 없음',citations:e?[{evidence_id:e.evidence_id,quote:e.text,occurrence:1}]:[]};}
  return {parsed,raw:JSON.stringify(parsed),elapsed_ms:1,usage:{prompt_tokens:1,completion_tokens:1}};
 }
}
const testOutput=path.join(__dirname,'..','.test-output');fs.mkdirSync(testOutput,{recursive:true});
function fixture(){const dir=fs.mkdtempSync(path.join(testOutput,'offline-'));fs.cpSync(path.join(__dirname,'..','datasets'),path.join(dir,'datasets'),{recursive:true});const store=new Store(dir),runtime=new FakeRuntime(),engine=new Engine(dir,store,runtime);return {dir,store,runtime,engine};}
async function finish(engine,store,run){for(let i=0;i<500;i++){const r=store.run(run.id);if(!['QUEUED','RUNNING'].includes(r.status)&&!engine.busy)return r;await sleep(10);}throw Error('offline test timed out');}
test('source spans preserve emoji, decimal, repeated substrings and role offsets',()=>{
 const text='오늘 🌿 정확도는 0.89다. 민수가 민수에게 전달했다.';const s=sentences(text);assert.equal(s.length,2);for(const x of s)assert.equal(text.slice(x.start,x.end),x.text);assert.equal(locate(s[1].text,'민수',2).start,4);
 const source={id:'SRC',revision:1,text},parsed={facts:[{subject:'민수',relation:'전달',object:'민수',polarity:'positive',status:'completed',modality:'asserted',time:'',event_time:'',speech_time:'',valid_from:'',valid_to:'',condition:'',evidence:[{sentence_id:'S2',quote:s[1].text,occurrence:1}],mentions:[{role:'recipient',sentence_id:'S2',text:'민수',occurrence:2}]}]};const v=validateNative('triples',parsed,source);assert.equal(v.valid,true);assert.equal(text.slice(v.units[0].highlights[0].start,v.units[0].highlights[0].end),'민수');parsed.facts[0].evidence[0].quote='없는 문구';assert.equal(validateNative('triples',parsed,source).valid,false);
});
test('native method schemas, prompt edits and citation validation are enforced',()=>{
 for(const [method,value]of [['triples',{facts:[]}],['events',{events:[]}],['entities',{entities:[],relationships:[]}]])assert.deepEqual(schemaIssues(value,prompts.schemas[method]),[]);
 assert.ok(schemaIssues({facts:'bad'},prompts.schemas.triples).length);assert.ok(schemaIssues({events:[],extra:true},prompts.schemas.events).length);
 const e=[{evidence_id:'E1',source_id:'A',revision:1,start:10,text:'민수와 민수'}];assert.equal(validateCitations({action:'answer',answer:'x',citations:[{evidence_id:'E1',quote:'민수',occurrence:2}]},e).citations[0].start,14);assert.equal(validateCitations({action:'answer',answer:'x',citations:[{evidence_id:'E9',quote:'민수',occurrence:1}]},e).errors.length,2);
 const cfg={method:'triples',structure_version:'v1',extraction_prompt:'extract-conservative-v1',extraction_prompt_text:'CUSTOM GUIDANCE'};assert.ok(prompts.extractMessages(cfg,{id:'A',revision:1,metadata:{}},[])[0].content.includes('CUSTOM GUIDANCE'));
 assert.equal(rrf([[{id:'a'},{id:'b'}],[{id:'b'}]])[0].id,'b');assert.throws(()=>cosine([0],[1]),/영벡터/);
});
test('actual pipeline plumbing freezes artifacts and never passes evaluator gold to models',async()=>{
 const {store,runtime,engine}=fixture();const first=await finish(engine,store,await engine.create({config:{route:'S0'},question_ids:['F02-Q1','F02-Q2']}));assert.equal(first.status,'COMPLETED');assert.equal(first.results.length,2);assert.equal(first.results[0].status,'PENDING_REVIEW');const ext=first.results[0].stages.extraction.artifact_id;assert.equal(ext,first.results[1].stages.extraction.artifact_id);
 const chatCount=runtime.calls.filter(c=>c.kind==='chat').length;assert.equal(chatCount,3);for(const call of runtime.calls.filter(c=>c.kind==='chat')){const content=call.messages.map(m=>m.content).join(' ');for(const forbidden of ['"gold":','"required_claims":','"reference_answer":','"expected_state":'])assert.ok(!content.includes(forbidden));}
 const second=await finish(engine,store,await engine.create({stage:'retrieve',config:{route:'S0',method:'entities'},question_ids:['F02-Q1'],artifacts:[ext]}));assert.equal(second.results[0].status,'PENDING_REVIEW');assert.equal(second.results[0].stages.extraction.reused,true);assert.equal(runtime.calls.filter(c=>c.kind==='chat').length,chatCount);
 const ret=second.results[0].stages.retrieval.artifact_id;const third=await finish(engine,store,await engine.create({stage:'answer',config:{answer_prompt_text:'CUSTOM ANSWER'},question_ids:['F02-Q1'],artifacts:[ret]}));assert.equal(third.results[0].stages.answer.retrieval_artifact_id,ret);assert.ok(runtime.calls.filter(c=>c.kind==='chat').at(-1).messages[0].content.includes('CUSTOM ANSWER'));
 const mismatch=await finish(engine,store,await engine.create({stage:'retrieve',config:{route:'S0'},question_ids:['F03-Q1'],artifacts:[ext]}));assert.equal(mismatch.results[0].status,'ERROR');assert.match(mismatch.results[0].error,/산출물/);store.db.close();
});
test('owner, delete and non-consent fixtures exclude raw inputs before model calls',async()=>{
 const {store,runtime,engine}=fixture();const run=await finish(engine,store,await engine.create({config:{route:'S0'},question_ids:['F30-Q1','F28-Q2','F29-Q2']}));assert.equal(run.status,'COMPLETED');assert.deepEqual(run.results[0].accessible_source_ids,['F30-A']);for(const r of run.results.slice(1)){assert.deepEqual(r.accessible_source_ids,[]);assert.equal(r.stages.answer.citations.length,0);assert.equal(r.stages.answer.action,'abstain');}
 const calls=runtime.calls.filter(c=>c.kind==='chat').map(c=>c.messages[1].content).join('\n');assert.ok(!calls.includes('하린'));assert.ok(!calls.includes('TEST-ONLY-582'));assert.ok(!calls.includes('합성차-882'));store.db.close();
});
test('concurrent start is rejected and lexical search handles short Korean names and C++',async()=>{
 const {store,engine}=fixture();const attempts=await Promise.allSettled([engine.create({stage:'extract',question_ids:['F01-Q1']}),engine.create({stage:'extract',question_ids:['F01-Q1']})]);assert.equal(attempts.filter(a=>a.status==='fulfilled').length,1);await finish(engine,store,attempts.find(a=>a.status==='fulfilled').value);
 assert.equal(engine.lexical([{id:'A',text:'민수는 C++ 개발자다.'},{id:'B',text:'지연은 교사다.'}],'민수')[0].id,'A');assert.equal(engine.lexical([{id:'A',text:'민수는 C++ 개발자다.'}],'C++')[0].id,'A');store.db.close();
});
test('GET initialization does not start models; token and Origin protect mutations',async()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'memory-lab-http-'));fs.cpSync(path.join(__dirname,'..','datasets'),path.join(dir,'datasets'),{recursive:true});const runtime=new FakeRuntime(),api=createApi(dir,{runtime});const server=http.createServer((req,res)=>api.handle(req,res,new URL(req.url,'http://'+req.headers.host)));await new Promise(r=>server.listen(0,'127.0.0.1',r));const base='http://127.0.0.1:'+server.address().port;
 try{for(const route of ['/bootstrap','/dataset','/runs','/status']){const r=await fetch(base+'/api/baseline'+route);assert.equal(r.status,200);}assert.equal(runtime.calls.length,0);
  assert.equal((await fetch(base+'/api/baseline/runs',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})).status,403);
  const {token}=await (await fetch(base+'/api/baseline/bootstrap')).json();assert.equal((await fetch(base+'/api/baseline/runs',{method:'POST',headers:{'Content-Type':'application/json','X-Memory-Lab-Token':token,Origin:'https://example.invalid'},body:'{}'})).status,403);assert.equal(runtime.calls.length,0);
 }finally{await new Promise(r=>server.close(r));await api.close();}
});
test('ranking extension preserves old data and has 34 eligible sources with separate-project distractors',async()=>{
 const {engine,store}=fixture(),base=await engine.dataset('pma-dev-v0.1.0'),rank=await engine.dataset('pma-dev-v0.2.0');assert.equal(base.d.questions.questions.length,114);assert.equal(rank.d.questions.questions.length,117);assert.deepEqual(rank.d.sources.records.slice(0,59),base.d.sources.records);const c=rank.d.contexts.contexts.find(c=>c.id==='F37-RANKING');assert.equal(c.expected_state.accessible_sources.length,34);assert.equal(rank.d.sources.records.filter(s=>s.family_id==='F37'&&s.id.includes('-N')).length,32);store.db.close();
});
test('retrieval evidence and progress are persisted while answer generation is still running',async()=>{
 const {engine,store,runtime}=fixture();let release;const gate=new Promise(r=>release=r),chat=runtime.chat.bind(runtime);
 runtime.chat=async(...args)=>{if(JSON.parse(args[0][1].content).evidence)await gate;return chat(...args);};
 const created=await engine.create({config:{route:'S0'},question_ids:['F01-Q1']});let partial;
 try{for(let i=0;i<300;i++){partial=store.run(created.id);if(partial.active_result?.stage_progress.answer==='RUNNING')break;await sleep(10);}
  assert.equal(partial.status,'RUNNING');assert.equal(partial.results.length,0);assert.equal(partial.active_result.stage_progress.retrieval,'COMPLETED');
  const retrieved=partial.active_result.stages.retrieval;assert.ok(retrieved.vector_candidates.length);assert.ok(retrieved.lexical_candidates.length);assert.equal(retrieved.source_snapshots[0].id,'F01-A');
  for(const hit of [...retrieved.lexical_candidates,...retrieved.vector_candidates])assert.ok(retrieved.index_units.some(u=>u.id===hit.id));
  assert.ok(partial.events.some(e=>e.stage==='document_embedding'));assert.equal(partial.progress_detail.total,1);
 }finally{release();}const result=await finish(engine,store,created);assert.equal(result.progress_detail.processed,1);assert.equal(result.active_result,null);assert.equal(result.progress_detail.stage,'finished');store.db.close();
});
test('process termination endpoint is available while model setup is running',async()=>{
 const {dir,store,runtime}=fixture();let entered=false;runtime.ensure=async(role,id,signal)=>{entered=true;await new Promise((_,reject)=>signal.addEventListener('abort',()=>reject(Error('setup cancelled')),{once:true}));};runtime.forceStop=async()=>({verified:true,remaining:[],terminated_pids:[],checked_at:new Date().toISOString()});runtime.inspectProcesses=async()=>({verified:true,remaining:[],terminated_pids:[],checked_at:new Date().toISOString()});
 const api=createApi(dir,{store,runtime}),server=http.createServer((req,res)=>api.handle(req,res,new URL(req.url,'http://'+req.headers.host)));await new Promise(r=>server.listen(0,'127.0.0.1',r));const base='http://127.0.0.1:'+server.address().port+'/api/baseline';
 try{const {token}=await(await fetch(base+'/bootstrap')).json();const post=(route)=>fetch(base+route,{method:'POST',headers:{'Content-Type':'application/json','X-Memory-Lab-Token':token},body:'{}'});assert.equal((await post('/runtime/start')).status,202);for(let i=0;i<30&&!entered;i++)await sleep(10);assert.ok(entered);const result=await post('/runtime/terminate');assert.equal(result.status,200);assert.deepEqual((await result.json()).report.remaining,[]);assert.equal((await(await fetch(base+'/status')).json()).setup.status,'CANCELLED');assert.equal((await post('/runtime/processes')).status,200);
 }finally{await new Promise(r=>server.close(r));await api.close();}
});
