const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os'),{pathToFileURL}=require('node:url');
const root=path.resolve(__dirname,'..'),dir=path.join(root,'datasets','pma-long-v2.0.0');
const libPromise=import(pathToFileURL(path.join(dir,'lib.mjs')).href);
test('v2 composition, exact spans, source-local gold, paired controls, connections and v1 preservation validate',async()=>{
 const lib=await libPromise,d=lib.loadDataset(dir),v=lib.validate(d,dir);assert.deepEqual(v.errors,[]);assert.equal(v.ok,true);assert.ok(v.checks>3000);
 assert.equal(d.manifest.counts.sources,84);assert.equal(d.manifest.counts.questions,140);assert.equal(d.manifest.counts.new_sentence_meaning_bundles,264);assert.equal(d.connections.relations.length,59);
 assert.deepEqual(d.cases.cases.map(c=>c.question_ids.length),Array(12).fill(6));
 assert.ok(d.cases.cases.every(c=>c.characters>=1200&&c.characters<=1400));
});
test('natural original scopes contain no other case, paired short control or v1 shortcut',async()=>{
 const lib=await libPromise,d=lib.loadDataset(dir);
 for(const c of d.cases.cases){const context=d.contexts.contexts.find(x=>x.id===c.context_id),state=lib.materialize(context,d.sources.records);
  assert.equal(state.accessible.length,c.profile==='natural_single'?1:2);assert.ok(state.accessible.every(s=>s.provenance.case_id===c.id));
  const control=d.questions.questions.find(q=>q.id===c.id+'-CONTROL-Q1'),shortContext=d.contexts.contexts.find(x=>x.id===control.context_id),short=lib.materialize(shortContext,d.sources.records);
  assert.equal(short.accessible.length,1);assert.ok(!state.accessible.some(s=>s.id===short.accessible[0].id));assert.ok(short.accessible[0].text.length<350);
 }
});
test('every first multi-record question needs facts in both originals; later report cannot silently resolve a conflict',async()=>{
 const lib=await libPromise,d=lib.loadDataset(dir),facts=new Map(d.sources.records.flatMap(s=>s.gold.facts.map(f=>[f.id,s.id])));
 for(const c of d.cases.cases.filter(c=>c.profile==='natural_multi')){const q=d.questions.questions.find(q=>q.id===c.question_ids[0]);assert.equal(new Set(q.gold.evidence_groups.flatMap(g=>g.any_of_fact_ids.map(id=>facts.get(id)))).size,2);}
 const q=d.questions.questions.find(q=>q.id==='NC-11-Q1');assert.equal(q.gold.expected_action,'report_conflict');assert.ok(q.gold.forbidden_claims.some(x=>x.includes('최신')));
});
test('mutation of paired meanings or source scope fails validation without an LLM judge',async()=>{
 const lib=await libPromise,d=lib.loadDataset(dir);d.questions.questions.find(q=>q.id==='NC-01-CONTROL-Q1').gold.reference_answer='민수가 계속 맡는다';
 const c=d.contexts.contexts.find(c=>c.id===d.cases.cases[0].context_id);c.setup.initial_sources.push(d.cases.cases[1].source_refs[0]);
 const v=lib.validate(d,dir,{checkHashes:false});assert.equal(v.ok,false);assert.ok(v.errors.some(e=>e.includes('target gold preserved reference_answer')));assert.ok(v.errors.some(e=>e.includes('fixed scope')));
});
test('new metadata and extraction messages do not include case labels, gold, questions or connections',async()=>{
 const lib=await libPromise,d=lib.loadDataset(dir),prompts=require('../local/prompts.cjs'),{sentences}=require('../local/core.cjs'),{Engine}=require('../local/engine.cjs');
 const engine=new Engine(root,{recover(){}},{version:'OFFLINE_NO_MODEL_CALLS'}),config=engine.config({dataset:'pma-long-v2.0.0',dataset_profile:'natural_single'});
 for(const source of d.sources.records.filter(s=>s.provenance.case_id)){
  const input=JSON.parse(prompts.extractMessages(config,source,sentences(source.text))[1].content);
  assert.deepEqual(Object.keys(input),['source_id','revision','metadata','sentences']);assert.match(input.source_id,/^NIS-[a-f0-9]{16}$/);
  assert.ok(!Object.keys(input.metadata).some(key=>/case|profile|family|gold|question|pair|expected|answer/.test(key)));
 }
});
test('new dataset loader/config work and profile mismatch is rejected before recording or model startup',async()=>{
 const {Engine}=require('../local/engine.cjs');let stored=false;const engine=new Engine(root,{recover(){},putRun(){stored=true;}},{version:'OFFLINE_NO_MODEL_CALLS'});
 assert.equal((await engine.dataset('pma-long-v2.0.0')).d.questions.questions.length,140);
 const config=engine.config({dataset:'pma-long-v2.0.0',dataset_profile:'natural_multi'});assert.equal(config.dataset_profile,'natural_multi');assert.equal(config.input_path,'raw_original_v1');
 await assert.rejects(()=>engine.create({config:{dataset:'pma-long-v2.0.0',dataset_profile:'natural_single'},question_ids:['NC-09-Q1']}),/프로필 밖/);assert.equal(stored,false);
});
test('file mutation is caught by manifest hashes even when its JSON remains equivalent',async()=>{
 const lib=await libPromise,tmp=fs.mkdtempSync(path.join(os.tmpdir(),'pma-natural-integrity-'));
 try{const target=path.join(tmp,'datasets','pma-long-v2.0.0');fs.cpSync(path.join(root,'datasets','pma-long-v1.0.1'),path.join(tmp,'datasets','pma-long-v1.0.1'),{recursive:true});fs.cpSync(dir,target,{recursive:true});fs.mkdirSync(path.join(tmp,'tools'));for(const name of ['natural_cases.py','build-natural-dataset.py'])fs.copyFileSync(path.join(root,'tools',name),path.join(tmp,'tools',name));fs.appendFileSync(path.join(target,'questions.json'),'\n');assert.ok(lib.validate(lib.loadDataset(target),target).errors.includes('hash questions.json'));}
 finally{fs.rmSync(tmp,{recursive:true,force:true});}
});
test('cross-record evidence diagnostics cannot count the second original as found when it is absent',async()=>{
 const lib=await libPromise,d=lib.loadDataset(dir),{Engine}=require('../local/engine.cjs'),engine=new Engine(root,{recover(){}},{}),q=d.questions.questions.find(q=>q.id==='NC-09-Q1'),c=d.contexts.contexts.find(c=>c.id===q.context_id),sources=lib.materialize(c,d.sources.records).accessible;
 const first=sources[0],second=sources[1],evidence=[{source_id:first.id,start:0,end:first.text.length,text:first.text}];
 const partial=engine.retrievalMetrics(d,q,[{source_id:first.id,rank:1}],evidence);assert.equal(partial.required_groups,3);assert.equal(partial.source_groups_found,2);assert.equal(partial.span_groups_fully_covered,2);
 const complete=engine.retrievalMetrics(d,q,[{source_id:first.id,rank:1},{source_id:second.id,rank:2}],[...evidence,{source_id:second.id,start:0,end:second.text.length,text:second.text}]);assert.equal(complete.span_groups_fully_covered,3);
});
test('mocked new two-original pipeline preserves authored gold and does not start a real model',async()=>{
 const {Store}=require('../local/store.cjs'),{Engine}=require('../local/engine.cjs'),tmp=fs.mkdtempSync(path.join(os.tmpdir(),'pma-natural-pipeline-'));let store;
 try{
  fs.cpSync(path.join(root,'datasets'),path.join(tmp,'datasets'),{recursive:true});fs.mkdirSync(path.join(tmp,'tools'));for(const name of ['natural_cases.py','build-natural-dataset.py'])fs.copyFileSync(path.join(root,'tools',name),path.join(tmp,'tools',name));store=new Store(tmp);
  const calls=[],runtime={version:'OFFLINE_TEST_DOUBLE',async ensure(){},status(){return {};},async tokenize(t){return Math.ceil(t.length/3);},async embed(){return [1,2,3];},async chat(messages){calls.push(messages);const input=JSON.parse(messages[1].content);let parsed;if(input.sentences){const s=input.sentences[0];parsed={facts:[{subject:'오프라인 대체',relation:'기록',object:s.text,polarity:'unknown',status:'unknown',modality:'unknown',time:'',event_time:'',speech_time:'',valid_from:'',valid_to:'',condition:'',evidence:[{sentence_id:s.sentence_id,quote:s.text,occurrence:1}],mentions:[]}]};}else{const e=input.evidence[0];parsed={action:e?'answer':'abstain',answer:'오프라인 대체 응답',citations:e?[{evidence_id:e.evidence_id,quote:e.text,occurrence:1}]:[]};}return {parsed,raw:JSON.stringify(parsed),elapsed_ms:1,usage:{}};}};
  const engine=new Engine(tmp,store,runtime),run=await engine.create({config:{dataset:'pma-long-v2.0.0',dataset_profile:'natural_multi',route:'S0'},stage:'end_to_end',question_ids:['NC-09-Q1']});for(let i=0;i<300&&engine.busy;i++)await new Promise(resolve=>setTimeout(resolve,10));const saved=store.run(run.id);assert.equal(saved.status,'COMPLETED');const result=saved.results[0];assert.equal(result.stages.extraction.records.length,2);assert.equal(result.stages.retrieval.source_refs.length,2);assert.equal(result.stages.answer.assessment.reference_answer.includes('회사 동료 하린'),true);assert.equal(result.stages.answer.assessment.semantic_correct,null);assert.equal(calls.length,3);for(const messages of calls){const payload=JSON.parse(messages[1].content);assert.equal(payload.gold,undefined);assert.equal(payload.required_claims,undefined);assert.equal(payload.connections,undefined);}
 }finally{store?.db.close();fs.rmSync(tmp,{recursive:true,force:true});}
});
