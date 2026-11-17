const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'..'),{Store}=require('../local/store.cjs'),{Engine}=require('../local/engine.cjs'),{buildReview}=require('../local/review.cjs');
class OfflineRuntime{
 constructor(){this.version='OFFLINE-FULL';this.calls=[];this.states={generation:{status:'stopped'},embedding:{status:'ready'}};}
 status(){return {version:this.version,states:this.states,models:[]};}
 async ensure(role,id){this.calls.push({kind:'ensure',role});this.states[role]={status:'ready',model_id:id};}
 async stop(role){this.calls.push({kind:'stop',role});this.states[role]={status:'stopped'};}
 async tokenize(text){this.calls.push({kind:'tokenize'});return this.tokenizer?this.tokenizer(text):Math.ceil(text.length/3);}
 async countChatTokens(messages){this.calls.push({kind:'countChatTokens'});return this.tokenize(messages.map(m=>m.content).join('\n'));}
 async embed(text){this.calls.push({kind:'embed',text});return [1,text.length/100,1];}
 async chat(messages){this.calls.push({kind:'chat',messages});const p=JSON.parse(messages[1].content),e=p.evidence[0],parsed={action:e?'answer':'abstain',answer:e?'근거 확인':'근거 없음',citations:e?[{evidence_id:e.evidence_id,quote:e.text,occurrence:1}]:[]};return {parsed,raw:JSON.stringify(parsed),usage:{prompt_tokens:100,completion_tokens:20},input_tokens:84,elapsed_ms:1};}
}
function fixture(){const dir=fs.mkdtempSync(path.join(os.tmpdir(),'pma-full-'));fs.cpSync(path.join(root,'datasets'),path.join(dir,'datasets'),{recursive:true});const store=new Store(dir),runtime=new OfflineRuntime(),engine=new Engine(dir,store,runtime);return {dir,store,runtime,engine};}
async function execute(f,input){const created=await f.engine.create(input);for(let i=0;i<500;i++){const r=f.store.run(created.id);if(!f.engine.busy&&!['RUNNING','QUEUED'].includes(r.status))return r;await new Promise(resolve=>setTimeout(resolve,5));}throw Error('Offline execution timed out');}
const natural={dataset:'pma-context-v1.0.0',dataset_profile:'all'};

test('Full is a separate versioned route while legacy R0 and the Chunk alias remain supported',async()=>{
 const f=fixture();try{assert.equal(f.engine.config({route:'R0-Chunk'}).route,'R0');assert.equal(f.engine.config({route:'R0'}).raw_delivery_version,undefined);assert.equal(f.engine.config({route:'R0-Full'}).raw_delivery_version,'accessible-full-originals-v1');await assert.rejects(()=>f.engine.create({stage:'extract',config:{route:'R0-Full'},question_ids:['F01-Q1']}),/구조화/);assert.equal(f.runtime.calls.length,0);}finally{f.store.db.close();}
});

test('Full sends all accessible originals without embedding, ranking, splitting, gold or extraction',async()=>{
 const f=fixture();try{
  const run=await execute(f,{config:{...natural,route:'R0-Full'},question_ids:['NC-09-Q1']}),r=run.results[0],retr=r.stages.retrieval,answer=r.stages.answer;
  assert.equal(r.status,'PENDING_REVIEW');assert.equal(r.stage_progress.extraction,'SKIPPED');assert.equal(r.stages.extraction,undefined);
  assert.equal(f.runtime.calls.filter(c=>c.kind==='embed').length,0);assert.ok(f.runtime.calls.filter(c=>c.kind==='ensure').every(c=>c.role==='generation'));assert.equal(f.runtime.states.embedding.status,'stopped');
  assert.equal(retr.source_snapshots.length,2);assert.equal(retr.evidence.length,2);assert.equal(retr.index_units.length,0);assert.equal(retr.metrics.mrr,null);assert.equal(retr.metrics.source_group_recall,null);
  for(let i=0;i<retr.evidence.length;i++){const e=retr.evidence[i],s=retr.source_snapshots[i];assert.equal(e.text,s.text);assert.equal(e.start,0);assert.equal(e.end,s.text.length);assert.equal(e.source_id,s.id);}
  const p=JSON.parse(f.runtime.calls.find(c=>c.kind==='chat').messages[1].content);assert.deepEqual(p.evidence,answer.evidence_used);assert.equal(JSON.stringify(p).includes('any_of_fact_ids'),false);assert.equal(JSON.stringify(p).includes('required_claims'),false);assert.deepEqual(answer.omitted_by_token_budget,[]);
  assert.ok(run.resources.samples>0);const ds=await f.engine.dataset(natural.dataset),review=buildReview(run,f.store,ds,'retrieval');assert.equal(review.targets[0].checks.find(c=>c.code==='SEARCH.RANK').status,'NOT_MEASURED');assert.equal(buildReview(run,f.store,ds,'extraction').targets.length,0);
 }finally{f.store.db.close();}
});

