const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'..');
function harness(){
 const nodes=new Map(),requests=[];
 class Element{
  constructor(){this.innerHTML='';this.textContent='';this.value='';this.scrollTop=0;this.scrollLeft=0;this.details=[];this.writes=0;}
  querySelectorAll(s){return s==='details'?this.details:[];}
 }
 const el=s=>{if(!nodes.has(s))nodes.set(s,new Element());return nodes.get(s);};
 const ctx=vm.createContext({console,document:{querySelector:el,querySelectorAll:()=>[],addEventListener(){}},localStorage:{setItem(){}},setTimeout,clearTimeout,MemoryTiming:{format:()=>'',elapsed:()=>0,isActive:()=>false}});
 vm.runInContext(fs.readFileSync(path.join(root,'baseline.js'),'utf8').replace('\ninitialize();','\n').replace('\ninitializeSelectionGuide();','\n'),ctx);
 const run=s=>vm.runInContext(s,ctx);
 ctx.responses={};ctx.requests=requests;
 run(`api=async route=>{requests.push(route);const x=responses[route];return typeof x==='function'?await x():structuredCloneForTest(x);};
 showRuntime=s=>{lastStatus=s;busyId=s.busy;};renderStageHelp=()=>{};renderTrace=()=>{};renderDialogueVerdict=()=>{};renderExecutionMonitor=r=>{globalThis.monitor=r;};updateTimingLabels=()=>{};notify=()=>{};
 globalThis.renders=[];globalThis.workspacePaints=0;renderWorkspace=()=>workspacePaints++;
 globalThis.originalRenderResult=renderResult;renderResult=(r,refresh)=>renders.push({r,refresh});
 data={questions:{questions:[{id:'Q',context_id:'C'}]},contexts:{contexts:[{id:'C'}]}};questionId='Q';
 shownRun={id:'VIEW',status:'RUNNING',results:[],reviews:[]};`);
 ctx.structuredCloneForTest=structuredClone;
 return {ctx,run,el,requests};
}
const record=(id,status='RUNNING')=>({id,status,results:[{question_id:'Q',status:'PENDING_REVIEW',stages:{answer:{answer:'new'}}}],reviews:[],progress:'검색 중'});
test('answer criteria show frozen expected answer, required and forbidden meaning beside citations',()=>{
 const h=harness();h.ctx.answer={answer:'답변',action:'answer',elapsed_ms:1,citations:[{source_id:'S',evidence_id:'E',quote:'인용',start:0,end:2}],citation_errors:[],omitted_by_token_budget:[],assessment:{status:'PENDING_REVIEW',provenance_valid:true,reference_answer:'실행 당시 정답 <확인>',required_claims:['반드시 포함'],forbidden_claims:['주장 금지'],expected_action:'answer'}};
 const html=h.run('answerHTML(answer)');assert.ok(html.includes('answer-review-layout'));assert.ok(html.includes('data-citation="S"'));for(const text of ['실행 당시 정답 &lt;확인&gt;','반드시 포함','주장 금지','실행 당시 저장된 작성자 초안'])assert.ok(html.includes(text));
 h.ctx.answer.assessment={status:'PENDING_REVIEW'};assert.ok(h.run('answerCriteriaHTML(answer)').includes('현재 데이터셋의 정답으로 대체하지 않습니다'));
});
test('active progress never replaces another selected run or dataset browser',async()=>{
 const h=harness();h.ctx.responses={'/status':{busy:'ACTIVE'},'/runs/ACTIVE':record('ACTIVE')};h.run("page='datasets'");await h.run('tick()');assert.equal(h.run('shownRun.id'),'VIEW');assert.equal(h.ctx.monitor.id,'ACTIVE');assert.equal(h.ctx.renders.length,0);assert.equal(h.ctx.workspacePaints,0);
});
test('same selected result refreshes only result content while filters and draft remain intact',async()=>{
 const h=harness();h.el('#review-notes').value='작성 중인 메모';h.el('#question-search').value='필터';h.ctx.responses={'/status':{busy:'VIEW'},'/runs/VIEW':record('VIEW')};await h.run('tick()');assert.equal(h.ctx.renders.length,1);assert.equal(h.ctx.renders[0].refresh,true);assert.equal(h.ctx.workspacePaints,0);assert.equal(h.el('#review-notes').value,'작성 중인 메모');assert.equal(h.el('#question-search').value,'필터');
});
test('judgment criteria default to expanded, including the workbench sidebar',()=>{
 const h=harness();h.ctx.q={gold:{expected_action:'answer',reference_answer:'기준',required_claims:['필수'],forbidden_claims:[],evidence_groups:[]}};h.run('renderGold(q)');assert.ok(h.el('#gold-panel').innerHTML.includes('<details open><summary>예상 답변과 필수 사실 보기'));
});
test('an in-progress search filter, focus, caret and open sections survive content refresh',()=>{
 const h=harness();let focused=0,filtered=0,selection;
 const input={id:'',name:'',value:'지연',checked:false,selectionStart:1,selectionEnd:2,getAttribute:()=> '근거 필터',hasAttribute:()=>true,focus:()=>focused++,setSelectionRange:(a,b)=>selection=[a,b]};
 const panel={innerHTML:'old',scrollTop:45,scrollLeft:0,querySelectorAll:s=>s==='details'?[{open:true}]:[input]};
 h.ctx.panel=panel;h.ctx.document.activeElement=input;h.ctx.filtered=()=>filtered++;h.run('filterCandidateChannel=()=>filtered();preservePanelHTML(panel,"new")');assert.equal(input.value,'지연');assert.equal(focused,1);assert.equal(filtered,1);assert.deepEqual(selection,[1,2]);assert.equal(panel.scrollTop,45);
});
test('delayed response cannot overwrite a newly selected saved run',async()=>{
 const h=harness();let release;h.ctx.responses={'/status':{busy:'VIEW'},'/runs/VIEW':()=>new Promise(r=>release=r)};const pending=h.run('tick()');await new Promise(r=>setImmediate(r));h.run("shownRun={id:'OTHER',results:[]}");release(record('VIEW'));await pending;assert.equal(h.run('shownRun.id'),'OTHER');assert.equal(h.ctx.renders.length,0);
});
test('changing dataset during a request suppresses the old result',async()=>{
 const h=harness();let release;h.ctx.responses={'/status':{busy:'VIEW'},'/runs/VIEW':()=>new Promise(r=>release=r)};const pending=h.run('tick()');await new Promise(r=>setImmediate(r));h.run('datasetLoadRequest++');release(record('VIEW'));await pending;assert.equal(h.ctx.renders.length,0);assert.equal(h.run('shownRun.results.length'),0);
});
test('result live update keeps the review editor and disclosure state',()=>{
 const h=harness();h.ctx.result={question_id:'Q',status:'PENDING_REVIEW',stages:{}};h.el('#review-notes').value='메모';h.el('#result-panel').innerHTML='stable review editor';h.el('#result-live').details=[{open:true},{open:false}];h.el('#result-live').scrollTop=34;
 h.run('resultTimingHTML=()=>"";originalRenderResult(result,true)');assert.equal(h.el('#result-panel').innerHTML,'stable review editor');assert.equal(h.el('#review-notes').value,'메모');assert.equal(h.el('#result-live').scrollTop,34);assert.deepEqual(h.el('#result-live').details.map(d=>d.open),[true,false]);
});
test('completion while reading another page does not repaint the workspace or history',async()=>{
 const h=harness();h.run("page='review';monitoredRun=shownRun;refreshHistory=()=>{throw Error('background history repaint')}");h.ctx.responses={'/status':{busy:null},'/runs/VIEW':record('VIEW','COMPLETED')};await h.run('tick()');assert.equal(h.run('shownRun.status'),'COMPLETED');assert.equal(h.ctx.renders.length,0);assert.equal(h.ctx.workspacePaints,0);assert.ok(h.requests.every(r=>['/status','/runs/VIEW'].includes(r)));
});
