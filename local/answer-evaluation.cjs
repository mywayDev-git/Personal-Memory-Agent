const {arithmeticTask}=require('./summary-dialogue.cjs');
const fs=require('node:fs'),path=require('node:path');
const {hash,locate,validateCitations}=require('./core.cjs');
const rules=JSON.parse(fs.readFileSync(path.join(__dirname,'answer-criteria-v2.json'),'utf8'));
const VERSION='answer-evaluation-v2',CRITERIA_VERSION=rules.version,CRITERIA_HASH=hash(rules);
const MEANING_REASONS={FACT:'근거 없는 주장',OMISSION:'필수 내용 누락',STATE:'예정·진행·완료·미확인 상태',IDENTITY:'인물·대상·화자 연결',TIME:'시점·정정·최신 정보',NEGATION:'부정·자기모순',CALCULATION:'금액·수량·단위·범위',QUESTION:'질문 이탈·하위 질문 누락',CONTEXT:'이전 대화·주제 전환',OTHER:'기타 의미 문제'};
const fields=['reference_answer','required_claims','forbidden_claims','expected_action','acceptable_actions','completeness_scope','structured_expectations','annotation_status','coverage'];
const copy=x=>JSON.parse(JSON.stringify(x));
const goldFields=g=>Object.fromEntries(fields.filter(k=>g?.[k]!==undefined).map(k=>[k,copy(g[k])]));
const binding=(question,gold)=>hash({question,reference_answer:gold.reference_answer,required_claims:gold.required_claims,forbidden_claims:gold.forbidden_claims,expected_action:gold.expected_action});
function criteriaFor(run,id,question,gold){
 const original=goldFields(gold),effective=copy(original),override=rules.overrides.find(x=>x.dataset_fingerprint===run.dataset_fingerprint&&x.question_id===id&&x.binding===binding(question,original));
 if(override?.effective)Object.assign(effective,copy(override.effective));
 return {version:CRITERIA_VERSION,rules_hash:CRITERIA_HASH,original,effective,available:Array.isArray(original.required_claims),citation_required:override?.citation_required??!arithmeticTask(question),task_type:override?.task_type||(arithmeticTask(question)?'general_arithmetic':'personal_memory'),needs_revision:!!override?.needs_revision,note:override?.note||'필수 의미와 질문 범위만 요구합니다. 선택적인 배경 설명을 강제하지 않으며, 덧붙인 모든 사실도 원문으로 확인합니다.',checks:rules.semantic_checks};
}
function citationDiagnostics(parsed,evidence){return (parsed?.citations||[]).map((c,i)=>{
 const e=evidence.find(e=>e.evidence_id===c.evidence_id);let code='VALID',detail='정확한 연속 구절과 반복 순번 일치';
 if(!e){code='UNKNOWN_EVIDENCE';detail='제공되지 않은 근거 ID';}
 else if(!c.quote||!e.text.includes(c.quote)){
  if(c.quote&&e.text.replace(/\s+/gu,'').includes(c.quote.replace(/\s+/gu,''))){code='WHITESPACE';detail='공백 차이 진단. 자동 교정하거나 의미 통과로 바꾸지 않습니다.';}
  else if(/\.\.\.|…/u.test(c.quote||'')){code='NONCONTIGUOUS';detail='생략 기호로 연결한 구절은 정확한 연속 인용이 아닙니다.';}
  else{code='QUOTE_MISMATCH';detail='원문에 없는 인용 문구';}
 }else if(!locate(e.text,c.quote,c.occurrence)){code='OCCURRENCE';detail='반복 순번 오류. 인용 목록의 번호가 아니라 같은 문구의 등장 순번입니다.';}
 return {index:i+1,...c,code,detail};
});}
function automaticEvaluation(parsed,evidence,criteria){
 const required=criteria.citation_required&&['answer','partial_answer','deny','report_conflict'].includes(parsed.action);
 const checked=validateCitations(parsed,evidence,{require_citation:required});
 const allowed=criteria.effective.acceptable_actions||[criteria.effective.expected_action];
 return {...checked,axes:{version:VERSION,citation:{status:checked.errors.length?'FAIL':parsed.citations.length?'PASS':'NOT_APPLICABLE',required,errors:checked.errors,diagnostics:citationDiagnostics(parsed,evidence)},semantic:{status:'PENDING_REVIEW',source:'not_automatically_judged',note:'인용 검사는 답변 의미를 판정하지 않습니다.'},action:{status:allowed.includes(parsed.action)?'TAG_MATCH':'TAG_MISMATCH',actual:parsed.action,allowed,note:'행동 태그 일치 여부이며 답변 의미의 통과·실패가 아닙니다.'}}};
}
function loadAnswer(store,r){const ref=r?.stages?.answer;if(!ref)return null;return ref.artifact_id?{...store.readArtifact(ref.artifact_id),artifact_id:ref.artifact_id}:ref;}
function savedView(run,r,a){
 const criteria=a.assessment?.criteria_snapshot||criteriaFor(run,r.question_id,r.question,a.assessment||{});
 const axes=a.assessment?.axes||{version:'legacy-saved',citation:{status:Array.isArray(a.citation_errors)?a.citation_errors.length?'FAIL':'PASS':'NOT_OBSERVED',errors:a.citation_errors||[],note:'당시 저장된 인용 결과입니다. 새 기준으로 재채점하지 않습니다.'},semantic:{status:'PENDING_REVIEW',source:'not_automatically_judged'},action:{status:(criteria.original.acceptable_actions||[criteria.original.expected_action]).includes(a.action)?'TAG_MATCH':'TAG_MISMATCH',actual:a.action,allowed:criteria.original.acceptable_actions||[criteria.original.expected_action]}};
 const fingerprint=hash({version:VERSION,run:run.id,config:run.config_hash,dataset:run.dataset_fingerprint,question_id:r.question_id,question:r.question,answer_artifact:a.artifact_id||hash(a),criteria});
 return {criteria,axes,fingerprint};
}
function buildAnswerEvaluation(run,store,questionId){
 const reviews=new Map(store.answerReviews(run.id).map(x=>[x.question_id,x])),summary={total:0,answered:0,citation_fail:0,citation_pass:0,citation_not_applicable:0,semantic_pass:0,semantic_fail:0,semantic_partial:0,semantic_pending:0,criteria_issue:0,execution_error:0,excluded:0},rows=[];let detail=null;
 for(const id of run.question_ids){const r=run.results.find(r=>r.question_id===id);summary.total++;
  if(!r?.stages?.answer){if(r?.status==='NOT_APPLICABLE')summary.excluded++;else if(['ERROR','VALIDATION_FAILED','BLOCKED','CANCELLED','INTERRUPTED'].includes(r?.status))summary.execution_error++;rows.push({question_id:id,question:r?.question||id,original_status:r?.status||'NOT_RUN',has_answer:false,error:r?.error||'',citation_status:'NOT_RUN',semantic_status:'NOT_RUN'});if(id===questionId)detail={...rows.at(-1),error_details:r?.error_details||null};continue;}
  const a=loadAnswer(store,r),view=savedView(run,r,a),latest=reviews.get(id),review=latest?.target_fingerprint===view.fingerprint?latest:null,meaning=review?.semantic.verdict||'PENDING_REVIEW';summary.answered++;
  if(view.axes.citation.status==='FAIL')summary.citation_fail++;else if(view.axes.citation.status==='PASS')summary.citation_pass++;else summary.citation_not_applicable++;
  summary[{PASS:'semantic_pass',FAIL:'semantic_fail',PARTIAL:'semantic_partial',PENDING_REVIEW:'semantic_pending'}[meaning]]++;
  if(view.criteria.needs_revision||review?.criteria_status==='issue')summary.criteria_issue++;
  rows.push({question_id:id,question:r.question,original_status:r.status,has_answer:true,citation_status:view.axes.citation.status,semantic_status:meaning,action_status:view.axes.action.status,criteria_issue:view.criteria.needs_revision||review?.criteria_status==='issue',legacy:!a.assessment?.axes,stale_review:!!latest&&!review,review_revision:latest?.revision||0});
  if(id===questionId){const validSources=a.evidence_used||[];detail={...rows.at(-1),target_fingerprint:view.fingerprint,question:r.question,answer:a.answer,action:a.action,criteria:view.criteria,axes:view.axes,citations:a.citations||[],citation_diagnostics:citationDiagnostics(a.response?.parsed||{citations:a.citations||[]},validSources),raw_output:a.response?.raw||'',sources:validSources,review,history:store.answerReviewHistory(run.id,id),legacy_question_review:store.reviews(run.id).find(v=>v.question_id===id)||null,legacy_stage_review:store.stageReviews(run.id,'answer').find(v=>v.target_key==='answer:'+id)||null};}
 }
 if(questionId&&!rows.some(r=>r.question_id===questionId))throw Error('실행에 없는 질문입니다.');
 return {version:VERSION,criteria_version:CRITERIA_VERSION,run:{id:run.id,status:run.status,deleted_at:run.deleted_at,config:run.config},summary,rows,...(questionId?{detail}:{}),meaning_reasons:MEANING_REASONS,note:'기존 실행 상태와 판정은 보존합니다. 분리 판정은 별도 이력에 저장하며 과거 종합 판정에서 자동 변환하지 않습니다.'};
}
function validateAnswerReview(detail,input){
 if(!detail?.has_answer)throw Error('실제 답변이 있는 질문만 검토할 수 있습니다.');
 if(input.target_fingerprint!==detail.target_fingerprint)throw Error('검토 대상이나 기준이 변경됐습니다. 새로 불러오세요.');
 const semantic=input.semantic||{},citation=input.citation||{},action=input.action||{};
 if(!['PASS','FAIL','PARTIAL','PENDING_REVIEW'].includes(semantic.verdict))throw Error('의미 판정 값 오류');
 if(!['PASS','FAIL','PENDING_REVIEW','NOT_APPLICABLE'].includes(citation.verdict)||!['PASS','FAIL','PENDING_REVIEW','NOT_APPLICABLE'].includes(action.verdict))throw Error('인용·행동 판정 값 오류');
 if(!['confirmed','issue','unreviewed'].includes(input.criteria_status))throw Error('판정 기준 확인 값 오류');
 if(semantic.verdict!=='PENDING_REVIEW'){
  if(!detail.criteria.available||input.criteria_status!=='confirmed'||detail.criteria.needs_revision)throw Error('판정 기준을 먼저 확인하세요. 모호한 기준은 보류로 남깁니다.');
  if(!input.coverage_confirmed)throw Error('필수 내용·부가 주장·누락·부정·시점·대상을 모두 확인해 주세요.');
 }
 if(semantic.reason&&!MEANING_REASONS[semantic.reason])throw Error('의미 오류 종류에 인용·행동 오류를 혼합하지 않습니다.');
 if(['FAIL','PARTIAL'].includes(semantic.verdict)&&(!semantic.reason||!String(semantic.notes||'').trim()))throw Error('의미 오류 종류와 구체적인 근거를 기록하세요.');
 return {version:VERSION,criteria_version:detail.criteria.version,criteria_snapshot:detail.criteria,question_id:detail.question_id,target_fingerprint:detail.target_fingerprint,semantic:{verdict:semantic.verdict,reason:semantic.reason||'',notes:String(semantic.notes||'').slice(0,4000)},citation:{verdict:citation.verdict,notes:String(citation.notes||'').slice(0,4000)},action:{verdict:action.verdict,notes:String(action.notes||'').slice(0,4000)},criteria_status:input.criteria_status,criteria_notes:String(input.criteria_notes||'').slice(0,4000),coverage_confirmed:!!input.coverage_confirmed,reviewer:'local-user'};
}
module.exports={VERSION,CRITERIA_VERSION,CRITERIA_HASH,criteriaFor,binding,automaticEvaluation,citationDiagnostics,buildAnswerEvaluation,validateAnswerReview};
