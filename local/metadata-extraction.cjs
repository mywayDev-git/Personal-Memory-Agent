const {recoverMetadata}=require('./metadata-recovery.cjs');
const {normalizeRelationReferences,INSTRUCTION:REFERENCE_INSTRUCTION}=require('./relation-references.cjs');
const {normalizeTemporalPrecision,INSTRUCTION:PRECISION_INSTRUCTION}=require('./temporal-precision.cjs');
const {schemaIssues,sentences}=require('./core.cjs');
const {requestSchema,INSTRUCTION,VERSION,SCHEMA}=require('./metadata-schema.cjs'),{inputFor,resolveEvidence,validateDraft,invalid,issue,schemaValidationIssues,occurrenceAt}=require('./metadata-grounding.cjs'),usage=require('./token-usage.cjs'),diagnostics=require('./request-diagnostics.cjs');
const MAX_ATTEMPTS=2;

function repairFeedback(issues){
 const groups=new Map();
 for(const {path,code,message,value} of issues){
  const key=JSON.stringify([code,message]);
  if(!groups.has(key))groups.set(key,{code,message,items:[]});
  groups.get(key).items.push({path,...(typeof value==='string'?{value:value.slice(0,80)}:{})});
 }
 return [...groups.values()];
}

function splitUnit(unit){
 const lines=sentences(unit.text);
 if(lines.length<2)return null;
 const cut=lines[Math.floor(lines.length/2)].start;
 const start=unit.start+cut;
 return [
  {...unit,id:unit.id+'/0',end:start,text:unit.text.slice(0,cut)},
  {...unit,id:unit.id+'/1',start,text:unit.text.slice(cut)}
 ];
}

function mergeMetadata(unit,record,parts){
 const occurrence=evidence=>occurrenceAt(unit.text,evidence.quote,evidence.start-unit.start);
 const pick=(key,identity)=>{
  const picked=new Map(),limit=SCHEMA.properties[key].maxItems;
  const lists=parts.map(part=>part.metadata[key]);
  for(let i=0;i<Math.max(...lists.map(list=>list.length));i++){
   for(const list of lists){
    const value=list[i];
    if(value===undefined)continue;
    const id=identity(value);
    if(!picked.has(id))picked.set(id,value);
    if(picked.size===limit)return [...picked.values()];
   }
  }
  return [...picked.values()];
 };
 const searchTerms=pick('search_terms',term=>term);
 const termEvidence=parts.flatMap(part=>part.metadata.search_term_evidence);
 const spanKey=item=>JSON.stringify([item.evidence.start,item.evidence.end]);
 const metadata=validateDraft({
  search_terms:searchTerms,
  search_term_evidence:searchTerms.map(term=>{
   const evidence=termEvidence.find(item=>item.quote===term);
   return {quote:term,occurrence:occurrence(evidence)};
  }),
  entities:pick('entities',item=>JSON.stringify([item.entity_id,spanKey(item)])).map(
   ({entity_id,evidence,...item})=>({...item,occurrence:occurrence(evidence)})),
  time_mentions:pick('time_mentions',item=>JSON.stringify([item.kind,item.value,spanKey(item)])).map(
   ({evidence,...item})=>({...item,occurrence:occurrence(evidence)})),
  relations:pick('relations',item=>item.relation_id).map(
   ({relation_id,subject_id,object_id,valid_time,valid_time_evidence,event_time_evidence,evidence,...item})=>({
    ...item,occurrence:occurrence(evidence),
    valid_time_occurrence:valid_time_evidence?occurrence(valid_time_evidence):1,
    event_time_occurrence:event_time_evidence?occurrence(event_time_evidence):1
   }))
 },unit,record);
 for(const key of ['temporal_adjustments','relation_adjustments','metadata_omissions']){
  const entries=parts.flatMap(part=>part.metadata[key]||[]);
  if(entries.length)metadata[key]=entries;
 }
 return metadata;
}

function metadataRequest(record,unit,config){
 const input=inputFor(unit,record),schema=requestSchema(input),payload={...input,search_candidates:input.search_candidates.map(({start,end,...c})=>c)},instruction=INSTRUCTION+'\n'+PRECISION_INSTRUCTION+'\n'+REFERENCE_INSTRUCTION+' 검색어는 최대 8개, 개체는 4개, 관계는 3개, 시간은 4개만 선택한다. 모든 사실은 요약 본문에 남아 있으므로 메타정보는 핵심만 간결하게 만든다.'+(config.metadata_prompt_text&&config.metadata_prompt_text!==INSTRUCTION?'\n추가 지침: '+config.metadata_prompt_text:'');
 const system={role:'system',content:instruction};
 const messages=feedback=>[system,{role:'user',content:JSON.stringify(feedback?{...payload,
  validation_feedback:repairFeedback(feedback),
  instruction:'오류 항목을 참고해 제공된 요약에서 메타정보를 다시 추출한다. 근거 없는 관계와 시각은 빼거나 null로 두고 전체 JSON을 출력한다.'
 }:payload)}];
 return {input,schema,messages};
}

