const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {Engine}=require('../local/engine.cjs'),{Store}=require('../local/store.cjs'),{hash}=require('../local/core.cjs'),{BATCH_VERSION}=require('../local/summary-batch.cjs');
const root=path.resolve(__dirname,'..'),pause=ms=>new Promise(r=>setTimeout(r,ms));
class Runtime{
 constructor(){this.version='BATCH_OFFLINE';this.events=[];this.states={generation:{status:'stopped'},embedding:{status:'stopped'}};}
 status(){return {version:this.version,states:this.states,models:[]};}async ensure(role,id){this.states[role]={status:'ready',model_id:id};}async stopAll(){}
 async tokenize(text){return Math.ceil(text.length/3);}
 async embed(text,query,signal){signal?.throwIfAborted();this.events.push({kind:query?'query_embedding':'summary_embedding',text});return [1,1+text.length/100,2];}
 async chat(messages,schema,config,signal){signal?.throwIfAborted();const p=JSON.parse(messages[1].content);let parsed;if(schema.properties.summary){this.events.push({kind:'summary',source:p.source_id,revision:p.revision,messages});parsed={summary:`요약 ${p.source_id} v${p.revision}: 예정된 회의의 예산은 미확정이다.`};}else{this.events.push({kind:'answer',question:p.question,messages});const e=p.evidence[0];parsed={action:e?'answer':'abstain',answer:e?e.text:'요약 근거 없음',citations:e?[{evidence_id:e.evidence_id,quote:e.text,occurrence:1}]:[]};}return {parsed,raw:JSON.stringify(parsed),elapsed_ms:1,usage:{prompt_tokens:1,completion_tokens:1}};}
}
async function fixture(ds){const dir=fs.mkdtempSync(path.join(os.tmpdir(),'summary-batch-')),store=new Store(dir),runtime=new Runtime(),engine=new Engine(dir,store,runtime);if(ds)engine.dataset=async()=>ds;else{const loader=new Engine(root,{recover(){}},runtime);engine.dataset=id=>loader.dataset(id);}return {dir,store,runtime,engine};}
async function finish(f,run){for(let i=0;i<1200;i++){if(!f.engine.busy)return f.store.run(run.id);await pause(5);}throw Error('batch timed out');}
async function waitFor(check){for(let i=0;i<300;i++){if(check())return;await pause(5);}throw Error('condition timed out');}
const ids=['F02-Q1','F01-Q1','F02-Q2'];

