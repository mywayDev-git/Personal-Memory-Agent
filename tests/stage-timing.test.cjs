const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=process.env.PMA_APP_ROOT||path.resolve(__dirname,'..'),code=process.env.PMA_TIMING_CODE_ROOT||root;
const {Engine}=require(path.join(code,'local','engine.cjs')),timing=require(path.join(code,'timing.js'));
const delay=ms=>new Promise(r=>setTimeout(r,ms));
async function fixture(stage='end_to_end',route='S0',ids=['F02-Q1']){
 const saves=[],store={recover(){},putRun:r=>saves.push(JSON.parse(JSON.stringify(r)))},runtime={version:'OFFLINE',ensure:async()=>{},status:()=>({})},e=new Engine(root,store,runtime),ds=await e.dataset('pma-dev-v0.1.0');
 const run={id:'OFFLINE-TIMING',status:'QUEUED',stage,config:e.config({route}),question_ids:ids,results:[],events:[],created_at:new Date().toISOString()};
 e.abort=new AbortController();let extractions=0;
 e.extract=async(run,ds,context,sources)=>{extractions++;await delay(8);return {context_id:context.id,config:run.config,artifact_id:'EX',source_refs:sources.map(s=>({source_id:s.id,revision:s.revision})),records:[],elapsed_ms:8};};
 e.retrieve=async(run,ds,q)=>{await delay(8);return {question_id:q.id,artifact_id:'RET',elapsed_ms:8};};
 e.answer=async()=>{await delay(8);return {citation_errors:[],elapsed_ms:8};};
 return {e,ds,run,saves,count:()=>extractions};
}

test('extract-only execution persists structure start/end/duration without inventing search or answer times',async()=>{
 const f=await fixture('extract');await f.e.execute(f.run,f.ds);const r=f.run.results[0];
 assert.ok(r.stage_timings.extraction.started_at);assert.ok(r.stage_timings.extraction.finished_at);assert.ok(r.stage_timings.extraction.elapsed_ms>=5);
 assert.equal(r.stage_timings.retrieval,undefined);assert.equal(r.stage_timings.answer,undefined);
 assert.ok(f.saves.some(s=>s.active_result?.stage_timings?.extraction?.status==='RUNNING'));
 assert.equal(timing.stage(r,'extraction').status,'RECORDED');
});

test('search clock survives keyword, query-embedding, document-embedding and fusion progress changes',async()=>{
 const f=await fixture('retrieve','R0');let start;
 f.e.retrieve=async(run,ds,q)=>{const r=run.active_result;start=r.stage_timings.retrieval.started_at;for(const stage of ['lexical','query_embedding','document_embedding','fusion']){f.e.update(run,'offline '+stage,{stage});await delay(3);assert.equal(r.stage_timings.retrieval.started_at,start);const t=timing.stage(r,'retrieval');assert.equal(t.status,'RUNNING');assert.equal(t.started_at,start);assert.ok(t.ms>=0);}return {artifact_id:'RET',elapsed_ms:12};};
 await f.e.execute(f.run,f.ds);const r=f.run.results[0];assert.equal(r.stage_timings.retrieval.started_at,start);assert.ok(r.stage_timings.retrieval.elapsed_ms>=10);assert.equal(timing.stage(r,'extraction').ms,null);
});

test('failed and cancelled searches preserve elapsed time and stop growing after termination',async()=>{
 for(const cancel of [false,true]){const f=await fixture('retrieve','R0');f.e.retrieve=async()=>{await delay(8);if(cancel)f.e.abort.abort();throw Error('offline failure');};await f.e.execute(f.run,f.ds);const r=f.run.results[0],t=timing.stage(r,'retrieval');assert.equal(t.status,cancel?'CANCELLED':'ERROR');assert.ok(t.ms>=5);assert.equal(timing.stage(r,'retrieval',Date.now()+60000).ms,t.ms);assert.equal(r.stage_timings.answer,undefined);}
});