test('Full preserves owner, deletion and non-consent fixture boundaries, including empty memory',async()=>{
 const f=fixture();try{const run=await execute(f,{config:{dataset:'pma-dev-v0.2.0',route:'R0-Full'},question_ids:['F30-Q1','F28-Q2','F29-Q2']});assert.deepEqual(run.results[0].accessible_source_ids,['F30-A']);for(const r of run.results.slice(1)){assert.deepEqual(r.stages.retrieval.evidence,[]);assert.equal(r.stages.answer.action,'abstain');assert.deepEqual(r.stages.answer.citations,[]);}assert.equal(f.runtime.calls.filter(c=>c.kind==='embed').length,0);}finally{f.store.db.close();}
});

test('a full-request overflow preserves the full candidate but never creates a partial answer or fake pass',async()=>{
 const f=fixture();f.runtime.tokenizer=text=>text.startsWith('[')?2049:5633;try{
  const run=await execute(f,{config:{...natural,route:'R0-Full'},question_ids:['NC-01-Q1']}),r=run.results[0];
  assert.equal(r.status,'NOT_APPLICABLE');assert.equal(r.error_code,'FULL.BUDGET');assert.equal(r.stages.answer,undefined);assert.equal(f.runtime.calls.filter(c=>c.kind==='chat'||c.kind==='embed').length,0);
  assert.equal(r.stages.retrieval.delivery.budget.evidence_tokens,2049);assert.deepEqual(r.stages.retrieval.evidence,[]);assert.equal(r.stages.retrieval.source_snapshots[0].text.length,1251);
  const summary=f.store.list()[0].summary;assert.equal(summary.result_counts.not_applicable,1);assert.equal(summary.result_counts.needs_review,0);assert.equal(summary.result_counts.error,0);assert.equal(summary.unreviewed,0);
  const review=buildReview(run,f.store,await f.engine.dataset(natural.dataset),'retrieval');assert.equal(review.targets[0].status,'NOT_APPLICABLE');assert.equal(review.targets[0].has_output,false);assert.equal(review.summary.pending,0);
 }finally{f.store.db.close();}
});

test('the full-request input limit is checked independently of the evidence limit',async()=>{
 const f=fixture();f.runtime.tokenizer=text=>text.startsWith('[')?100:5633;try{const run=await execute(f,{config:{...natural,route:'R0-Full'},question_ids:['NC-01-Q1']}),r=run.results[0];assert.equal(r.status,'NOT_APPLICABLE');assert.equal(r.token_budget.input_limit,5632);assert.equal(r.token_budget.input_tokens_estimate,5633);assert.equal(r.token_budget.evidence_tokens,100);assert.equal(f.runtime.calls.filter(c=>c.kind==='chat').length,0);}finally{f.store.db.close();}
});

test('frozen Full evidence is reusable and current edited prompts are budget-checked without modifying the artifact',async()=>{
 const f=fixture();try{
  const initial=await execute(f,{stage:'retrieve',config:{...natural,route:'R0-Full'},question_ids:['NC-01-Q1']}),artifact=initial.results[0].stages.retrieval.artifact_id,before=JSON.stringify(f.store.readArtifact(artifact));assert.equal(f.runtime.calls.filter(c=>c.kind==='chat').length,0);
  const answered=await execute(f,{stage:'answer',config:{...natural,route:'R0-Full'},question_ids:['NC-01-Q1'],artifacts:[artifact]});assert.equal(answered.results[0].status,'PENDING_REVIEW');assert.equal(answered.results[0].stages.retrieval.reused,true);
  const chatCount=f.runtime.calls.filter(c=>c.kind==='chat').length;
  const tooLong=await execute(f,{stage:'answer',config:{...natural,route:'R0-Full',answer_prompt_text:'x'.repeat(19000)},question_ids:['NC-01-Q1'],artifacts:[artifact]});assert.equal(tooLong.results[0].status,'NOT_APPLICABLE');assert.equal(f.runtime.calls.filter(c=>c.kind==='chat').length,chatCount);assert.equal(JSON.stringify(f.store.readArtifact(artifact)),before);
 }finally{f.store.db.close();}
});

test('a Chunk retrieval cannot masquerade as Full in answer-only execution',async()=>{
 const f=fixture();try{
  const chunk=await execute(f,{stage:'retrieve',config:{...natural,route:'R0'},question_ids:['NC-01-Q1']}),artifact=chunk.results[0].stages.retrieval.artifact_id;
  assert.equal(chunk.results[0].stages.retrieval.index_units.length,2);
  const run=await execute(f,{stage:'answer',config:{...natural,route:'R0-Full'},question_ids:['NC-01-Q1'],artifacts:[artifact]});assert.equal(run.results[0].status,'ERROR');assert.match(run.results[0].error,/Full 산출물/);assert.equal(f.runtime.calls.filter(c=>c.kind==='chat').length,0);
 }finally{f.store.db.close();}
});

