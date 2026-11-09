const {hash,sentences,validateNative}=require('./core.cjs');
const STAGES=['extraction','retrieval','answer'];
const VERSION='stage-review-v1';
const CODES={
 'EXEC.MODEL':'모델 준비 실패','EXEC.CONNECTION':'서버·통신 오류','EXEC.RESOURCE':'확인된 자원 부족','EXEC.BUDGET':'입출력 한도 초과','EXEC.STORAGE':'저장·읽기 실패','EXEC.CONTROL':'실행 제어 오류',
 'OUTPUT.PARSE':'출력 해석 실패','OUTPUT.SCHEMA':'출력 형식·자료형 오류',
 'EXTRACT.EVIDENCE':'원문 근거 불일치','EXTRACT.HIGHLIGHT':'하이라이트 위치 불일치','EXTRACT.OMISSION':'의미 누락','EXTRACT.ADDITION':'원문에 없는 의미 추가','EXTRACT.MEANING':'역할·관계·부정·시간 의미 오류','EXTRACT.IDENTITY':'개체·사건 연결 오류',
 'SEARCH.ROUTE':'검색 필요 여부 오판','SEARCH.QUERY':'검색 질문 변형','SEARCH.FILTER':'검색 조건 오류','SEARCH.INDEX':'색인·임베딩 오류','SEARCH.RANK':'필요 근거 검색 실패','SEARCH.SELECTION':'근거 선택 오류','SEARCH.RESTORE':'원문 근거 복원 오류',
 'ANSWER.FACT':'근거 없는 주장','ANSWER.OMISSION':'답변 내용 누락','ANSWER.ACTION':'응답 행동 오류','ANSWER.CITATION':'인용 오류','ANSWER.CONSISTENCY':'답변 모순','ANSWER.TURN':'대화 턴 오류',
 'STATE.ACCESS':'접근 범위 위반','STATE.CONSENT':'저장 동의 위반','STATE.REVISION':'기억·색인 버전 불일치','STATE.CONTEXT':'대화 맥락 오류',
 'EVAL.GOLD':'판정 기준 수정 필요','EVAL.JUDGE':'판정 로직 오류','EVAL.OBSERVATION':'관측 기록 부족','EVAL.METRIC':'지표 계산 오류','EVAL.INTEGRITY':'평가 무결성 오류','EVAL.DISPLAY':'결과 표시 오류'
};
function errorCode(message=''){
 if(/하이라이트/.test(message))return 'EXTRACT.HIGHLIGHT';
 if(/원문 근거|근거 문구/.test(message))return 'EXTRACT.EVIDENCE';
 if(/한도|토큰|잘린 출력/.test(message))return 'EXEC.BUDGET';
 if(/JSON 파싱|텍스트 응답 누락/.test(message))return 'OUTPUT.PARSE';
 if(/스키마|문자열 누락|값 오류|배열 누락/.test(message))return 'OUTPUT.SCHEMA';
 if(/임베딩|벡터/.test(message))return 'SEARCH.INDEX';
 if(/포트|파일 해시|다운로드|llama-server.*찾/.test(message))return 'EXEC.MODEL';
 if(/fetch failed|준비되지|서버.*종료|HTTP|시간 초과|aborted|cancelled/i.test(message))return 'EXEC.CONNECTION';
 if(/산출물|context|기억 범위|구버전/.test(message))return 'STATE.REVISION';
 return 'EXEC.CONTROL';
}
const CHECK_LABELS={'OUTPUT.SCHEMA':'출력 형식·자료형','EXTRACT.EVIDENCE':'원문 근거 위치','EXTRACT.HIGHLIGHT':'하이라이트 위치','ANSWER.CITATION':'인용 위치·버전','SEARCH.RESTORE':'원문 근거 복원','SEARCH.RANK':'필요 근거 포함 측정'};
const check=(code,status,detail)=>({code,label:CHECK_LABELS[code]||CODES[code]||code,status,detail});
function extractionChecks(validated){
 const errors=validated.errors||[];
 return [check('OUTPUT.SCHEMA','PASS','모델 출력 스키마 검사 통과'),check('EXTRACT.EVIDENCE',errors.some(e=>/근거/.test(e))?'FAIL':'PASS',errors.filter(e=>/근거/.test(e)).join('; ')||'근거 문장·문구·등장 순서 검사 통과'),check('EXTRACT.HIGHLIGHT',errors.some(e=>/하이라이트/.test(e))?'FAIL':'PASS',errors.filter(e=>/하이라이트/.test(e)).join('; ')||'하이라이트 구절 위치 검사 통과')];
}
function getArtifact(store,value){if(!value)return null;return value.artifact_id?store.readArtifact(value.artifact_id):value;}
function nativeUnits(method,native){
 if(!native||typeof native!=='object')return [];
 if(method==='events')return (Array.isArray(native.events)?native.events:[]).map((x,i)=>({...x,id:'EV'+(i+1),subject:x.actor,relation:x.action}));
 if(method==='entities')return [...(Array.isArray(native.entities)?native.entities:[]).flatMap((e,i)=>(Array.isArray(e.attributes)?e.attributes:[]).map((a,j)=>({...a,id:`EN${i+1}-A${j+1}`,subject:e.name,object:a.value}))),...(Array.isArray(native.relationships)?native.relationships:[]).map((r,i)=>({...r,id:'REL'+(i+1)}))];
 return (Array.isArray(native.facts)?native.facts:[]).map((x,i)=>({...x,id:'F'+(i+1)}));
}
function recordView(record,source,method){
 let validated;try{if(record.native&&source)validated=validateNative(method,record.native,source);}catch{}
 const rawUnits=record.units?.length?record.units:validated?.units||nativeUnits(method,record.native);
 const original=nativeUnits(method,record.native);
 return rawUnits.filter(u=>u&&typeof u==='object').map(u=>({...u,model_evidence:original.find(x=>x.id===u.id)?.evidence||[],model_mentions:original.find(x=>x.id===u.id)?.mentions||[],evidence:Array.isArray(u.evidence)?u.evidence:[],highlights:Array.isArray(u.highlights)?u.highlights:[]}));
}
function buildReview(run,store,ds,stage){
 if(!STAGES.includes(stage))throw Error('검토 단계가 올바르지 않습니다.');
 const compatible=ds?.fingerprint===run.dataset_fingerprint;
 const sources=compatible?ds.d.sources.records:[],questions=compatible?ds.d.questions.questions:[];
 const latest=store.stageReviews(run.id,stage),reviews=new Map(latest.map(r=>[r.target_key,r]));
 const targets=[],byKey=new Map();
 const artifactCache=new Map(),loadArtifact=value=>{if(!value?.artifact_id)return value||null;if(!artifactCache.has(value.artifact_id))artifactCache.set(value.artifact_id,store.readArtifact(value.artifact_id));return artifactCache.get(value.artifact_id);};
 const sourceById=id=>sources.find(s=>s.id===id);
 function add(t,r){
  const existing=byKey.get(t.target_key);if(existing){if(!existing.question_ids.includes(r.question_id))existing.question_ids.push(r.question_id);return;}
  t.stage=stage;t.question_ids=[r.question_id];t.config_hash=run.config_hash;t.dataset_fingerprint=run.dataset_fingerprint;
  t.fingerprint=hash({version:VERSION,run:run.id,stage,key:t.target_key,config:run.config_hash,dataset:run.dataset_fingerprint,sources:t.sources,units:t.units,expected:t.expected,question_gold:t.question_gold,gold_available:t.gold_available,answer:t.answer,checks:t.checks});
  const review=reviews.get(t.target_key);t.review=review?.target_fingerprint===t.fingerprint?review:null;t.stale_review=!!review&&!t.review;t.previous_review_revision=review?.revision||0;
  targets.push(t);byKey.set(t.target_key,t);
 }
 for(const r of run.results||[]){
  if(stage==='extraction'){
   let ext;try{ext=loadArtifact(r.stages?.extraction);}catch(e){add({target_key:'unreadable:'+r.question_id,title:r.question_id,status:'ERROR',bound:false,has_output:false,sources:[],units:[],expected:[],checks:[check('EXEC.STORAGE','ERROR',e.message)],raw:''},r);continue;}
   if(ext&&Array.isArray(ext.records)&&ext.records.length===0&&(r.accessible_source_ids||[]).length===0&&!r.error)continue;
   if(ext?.records?.length){
    for(const record of ext.records){
     const same=byKey.get((r.stages.extraction.artifact_id||'inline:'+r.question_id)+':'+record.source_id);if(same){if(!same.question_ids.includes(r.question_id))same.question_ids.push(r.question_id);continue;}
     if(ext.kind==='summary-only-v1'){
      let original;try{original=store.readArtifact(record.original_artifact_id).source;}catch{}
      const registered=sourceById(record.source_id),gold=registered&&registered.revision===record.revision&&registered.text===original?.text?registered.gold:null;
      add({target_key:(r.stages.extraction.artifact_id||'inline:'+r.question_id)+':'+record.source_id,title:record.source_id,source_id:record.source_id,status:record.valid?'COMPLETED':'ERROR',bound:!!original,has_output:!!record.summary,gold_available:!!gold,sources:original?[{...original,gold}]:[],units:[{id:'SUMMARY',subject:record.source_id,relation:'자연어 요약',object:record.summary,evidence:[],highlights:[],model_evidence:[],model_mentions:[]}],expected:gold?.facts||[],checks:[check('OUTPUT.SCHEMA',record.valid?'PASS':'ERROR','자연어 요약 형식 검사. 의미 보존은 사람 검토 필요'),check('EXTRACT.EVIDENCE','NOT_OBSERVED','생성 요약은 원본 구간 일치 검사 대상이 아님')],raw:record.summary,method:'summary',origin:'saved',empty_output:!record.summary},r);continue;
     }
     const registered=sourceById(record.source_id),snap=record.source_snapshot;
     const source=snap?{...snap}:record.text!==undefined?{id:record.source_id,revision:record.revision,text:record.text,metadata:registered?.metadata,gold:registered?.text===record.text&&registered.revision===record.revision?registered.gold:null}:null;
     const native=record.native||record.response?.parsed;
     const displayed={...record,native};
     const checks=record.checks||[check('OUTPUT.SCHEMA',record.valid===true?'PASS':'NOT_OBSERVED','기존 산출물의 저장된 검증 결과'),check('EXTRACT.EVIDENCE',record.errors?.some(e=>/근거/.test(e))?'FAIL':record.valid===true?'PASS':'NOT_OBSERVED',(record.errors||[]).filter(e=>/근거/.test(e)).join('; ')||'저장된 원문 근거 검사 결과'),check('EXTRACT.HIGHLIGHT',record.errors?.some(e=>/하이라이트/.test(e))?'FAIL':record.valid===true?'PASS':'NOT_OBSERVED',(record.errors||[]).filter(e=>/하이라이트/.test(e)).join('; ')||'저장된 하이라이트 검사 결과')];
     if(record.error&&!record.cancelled&&!checks.some(c=>['FAIL','ERROR'].includes(c.status)))checks.push(check(record.error_code||errorCode(record.error),'ERROR',record.error));
     add({target_key:(r.stages.extraction.artifact_id||'inline:'+r.question_id)+':'+record.source_id,title:record.source_id,source_id:record.source_id,status:record.cancelled?'CANCELLED':record.error?'ERROR':record.valid===false?'VALIDATION_FAILED':'COMPLETED',bound:!!source,has_output:!!native,gold_available:!!source?.gold,sources:source?[source]:[],units:recordView(displayed,source,ext.config?.method||run.config.method),expected:source?.gold?.facts||[],checks,raw:record.response?.raw||record.raw_error_output||JSON.stringify(native||{},null,2),method:ext.config?.method||run.config.method,origin:'saved',empty_output:!!native&&!nativeUnits(ext.config?.method||run.config.method,native).length},r);
    }
   }else if(r.raw_error_output&&/구조화 검증|하이라이트|근거 문구/.test(r.error||'')){
    // Older failures did not save their source ID. Bind only a unique recorded scope.
    const source=r.accessible_source_ids?.length===1?sourceById(r.accessible_source_ids[0]):null;
    let native;try{native=JSON.parse(r.raw_error_output);}catch{}
    const details=(r.error||'').replace(/^원문 근거\/구조화 검증 실패:\s*/,'').split('; ').filter(Boolean);
    add({target_key:'legacy:'+r.question_id,title:source?.id||r.question_id+' · 원문 미확정',source_id:source?.id,status:'VALIDATION_FAILED',bound:!!source,has_output:!!native,gold_available:!!source?.gold,sources:source?[source]:(r.accessible_source_ids||[]).map(sourceById).filter(Boolean),units:recordView({native},source,run.config.method),expected:source?.gold?.facts||[],checks:details.map(detail=>check(errorCode(detail),'FAIL',detail)),raw:r.raw_error_output,method:run.config.method,origin:'legacy',warning:source?'기존 실패 출력 재표시 · 당시 원문은 데이터셋 해시 일치로 확인했습니다. 원래 판정은 유지됩니다.':'기존 기록에는 실패한 원문 ID가 없습니다. 원문을 임의 연결하지 않으며 의미 판정 저장은 제한합니다.'},r);
   }else if(run.stage==='extract'||run.stage==='end_to_end'&&!['R0','R0-Full'].includes(run.config.route)){
    add({target_key:'no-output:'+r.question_id,title:r.question_id,status:r.error?'ERROR':'NOT_RUN',bound:false,has_output:false,sources:[],units:[],expected:[],checks:r.error?[check(r.error_code||errorCode(r.error),'ERROR',r.error)]:[],raw:r.raw_error_output||'',warning:'이 기록에는 검토할 구조화 출력이 저장되지 않았습니다.'},r);
   }
  }else{
   let artifact;try{artifact=loadArtifact(r.stages?.[stage]);}catch(e){artifact={load_error:e.message};}
   const q=questions.find(q=>q.id===r.question_id),available=(r.accessible_source_ids||[]).map(sourceById).filter(Boolean);
   let used=stage==='answer'?artifact?.evidence_used:artifact?.evidence;
   used=Array.isArray(used)?used:[];
   const storedSources=artifact?.kind==='summary-only-v1'?(artifact.summary_records||[]).map(r=>({id:r.source_id,revision:r.revision,text:r.summary,basis:'summary',summary_id:r.summary_id})):(artifact?.source_snapshots||[]);
   const reviewSources=stage==='answer'?used.map(e=>({id:e.source_id,revision:e.revision,text:e.text,metadata:e.metadata,evidence_only:true,start:e.start})):storedSources.length?storedSources:available;
   let expected=stage==='answer'?(artifact?.assessment?{reference_answer:artifact.assessment.reference_answer,required_claims:artifact.assessment.required_claims,forbidden_claims:artifact.assessment.forbidden_claims,expected_action:artifact.assessment.expected_action,...(artifact.assessment.structured_expectations?{structured_expectations:artifact.assessment.structured_expectations,annotation_status:artifact.assessment.annotation_status,coverage:artifact.assessment.coverage}:{})}:null):q?.gold;
   if(!expected&&q)expected=q.gold;
   let checks=[];
   if(artifact?.load_error)checks=[check('EXEC.STORAGE','ERROR',artifact.load_error)];
   else if(artifact){
    if(artifact.kind==='summary-only-v1'){checks=[check('SEARCH.INDEX','PASS','요약문만 색인·검색. 원본 복원 없음'),check('SEARCH.RANK',artifact.metrics?.required_groups>0?'MEASURED':'NOT_MEASURED','요약 출처 발견 측정. 원본 구간 포함은 해당 없음')];}
    else if(artifact.delivery){checks=[check('SEARCH.RANK','NOT_MEASURED','R0-Full 검색 생략: Recall·MRR은 해당 없음'),check('EXEC.BUDGET',artifact.delivery.budget.eligible?'PASS':'NOT_APPLICABLE',JSON.stringify(artifact.delivery.budget))];}
     else if(stage==='answer')checks=[check('OUTPUT.SCHEMA','PASS','저장된 답변 형식 검사 결과'),check('ANSWER.CITATION',artifact.citation_errors?.length?'FAIL':'PASS',(artifact.citation_errors||[]).join('; ')||'저장된 인용 위치 검사 통과. 의미적 근거 충족은 사람 검토 필요')];
    else checks=[check('SEARCH.RESTORE','PASS','저장된 검색·원문 복원 산출물'),check('SEARCH.RANK',artifact.metrics?.required_groups>0?'MEASURED':'NOT_MEASURED',artifact.metrics?.required_groups>0?`필요 근거 그룹 ${artifact.metrics.required_groups}개 중 원문 포함 ${artifact.metrics.source_groups_found}개. 원문 수 ${artifact.source_refs?.length||0}개 / Top-K ${artifact.config?.top_k||run.config.top_k}. 의미 정확도 지표가 아닙니다.`:'필요 근거 주석이 없는 경우 미측정')];
   }else if(r.error){const failedExtraction=r.error_stage==='extraction'||['ERROR','VALIDATION_FAILED'].includes(r.stages?.extraction?.extraction_state)||/구조화 검증|하이라이트 문구/.test(r.error);const upstream=stage==='answer'&&!r.stages?.retrieval||stage==='retrieval'&&(failedExtraction||!r.stages?.extraction&&!['R0','R0-Full'].includes(run.config.route));checks=[check(r.error_code||errorCode(r.error),upstream?'BLOCKED':'ERROR',(upstream?'상위 단계 실패로 미실행: ':'')+r.error)];}
   const notApplicable=r.status==='NOT_APPLICABLE',hasOutput=!!artifact&&!artifact.load_error&&!notApplicable;
    if(notApplicable)checks=[check('EXEC.BUDGET','NOT_APPLICABLE',r.error||'전체 제공 예산 초과')];
   add({target_key:stage+':'+r.question_id,title:r.question_id,question:r.question||q?.text||r.question_id,status:notApplicable?'NOT_APPLICABLE':hasOutput?'COMPLETED':checks.some(c=>c.status==='BLOCKED')?'BLOCKED':r.error?'ERROR':'NOT_RUN',bound:true,has_output:hasOutput,gold_available:!!expected,sources:reviewSources,units:hasOutput?[{id:'RESULT',subject:r.question_id,relation:stage==='answer'?'답변':'검색',object:''}]:[],expected:[],question_gold:expected,checks,answer:artifact?.answer,action:artifact?.action,citations:artifact?.citations||[],evidence:used,retrieval:stage==='retrieval'?{query:artifact?.query_used,lexical:artifact?.lexical_candidates||[],vector:artifact?.vector_candidates||[],selected:artifact?.selected_sources||[],ranked:artifact?.ranked_sources||[],metrics:artifact?.metrics,delivery:artifact?.delivery,warning:artifact?.warning}:null,raw:artifact?.response?.raw||r.raw_error_output||'',warning:hasOutput?null:'이 단계는 실행되지 않았거나 검토 가능한 출력이 없습니다.',origin:'saved',legacy_review:(run.reviews||[]).find(x=>x.question_id===r.question_id)||null},r);
  }
 }
 const summary={total:targets.length,automatic_fail:0,execution_error:0,blocked:0,not_run:0,unreviewable:0,human_pass:0,human_fail:0,pending:0};
 for(const t of targets){if(t.checks.some(c=>c.status==='FAIL'))summary.automatic_fail++;if(t.checks.some(c=>c.status==='ERROR'))summary.execution_error++;if(t.status==='BLOCKED')summary.blocked++;if(t.status==='NOT_RUN')summary.not_run++;if(!t.has_output||!t.bound)summary.unreviewable++;else if(t.review?.review_state==='COMPLETE'&&t.review.verdict==='PASS')summary.human_pass++;else if(t.review?.review_state==='COMPLETE'&&t.review.verdict==='FAIL')summary.human_fail++;else summary.pending++;}
 return {version:VERSION,run:{id:run.id,status:run.status,error:run.error,deleted_at:run.deleted_at,stage:run.stage,config:run.config,config_hash:run.config_hash,dataset_fingerprint:run.dataset_fingerprint},stage,unit_label:stage==='extraction'?'원문 산출물':'질문',summary,targets,codes:CODES};
}
function publicReview(catalog,targetKey){
 const selected=catalog.targets.find(t=>t.target_key===targetKey)||catalog.targets[0]||null;
 return {...catalog,targets:catalog.targets.map(t=>({target_key:t.target_key,title:t.title,description:t.question||t.expected[0]?.statement||t.title,source_id:t.source_id,status:t.status,question:t.question,question_ids:t.question_ids,has_output:t.has_output,bound:t.bound,automatic_fail:t.checks.some(c=>c.status==='FAIL'),execution_error:t.checks.some(c=>c.status==='ERROR'),review:t.review?{verdict:t.review.verdict,review_state:t.review.review_state,revision:t.review.revision}:null,stale_review:t.stale_review})),selected};
}
function validateReview(target,input){
 if(!target.has_output||!target.bound)throw Error('원문이 확정되고 실제 출력이 있는 항목만 판정할 수 있습니다.');
 if(input.target_fingerprint!==target.fingerprint)throw Error('검토 대상이 변경됐습니다. 새로 불러오세요.');
 if(!['draft','final'].includes(input.save_mode))throw Error('저장 방식 오류');
 const verdicts=['PASS','FAIL','PENDING_REVIEW'],goldStates=['matched','missing','hold'];
 const units={},gold_decisions={},reasons=new Set(Object.keys(CODES));
 for(const [id,v]of Object.entries(input.units||{})){
  if(!target.units.some(u=>u.id===id)||!v||!verdicts.includes(v.verdict))throw Error('기억·질문 판정 대상 또는 값 오류');
  if(v.reason&&!reasons.has(v.reason))throw Error('오류 종류가 올바르지 않습니다.');
  units[id]={verdict:v.verdict,reason:v.reason||'',notes:String(v.notes||'').slice(0,3000)};
 }
 for(const [id,v]of Object.entries(input.gold_decisions||{})){
  if(!target.expected.some(f=>f.id===id)||!v||!goldStates.includes(v.status))throw Error('기대 기억 판정 오류');
  const ids=[...new Set(v.unit_ids||[])];if(ids.some(id=>!target.units.some(u=>u.id===id)))throw Error('존재하지 않는 실제 기억 연결');
  if(v.status==='matched'&&!ids.length)throw Error('대응하는 실제 기억을 선택하세요.');
  gold_decisions[id]={status:v.status,unit_ids:ids};
 }
 const gold_status=['confirmed','issue','draft'].includes(input.gold_status)?input.gold_status:'draft';
 let verdict='PENDING_REVIEW',review_state='DRAFT';
 if(input.save_mode==='final'){
  if(gold_status==='issue'){review_state='NEEDS_GOLD';}
  else{
   if(!target.gold_available||gold_status!=='confirmed')throw Error('검토할 판정 기준을 먼저 확인하세요.');
   if(!input.coverage_confirmed)throw Error('전체 원문·질문의 누락·추가 확인이 필요합니다.');
   if(target.units.some(u=>!units[u.id]))throw Error('판정하지 않은 실제 기억 또는 질문이 있습니다.');
   if(target.expected.some(f=>!gold_decisions[f.id]))throw Error('기대 기억마다 대응·누락·보류를 선택하세요.');
   if(Object.values(units).some(v=>v.verdict==='FAIL'&&!v.reason))throw Error('실패한 기억 또는 질문의 오류 종류를 선택하세요.');
   const pending=Object.values(units).some(v=>v.verdict==='PENDING_REVIEW')||Object.values(gold_decisions).some(v=>v.status==='hold');
   const failed=Object.values(units).some(v=>v.verdict==='FAIL')||Object.values(gold_decisions).some(v=>v.status==='missing');
   review_state=pending?'IN_PROGRESS':'COMPLETE';verdict=pending?'PENDING_REVIEW':failed?'FAIL':'PASS';
  }
 }
 return {version:VERSION,stage:target.stage,target_key:target.target_key,target_fingerprint:target.fingerprint,config_hash:target.config_hash,dataset_fingerprint:target.dataset_fingerprint,save_mode:input.save_mode,gold_status,coverage_confirmed:!!input.coverage_confirmed,units,gold_decisions,notes:String(input.notes||'').slice(0,3000),verdict,review_state,reviewer:'local-user'};
}
module.exports={VERSION,CODES,STAGES,errorCode,extractionChecks,buildReview,publicReview,validateReview};