test('same-context extraction is measured once and later questions explicitly identify reuse',async()=>{
 const f=await fixture('end_to_end','S0',['F02-Q1','F02-Q2']);await f.e.execute(f.run,f.ds);assert.equal(f.count(),1);const [a,b]=f.run.results;
 assert.equal(a.stage_timings.extraction.reused,false);assert.equal(b.stage_timings.extraction.reused,true);assert.equal(b.stage_progress.extraction,'REUSED');
 assert.equal(b.stage_timings.extraction.original_elapsed_ms,8);assert.equal(timing.stage(b,'extraction').status,'REUSED');assert.equal(b.stages.extraction.reused,true);
 assert.equal(a.stages.extraction.reused,undefined,'shared original artifact must not be mutated');
});

test('frozen retrieval carries its original time in the saved result without artifact hydration',async()=>{
 const f=await fixture('answer');f.e.findArtifact=(run,type,contextId)=>{const c=f.ds.d.contexts.contexts.find(c=>c.id===contextId);return {artifact_id:'FROZEN',context_id:contextId,source_refs:c.expected_state.accessible_sources,elapsed_ms:1234};};
 await f.e.execute(f.run,f.ds);const r=JSON.parse(JSON.stringify(f.run.results[0]));assert.equal(r.stages.retrieval.reused,true);assert.equal(r.stages.retrieval.elapsed_ms,1234);assert.deepEqual(timing.stage(r,'retrieval'),{ms:1234,reused:true,status:'REUSED'});
});

test('legacy stage times remain readable; unmeasured historical errors remain unknown',()=>{
 assert.deepEqual(timing.stage({stages:{extraction:{elapsed_ms:23}}},'extraction'),{ms:23,reused:false,status:'RECORDED'});
 assert.equal(timing.stage({stage_progress:{retrieval:'ERROR'}},'retrieval').ms,null);
 assert.equal(timing.stage({status:'INTERRUPTED',stage_timings:{retrieval:{started_at:'2026-11-03T00:00:00Z',status:'RUNNING'}}},'retrieval').ms,null);
});

test('progress, result and saved-question table render a live search clock independent of subphase names',()=>{
 const nodes=new Map(),el=s=>{if(!nodes.has(s))nodes.set(s,{innerHTML:'',textContent:'',value:'',querySelectorAll:()=>[],classList:{toggle(){}},addEventListener(){}});return nodes.get(s);};
 const ctx=vm.createContext({console,MemoryTiming:timing,setTimeout,clearTimeout,document:{querySelector:el,querySelectorAll:()=>[],addEventListener(){}}});
 const source=fs.readFileSync(path.join(code,'baseline.js'),'utf8').replace('\ninitialize();','\n').replace('\ninitializeSelectionGuide();','\n');vm.runInContext(source,ctx);
 const started_at=new Date(Date.now()-5000).toISOString(),result={question_id:'Q',status:'RUNNING',started_at,stages:{},stage_progress:{extraction:'SKIPPED',retrieval:'RUNNING',answer:'NOT_RUN'},stage_timings:{retrieval:{status:'RUNNING',started_at}}};
 ctx.record={id:'R',created_at:started_at,status:'RUNNING',question_ids:['Q'],results:[],active_result:result,progress_detail:{stage:'document_embedding'}};ctx.result=result;
 vm.runInContext('renderExecutionMonitor(record)',ctx);assert.ok(el('#execution-monitor').innerHTML.includes('data-elapsed-start="'+started_at+'"'));assert.ok(el('#execution-monitor').innerHTML.includes('검색 · 진행 중 · <span'));
 assert.ok(vm.runInContext('resultTimingHTML(result)',ctx).includes('<b>검색</b> <span data-elapsed-start='));assert.ok(vm.runInContext('questionTimesHTML(record)',ctx).includes('<td><span data-elapsed-start='));
});
