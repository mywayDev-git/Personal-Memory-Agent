const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {Store}=require('./store.cjs'),{Runtime}=require('./runtime.cjs'),{Engine}=require('./engine.cjs'),{download}=require('./download.cjs'),models=require('./model-registry.cjs'),prompts=require('./prompts.cjs');
const {buildAnswerEvaluation,validateAnswerReview}=require('./answer-evaluation.cjs');
const {buildReview,publicReview,validateReview,STAGES}=require('./review.cjs');
function createApi(root,options={}){
 const store=options.store||new Store(root),runtime=options.runtime||new Runtime(root),engine=new Engine(root,store,runtime),token=crypto.randomBytes(32).toString('hex');let setup=null,terminating=false,setupAbort=null;
 const summaryApi=require('./summary-api.cjs').createSummaryApi(engine,runtime);
 const json=(res,code,data)=>{res.writeHead(code,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'});res.end(JSON.stringify(data));};
 const body=async req=>{let size=0,parts=[];for await(const part of req){size+=part.length;if(size>200000)throw Error('요청 크기 초과');parts.push(part);}return JSON.parse(Buffer.concat(parts).toString()||'{}');};
 async function handle(req,res,url){
  if(!url.pathname.startsWith('/api/baseline/'))return false;
  try{
   const host=req.headers.host||'';if(!/^(127\.0\.0\.1|localhost):\d+$/.test(host))return json(res,403,{error:'로컬 호스트만 허용합니다.'}),true;
   if(req.headers.origin&&req.headers.origin!=='http://'+host)return json(res,403,{error:'다른 Origin의 요청은 허용하지 않습니다.'}),true;
   const route=url.pathname.slice('/api/baseline'.length);
   if(req.method==='GET'&&route.startsWith('/summary-memory'))return json(res,200,await summaryApi.get(route,url)),true;
   if(req.method==='GET'&&route==='/bootstrap')return json(res,200,{token,runtime:runtime.status(),prompts:{extraction:prompts.extractionPrompts,answer:prompts.answerPrompts,query:prompts.queryPrompts},datasets:['pma-dev-v0.1.0',...(fs.existsSync(path.join(root,'datasets','pma-dev-v0.2.0'))?['pma-dev-v0.2.0']:[]),...(fs.existsSync(path.join(root,'datasets','pma-long-v1.0.1','manifest.json'))?['pma-long-v1.0.1']:[]),...(fs.existsSync(path.join(root,'datasets','pma-long-v2.0.0','manifest.json'))?['pma-long-v2.0.0']:[]),...(fs.existsSync(path.join(root,'datasets','pma-context-v1.0.0','manifest.json'))?['pma-context-v1.0.0']:[]),...(fs.existsSync(path.join(root,'datasets','pma-memory-v2.0.0','manifest.json'))?['pma-memory-v2.0.0']:[]),...(fs.existsSync(path.join(root,'datasets','pma-memory-v3.0.0','manifest.json'))?['pma-memory-v3.0.0']:[]),...(fs.existsSync(path.join(root,'datasets','pma-generalization-v1.0.0','manifest.json'))?['pma-generalization-v1.0.0']:[])],busy:engine.busy,setup}),true;
   if(req.method==='GET'&&route==='/status')return json(res,200,{runtime:runtime.status(),busy:engine.busy,setup}),true;
   if(req.method==='GET'&&route==='/dataset'){const ds=await engine.dataset(url.searchParams.get('id')||undefined);return json(res,200,{...ds.d,fingerprint:ds.fingerprint}),true;}
   if(req.method==='GET'&&route==='/runs')return json(res,200,{runs:store.list(url.searchParams.get('trash')==='1')}),true;
   if(req.method==='GET'&&/^\/runs\/[^/]+\/review-export$/.test(route)){const id=route.split('/')[2];if(!store.run(id))throw Error('실행 기록 없음');return json(res,200,{version:'stage-review-v1',reviews:store.exportStageReviews(id)}),true;}
   if(req.method==='GET'&&/^\/runs\/[^/]+\/review-lab$/.test(route)){
    const id=route.split('/')[2],r=store.run(id);if(!r)throw Error('실행 기록 없음');
    let ds;try{ds=await engine.dataset(r.config.dataset);}catch{}
    r.reviews=store.reviews(id);const stage=url.searchParams.get('stage')||'extraction',catalog=buildReview(r,store,ds,stage),view=publicReview(catalog,url.searchParams.get('target'));
    if(view.selected)view.history=store.stageReviewHistory(id,stage,view.selected.target_key).map(h=>({revision:h.revision,verdict:h.verdict,review_state:h.review_state,reviewed_at:h.reviewed_at,reviewer:h.reviewer,notes:h.notes}));
    return json(res,200,view),true;
   }
   if(req.method==='GET'&&/^\/runs\/[^/]+\/token-usage$/.test(route)){const id=route.split('/')[2],run=store.run(id);if(!run)throw Error('실행 기록 없음');return json(res,200,{version:require('./token-usage.cjs').VERSION,report:run.token_usage||null,events:store.db.prepare('SELECT payload FROM token_usage_events WHERE operation_id=? ORDER BY at,id').all(id).map(r=>JSON.parse(r.payload))}),true;}
   if(req.method==='GET'&&/^\/runs\/[^/]+\/answer-evaluation$/.test(route)){const id=route.split('/')[2],run=store.run(id);if(!run)throw Error('실행 기록 없음');return json(res,200,buildAnswerEvaluation(run,store,url.searchParams.get('question'))),true;}
   if(req.method==='GET'&&/^\/runs\/[^/]+\/answer-review-export$/.test(route)){const id=route.split('/')[2];if(!store.run(id))throw Error('실행 기록 없음');return json(res,200,{version:'answer-evaluation-v2',reviews:store.exportAnswerReviews(id)}),true;}
   if(req.method==='GET'&&route.startsWith('/runs/')){const id=route.split('/')[2],r=store.run(id);if(!r)return json(res,404,{error:'실행 기록 없음'}),true;return json(res,200,{...r,reviews:store.reviews(id)}),true;}
   if(req.method==='GET'&&route.startsWith('/artifacts/'))return json(res,200,store.readArtifact(route.split('/')[2])),true;
   if(req.method!=='POST')return json(res,405,{error:'지원하지 않는 메서드'}),true;
   if(req.headers['x-memory-lab-token']!==token)return json(res,403,{error:'실행 토큰 오류. 화면을 새로고침하세요.'}),true;
   const data=await body(req);
   if(/^\/runs\/[^/]+\/stage-review$/.test(route)){
    const id=route.split('/')[2],r=store.run(id);if(!r||r.deleted_at)throw Error('검토할 실행 기록이 없습니다.');if(!STAGES.includes(data.stage))throw Error('검토 단계 오류');
    let ds;try{ds=await engine.dataset(r.config.dataset);}catch{}
    const catalog=buildReview(r,store,ds,data.stage),target=catalog.targets.find(t=>t.target_key===data.target_key);if(!target)throw Error('실제 실행에서 찾을 수 없는 판정 대상입니다.');
    const value=validateReview(target,data),review=store.putStageReview(id,value,data.base_revision||0);return json(res,200,{ok:true,review}),true;
   }
   if(/^\/runs\/[^/]+\/answer-review$/.test(route)){const id=route.split('/')[2],run=store.run(id);if(!run||run.deleted_at)throw Error('검토할 실행 기록 없음');const target=buildAnswerEvaluation(run,store,data.question_id).detail,value=validateAnswerReview(target,data);const review=store.putAnswerReview(id,value,data.base_revision||0);return json(res,200,{ok:true,review}),true;}
   if(route==='/runtime/processes')return json(res,200,await runtime.inspectProcesses()),true;
   if(route==='/runtime/terminate'){
    if(terminating)throw Error('프로세스 종료 확인 중입니다.');terminating=true;setupAbort?.abort();if(engine.busy)engine.cancel(engine.busy);
    try{const report=await runtime.forceStop();if(setup?.progress?.includes('모델 서버'))setup={status:'CANCELLED',progress:'모델 프로세스 종료 확인 완료'};json(res,200,{ok:true,report});}finally{terminating=false;}return true;
   }
   if(terminating)throw Error('모델 프로세스 종료를 확인하는 중입니다.');
   if(route.startsWith('/summary-memory')){if(setup?.status==='RUNNING')throw Error('모델 설정 작업 중입니다.');return json(res,200,await summaryApi.post(route,data)),true;}
   if(route==='/budget-preview'){if(setup?.status==='RUNNING')throw Error('모델 설정 작업 중입니다.');return json(res,200,await engine.previewBudget(data)),true;}
   if(route==='/models/download'){
    if(engine.busy||setup?.status==='RUNNING')throw Error('실행/설정 작업 중입니다.');const selected=models.filter(m=>(data.model_ids||[]).includes(m.id));if(!selected.length||selected.length!==(data.model_ids||[]).length)throw Error('모델 선택 오류');
    setup={status:'RUNNING',progress:'다운로드 준비'};setImmediate(async()=>{try{for(const m of selected)await download(m,root,p=>{setup={...setup,model_id:m.id,phase:p.phase,downloaded:p.downloaded,total:p.total,progress:m.name+' '+Math.floor(100*p.downloaded/p.total)+'%'};});setup.status='COMPLETED';setup.progress='해시 검증 완료';}catch(e){setup.status='ERROR';setup.error=e.message;}});return json(res,202,{setup}),true;
   }
   if(route==='/runtime/start'){
    if(engine.busy||setup?.status==='RUNNING')throw Error('실행/설정 작업 중입니다.');const config=engine.config(data);runtime.allowStart?.();setupAbort=new AbortController();const setupSignal=setupAbort.signal;setup={status:'RUNNING',progress:'모델 서버 로드'};setImmediate(async()=>{try{if(config.route==='R0-Full'&&runtime.stop)await runtime.stop('embedding');await runtime.ensure('generation',config.model,setupSignal);if(config.route!=='R0-Full')await runtime.ensure('embedding',config.embedding_model,setupSignal);setup.status='COMPLETED';setup.progress='모델 서버 준비 완료 · 아직 테스트 미실행';}catch(e){setup.status=setupSignal.aborted?'CANCELLED':'ERROR';setup.error=e.message;}finally{setupAbort=null;}});return json(res,202,{setup}),true;
   }
   if(route==='/runtime/stop'){if(engine.busy||setup?.status==='RUNNING')throw Error('실행/설정 작업 중입니다.');const report=await runtime.forceStop();return json(res,200,{ok:true,report}),true;}
   if(route==='/runs'){if(setup?.status==='RUNNING')throw Error('모델 설정이 끝난 뒤 실행하세요.');if(engine.busy)throw Error('현재 실행을 먼저 중단하세요.');runtime.allowStart?.();return json(res,202,await engine.create(data)),true;}
   if(/^\/runs\/[^/]+\/cancel$/.test(route)){engine.cancel(route.split('/')[2]);return json(res,200,{ok:true}),true;}
   if(/^\/runs\/[^/]+\/review$/.test(route)){const id=route.split('/')[2],run=store.run(id);if(!run||!run.results.some(r=>r.question_id===data.question_id&&r.status!=='NOT_APPLICABLE')||!['PASS','FAIL','PENDING_REVIEW'].includes(data.verdict))throw Error('판정 대상/값 오류');store.review(id,data.question_id,{verdict:data.verdict,notes:String(data.notes||'').slice(0,3000),reviewer:'local-user',config_hash:run.config_hash,dataset_fingerprint:run.dataset_fingerprint});return json(res,200,{ok:true}),true;}
   if(/^\/runs\/[^/]+\/freeze$/.test(route)){const id=route.split('/')[2],r=store.run(id);if(!r||!['COMPLETED','COMPLETED_WITH_ERRORS'].includes(r.status))throw Error('종료된 실행만 기준선으로 지정할 수 있습니다.');r.baseline={label:'baseline-v1',frozen_at:new Date().toISOString(),config_hash:r.config_hash,dataset_fingerprint:r.dataset_fingerprint,artifact_ids:[...new Set(r.results.flatMap(x=>Object.values(x.stages).map(s=>s.artifact_id)).filter(Boolean))],note:'고정된 비교 기준이며 의미 정확도 통과를 뜻하지 않습니다.'};store.putRun(r);return json(res,200,{ok:true}),true;}
   if(/^\/runs\/[^/]+\/(delete|restore)$/.test(route)){const id=route.split('/')[2],r=store.run(id);if(!r||engine.busy===id)throw Error('실행 중인 기록은 삭제할 수 없습니다.');r.deleted_at=route.endsWith('/delete')?new Date().toISOString():null;store.putRun(r);return json(res,200,{ok:true}),true;}
   json(res,404,{error:'지원하지 않는 API'});return true;
  }catch(e){json(res,400,{error:e.message,operation_id:e.operation_id,token_usage:e.token_usage,metadata_artifact_id:e.metadata_artifact_id,index_validation:e.index_validation});return true;}
 }
 return {handle,engine,store,runtime,close:async()=>{if(engine.abort)engine.abort.abort();await runtime.stopAll();store.db.close();}};
}
module.exports={createApi};
