const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os'),http=require('node:http'),vm=require('node:vm');
const {Store}=require('../local/store.cjs'),{Engine}=require('../local/engine.cjs'),{createApi}=require('../local/api.cjs'),{hash,validateCitations}=require('../local/core.cjs');
const {criteriaFor,automaticEvaluation,buildAnswerEvaluation,validateAnswerReview,citationDiagnostics}=require('../local/answer-evaluation.cjs');
const root=path.resolve(__dirname,'..'),evidence=[{evidence_id:'E1',source_id:'S1',revision:1,start:0,text:'민수는 계획했다. 지연은 완료했다. 계획했다.'}],gold={reference_answer:'민수는 계획했다.',required_claims:['민수는 계획했다.'],forbidden_claims:['민수 완료'],expected_action:'answer'};
const answer=(quote='계획했다.',action='answer')=>({action,answer:'민수는 계획했다.',citations:quote===null?[]:[{evidence_id:'E1',quote,occurrence:1}]});
function fixture(){const dir=fs.mkdtempSync(path.join(os.tmpdir(),'pma-answer-axes-')),store=new Store(dir),a={answer:'민수는 계획했다.',action:'answer',citations:[],citation_errors:['원문 불일치'],response:{parsed:answer('계획 했다.'),raw:'ORIGINAL RAW'},evidence_used:evidence,assessment:{status:'PENDING_REVIEW',...gold}},aid=store.artifact('answer',a),run={id:'R',created_at:'2026-11-05',status:'COMPLETED_WITH_ERRORS',stage:'end_to_end',config:{},config_hash:'cfg',dataset_fingerprint:'data',question_ids:['Q','EXCLUDED','ERROR'],results:[{question_id:'Q',question:'민수의 상태는?',status:'FAIL',stages:{answer:{...a,artifact_id:aid}}},{question_id:'EXCLUDED',status:'NOT_APPLICABLE',stages:{}},{question_id:'ERROR',status:'ERROR',error:'fetch failed',stages:{}}]};store.putRun(run);return {dir,store,run,cleanup(){this.store.db.close();fs.rmSync(dir,{recursive:true,force:true});}};}
const reviewInput=t=>({target_fingerprint:t.target_fingerprint,semantic:{verdict:'PASS',notes:'필수 의미와 추가 주장 확인'},citation:{verdict:'FAIL',notes:'공백이 다름'},action:{verdict:'PASS'},criteria_status:'confirmed',coverage_confirmed:true});
test('citation errors and valid quotes never automatically decide meaning; legacy validator default is unchanged',()=>{
 const c=criteriaFor({},'Q','질문',gold);for(const quote of ['계획했다.','계획 했다.',null]){const a=answer(quote),v=automaticEvaluation(a,evidence,c);assert.equal(v.axes.semantic.status,'PENDING_REVIEW');assert.equal(v.axes.citation.status,quote==='계획했다.'?'PASS':'FAIL');}
 assert.deepEqual(validateCitations(answer(null,'partial_answer'),evidence),{citations:[],errors:[]});
 for(const action of ['partial_answer','deny','report_conflict'])assert.equal(automaticEvaluation(answer(null,action),evidence,c).axes.citation.status,'FAIL');
 for(const action of ['abstain','clarify'])assert.equal(automaticEvaluation(answer(null,action),evidence,c).axes.citation.status,'NOT_APPLICABLE');
 assert.equal(automaticEvaluation(answer(null,'abstain'),evidence,c).axes.action.status,'TAG_MISMATCH');
});
test('v2 criteria bind dataset fingerprint, question and original gold; no blanket empty-evidence exemption',async()=>{
 const engine=new Engine(root,{recover(){}},{version:'offline'}),ds=await engine.dataset('pma-memory-v3.0.0'),run={dataset_fingerprint:ds.fingerprint};
 for(const id of ['CHAT-development-T4','CHAT-final-T4']){const q=ds.d.questions.questions.find(q=>q.id===id),c=criteriaFor(run,id,q.text,q.gold);assert.equal(c.citation_required,false);assert.equal(automaticEvaluation(answer(null),[],c).axes.citation.status,'NOT_APPLICABLE');assert.equal(criteriaFor({dataset_fingerprint:'changed'},id,q.text,q.gold).citation_required,true);assert.equal(criteriaFor(run,id,q.text+' changed',q.gold).citation_required,true);assert.equal(criteriaFor(run,id,q.text,{...q.gold,reference_answer:'changed'}).citation_required,true);}
 for(const id of ['MC-01-Q6','NR-F-03-Q1','NR-D-02-Q6']){const q=ds.d.questions.questions.find(q=>q.id===id),c=criteriaFor(run,id,q.text,q.gold);assert.notDeepEqual(c.effective.required_claims,c.original.required_claims);assert.deepEqual(c.original.required_claims,q.gold.required_claims);}
 const q=ds.d.questions.questions.find(q=>q.id==='STATE-final-replace');assert.equal(criteriaFor(run,q.id,q.text,q.gold).needs_revision,true);
 const c=criteriaFor(run,'unknown','7+5?',{...gold,evidence_groups:[]});assert.equal(c.citation_required,true);
});
test('raw invalid quotes, occurrence and disjoint wording remain diagnostics without repair',()=>{
 for(const [quote,occurrence,code]of [['계획 했다.',1,'WHITESPACE'],['계획했다.',3,'OCCURRENCE'],['민수…완료했다.',1,'NONCONTIGUOUS'],['없는 문구',1,'QUOTE_MISMATCH']]){const a=answer(quote);a.citations[0].occurrence=occurrence;assert.equal(citationDiagnostics(a,evidence)[0].code,code);assert.equal(a.citations[0].quote,quote);assert.equal(automaticEvaluation(a,evidence,criteriaFor({},'Q','?',gold)).axes.citation.status,'FAIL');}
 const a=answer();a.citations[0].evidence_id='NONE';assert.equal(citationDiagnostics(a,evidence)[0].code,'UNKNOWN_EVIDENCE');
});
test('append-only split reviews preserve all original rows, artifacts and legacy judgments across reopen',()=>{
 const f=fixture();try{const {store,run}=f;store.review('R','Q',{verdict:'FAIL',notes:'LEGACY'});store.putStageReview('R',{stage:'answer',target_key:'answer:Q',verdict:'FAIL',notes:'LEGACY STAGE'},0);
 const snapshot=()=>JSON.stringify([store.run('R'),store.reviews('R'),store.exportStageReviews('R')]),before=snapshot(),bytes=fs.readFileSync(path.join(store.dir,'artifacts',run.results[0].stages.answer.artifact_id+'.json'));
 let view=buildAnswerEvaluation(run,store,'Q');assert.equal(view.summary.answered,1);assert.equal(view.summary.excluded,1);assert.equal(view.summary.execution_error,1);assert.equal(view.summary.semantic_pending,1);assert.equal(view.detail.citation_diagnostics[0].quote,'계획 했다.');assert.equal(view.rows[0].original_status,'FAIL');
 const value=validateAnswerReview(view.detail,reviewInput(view.detail)),first=store.putAnswerReview('R',value,0);assert.equal(buildAnswerEvaluation(run,store).summary.semantic_pass,1);assert.equal(buildAnswerEvaluation(run,store).summary.citation_fail,1);assert.throws(()=>store.putAnswerReview('R',value,0),/다른 화면/);
 store.putAnswerReview('R',{...value,semantic:{verdict:'PENDING_REVIEW',notes:'다시 확인'}},first.revision);assert.equal(store.answerReviewHistory('R','Q').length,2);assert.equal(snapshot(),before);assert.deepEqual(fs.readFileSync(path.join(store.dir,'artifacts',run.results[0].stages.answer.artifact_id+'.json')),bytes);
 store.db.close();f.store=new Store(f.dir);assert.equal(f.store.exportAnswerReviews('R').length,2);assert.equal(JSON.stringify([f.store.run('R'),f.store.reviews('R'),f.store.exportStageReviews('R')]),before);
 }finally{f.cleanup();}
});
test('meaning decisions require confirmed criteria and comprehensive review; citation cannot be a meaning reason',()=>{
 const f=fixture();try{const t=buildAnswerEvaluation(f.run,f.store,'Q').detail,v=reviewInput(t);assert.equal(validateAnswerReview(t,v).semantic.verdict,'PASS');
 for(const input of [{...v,target_fingerprint:'bad'},{...v,coverage_confirmed:false},{...v,criteria_status:'issue'},{...v,semantic:{verdict:'FAIL',reason:'CITATION',notes:'bad quote'}},{...v,semantic:{verdict:'PARTIAL',reason:'OMISSION',notes:''}}])assert.throws(()=>validateAnswerReview(t,input));
 assert.throws(()=>validateAnswerReview({...t,criteria:{...t.criteria,needs_revision:true}},v),/모호/);
 const pending=validateAnswerReview({...t,criteria:{...t.criteria,needs_revision:true}},{...v,semantic:{verdict:'PENDING_REVIEW'},criteria_status:'issue',coverage_confirmed:false});assert.equal(pending.criteria_status,'issue');
 const fail=validateAnswerReview(t,{...v,semantic:{verdict:'FAIL',reason:'STATE',notes:'예정을 완료로 바꿈'}});assert.equal(fail.semantic.reason,'STATE');
 }finally{f.cleanup();}
});
test('new table migration does not rewrite old tables and stale reviews are never reused',()=>{
 const f=fixture();try{const t=buildAnswerEvaluation(f.run,f.store,'Q').detail;f.store.putAnswerReview('R',{...validateAnswerReview(t,reviewInput(t)),target_fingerprint:'stale'},0);const r=buildAnswerEvaluation(f.run,f.store,'Q');assert.equal(r.detail.review,null);assert.equal(r.detail.stale_review,true);assert.equal(r.detail.semantic_status,'PENDING_REVIEW');assert.ok(r.detail.review_revision>0);
 const before=JSON.stringify(f.store.run('R'));f.store.db.exec('DROP TABLE answer_review_events');f.store.db.close();f.store=new Store(f.dir);assert.equal(JSON.stringify(f.store.run('R')),before);assert.deepEqual(f.store.answerReviews('R'),[]);
 }finally{f.cleanup();}
});
test('split-review API is protected and never loads models, changes old judgments, or records executions',async()=>{
 const f=fixture(),runtime={version:'OFFLINE',status:()=>({}),stopAll:async()=>{},ensure:async()=>{throw Error('unexpected model call');}},api=createApi(f.dir,{store:f.store,runtime}),server=http.createServer((req,res)=>api.handle(req,res,new URL(req.url,'http://'+req.headers.host)));
 await new Promise(r=>server.listen(0,'127.0.0.1',r));const base='http://127.0.0.1:'+server.address().port+'/api/baseline',get=async route=>(await fetch(base+route)).json();
 try{const before=JSON.stringify(f.store.run('R')),boot=await get('/bootstrap'),p=await get('/runs/R/answer-evaluation?question=Q'),body={...reviewInput(p.detail),question_id:'Q',base_revision:0},post=headers=>fetch(base+'/runs/R/answer-review',{method:'POST',headers:{'Content-Type':'application/json',...headers},body:JSON.stringify(body)});
 assert.equal((await post({})).status,403);assert.equal((await post({'X-Memory-Lab-Token':boot.token,Origin:'http://elsewhere'})).status,403);assert.equal((await post({'X-Memory-Lab-Token':boot.token})).status,200);assert.equal((await post({'X-Memory-Lab-Token':boot.token})).status,400);
 assert.equal((await get('/runs/R/answer-review-export')).reviews.length,1);assert.equal((await get('/runs/R/answer-evaluation')).summary.semantic_pass,1);assert.equal(JSON.stringify(f.store.run('R')),before);assert.equal(f.store.reviews('R').length,0);assert.equal(f.store.exportStageReviews('R').length,0);
 }finally{await new Promise(r=>server.close(r));f.cleanup();}
});
function ui(){const elements=new Map(),el=s=>{if(!elements.has(s))elements.set(s,{innerHTML:'',value:'',checked:false,isConnected:true,insertAdjacentHTML(){},querySelector:el});return elements.get(s);},ctx=vm.createContext({document:{querySelector:el,querySelectorAll:()=>[],addEventListener(){}},console,structuredClone,page:'answer-evaluation',esc:x=>String(x??'').replaceAll('<','&lt;'),statusNames:{},notify(){},api:async()=>{throw Error('unexpected request');}});let script=fs.readFileSync(path.join(root,'answer-evaluation.js'),'utf8');script=script.replace(/\}\)\(\);\s*$/,'globalThis.unit={state,filtered,mark,load,draft,panel,save,capture};})();');ctx.$=el;vm.runInContext(script,ctx);return {ctx,el,u:ctx.unit};}
test('new review UI filters the entire list and highlights the actual occurrence without injecting text',()=>{
 const {u}=ui();u.state.payload={rows:Array.from({length:671},(_,i)=>({question_id:'Q'+i,question:'문항',has_answer:true,citation_status:i<100?'FAIL':'PASS',semantic_status:'PENDING_REVIEW'}))};assert.equal(u.filtered().length,671);u.state.filter='citation';assert.equal(u.filtered().length,100);u.state.filter='pending';assert.equal(u.filtered().length,671);u.state.query='Q670';assert.equal(u.filtered().length,1);assert.equal(u.mark('ab ab<',[{start:3,end:5}]),'ab <mark>ab</mark>&lt;');
});
test('late reads cannot overwrite another question, and drafts survive polling and navigation',async()=>{
 const {ctx,el,u}=ui();let release;ctx.api=route=>route.includes('question=Q1')?new Promise(r=>release=r):Promise.resolve({summary:{},note:'',run:{id:'R'},rows:[{question_id:'Q2',question:'two',has_answer:false}],detail:null});const p=u.load('R','Q1');await u.load('R','Q2');release({run:{id:'WRONG'},rows:[]});await p;assert.equal(u.state.qid,'Q2');assert.equal(u.state.payload.run.id,'R');u.state.detail={review:null,has_answer:true};const d=u.draft();d.semantic.notes='작성중';u.state.qid='Q3';u.draft();u.state.qid='Q2';assert.equal(u.draft().semantic.notes,'작성중');assert.equal(el('#ae-detail').innerHTML.includes('답변 산출물'),true);
 assert.ok(!fs.readFileSync(path.join(root,'answer-evaluation.js'),'utf8').includes('setInterval'));
});
