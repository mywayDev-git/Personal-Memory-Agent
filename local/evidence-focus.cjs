const {needsHistory}=require('./summary-dialogue.cjs');
const diagnostics=require('./request-diagnostics.cjs');
const {requestBudget}=require('./token-budget.cjs');

const SELECTION_INSTRUCTION=[
 '질문에 답할 때 필요한 요약 근거를 선택한다. 답변을 만들지 않는다.',
 '개인 기록 질문에서 대상이 생략되면 사용자의 대상이 기본이다. 다른 사람·다른 물건·옆 동 등 명시적으로 다른 대상인 비교 자료는 제외한다.',
 '같은 단어가 있다는 이유만으로 관련 근거로 선택하지 않는다. 계산 질문은 총액뿐 아니라 이미 지급한 금액 등 계산에 필요한 모든 관련 근거를 함께 선택한다.',
 '상태 질문은 같은 대상의 신청·제출·승인·완료 단계 근거를 선택한다. 복수 질문은 각 부분을 뒷받침하는 근거를 선택한다. 실제로 답을 뒷받침할 근거가 없으면 빈 배열이다.',
 '같은 topic_group은 같은 소유자의 같은 주제에 속한 여러 요약 기록이다. 한 기록에 생략된 대상이나 기납부 정보는 같은 그룹의 관련 기록과 연결해 확인한다.',
 '현재의 신청·제출 예정 같은 단계도 확정 여부를 답하는 근거이므로 완료라는 단어가 없다는 이유로 제외하지 않는다.',
 '중요한 근거부터 ID만 선택하고 설명은 출력하지 않는다. 제공된 ID만 선택한다.',
].join(' ');

function selectionRequest(question,context,evidence,inBatches=false){
 const groups=context.summary_topic_groups||{};
 const schema={
  type:'object',
  properties:{selected_ids:{type:'array',maxItems:6,items:{type:'string',enum:evidence.map(e=>e.evidence_id)}}},
  required:['selected_ids'],additionalProperties:false,
 };
 const batchInstruction=inBatches?' 이 후보들은 전체 기억 중 일부일 수 있다. 다른 기록과 결합해야 하는 질문이라면 질문의 일부를 뒷받침하는 후보도 선택한다.':'';
 const payload={
  question:question.text,
  conversation:needsHistory(question.text)?context.summary_generated_conversation||[]:[],
  evidence:evidence.map(e=>({evidence_id:e.evidence_id,topic_group:groups[e.source_id]||e.source_id,text:e.text})),
 };
 const messages=[
  {role:'system',content:SELECTION_INSTRUCTION+batchInstruction},
  {role:'user',content:JSON.stringify(payload)},
 ];
 return {messages,schema};
}

function relatedPayments(question,groups,evidence,selected){
 if(!/(추가|더\s*(내|낼)|남은|잔액)/u.test(question.text))return [];
 const expanded=[];
 const seen=new Set(selected.map(e=>e.evidence_id));
 for(const total of selected){
  if(!/포함/u.test(total.text)||!/(기납부|이미\s*(납부|지불)|낸\s*점검비)/u.test(total.text))continue;
  const group=groups[total.source_id];
  if(!group)continue;
  for(const candidate of evidence){
   if(seen.has(candidate.evidence_id)||groups[candidate.source_id]!==group)continue;
   if(!/(결제|지불|납부|지급)/u.test(candidate.text)||!/\d/u.test(candidate.text)||/(견적|제시|예정|계획)/u.test(candidate.text))continue;
   expanded.push(candidate);
   seen.add(candidate.evidence_id);
  }
 }
 return expanded;
}

