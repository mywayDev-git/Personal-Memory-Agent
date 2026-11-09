const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os'),{pathToFileURL}=require('node:url');
const root=path.resolve(__dirname,'..'),dir=path.join(root,'datasets','pma-memory-v2.0.0'),libPromise=import(pathToFileURL(path.join(dir,'lib.mjs')).href);
test('new version preserves the planned source split and separates base questions from reused variants',async()=>{
 const lib=await libPromise,d=lib.loadDataset(dir),v=lib.validate(d,dir);assert.deepEqual(v.errors,[]);assert.ok(v.checks>6000);
 assert.deepEqual(d.manifest.profiles,{development_a:96,development_b:96,controlled:72,final:96});assert.equal(d.sources.records.length,288);assert.equal(d.questions.questions.length,360);
 assert.equal(d.questions.questions.filter(q=>!q.variant&&q.split==='development').length,192);assert.equal(d.questions.questions.filter(q=>q.split==='final').length,96);
 for(const c of d.cases.cases){assert.equal(c.source_refs.length,8);assert.equal(c.question_ids.length,8);}
});
test('every question has original support, reference meaning and no inaccessible gold',async()=>{
 const lib=await libPromise,d=lib.loadDataset(dir),facts=new Map(d.sources.records.flatMap(s=>s.gold.facts.map(f=>[f.id,s.id])));
 for(const q of d.questions.questions){const c=d.contexts.contexts.find(c=>c.id===q.context_id),ids=new Set(lib.materialize(c,d.sources.records).accessible.map(s=>s.id));assert.ok(q.gold.reference_answer);for(const g of q.gold.evidence_groups)for(const f of g.any_of_fact_ids)assert.ok(ids.has(facts.get(f)));}
});
test('input variants keep the answer invariant and actually move the target in larger histories',async()=>{
 const lib=await libPromise,d=lib.loadDataset(dir);
 for(let i=13;i<=20;i++){
  const parent=d.questions.questions.find(q=>q.id===`MC-${i}-Q1`),variants=d.questions.questions.filter(q=>q.variant?.paired_question_id===parent.id);assert.equal(variants.length,9);
  for(const q of variants){assert.equal(q.text,parent.text);assert.equal(q.gold.reference_answer,parent.gold.reference_answer);const c=d.contexts.contexts.find(c=>c.id===q.context_id);assert.equal(c.expected_state.accessible_sources.length,q.variant.source_count);}
  const order=pos=>d.contexts.contexts.find(c=>c.id===variants.find(q=>q.variant.source_count===8&&q.position===pos).context_id).setup.initial_sources.map(r=>r.source_id);
  assert.notDeepEqual(order('front'),order('middle'));assert.notDeepEqual(order('middle'),order('end'));
 }
});
test('fixed followup contexts preserve the changed date, project and ordered candidates',async()=>{
 const lib=await libPromise,d=lib.loadDataset(dir);for(const n of [2,3,4,6,7]){const q=d.questions.questions.find(q=>q.id===`MC-23-Q${n}`),c=d.contexts.contexts.find(c=>c.id===q.context_id);assert.ok(c.conversation.length);}
 const q=d.questions.questions.find(q=>q.id==='MC-23-Q3'),c=d.contexts.contexts.find(c=>c.id===q.context_id);assert.ok(c.conversation[0].text.includes('11월 에코'));
});
test('static validation rejects corrupted evidence, split leakage and duplicate filler',async()=>{
 const lib=await libPromise,d=lib.loadDataset(dir),bad=structuredClone(d);bad.sources.records[0].gold.facts[0].evidence[0].end=1;assert.ok(!lib.validate(bad,dir,{checkHashes:false}).ok);
 const leak=structuredClone(d);leak.contexts.contexts[0].expected_state.accessible_sources.push(leak.cases.cases.at(-1).source_refs[0]);assert.ok(!lib.validate(leak,dir,{checkHashes:false}).ok);
 const dup=structuredClone(d);dup.sources.records[0].text+=' '+dup.sources.records[0].text;assert.ok(lib.validate(dup,dir,{checkHashes:false}).errors.some(e=>/repeated sentence/.test(e)));
});
test('coverage reports all 489 variables honestly and keeps functional tests out of content-only claims',async()=>{
 const lib=await libPromise,d=lib.loadDataset(dir);assert.equal(d.coverage.variables.length,489);assert.ok(d.coverage.variables.some(v=>v.status==='NOT_COVERED'));assert.equal(d.coverage.variables.find(v=>v.id==='SEC-04').status,'SEPARATE_FUNCTIONAL_TEST');assert.ok(d.coverage.variables.every(v=>v.status!=='COVERED'));assert.equal(d.manifest.model_execution,false);
});
test('version is portable and has no sibling dataset dependency',async()=>{
 const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'pma-memory-portable-'));try{fs.cpSync(dir,tmp,{recursive:true});const lib=await import(pathToFileURL(path.join(tmp,'lib.mjs')).href);assert.deepEqual(lib.validate(lib.loadDataset(tmp),tmp).errors,[]);}finally{fs.rmSync(tmp,{recursive:true,force:true});}
});
test('loader accepts four profiles and whole dataset scheduling without touching a model',async()=>{
 const {Engine}=require('../local/engine.cjs');let writes=0;const e=new Engine(root,{recover(){},putRun(){writes++;}},{version:'OFFLINE-NO-MODEL'}),ds=await e.dataset('pma-memory-v2.0.0');
 assert.equal(e.config({dataset:'pma-memory-v2.0.0'}).dataset_profile,'development_a');for(const p of ['all','development_a','development_b','controlled','final'])assert.equal(e.config({dataset:'pma-memory-v2.0.0',dataset_profile:p}).dataset_profile,p);
 assert.throws(()=>e.config({dataset:'pma-memory-v2.0.0',dataset_profile:'natural_single'}),/프로필/);
 e.execute=async()=>{};const created=await e.create({config:{dataset:'pma-memory-v2.0.0',dataset_profile:'all'},question_ids:ds.d.questions.questions.map(q=>q.id)});assert.equal(created.question_ids.length,360);await new Promise(r=>setImmediate(r));
 await assert.rejects(()=>e.create({config:{dataset:'pma-memory-v2.0.0',dataset_profile:'development_a'},question_ids:['MC-25-Q1']}),/프로필/);assert.equal(writes,1);
});
test('Full pipeline uses all eight new originals in order and never sends evaluation answers',async()=>{
 const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'pma-memory-pipeline-')),{Store}=require('../local/store.cjs'),{Engine}=require('../local/engine.cjs');
 fs.cpSync(path.join(root,'datasets'),path.join(tmp,'datasets'),{recursive:true});const store=new Store(tmp);let chatCalls=0,embedCalls=0;const runtime={version:'MOCK-ONLY',status:()=>({states:{generation:{status:'stopped'},embedding:{status:'stopped'}}}),stop:async()=>{},ensure:async()=>{},countChatTokens:async()=>1,tokenize:async()=>1,embed:async()=>{embedCalls++;return [1];}};
 // Use a new question and a synthetic response; this checks wiring, not model accuracy.
 runtime.chat=async messages=>{chatCalls++;const p=JSON.parse(messages[1].content);assert.equal(p.evidence.length,8);assert.equal(p.question,'서버 배포 인계를 수락한 사람은?');assert.equal(JSON.stringify(p).includes('required_claims'),false);assert.equal(JSON.stringify(p).includes('reference_answer'),false);const parsed={action:'answer',answer:'MOCK ONLY',citations:[{evidence_id:p.evidence[0].evidence_id,quote:p.evidence[0].text,occurrence:1}]};return {parsed,raw:JSON.stringify(parsed),usage:{prompt_tokens:1,completion_tokens:1},input_tokens:1,elapsed_ms:1};};
 try{const e=new Engine(tmp,store,runtime),r=await e.create({config:{dataset:'pma-memory-v2.0.0',dataset_profile:'development_a',route:'R0-Full'},question_ids:['MC-01-Q1']});for(let n=0;n<100&&e.busy;n++)await new Promise(resolve=>setTimeout(resolve,5));assert.equal(e.busy,null);const saved=store.run(r.id);assert.equal(saved.results.length,1);assert.equal(saved.results[0].stages.retrieval.evidence.length,8);assert.equal(chatCalls,1);assert.equal(embedCalls,0);}
 finally{store.db.close();fs.rmSync(tmp,{recursive:true,force:true});}
});
