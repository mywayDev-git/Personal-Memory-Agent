const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=process.env.PMA_APP_ROOT||path.resolve(__dirname,'..'),script=process.env.PMA_UI_SCRIPT||path.join(root,'baseline.js');
function fixture(){
 const text='민수는 🌿 문서를 전달했다. 지연은 내일 검토한다.',quote='민수는 🌿 문서를 전달했다.',second='지연은 내일 검토한다.',at=text.indexOf(second),span=(start,value,extra={})=>({source_id:'S',revision:1,start,end:start+value.length,quote:value,...extra});
 const units=[{id:'F1',subject:'민수',relation:'전달',object:'문서',evidence:[span(0,quote)],highlights:[span(0,'민수',{role:'actor'}),span(text.indexOf('문서'),'문서',{role:'object'})],validation_errors:[]},{id:'F2',subject:'지연',relation:'검토',object:'문서',evidence:[span(at,second)],highlights:[span(at,'지연',{role:'actor'}),span(text.indexOf('내일'),'내일',{role:'time'})],validation_errors:[]}];
 const ext={records:[{source_id:'S',revision:1,text,units,gold:{highlights:[span(at,'지연',{role:'project'})]}}]},evidence={evidence_id:'E1',source_id:'S',revision:1,start:at,end:text.length,text:second};
 const result={question_id:'Q1',question:'누가 검토해?',status:'PENDING_REVIEW',stages:{extraction:ext,retrieval:{query_used:'검토',source_snapshots:[{id:'S',revision:1,text}],evidence:[evidence],lexical_candidates:[],vector_candidates:[],selected_sources:[{source_id:'S'}]},answer:{answer:'지연이 검토한다.',citations:[span(at,'지연',{evidence_id:'E1'})],evidence_used:[evidence]}}};
 return {run:{id:'RUN',config:{route:'S0'},stage:'end_to_end',question_ids:['Q1','Q2'],results:[result]},result,ext,text,at};
}
function harness(data=fixture()){
 const nodes=new Map(),listeners={},requests=[],pending=new Map();
 class Element{constructor(){this.innerHTML='';this.textContent='';this.value='';this.isConnected=true;this.hidden=true;this.dataset={};this.attrs={};this.classList={toggle(){},add(){},remove(){}};}setAttribute(k,v){this.attrs[k]=v;}removeAttribute(k){delete this.attrs[k];}addEventListener(){}scrollIntoView(){}querySelector(s){return el(s);}}
 const el=s=>{if(!nodes.has(s))nodes.set(s,new Element());return nodes.get(s);};
 const panel=el('.history-evidence-panel'),card=el('.history-row'),opener=el('opener');opener.dataset.historyEvidence='RUN';opener.closest=()=>card;
 const ctx=vm.createContext({console,setTimeout,clearTimeout,MemoryTiming:require(path.join(root,'timing.js')),document:{querySelector:el,querySelectorAll:()=>[],addEventListener:(k,v)=>(listeners[k]??=[]).push(v)},localStorage:{setItem(){}},fetch:async(url,opts)=>{assert.ok(!opts?.method,'History viewer must be read-only');requests.push(url);if(pending.has(url))return pending.get(url);if(url==='/api/baseline/runs/RUN')return {ok:true,json:async()=>structuredClone(data.run)};if(url==='/api/baseline/artifacts/EXT')return {ok:true,json:async()=>structuredClone(data.ext)};throw Error('Unexpected fetch '+url);}});
 vm.runInContext(fs.readFileSync(script,'utf8').replace('\ninitialize();','\n').replace('\ninitializeSelectionGuide();','\n'),ctx);
 const run=s=>vm.runInContext(s,ctx),click=async dataset=>{const button={dataset,hasAttribute:k=>k==='data-he-close'&&dataset.heClose!==undefined||k==='data-he-refresh'&&dataset.heRefresh!==undefined};for(const fn of listeners.click||[])await fn({target:{closest:s=>s.includes('[data-history-evidence]')?button:null}});};
 ctx.opener=opener;
 return {data,el,panel,opener,requests,pending,run,ctx,click};
}

