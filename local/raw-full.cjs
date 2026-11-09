const {answerMessages,answerSchema}=require('./prompts.cjs');
const {requestBudget,FULL_POLICY}=require('./token-budget.cjs');
const FULL_ROUTE='R0-Full',FULL_VERSION='accessible-full-originals-v1';
const isFull=route=>route===FULL_ROUTE;
const isRaw=route=>route==='R0'||isFull(route);
function fullEvidence(sources){return sources.map((s,i)=>({evidence_id:'E'+(i+1),source_id:s.id,revision:s.revision,start:0,end:s.text.length,text:s.text,metadata:s.metadata,origin:'raw_full',unit_id:s.id+':FULL'}));}
async function fullBudget(runtime,config,question,context,evidence,signal){
 const messages=answerMessages(config,question,context,evidence);
 const evidenceTokens=await runtime.tokenize(JSON.stringify(evidence),signal);
 const measured=await requestBudget(runtime,messages,answerSchema,config,signal);
 const reasons=measured.eligible?[]:[`전체 입력 ${measured.input_tokens} / ${measured.input_limit}토큰`];
 return {...measured,reasons,evidence_tokens:evidenceTokens,evidence_limit:null,budget_policy:FULL_POLICY};
}
function budgetError(budget,artifact){return Object.assign(Error('R0-Full 전체 제공 예산 초과: '+budget.reasons.join(' · ')+'; 원문을 자르거나 다른 방식으로 전환하지 않았습니다.'),{code:'FULL.BUDGET',not_applicable:true,token_budget:budget,...(artifact?{full_delivery:artifact}:{})});}
function assertFullEvidence(artifact,sources){
 if(artifact.delivery?.version!==FULL_VERSION||!artifact.delivery.budget?.eligible)throw Error('R0-Full 답변만 실행에는 전체 제공 예산을 통과한 Full 산출물이 필요합니다.');
 const expected=fullEvidence(sources),actual=artifact.evidence||[];
 if(actual.length!==expected.length||actual.some((e,i)=>e.source_id!==expected[i].source_id||e.revision!==expected[i].revision||e.start!==0||e.end!==expected[i].end||e.text!==expected[i].text))throw Error('R0-Full 산출물이 현재 기억 범위의 원문 전체와 일치하지 않습니다.');
}
module.exports={FULL_ROUTE,FULL_VERSION,isFull,isRaw,fullEvidence,fullBudget,budgetError,assertFullEvidence};