test('all distinct sources finish generation and storage before the first query; questions retain their order',async()=>{
 const f=await fixture();let release;try{
  let pending=false;const gate=new Promise(r=>release=r),embed=f.runtime.embed.bind(f.runtime);f.runtime.embed=async(text,query,signal)=>{if(!query&&text.includes('F01-A')){pending=true;await gate;}return embed(text,query,signal);};
  const events=[],retrieve=f.engine.retrieve.bind(f.engine),answer=f.engine.answer.bind(f.engine),save=f.engine.summary.save.bind(f.engine.summary);f.engine.summary.save=async(...args)=>{const row=await save(...args);events.push('saved:'+row.source_id);return row;};
  f.engine.retrieve=async(run,ds,q,...args)=>{assert.equal(run.summary_batch.status,'COMPLETED');assert.equal(run.summary_batch.completed_sources,2);assert.equal(run.summary_batch.prepared_contexts,2);assert.ok(run.summary_batch.context_artifact_ids.every(id=>f.store.readArtifact(id).extraction_state==='COMPLETED'));events.push('search:'+q.id);return retrieve(run,ds,q,...args);};
  f.engine.answer=async(run,ds,q,...args)=>{events.push('answer:'+q.id);return answer(run,ds,q,...args);};
  const created=await f.engine.create({config:{route:'M0',summary_force:true},question_ids:ids});await waitFor(()=>pending);const active=f.store.run(created.id);assert.equal(active.results.length,0);assert.equal(active.active_result,undefined);assert.equal(active.summary_batch.completed_sources,1);assert.equal(active.summary_batch.status,'RUNNING');assert.equal(f.runtime.events.filter(e=>['answer','query_embedding'].includes(e.kind)).length,0);assert.equal(f.engine.summary.list('dataset:'+active.dataset_fingerprint,'user-a').length,1);
  release();const run=await finish(f,created);assert.equal(run.status,'COMPLETED');assert.deepEqual(events,['saved:F02-A','saved:F01-A','search:F02-Q1','answer:F02-Q1','search:F01-Q1','answer:F01-Q1','search:F02-Q2','answer:F02-Q2']);assert.equal(f.runtime.events.filter(e=>e.kind==='summary').length,2);
  assert.equal(run.config.summary_execution_order,BATCH_VERSION);assert.equal(run.summary_batch.generated_sources,2);assert.ok(run.summary_batch.elapsed_ms>=0);assert.deepEqual(run.results.map(r=>r.question_id),ids);for(const r of run.results){assert.equal(r.stages.extraction.reuse_reason,'summary_batch');assert.equal(r.stage_timings.extraction.reused,true);assert.equal(r.stages.extraction.summary_batch_artifact_id,run.summary_batch.artifact_id);assert.ok(r.stages.retrieval.index_units.every(u=>u.origin==='summary'));}
  assert.ok(Date.parse(run.summary_batch.finished_at)<=Date.parse(run.results[0].started_at));
 }finally{release?.();if(f.engine.busy)await waitFor(()=>!f.engine.busy);f.store.db.close();}
});
test('a late summary failure blocks every question and preserves completed source summaries for retry',async()=>{
 const f=await fixture();try{const chat=f.runtime.chat.bind(f.runtime);f.runtime.chat=async(messages,...args)=>{if(JSON.parse(messages[1].content).source_id==='F01-A')throw Error('late summary failure');return chat(messages,...args);};
  const run=await finish(f,await f.engine.create({config:{route:'M0'},question_ids:ids}));assert.equal(run.status,'ERROR');assert.equal(run.error_stage,'summary_prepare');assert.equal(run.summary_batch.status,'ERROR');assert.equal(run.summary_batch.completed_sources,1);assert.equal(run.summary_batch.active_source_id,'F01-A');assert.equal(run.results.length,0);assert.equal(f.runtime.events.filter(e=>['answer','query_embedding'].includes(e.kind)).length,0);
  f.runtime.chat=chat;const retried=await finish(f,await f.engine.create({config:{route:'M0'},question_ids:ids}));assert.equal(retried.status,'COMPLETED');assert.equal(retried.summary_batch.reused_sources,1);assert.equal(retried.summary_batch.generated_sources,1);
 }finally{f.store.db.close();}
});
test('cancelling shared summarization never starts a question or marks the batch complete',async()=>{
 const f=await fixture();try{const chat=f.runtime.chat.bind(f.runtime);let pending=false;f.runtime.chat=async(messages,schema,c,signal)=>{if(JSON.parse(messages[1].content).source_id==='F01-A'){pending=true;return new Promise((_,reject)=>signal.addEventListener('abort',()=>reject(Error('summary cancelled')),{once:true}));}return chat(messages,schema,c,signal);};
  const created=await f.engine.create({config:{route:'M0'},question_ids:ids});await waitFor(()=>pending);f.engine.cancel(created.id);const run=await finish(f,created);assert.equal(run.status,'CANCELLED');assert.equal(run.summary_batch.status,'CANCELLED');assert.equal(run.summary_batch.completed_sources,1);assert.equal(run.results.length,0);assert.equal(f.runtime.events.filter(e=>['answer','query_embedding'].includes(e.kind)).length,0);
 }finally{f.store.db.close();}
});
test('extract-only prepares all sources once, and frozen search/answer do not generate summaries',async()=>{
 const f=await fixture();try{const run=await finish(f,await f.engine.create({config:{route:'M0'},stage:'extract',question_ids:ids}));assert.equal(run.status,'COMPLETED');assert.equal(run.summary_batch.total_sources,2);assert.equal(f.runtime.events.filter(e=>e.kind==='summary').length,2);assert.equal(f.runtime.events.filter(e=>e.kind==='answer').length,0);assert.ok(run.results.every(r=>!r.stages.retrieval&&!r.stages.answer));
  const artifacts=[...new Set(run.results.map(r=>r.stages.extraction.artifact_id))];const search=await finish(f,await f.engine.create({config:{route:'M0'},stage:'retrieve',question_ids:['F02-Q1','F01-Q1'],artifacts}));assert.equal(search.status,'COMPLETED');assert.equal(search.summary_batch,undefined);assert.equal(f.runtime.events.filter(e=>e.kind==='summary').length,2);
  const answered=await finish(f,await f.engine.create({config:{route:'M0'},stage:'answer',question_ids:['F02-Q1'],artifacts:[search.results[0].stages.retrieval.artifact_id]}));assert.equal(answered.status,'COMPLETED');assert.equal(f.runtime.events.filter(e=>e.kind==='summary').length,2);assert.equal(f.runtime.events.filter(e=>e.kind==='answer').length,1);
 }finally{f.store.db.close();}
});
test('empty, deleted, foreign-owner and non-consent scope stays excluded during shared preparation',async()=>{
 const f=await fixture();try{const run=await finish(f,await f.engine.create({config:{route:'M0'},question_ids:['F30-Q1','F28-Q2','F29-Q2']}));assert.equal(run.status,'COMPLETED');assert.equal(run.summary_batch.total_sources,1);assert.deepEqual(f.runtime.events.filter(e=>e.kind==='summary').map(e=>e.source),['F30-A']);for(const r of run.results.slice(1)){assert.deepEqual(r.accessible_source_ids,[]);assert.equal(r.stages.retrieval.evidence.length,0);assert.equal(r.stages.answer.action,'abstain');}
  const empty=await finish(f,await f.engine.create({config:{route:'M0'},question_ids:['F28-Q2','F29-Q2']}));assert.equal(empty.summary_batch.status,'COMPLETED');assert.equal(empty.summary_batch.total_sources,0);assert.equal(empty.summary_batch.prepared_contexts,2);
 }finally{f.store.db.close();}
});
test('preparing old and new revisions together never exposes a future revision to an earlier question',async()=>{
 const source=revision=>({id:'SAME',revision,text:'원본만의 문구 '+revision,metadata:{owner_id:'local-user',created_at:'2026-11-05T00:00:00Z'},gold:{facts:[]}}),sources=[source(1),source(2)];
 const contexts=[1,2].map(revision=>({id:'C'+revision,actor_id:'local-user',now:'2026-11-05T00:00:00Z',conversation:[],required_observations:[],expected_state:{accessible_sources:[{source_id:'SAME',revision}]}})),questions=[1,2].map(n=>({id:'Q'+n,context_id:'C'+n,text:'질문 '+n,gold:{required_claims:[],forbidden_claims:[],evidence_groups:[],expected_action:'answer',reference_answer:''}}));
 const ds={fingerprint:hash('versions'),d:{sources:{records:sources},contexts:{contexts},questions:{questions},manifest:{}},lib:{materialize:c=>({accessible:sources.filter(s=>c.expected_state.accessible_sources.some(r=>r.source_id===s.id&&r.revision===s.revision)),trace:[]})}};
 const f=await fixture(ds);try{const run=await finish(f,await f.engine.create({config:{route:'M0'},question_ids:['Q1','Q2']}));assert.equal(run.status,'COMPLETED');assert.equal(run.summary_batch.total_sources,2);for(const [i,r]of run.results.entries()){assert.ok(r.stages.retrieval.index_units.every(u=>u.revision===i+1));assert.ok(r.stages.answer.evidence_used.every(e=>e.revision===i+1));}assert.equal(run.results[0].stages.answer.answer.includes('v2'),false);}
 finally{f.store.db.close();}
});