test('history highlights use saved role spans and relationships, never gold or the current dataset',async()=>{
 const h=harness();await h.run('openHistoryEvidence(opener)');
 assert.equal(h.panel.hidden,false);assert.ok(h.panel.innerHTML.includes('<mark class="actor active"'));assert.ok(h.panel.innerHTML.includes('<mark class="object active"'));assert.ok(h.panel.innerHTML.includes('<mark class="time active"'));
 assert.ok(!h.panel.innerHTML.includes('<mark class="project'));assert.ok(h.panel.innerHTML.includes('→ 전달 →'));assert.ok(h.panel.innerHTML.includes('민수는 🌿 문서를 전달했다.'));
 assert.deepEqual(h.requests,['/api/baseline/runs/RUN']);
});

test('selecting a memory highlights only its source-linked spans, then toggles back to all memories',async()=>{
 const h=harness();await h.run('openHistoryEvidence(opener)');await h.click({heUnit:'0'});
 assert.equal((h.panel.innerHTML.match(/<mark class="actor/g)||[]).length,1);assert.ok(!h.panel.innerHTML.includes('<mark class="time'));
 await h.click({heUnit:'0'});assert.equal((h.panel.innerHTML.match(/<mark class="actor/g)||[]).length,2);
});

test('raw search and answer citations highlight only matching frozen original spans',async()=>{
 const f=fixture();delete f.result.stages.extraction;f.run.config.route='R0';const h=harness(f);await h.run('openHistoryEvidence(opener)');
 assert.match(h.panel.innerHTML,/<mark class="evidence active"[^>]*>지연은 내일 검토한다\.<\/mark>/);
 await h.click({heTab:'answer'});assert.ok(h.panel.innerHTML.includes('지연이 검토한다.'));assert.match(h.panel.innerHTML,/<mark class="evidence active"[^>]*>지연<\/mark>/);
});

test('mismatching quotes, stale revisions and invalid UTF16 offsets are never highlighted',async()=>{
 const f=fixture();f.ext.records[0].units=[{id:'BAD',subject:'wrong',evidence:[{source_id:'S',revision:2,start:0,end:2,quote:'민수'},{source_id:'S',revision:1,start:0,end:2,quote:'위조'}],highlights:[{start:999,end:1001,quote:'민수',role:'actor'}]}];
 const h=harness(f);await h.run('openHistoryEvidence(opener)');assert.ok(!h.panel.innerHTML.includes('<mark'));
});

test('evidence-only snapshots convert absolute offsets locally and explicitly disclose missing full originals',async()=>{
 const f=fixture();delete f.result.stages.extraction;delete f.result.stages.retrieval.source_snapshots;const h=harness(f);await h.run('openHistoryEvidence(opener)');await h.click({heTab:'answer'});
 assert.ok(h.panel.innerHTML.includes('원문 전체가 없는 기록'));assert.match(h.panel.innerHTML,/<mark class="evidence active"[^>]*>지연<\/mark>/);
 assert.ok(!h.panel.innerHTML.includes('민수는 🌿'));
});

test('unexecuted questions and missing snapshots remain empty rather than falling back to current data',async()=>{
 const h=harness();await h.run('openHistoryEvidence(opener)');h.el('[data-he-question]').value='Q2';await h.el('[data-he-question]').onchange();
 await new Promise(r=>setImmediate(r));assert.ok(h.panel.innerHTML.includes('이 질문은 아직 실행되지 않았습니다'));assert.ok(h.panel.innerHTML.includes('원문 스냅샷이 없습니다'));assert.ok(!h.panel.innerHTML.includes('<mark'));
 assert.equal(h.requests.length,1);
});

test('frozen artifacts are read lazily, and closing a pending read prevents reopening stale content',async()=>{
 const f=fixture();f.result.stages.extraction={artifact_id:'EXT',reused:true};const h=harness(f);await h.run('openHistoryEvidence(opener)');assert.deepEqual(h.requests,['/api/baseline/runs/RUN','/api/baseline/artifacts/EXT']);assert.ok(h.panel.innerHTML.includes('<mark'));
 await h.click({heClose:''});assert.equal(h.panel.hidden,true);assert.equal(h.opener.attrs['aria-expanded'],'false');
 let resolve;h.pending.set('/api/baseline/runs/RUN',new Promise(r=>resolve=r));const opening=h.run('openHistoryEvidence(opener)');await h.click({heClose:''});resolve({ok:true,json:async()=>f.run});await opening;assert.equal(h.panel.hidden,true);assert.equal(h.run('historyEvidence.run'),null);
});