async function focusAllEvidence(engine,question,context,evidence,config,signal){
 const batches=[];
 const selectionConfig={...config,output_tokens:128};

 async function review(candidates,phase){
  signal.throwIfAborted();
  const {messages,schema}=selectionRequest(question,context,candidates,phase==='BATCH');
  const budget=await diagnostics.withContext({purpose:'all_candidate_focus'},()=>requestBudget(engine.runtime,messages,schema,selectionConfig,signal));
  if(!budget.eligible){
   if(phase==='FINAL')return null;
   if(candidates.length===1)throw Object.assign(Error('요약 후보 한 개도 현재 질문과 함께 입력 한도에 담을 수 없습니다.'),{token_budget:budget});
   const middle=Math.ceil(candidates.length/2);
   const first=await review(candidates.slice(0,middle),'BATCH');
   const second=await review(candidates.slice(middle),'BATCH');
   return [...first,...second];
  }
  const result=await diagnostics.withContext({purpose:'all_candidate_focus'},()=>engine.runtime.chat(messages,schema,selectionConfig,signal));
  const byId=new Map(candidates.map(e=>[e.evidence_id,e]));
  const selectedIds=[...new Set(result.parsed.selected_ids)];
  batches.push({phase,candidate_ids:[...byId.keys()],selected_ids:selectedIds,input_tokens:budget.input_tokens});
  return selectedIds.map(id=>byId.get(id));
 }

 let selected=evidence.length?await review(evidence,'ALL'):[];
 const candidateBatches=batches.length;
 let finalComparison=false;
 if(candidateBatches>1&&selected.length>1){
  // A second comparison is optional when the combined shortlists still exceed the budget.
  const compared=await review(selected,'FINAL');
  if(compared!==null){selected=compared;finalComparison=true;}
 }
 const payment=relatedPayments(question,context.summary_topic_groups||{},evidence,selected);
 const used=[...selected,...payment];
 return {evidence:used,trace:{
  status:'ALL_CANDIDATES_REVIEWED',candidate_count:evidence.length,candidate_batches:candidateBatches,
  final_comparison:finalComparison,batches,selected_ids:used.map(e=>e.evidence_id),related_payment_ids:payment.map(e=>e.evidence_id),
 }};
}
async function focusEvidence(engine,question,context,evidence,config,signal){
 const groups=context.summary_topic_groups||{},other=/^\s*(옆\s*[\p{L}\p{N}]+|다른\s*[\p{L}\p{N}]+|동생(?:의)?|친구(?:의)?)/u;evidence=evidence.filter(e=>{const m=e.text.match(other);return !m||!/(별개|무관|다른|아니)/u.test(e.text)||question.text.replace(/\s/g,'').includes(m[1].replace(/\s/g,'').replace(/의$/u,''));});
 if(new Set(evidence.map(e=>e.source_id)).size<=1)return {evidence,trace:{status:'SINGLE_SOURCE',selected_ids:evidence.map(e=>e.evidence_id)}};
 const {messages,schema}=selectionRequest(question,context,evidence);
 try{const result=await diagnostics.withContext({purpose:'evidence_focus'},()=>engine.runtime.chat(messages,schema,{...config,output_tokens:128},signal)),ids=new Set(result.parsed.selected_ids);let selected=[...ids].map(id=>evidence.find(e=>e.evidence_id===id)).filter(Boolean);
 const words=(question.text.match(/[\p{L}\p{N}]+/gu)||[]).map(t=>t.replace(/(으로|대로|에는|에서|은|는|이|가|을|를|의|에|도|야)$/u,'')).filter(t=>t.length>=3||['서버','배포','예약','신청','승인','운행','검사','작업'].includes(t));
 if(!selected.length||/(확정|완료|끝났|승인)/u.test(question.text)){const anchors=evidence.map(e=>({e,score:words.filter(w=>e.text.replace(/\s/g,'').includes(w)).reduce((n,w)=>n+w.length,0)})).filter(v=>v.score>0).sort((a,b)=>b.score-a.score);const best=anchors[0]?.score||0;anchors.splice(0,anchors.length,...anchors.filter(a=>a.score>=best*0.65).slice(0,2));if(anchors.length){const groupIds=new Set(anchors.map(({e})=>groups[e.source_id]));const related=selected.filter(e=>groupIds.has(groups[e.source_id]));selected=[...anchors.map(v=>v.e),...related].filter((e,i,a)=>a.findIndex(v=>v.evidence_id===e.evidence_id)===i);}}
 const expanded=relatedPayments(question,groups,evidence,selected);selected.push(...expanded);
 return {evidence:selected,trace:{status:'MODEL_SELECTED_WITH_SOURCE_COVERAGE',...result.parsed,model_selected_ids:result.parsed.selected_ids,selected_ids:selected.map(e=>e.evidence_id),related_payment_ids:expanded.map(e=>e.evidence_id),usage:result.usage,raw:result.raw}};}
 catch(error){signal?.throwIfAborted();return {evidence,trace:{status:'KEEP_VALIDATED_CANDIDATES',error:error.message}};}
}
function amount(quote){let sum=0,last=Infinity;const flat=quote.replace(/[,\s원]/gu,'');if(!/^(?:\d+(?:\.\d+)?[만천백]?)+$/u.test(flat))return null;for(const m of flat.matchAll(/(\d+(?:\.\d+)?)([만천백]?)/gu)){const multiplier=({만:10000,천:1000,백:100})[m[2]]||1;if(multiplier>=last)return null;last=multiplier;sum+=Number(m[1])*multiplier;}return Number.isFinite(sum)?sum:null;}
function moneyProof(question,evidence){
 if(!/(추가|더\s*(내|낼)|남은|잔액)/u.test(question)||!/(금액|얼마|원|비용)/u.test(question))return null;
 const totals=[],paid=[];for(const e of evidence){const text=e.text,total=text.match(/총\s*((?:\d[\d,]*(?:\.\d+)?\s*(?:만|천|백)?\s*)+)원/u);if(total&&/(포함)/u.test(text)&&/(기납부|이미\s*(납부|지불)|낸\s*점검비)/u.test(text)){const quote=total[1]+'원',value=amount(quote);if(value!==null)totals.push({evidence_id:e.evidence_id,value,quote});continue;}if(/(결제|지불|납부|지급)/u.test(text)&&!/(견적|제시|예정|계획)/u.test(text)){const matches=[...text.matchAll(/((?:\d[\d,]*(?:\.\d+)?\s*(?:만|천|백)?\s*)+)원/gu)];if(matches.length===1){const value=amount(matches[0][0]);if(value!==null)paid.push({evidence_id:e.evidence_id,value,quote:matches[0][0]});}}}
 if(totals.length!==1||paid.length!==1||paid[0].value>totals[0].value)return null;return {operation:'subtract_paid_from_inclusive_total',currency:'KRW',total:totals[0],already_paid:paid[0],result:totals[0].value-paid[0].value,expression:totals[0].value+' - '+paid[0].value+' = '+(totals[0].value-paid[0].value),basis:'현재 선택된 요약의 총액·기납부액과 포함 조건으로 계산. 외부 정보나 정답 참조 없음.'};
}
module.exports={focusAllEvidence,focusEvidence,moneyProof};
