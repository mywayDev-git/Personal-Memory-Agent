'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const MA=require('../local/multi-anchor.cjs'),{Engine}=require('../local/engine.cjs');
const retrieve=require('../local/structured-retrieve.cjs').retrieve;
const compound=require('../local/compound-search.cjs'),{answerMessages}=require('../local/prompts.cjs');
function record(id,text,entities=[],relation=null){
 const summary_id='summary-'+id,unit_id=summary_id+':U1',owner_id='user-a';
 const source={id,revision:1,text,metadata:{owner_id,created_at:'2026-11-16T00:00:00Z'}};
 const proof=quote=>({start:text.indexOf(quote),end:text.indexOf(quote)+quote.length,quote});
 const unit={id:unit_id,source_id:id,revision:1,source_revision:1,owner_id,summary_id,start:0,end:text.length,text,search_terms:[],timestamp:source.metadata.created_at,
  entities:entities.map(([name,type],i)=>({entity_id:id+'-E'+i,name,type,aliases:[],evidence:proof(name)})),
  relations:relation?[{relation_id:id+'-R',subject:relation[0],predicate:relation[1],object:relation[2],status:'not_applicable',polarity:'positive',event_time:null,valid_time:{from:null,to:null},evidence:proof(text)}]:[]};
 const index={index_id:'index-'+id,source_id:id,revision:1,owner_id,units:[unit]};
 return {source,unit,index};
}
function fixture(records){
 const sources=records.map(r=>r.source),indexes=records.map(r=>r.index),units=records.map(r=>r.unit),events=[];
 const engine={lexical:Engine.prototype.lexical,async vector(text){events.push(text);return {vector:text.includes('축제')?[1,0]:[0,1]};},
  summary:{units:()=>units,assertRetrieval(data,allowed){assert.deepEqual(data.source_refs,allowed.map(s=>({source_id:s.id,revision:s.revision})));for(const e of data.evidence){const s=allowed.find(s=>s.id===e.source_id&&s.revision===e.revision);assert.ok(s);assert.equal(s.text.slice(e.start,e.end),e.text);}}},
  structured:{indexes:()=>indexes,lexical(items,_indexes,q,limit){return Engine.prototype.lexical(items,q).slice(0,limit);}},
  update(){},retrievalMetrics(){return {};},store:{artifact(type,data){return 'TEST-'+type;}}};
 const config=Engine.prototype.config.call({code_hash:'test'},{route:'G2',top_k:5});
 return {sources,indexes,units,engine,events,config};
}
const preference=()=>record('preference','나는 조용한 공간을 선호한다.',[['조용한 공간','other']],['나','선호','조용한 공간']);
const role=()=>record('role','회사 민수는 알파 프로젝트 담당자다.',[['민수','person'],['알파 프로젝트','project']],['민수','담당','알파 프로젝트']);
const signal=()=>new AbortController().signal;
async function run(f,question,overrides={}){
 return retrieve(f.engine,{config:{...f.config,...overrides}},{d:{}},{id:'Q',text:question},{},f.sources,{records:[],structured_indexes:[]},signal(),false);
}
test('G2 is a separate extractive route, keeps G1 modes and rejects incompatible settings',()=>{
 const c=Engine.prototype.config.call({code_hash:'fixed'},{route:'G2'});assert.equal(c.route,'G2');assert.equal(c.summary_mode,'extractive-v1');assert.equal(c.multi_anchor_version,MA.VERSION);
 for(const mode of ['existing','linked-v2','claim-v1'])assert.equal(Engine.prototype.config.call({code_hash:'fixed'},{route:'G1',event_graph_mode:mode}).route,'G1');
 assert.throws(()=>Engine.prototype.config.call({code_hash:'fixed'},{route:'G2',event_graph_mode:'linked-v2'}));
 assert.throws(()=>Engine.prototype.config.call({code_hash:'fixed'},{route:'G2',excerpt_only:true}));
});
test('G2 reuses matching G1/M1 extraction settings, never a frozen search or changed metadata',()=>{
 const config=Engine.prototype.config.call({code_hash:'fixed'},{route:'G2'});
 for(const route of ['G1','M1']){
  const previous=Engine.prototype.config.call({code_hash:'fixed'},{route,summary_mode:'extractive-v1'}),artifact={kind:'summary-only-v1',type:'extraction',context_id:'C',dataset_fingerprint:'F',config:previous,structured_version:require('../local/metadata-schema.cjs').VERSION,structured_indexes:[]};
  assert.equal(MA.compatibleExtraction(config,artifact),true);
  const engine={config,store:{readArtifact:()=>artifact}},run={config,input_artifacts:['A']};
  assert.equal(Engine.prototype.findArtifact.call(engine,run,'extraction','C',null,'F').artifact_id,'A');
  const wrong=structuredClone(artifact);wrong.config.metadata_settings_hash='changed';assert.equal(MA.compatibleExtraction(config,wrong),false);
  engine.store.readArtifact=()=>({...artifact,type:'retrieval',question_id:'Q'});
  assert.throws(()=>Engine.prototype.findArtifact.call(engine,run,'retrieval','C','Q','F'),/같은 검색 경로/);
 }
});
test('event-free preferences become grounded independent Claims without a new generation call',async()=>{
 const f=fixture([preference()]);const result=await run(f,'조용한 공간 선호는?');
 assert.equal(result.multi_anchor_search.eligible_claim_count,1);assert.equal(result.multi_anchor_search.event_gate,false);
 assert.equal(result.evidence[0].text,f.units[0].text);assert.ok(result.multi_anchor_search.channels.some(c=>c.name==='claims'));
 assert.equal(result.multi_anchor_search.claim_matches[0].claim.event_id,undefined);
});
test('person/project mentions provide independent search lanes',async()=>{
 const f=fixture([role()]),r=await run(f,'민수의 알파 프로젝트 담당은?');
 for(const name of ['person','project','claims'])assert.ok(r.multi_anchor_search.channels.some(c=>c.name===name),name);
 assert.equal(r.multi_anchor_search.identity_merging,false);
});
test('document/place mentions keep the existing type and source identity',async()=>{
 const f=fixture([record('document','서울 서재에서 설계 문서를 보관한다.',[['서울 서재','place'],['설계 문서','other']],['서울 서재','보관','설계 문서'])]);
 const r=await run(f,'서울 서재의 설계 문서는?');for(const name of ['place','other'])assert.ok(r.multi_anchor_search.channels.some(c=>c.name===name));
});
test('same-name people remain distinct mentions with both source references',async()=>{
 const f=fixture([role(),record('school','학교 민수는 부산 독서 모임을 맡았다.',[['민수','person']],['민수','담당','부산 독서 모임'])]);
 const r=await run(f,'민수가 맡은 일은?');const mentions=r.multi_anchor_search.matched_entities.filter(e=>e.name==='민수');
 assert.equal(mentions.length,2);assert.notEqual(mentions[0].id,mentions[1].id);assert.deepEqual(new Set(r.evidence.map(e=>e.source_id)),new Set(['role','school']));
});
test('aliases are matched only when present on the source-grounded mention',async()=>{
 const f=fixture([role()]);assert.equal((await run(f,'김 대리가 맡은 일은?')).multi_anchor_search.matched_entities.length,0);
 f.units[0].entities[0].aliases=['김 대리'];assert.ok((await run(f,'김 대리가 맡은 일은?')).multi_anchor_search.matched_entities.some(e=>e.name==='민수'));
});
test('non-event evidence survives outside the three-graph shortlist',async()=>{
 const f=fixture([...Array.from({length:5},(_,i)=>record('festival'+i,'축제'+i+' 행사에서 만났다.',[['축제'+i,'event']],['나','참가','축제'+i])),preference()]);
 const r=await run(f,'축제와 조용한 공간 선호를 찾아줘.');
 assert.ok(r.evidence.some(e=>e.source_id==='preference'));assert.ok(r.multi_anchor_search.event_candidate_ids.length<=3);assert.equal(r.multi_anchor_search.event_gate,false);
});
test('text with no relation/entity metadata remains retrievable',async()=>{
 const f=fixture([record('plain','차분하게 생각을 정리하는 시간을 가졌다.')]),r=await run(f,'생각을 정리한 기록은?');
 assert.equal(r.multi_anchor_search.eligible_claim_count,0);assert.equal(r.evidence.length,1);assert.ok(r.evidence[0].text.includes('생각'));
});
test('explicit negation and plan status are preserved in Claim traces',async()=>{
 const r=record('denied','민수는 회의에 참석하지 않았다.',[['민수','person']],['민수','참석','회의']);r.unit.relations[0].polarity='negative';r.unit.relations[0].status='planned';
 const f=fixture([r]),result=await run(f,'민수 회의 참석 여부는?'),claim=result.multi_anchor_search.claim_matches[0].claim;
 assert.equal(claim.polarity,'negative');assert.equal(claim.status,'planned');assert.equal(result.evidence[0].text,r.source.text);
});
for(const field of ['source','owner','revision'])test('rejects out-of-scope '+field+' before scoring',async()=>{
 const f=fixture([preference()]);if(field==='source')f.sources=[];if(field==='owner')f.sources[0].metadata.owner_id='other';if(field==='revision')f.sources[0].revision=2;
 await assert.rejects(()=>run(f,'공간 선호는?'),/G2 색인/);
});
test('invalid Claim quote is rejected rather than repaired or answered',()=>{
 const f=fixture([preference()]);f.units[0].relations[0].evidence.quote='새로 만든 선호';assert.throws(()=>MA.catalog(f.indexes,f.sources,new Set(f.units.map(u=>u.id))),/Claim 근거/);
});
test('explicit valid-time excludes stale role while unknown validity is retained',async()=>{
 const a=role(),b=record('new','지수는 알파 프로젝트 담당자다.',[['지수','person']],['지수','담당','알파 프로젝트']);
 a.unit.relations[0].valid_time={from:'2026-01-01',to:'2026-06-30'};
 const f=fixture([a,b]),r=await run(f,'2026-11-16 알파 프로젝트 담당은?');
 assert.deepEqual(r.evidence.map(e=>e.source_id),['new']);assert.ok(r.structured_trace.time_filter.excluded.some(e=>e.source_id==='role'));
 const all=await run(f,'2026-11-16 알파 프로젝트 담당은?',{all_candidates:true});assert.equal(all.evidence.length,2);
});
test('empty access scope returns no evidence and completed search without model generation',async()=>{
 const f=fixture([]),r=await run(f,'어디에 갔었지?');assert.deepEqual(r.evidence,[]);assert.equal(r.multi_anchor_search.eligible_claim_count,0);assert.equal(r.multi_anchor_search.status,'COMPLETED');
});
test('cancellation and transport errors are not reported as empty memory',async()=>{
 const f=fixture([preference()]),controller=new AbortController();controller.abort();
 await assert.rejects(()=>retrieve(f.engine,{config:f.config},{d:{}},{id:'Q',text:'선호'},{},f.sources,{records:[]},controller.signal,false));
 f.engine.vector=async()=>{throw Error('embedding connection failed');};await assert.rejects(()=>run(f,'선호'),/embedding connection failed/);
});
test('compound retrieval preserves per-branch traces, unique evidence and coverage',async()=>{
 const f=fixture([role(),preference()]),question={id:'Q',text:'민수의 담당과 조용한 공간 선호는?'};
 f.engine.runtime={async chat(){return {parsed:{shared:[],parts:['민수의 담당','조용한 공간 선호']}};}};
 const result=await compound.retrieve(f.engine,{config:{...f.config,retrieval_strategy:'decomposed-v1'}},{d:{}},question,{},f.sources,signal(),sub=>run(f,sub.text));
 assert.equal(result.multi_anchor_search.branches.length,2);assert.equal(result.compound_search.status,'DECOMPOSED');
 assert.equal(new Set(result.evidence.map(e=>e.source_id+':'+e.start)).size,result.evidence.length);
 assert.ok(result.compound_search.branches.every(b=>b.evidence_ids.length));assert.equal(result.multi_anchor_search.returned_source_count,2);
});
test('G2 uses summary evidence and excludes original snapshots from answer prompts',()=>{
 const c=Engine.prototype.config.call({code_hash:'fixed'},{route:'G2'}),messages=answerMessages(c,{text:'선호는?'},{now:'2026-11-16',actor_id:'user-a',conversation:[],summary_generated_conversation:[]},[]);
 assert.ok(messages[0].content.includes('요약'));assert.ok(!JSON.stringify(messages).includes('ORIGINAL_CANARY'));
});
test('existing G1 sources stay byte-identical; UI only adds an option and existing details',()=>{
 const root=path.resolve(__dirname,'..'),original='D:/development/personal-memory-agent';
 for(const name of ['event-graph.cjs','event-linking.cjs','claim-graph.cjs','event-evidence.cjs'])assert.equal(fs.readFileSync(path.join(root,'local',name),'utf8'),fs.readFileSync(path.join(original,'local',name),'utf8'));
 assert.equal(fs.readFileSync(path.join(root,'baseline.css'),'utf8'),fs.readFileSync(path.join(original,'baseline.css'),'utf8'));
 assert.ok(fs.readFileSync(path.join(root,'baseline.html'),'utf8').includes('<option value="G2">G2 · 다중 대상·사실 검색</option>'));
});
test('actual save/index/retrieve/answer pipeline and frozen-answer reuse support G2',async()=>{
 const os=require('node:os'),{Store}=require('../local/store.cjs'),{hash}=require('../local/core.cjs');
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'g2-pipeline-')),store=new Store(dir),calls=[];
 const source={...preference().source,gold:{facts:[]}},context={id:'CTX',actor_id:'user-a',now:'2026-11-16T00:00:00Z',conversation:[],required_observations:[],expected_state:{accessible_sources:[{source_id:source.id,revision:1}]}};
 const question={id:'Q1',context_id:'CTX',text:'조용한 공간 선호는?',gold:{required_claims:['조용한 공간'],forbidden_claims:[],evidence_groups:[],expected_action:'answer',reference_answer:'조용한 공간'}};
 const ds={fingerprint:hash('g2-fixture'),d:{sources:{records:[source]},contexts:{contexts:[context]},questions:{questions:[question]},manifest:{}},lib:{materialize:()=>({accessible:[source],trace:[]})}};
 const runtime={version:'OFFLINE-G2',status:()=>({states:{generation:{status:'ready'},embedding:{status:'ready'}}}),async ensure(){},async tokenize(text){return Math.ceil(text.length/3);},async embed(){return [1,1,1];},async chat(messages,schema){
  const p=JSON.parse(messages[1].content);calls.push({schema,p});let parsed;
  if(schema.properties.search_terms){const sid=p.sentences[0].sentence_id;parsed={search_terms:[p.search_candidates[0].term_id],entities:[{name:'조용한 공간',type:'other',aliases:[],quote:'',occurrence:1,sentence_id:sid}],time_mentions:[],relations:[{subject:'나',predicate:'선호',object:'조용한 공간',polarity:'positive',status:'not_applicable',valid_from:null,valid_to:null,event_time:null,time_quote:'',quote:'',occurrence:1,sentence_id:sid,relation_clause_id:p.clauses[0].clause_id,validity_clause_id:null,event_clause_id:null}]};}
  else if(schema.properties.selected_ids)parsed={selected_ids:p.evidence.map(e=>e.evidence_id)};
  else{const e=p.evidence[0],s=e?.sentences?.[0];parsed={action:e?'answer':'abstain',answer:e?'조용한 공간을 선호한다고 기록되어 있어요.':'확인하지 못했어요.',citations:e?[{evidence_id:e.evidence_id,sentence_id:s.sentence_id,quote:'',occurrence:1}]:[]};}
  return {parsed,raw:JSON.stringify(parsed),usage:{prompt_tokens:10,completion_tokens:10}};
 }};
 const engine=new Engine(dir,store,runtime);engine.dataset=async()=>ds;
 const finish=async created=>{for(let i=0;i<500;i++){if(!engine.busy)return store.run(created.id);await new Promise(r=>setTimeout(r,5));}throw Error('G2 pipeline timed out');};
 try{
  const run=await finish(await engine.create({config:{route:'G2'},question_ids:['Q1']}));
  assert.equal(run.status,'COMPLETED',JSON.stringify(run.results.map(r=>r.error)));assert.equal(run.summary_batch.indexing.status,'COMPLETED');
  const result=run.results[0],retrieval=result.stages.retrieval,answer=result.stages.answer;
  assert.equal(retrieval.multi_anchor_search.eligible_claim_count,1);assert.equal(retrieval.multi_anchor_search.event_gate,false);assert.equal(answer.citation_errors.length,0);assert.equal(answer.citations[0].basis,'summary');
  assert.equal(answer.assessment.semantic_correct,null);assert.ok(calls.every(call=>!JSON.stringify(call.p).includes('required_claims')));
  const before=calls.filter(call=>call.schema.properties.search_terms).length;
  const reused=await finish(await engine.create({stage:'answer',config:{route:'G2'},question_ids:['Q1'],artifacts:[retrieval.artifact_id]}));
  assert.equal(reused.status,'COMPLETED');assert.equal(calls.filter(call=>call.schema.properties.search_terms).length,before);
 }finally{store.db.close();const resolved=path.resolve(dir),tmp=path.resolve(os.tmpdir())+path.sep;assert.ok(resolved.startsWith(tmp));fs.rmSync(resolved,{recursive:true,force:true});}
});
