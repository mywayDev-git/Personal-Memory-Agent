const test=require('node:test'),assert=require('node:assert/strict'),path=require('node:path'),fs=require('node:fs'),os=require('node:os');
const {pathToFileURL}=require('node:url');
const root=path.resolve(__dirname,'..'),dir=path.join(root,'datasets','pma-long-v1.0.1');
const library=()=>import(pathToFileURL(path.join(dir,'lib.mjs')).href);
const read=name=>JSON.parse(fs.readFileSync(path.join(dir,name),'utf8'));

test('long dataset has verified provenance, 56 isolated cases, 60 target regions and exact gold links',async()=>{
 const lib=await library(),d=lib.loadDataset(dir);assert.deepEqual(lib.validate(d,dir),{ok:true,errors:[]});
 assert.equal(d.manifest.counts.families,13);assert.equal(d.manifest.partition.final.length,0);
 assert.deepEqual(d.manifest.profiles,{smoke:8,core:24,sentence:8,boundary:6,dependency:4,stress:6});
 for(const q of d.questions.questions){const c=d.contexts.contexts.find(c=>c.id===q.context_id),state=lib.materialize(c,d.sources.records);
  assert.equal(state.accessible.length,1);assert.equal(state.accessible[0].provenance.upstream_case_id,q.display_case_id);
  assert.equal(q.gold.reference_answer,null);assert.equal(q.gold.expected_action,null);
  assert.equal(state.accessible[0].metadata.created_at,null);
 }
});
test('only the 4013 to 4001 boundary fixture changes text, keeping its intact evidence across the cut',()=>{
 const old=read('upstream/inputs.json'),current=read('inputs.json'),a=read('annotations.json');
 assert.deepEqual(current.filter((x,i)=>x.text!==old[i].text).map(x=>x.id),['LI-import-4001']);
 const x=current.find(x=>x.id==='LI-import-4001'),g=a.find(x=>x.id==='LI-import-4001').gold;
 assert.equal(Array.from(x.text).length,4001);assert.equal(g.evidence[0].start,3973);assert.equal(g.evidence[0].end,4001);
 assert.equal(x.text.slice(3973,4001),g.evidence[0].quote);
});
test('codepoint to UTF16 mapping retains supplementary characters without offset drift',async()=>{
 const {utf16Offset}=await library(),text='가😀나🧠다';
 assert.equal(utf16Offset(text,2),3);assert.equal(utf16Offset(text,4),6);
 assert.equal(text.slice(utf16Offset(text,1),utf16Offset(text,4)),'😀나🧠');
});
test('validation rejects gold mutation and cross-case source access',async()=>{
 const lib=await library(),d=lib.loadDataset(dir);
 d.questions.questions[0].gold.required_claims=['정답을 임의 변경'];
 d.contexts.contexts[0].setup.initial_sources.push(d.contexts.contexts[1].setup.initial_sources[0]);
 const result=lib.validate(d,dir,{checkHashes:false});assert.equal(result.ok,false);
 assert.ok(result.errors.some(s=>s.includes('gold required_claims')));assert.ok(result.errors.some(s=>s.includes('scope isolation')));
});
test('all model extraction requests exclude questions, labels, gold and semantic case IDs',async()=>{
 const {loadDataset}=await library(),d=loadDataset(dir),{Engine}=require('../local/engine.cjs'),prompts=require('../local/prompts.cjs'),{sentences}=require('../local/core.cjs');
 const engine=new Engine(root,{recover(){}},{version:'OFFLINE_NO_CALLS'}),config=engine.config({dataset:'pma-long-v1.0.1'});
 for(const s of d.sources.records){const payload=JSON.parse(prompts.extractMessages(config,s,sentences(s.text))[1].content);
  assert.deepEqual(Object.keys(payload),['source_id','revision','metadata','sentences']);
  assert.match(payload.source_id,/^LIS-[0-9a-f]{16}$/);assert.equal(payload.metadata.created_at,null);
  assert.deepEqual(payload.sentences.map(s=>s.text).join('').replace(/\s/g,''),s.text.replace(/\s/g,''));
  assert.ok(!Object.keys(payload.metadata).some(k=>/gold|family|profile|question|case|position|pair/.test(k)));
 }
});
test('loader selects independent validator and new run config freezes input path/profile without changing old defaults',async()=>{
 const {Engine}=require('../local/engine.cjs'),engine=new Engine(root,{recover(){}},{version:'OFFLINE_NO_CALLS'});
 assert.equal((await engine.dataset('pma-long-v1.0.1')).d.questions.questions.length,56);
 assert.equal((await engine.dataset('pma-dev-v0.1.0')).d.questions.questions.length,114);
 assert.equal((await engine.dataset('pma-dev-v0.2.0')).d.questions.questions.length,117);
 const long=engine.config({dataset:'pma-long-v1.0.1',dataset_profile:'boundary'}),old=engine.config({});
 assert.equal(long.dataset_profile,'boundary');assert.equal(long.input_path,'raw_original_v1');
 assert.equal(old.dataset,'pma-dev-v0.1.0');assert.equal(old.dataset_profile,undefined);assert.equal(long.model,old.model);
 assert.equal(long.extraction_prompt_text,old.extraction_prompt_text);
 assert.throws(()=>engine.config({dataset:'pma-long-v1.0.1',dataset_profile:'wrong'}),/프로필/);
 assert.throws(()=>engine.config({dataset:'pma-long-v1.0.1',input_path:'imported_chunks'}),/원문 전체/);
});
test('profile mismatch is rejected before a run is stored or a runtime is called',async()=>{
 const {Engine}=require('../local/engine.cjs');let stored=false;
 const engine=new Engine(root,{recover(){},putRun(){stored=true;}},{version:'OFFLINE_NO_CALLS'});
 await assert.rejects(()=>engine.create({config:{dataset:'pma-long-v1.0.1',dataset_profile:'smoke'},question_ids:['LI-import-4001:Q1']}),/프로필 밖/);
 assert.equal(stored,false);
});
test('paired short/core controls retain identical target questions and gold, with all three core positions',()=>{
 const a=read('annotations.json');
 for(const short of a.filter(x=>x.profile==='smoke')) {
  const variants=a.filter(x=>x.profile==='core'&&x.pair_group===short.pair_group);
  assert.deepEqual(variants.map(x=>x.position).sort(),['end','front','middle']);
  for(const v of variants){assert.equal(v.gold.question,short.gold.question);assert.deepEqual(v.gold.required_meanings,short.gold.required_meanings);assert.deepEqual(v.gold.structured_expectations,short.gold.structured_expectations);}
 }
});
test('hashed on-disk corruption is detected',async()=>{
 const lib=await library(),tmp=fs.mkdtempSync(path.join(os.tmpdir(),'pma-long-integrity-'));
 try{fs.cpSync(dir,tmp,{recursive:true});const file=path.join(tmp,'questions.json');fs.appendFileSync(file,'\n');
  assert.ok(lib.validate(lib.loadDataset(tmp),tmp).errors.some(s=>s==='hash questions.json'));
 }finally{fs.rmSync(tmp,{recursive:true,force:true});}
});
test('mocked long-case pipeline preserves unannotated answer fields and frozen structure gold through review',async()=>{
 const {Store}=require('../local/store.cjs'),{Engine}=require('../local/engine.cjs'),{buildReview}=require('../local/review.cjs');
 const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'pma-long-pipeline-'));let store;
 try {
  fs.cpSync(path.join(root,'datasets'),path.join(tmp,'datasets'),{recursive:true});store=new Store(tmp);
  const runtime={version:'OFFLINE_TEST_DOUBLE',calls:[],status(){return {};},async ensure(){},async tokenize(text){return Math.ceil(text.length/2);},async embed(){return [1,2,3];},
   async chat(messages){this.calls.push(messages);const p=JSON.parse(messages[1].content);let parsed;
    if(p.sentences){const s=p.sentences[0];parsed={facts:[{subject:'테스트 더블',relation:'기록',object:s.text,polarity:'unknown',status:'unknown',modality:'unknown',time:'',event_time:'',speech_time:'',valid_from:'',valid_to:'',condition:'',evidence:[{sentence_id:s.sentence_id,quote:s.text,occurrence:1}],mentions:[]}]};}
    else{const e=p.evidence[0];parsed={action:e?'answer':'abstain',answer:'오프라인 대체 응답',citations:e?[{evidence_id:e.evidence_id,quote:e.text,occurrence:1}]:[]};}
    return {parsed,raw:JSON.stringify(parsed),elapsed_ms:1,usage:{}};
   }};
  const engine=new Engine(tmp,store,runtime),ds=await engine.dataset('pma-long-v1.0.1'),q=ds.d.questions.questions.find(q=>q.profile==='smoke'&&q.family_id==='unknown_actor');
  const run=await engine.create({config:{dataset:'pma-long-v1.0.1',dataset_profile:'smoke',route:'S0'},stage:'end_to_end',question_ids:[q.id]});
  for(let i=0;i<300&&engine.busy;i++)await new Promise(r=>setTimeout(r,10));
  const saved=store.run(run.id);assert.equal(saved.status,'COMPLETED');assert.equal(saved.results[0].status,'PENDING_REVIEW');
  const assessment=saved.results[0].stages.answer.assessment;
  assert.equal(assessment.reference_answer,null);assert.equal(assessment.expected_action,null);
  assert.deepEqual(assessment.structured_expectations,q.gold.structured_expectations);assert.equal(assessment.semantic_correct,null);
  const review=buildReview(saved,store,ds,'answer');
  assert.deepEqual(review.targets[0].question_gold.structured_expectations,q.gold.structured_expectations);
  assert.equal(review.targets[0].question_gold.annotation_status.reference_answer,'NOT_ANNOTATED');
  assert.equal(runtime.calls.length,2);
  for(const messages of runtime.calls){const payload=JSON.parse(messages[1].content);assert.equal(payload.gold,undefined);assert.equal(payload.structured_expectations,undefined);}
 }finally{store?.db.close();fs.rmSync(tmp,{recursive:true,force:true});}
});
