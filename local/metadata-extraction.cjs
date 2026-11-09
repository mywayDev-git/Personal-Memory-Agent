const {recoverMetadata}=require('./metadata-recovery.cjs');
const {normalizeRelationReferences,INSTRUCTION:REFERENCE_INSTRUCTION}=require('./relation-references.cjs');
const {normalizeTemporalPrecision,INSTRUCTION:PRECISION_INSTRUCTION}=require('./temporal-precision.cjs');
const {schemaIssues}=require('./core.cjs');
const {requestSchema,INSTRUCTION,VERSION}=require('./metadata-schema.cjs'),{inputFor,resolveEvidence,validateDraft,invalid,issue,schemaValidationIssues}=require('./metadata-grounding.cjs'),usage=require('./token-usage.cjs'),diagnostics=require('./request-diagnostics.cjs');
const MAX_ATTEMPTS=2;
async function extractUnit(engine,record,unit,config,signal,onAttempt=()=>{}){
 const input=inputFor(unit,record),schema=requestSchema(input),payload={...input,search_candidates:input.search_candidates.map(({start,end,...c})=>c)},instruction=INSTRUCTION+'\n'+PRECISION_INSTRUCTION+'\n'+REFERENCE_INSTRUCTION+' 검색어는 최대 8개, 개체는 4개, 관계는 3개, 시간은 4개만 선택한다. 모든 사실은 요약 본문에 남아 있으므로 메타정보는 핵심만 간결하게 만든다.'+(config.metadata_prompt_text&&config.metadata_prompt_text!==INSTRUCTION?'\n추가 지침: '+config.metadata_prompt_text:'');
 const process=parsed=>{const references=normalizeRelationReferences(resolveEvidence(parsed,unit,input),input),normalized=normalizeTemporalPrecision(references.draft,record);return {...validateDraft(normalized.draft,unit,record),temporal_adjustments:normalized.adjustments,relation_adjustments:references.adjustments};};
 const base=[{role:'system',content:instruction},{role:'user',content:JSON.stringify(payload)}],attempts=[];let previous,feedback;
 for(let attempt=1;attempt<=MAX_ATTEMPTS;attempt++){
  signal?.throwIfAborted();diagnostics.setContext({metadata_attempt:attempt,metadata_attempts:MAX_ATTEMPTS});onAttempt({attempt,max_attempts:MAX_ATTEMPTS,unit_id:unit.id,status:attempt===1?'EXTRACTING':'REPAIRING',issues:feedback||[]});signal?.throwIfAborted();
  const messages=attempt===1?base:[...base,{role:'assistant',content:JSON.stringify(previous).slice(0,3200)},{role:'user',content:JSON.stringify({validation_feedback:feedback,instruction:'위 출력은 검증에 실패한 초안이다. 제공된 요약과 후보 ID만 다시 확인해 모든 오류를 수정한다. 없는 관계와 불명확한 시각·기간은 제거하거나 null로 두되, 확인 가능한 내용은 보존한다. 전체 JSON을 다시 출력한다.'})}];let response;
  try{
   response=await engine.runtime.chat(messages,schema,{...config,output_tokens:1536},signal);const schemaErrors=schemaIssues(response.parsed,schema);if(schemaErrors.length)throw invalid(schemaValidationIssues(schemaErrors,response.parsed));const metadata=process(response.parsed);signal?.throwIfAborted();return {metadata,response,attempt_count:attempt,attempt_artifacts:attempts};
  }catch(error){
   if(signal?.aborted)throw error;
   const repairable=Array.isArray(error.validation_issues)||typeof error.raw==='string';
   if(!repairable)throw error;
   let failedParsed;try{failedParsed=JSON.parse(error.raw);}catch{}const failedSchema=failedParsed?schemaIssues(failedParsed,schema):[];feedback=error.validation_issues||(failedSchema.length?schemaValidationIssues(failedSchema,failedParsed):[issue('$','MODEL_OUTPUT_FORMAT',/한도/u.test(error.message)?error.message:'모델 출력을 지정된 형식으로 읽지 못했습니다. 전체 JSON을 다시 출력해야 합니다.')]);previous=response?.parsed||{invalid_output:String(error.raw||'').slice(0,2400)};
   const artifact_id=engine.store.artifact('structured-index-attempt',{version:VERSION,summary_id:record.summary_id,unit_id:unit.id,summary_text:unit.text,attempt,max_attempts:MAX_ATTEMPTS,response:response||{raw:error.raw,usage:error.usage},error:error.message,validation_issues:feedback,token_usage:usage.report({stage:'indexing',source_id:record.source_id})});attempts.push({attempt,artifact_id,status:'VALIDATION_FAILED'});
   if(attempt===MAX_ATTEMPTS){try{const metadata=recoverMetadata(response?.parsed||failedParsed,process,input);return {metadata,response:response||{parsed:failedParsed,raw:error.raw,usage:error.usage},attempt_count:attempt,attempt_artifacts:attempts};}catch{}error.metadata_artifact_id=artifact_id;error.index_validation={status:'FAILED',source_id:record.source_id,unit_id:unit.id,summary_id:record.summary_id,attempts:attempt,max_attempts:MAX_ATTEMPTS,issues:feedback,attempt_artifacts:attempts,summary_excerpt:unit.text.slice(0,350)};error.message='색인 검증 실패 · '+attempt+'회 시도: '+error.message;throw error;}
  }
 }
}
module.exports={extractUnit,MAX_ATTEMPTS};