async function extractUnit(engine,record,unit,config,signal,onAttempt=()=>{}){
 const {input,schema,messages}=metadataRequest(record,unit,config);
 const process=parsed=>{const references=normalizeRelationReferences(resolveEvidence(parsed,unit,input),input),normalized=normalizeTemporalPrecision(references.draft,record);return {...validateDraft(normalized.draft,unit,record),temporal_adjustments:normalized.adjustments,relation_adjustments:references.adjustments};};
 const attempts=[];let previous,feedback;
 for(let attempt=1;attempt<=MAX_ATTEMPTS;attempt++){
  signal?.throwIfAborted();diagnostics.setContext({metadata_attempt:attempt,metadata_attempts:MAX_ATTEMPTS});onAttempt({attempt,max_attempts:MAX_ATTEMPTS,unit_id:unit.id,status:attempt===1?'EXTRACTING':'REPAIRING',issues:feedback||[]});signal?.throwIfAborted();
  let response;
  try{
   response=await engine.runtime.chat(messages(feedback),schema,{...config,output_tokens:1536},signal);const schemaErrors=schemaIssues(response.parsed,schema);if(schemaErrors.length)throw invalid(schemaValidationIssues(schemaErrors,response.parsed));const metadata=process(response.parsed);signal?.throwIfAborted();return {metadata,response,attempt_count:attempt,attempt_artifacts:attempts};
  }catch(error){
   if(signal?.aborted)throw error;
   if(error.token_budget?.eligible===false){
    const sections=splitUnit(unit);
    if(!sections){
     if(attempt>1&&previous){
      const metadata=recoverMetadata(previous.parsed,process,input);
      return {metadata:{...metadata,metadata_repair_budget:error.token_budget},
       response:previous,attempt_count:attempt-1,attempt_artifacts:attempts};
     }
     error.message='문장 한 개의 색인 요청이 입력 한도를 초과했습니다 · '+error.message;
     throw error;
    }
    const parts=[];
    for(const section of sections){
     signal?.throwIfAborted();
     const result=await extractUnit(engine,record,section,config,signal,onAttempt);
     parts.push({section,...result});
    }
    const metadata=mergeMetadata(unit,record,parts);
    return {
     metadata:{...metadata,metadata_split:{at_attempt:attempt,budget:error.token_budget,
      parts:parts.map(({section,metadata})=>({start:section.start,end:section.end,
       ...(metadata.metadata_split?{split:metadata.metadata_split}:{})}))}},
     response:{parsed:{parts:parts.map(({section,response})=>({
      start:section.start,end:section.end,output:response.parsed
     }))}},
     attempt_count:attempt-1+parts.reduce((sum,part)=>sum+part.attempt_count,0),
     attempt_artifacts:[...attempts,...parts.flatMap(part=>part.attempt_artifacts)]
    };
   }
   const repairable=Array.isArray(error.validation_issues)||typeof error.raw==='string';
   if(!repairable)throw error;
   let failedParsed;try{failedParsed=JSON.parse(error.raw);}catch{}const failedSchema=failedParsed?schemaIssues(failedParsed,schema):[];feedback=error.validation_issues||(failedSchema.length?schemaValidationIssues(failedSchema,failedParsed):[issue('$','MODEL_OUTPUT_FORMAT',/한도/u.test(error.message)?error.message:'모델 출력을 지정된 형식으로 읽지 못했습니다. 전체 JSON을 다시 출력해야 합니다.')]);previous=response||{parsed:failedParsed,raw:error.raw,usage:error.usage};
   const artifact_id=engine.store.artifact('structured-index-attempt',{version:VERSION,summary_id:record.summary_id,unit_id:unit.id,summary_text:unit.text,attempt,max_attempts:MAX_ATTEMPTS,response:response||{raw:error.raw,usage:error.usage},error:error.message,validation_issues:feedback,token_usage:usage.report({stage:'indexing',source_id:record.source_id})});attempts.push({attempt,artifact_id,status:'VALIDATION_FAILED'});
   if(attempt===MAX_ATTEMPTS){try{const metadata=recoverMetadata(response?.parsed||failedParsed,process,input);return {metadata,response:response||{parsed:failedParsed,raw:error.raw,usage:error.usage},attempt_count:attempt,attempt_artifacts:attempts};}catch{}error.metadata_artifact_id=artifact_id;error.index_validation={status:'FAILED',source_id:record.source_id,unit_id:unit.id,summary_id:record.summary_id,attempts:attempt,max_attempts:MAX_ATTEMPTS,issues:feedback,attempt_artifacts:attempts,summary_excerpt:unit.text.slice(0,350)};error.message='색인 검증 실패 · '+attempt+'회 시도: '+error.message;throw error;}
  }
 }
}
module.exports={extractUnit,MAX_ATTEMPTS};