test('existing Chunk still uses embedding and the original 700/100 split with separate ranking metrics',async()=>{
 const f=fixture();try{const run=await execute(f,{config:{...natural,route:'R0'},question_ids:['NC-01-Q1']}),r=run.results[0];assert.equal(r.status,'PENDING_REVIEW');assert.ok(f.runtime.calls.some(c=>c.kind==='embed'));assert.deepEqual(r.stages.retrieval.index_units.map(c=>[c.start,c.end]),[[0,664],[564,1251]]);assert.equal(r.stages.retrieval.delivery,undefined);assert.ok(Number.isFinite(r.stages.retrieval.metrics.mrr));assert.equal(r.stage_progress.extraction,'SKIPPED');}finally{f.store.db.close();}
});

test('Full UI shows complete-source scope and budget overflow without search-score claims',async()=>{
 const elements=new Map(),element=s=>{if(!elements.has(s))elements.set(s,{value:'',innerHTML:'',textContent:'',classList:{add(){},toggle(){},remove(){}},addEventListener(){},setAttribute(){},insertAdjacentHTML(position,html){this.innerHTML=html+this.innerHTML;}});return elements.get(s);};
 const context=vm.createContext({console,setTimeout,clearTimeout,Map,Set,document:{querySelector:element,querySelectorAll:()=>[],addEventListener(){},body:{classList:{toggle(){}}}},MemoryTiming:{format:()=>'',isActive:()=>false},localStorage:{getItem(){},setItem(){}}});
 vm.runInContext(fs.readFileSync(path.join(root,'baseline.js'),'utf8').replace('\ninitialize();','\n').replace('\ninitializeSelectionGuide();','\n'),context);
 const data={config:{route:'R0-Full'},elapsed_ms:1,source_snapshots:[{id:'A',revision:1,text:'원문 🌿 전체'}],evidence:[{source_id:'A',revision:1,start:0,end:8,text:'원문 🌿 전체'}],delivery:{candidate_sources:1,candidate_characters:8,status:'ELIGIBLE',budget:{eligible:true,evidence_tokens:15,evidence_limit:2048,input_tokens_estimate:100,input_limit:5632}},warning:'검색 생략'};context.saved=data;
 const html=vm.runInContext('searchHTML(saved)',context);assert.match(html,/검색·임베딩 생략/);assert.match(html,/검색 Recall·MRR·검색 순위: 해당 없음/);assert.match(html,/<mark/);assert.doesNotMatch(html,/BM25|코사인/);
 data.delivery.budget.eligible=false;data.delivery.status='BUDGET_EXCEEDED';data.evidence=[];const rejected=vm.runInContext('searchHTML(saved)',context);assert.match(rejected,/답변 모델에는 보내지 않았습니다/);assert.match(rejected,/비교 제외/);
 const scope=vm.runInContext("providedScopeHTML(saved,{evidence_used:[{source_id:'A',revision:1,start:0,end:2,text:'원문'}]})",context);assert.match(scope,/실제 제공한/);assert.match(scope,/포함 2\/8자/);
 element('#compare-question').value='Q1';context.pair={a:{dataset_fingerprint:'same',config:{route:'R0'},results:[{question_id:'Q1',context_id:'C',status:'PENDING_REVIEW',stages:{}}]},b:{dataset_fingerprint:'same',config:{route:'R0-Full'},results:[{question_id:'Q1',context_id:'C',status:'NOT_APPLICABLE',stages:{}}]}};
 vm.runInContext('compareRuns=pair',context);await vm.runInContext('renderComparison()',context);assert.match(element('#compare-body').innerHTML,/공통 적용 가능 0개/);assert.match(element('#compare-body').innerHTML,/전체 제공 예산 제외 1개/);
 element('#route').value='R0-Full';element('#stage').value='end_to_end';element('#local-model').value='qwen35-4b-q4';
 context.ready={runtime:{states:{generation:{status:'ready',model_id:'qwen35-4b-q4'},embedding:{status:'stopped'}},models:[{id:'qwen35-4b-q4',present:true}]},busy:null};
 vm.runInContext('showRuntime(ready)',context);assert.equal(element('#runtime-state').textContent,'서버 준비됨');assert.match(element('#runtime-description').textContent,/임베딩 미사용/);
 context.ready.busy='ACTIVE';vm.runInContext('showRuntime(ready);data={};chosenIds=()=>["Q1"];renderSelectionGuide=()=>{};renderStageHelp()',context);assert.equal(element('#run').disabled,true);
 context.ready.busy=null;element('#stage').value='extract';vm.runInContext('showRuntime(ready);renderStageHelp()',context);assert.equal(element('#run').disabled,true);


});
