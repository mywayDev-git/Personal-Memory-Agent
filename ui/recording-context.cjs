'use strict';
// Semantic review runs before preparing changes, never as a presentation filter.
const VERSION='recording-context-v1';
const changeTools=new Set(['create','save_transcript','update','delete','restore']);
const object=properties=>({type:'object',properties,required:Object.keys(properties),additionalProperties:false});
const string=maxLength=>({type:'string',maxLength});
const fail=message=>Object.assign(Error(message),{stage:'validation'});

async function review({plan,turns,pending,existing,call}){
 const steps=plan.steps.map((step,index)=>({...step,index})).filter(step=>changeTools.has(step.tool)&&!existing.has(step.index));
 if(!steps.length)return {version:VERSION,reviews:[],review_proposal_ids:[]};
 const users=turns.filter(turn=>turn.role==='user'),ids=users.map(turn=>turn.id);
 const schema=object({reviews:{type:'array',minItems:steps.length,maxItems:steps.length,items:object({
  index:{type:'integer',enum:steps.map(step=>step.index)},decision:{type:'string',enum:['prepare','skip']},
  basis:{type:'string',enum:['current_request','contextual_confirmation','standing_instruction','none']},reason:string(400),
  sources:{type:'array',maxItems:8,items:object({turn_id:{type:'string',enum:ids},quote:string(1000)})}
 })},review_proposal_ids:{type:'array',maxItems:pending.length,items:{type:'string',enum:pending.length?pending.map(p=>p.id):['unavailable']}}});
 const result=await call('recording_review',[
  {role:'system',content:`기록 도구 초안을 만들기 전에 각 작업이 현재 사용자 목표에 필요한지 대화의 의미로 검토한다. 특정 단어나 표현 목록으로 판단하지 않는다. 이 단계는 입력 의도 분류가 아니며 도구 실행도 아니다.
사용자와 AI 역할, 시간 순서, 최신 정정·취소, 앞서 합의한 범위를 함께 본다. 경험·감정·자랑·질문 자체는 기록 허락이 아니다. AI가 기록을 권하거나 준비했다고 말한 것만으로 사용자 허락이 생기지 않는다. 과거의 한 번짜리 기록 요청은 다음 주제까지 지속되지 않는다.
현재 기록 요청, 앞서 제안한 특정 작업에 대한 사용자의 문맥상 동의, 또는 현재도 유효한 지속 기록 지시가 실제로 해당 내용·행동을 포함할 때만 prepare다. 사용자 동의에 정해진 단어는 필요 없다. 지속 지시는 주제가 바뀌어도 적용 범위 안에서 유지하지만 철회·변경되면 최신 지시를 따른다. 요청이 부정·가정·인용되었거나 대상이 달라졌으면 이를 구분한다. 애매하거나 근거가 없으면 skip으로 하고 불필요한 확인 질문을 만들지 않는다.
prepare에는 basis와 그 허락을 뒷받침하는 실제 사용자 발언의 정확한 연속 인용을 sources에 적는다. 사용자가 직접 말한 경험이라는 사실과 그것을 기록하라는 허락은 다르다. 본문에 담을 사실 근거가 아니라 작업 허락의 근거를 고른다. 내용·대상 누락은 다음 도구 준비 단계에서 확인한다.
기존 초안을 보여주거나 설명해 달라는 목표는 새 초안 생성이 아니다. pending_proposals에서 해당 ID를 review_proposal_ids로 선택하고 중복 생성은 skip한다. 하나의 기록 요청을 사실 기록과 대화 원문 보관 두 개로 임의 확장하지 않는다. 별도로 요구된 범위에 필요한 작업만 남긴다. JSON만 출력한다.`},
  {role:'user',content:JSON.stringify({goal:plan.goal,conversation:turns,planned_changes:steps,pending_proposals:pending.map(p=>({id:p.id,operation:p.operation,title:p.after?.title||p.before?.title,submitted_text:p.submitted_text}))})}
 ],schema);
 const seen=new Set();
 for(const row of result.reviews||[]){
  if(!steps.some(step=>step.index===row.index)||seen.has(row.index))throw fail('기록 준비 검토 결과가 계획한 작업과 일치하지 않습니다.');
  seen.add(row.index);
  if(!['prepare','skip'].includes(row.decision)||!row.reason?.trim())throw fail('기록 준비 판단의 근거를 확인하지 못했습니다.');
  if(row.decision==='prepare'&&(!['current_request','contextual_confirmation','standing_instruction'].includes(row.basis)||!row.sources?.length))throw fail('기록 작업을 요청한 사용자 근거를 확인하지 못했습니다.');
  for(const source of row.sources||[]){
   const turn=users.find(turn=>turn.id===source.turn_id);
   if(!source.quote?.trim()||!turn?.text.includes(source.quote))throw fail('기록 준비 판단에 연결한 사용자 원문이 일치하지 않습니다.');
  }
 }
 if(seen.size!==steps.length)throw fail('일부 기록 작업의 필요성 검토가 누락되었습니다.');
 if(!Array.isArray(result.review_proposal_ids)||result.review_proposal_ids.some(id=>!pending.some(p=>p.id===id)))throw fail('다시 표시할 초안을 확인하지 못했습니다.');
 return {version:VERSION,reviews:result.reviews,review_proposal_ids:[...new Set(result.review_proposal_ids)]};
}

module.exports={VERSION,changeTools,review};
