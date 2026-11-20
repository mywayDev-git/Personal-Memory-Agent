'use strict';
// Public activity summaries only. Never expose model prompts or private reasoning.
const brief=(value,max=80)=>String(value||'').replace(/[\r\n\t]+/g,' ').replace(/\s+/g,' ').trim().slice(0,max);
const quote=value=>'“'+brief(value)+'”';
const actions={create:'새 기록',save_transcript:'대화 보관',update:'수정',delete:'삭제',restore:'복원'};
function label(event){const target=quote(event.target),scope=event.scope==='personal'?'개인 자료함':'선택한 자료함';switch(event.phase){
 case 'understand':return target+' 요청을 확인하고 있어요.';
 case 'context':return event.titles?.length?event.titles.slice(0,2).map(quote).join(', ')+' 주제의 이전 대화를 살펴보고 있어요.':target+'와 연결된 이전 대화를 살펴보고 있어요.';
 case 'organize':return target+'와 연결되는 대화를 주제별로 정리하고 있어요.';
 case 'plan':return (event.titles?.length?event.titles.slice(0,2).map(quote).join(', ')+' 대화를 참고해 ':'')+target+' 요청에 필요한 검색과 작업을 정하고 있어요.';
 case 'search':return scope+'에서 '+target+' 관련 기록을 찾고 있어요.';
 case 'evidence':return event.titles?.length?event.titles.slice(0,2).map(quote).join(', ')+' 기록의 내용을 확인하고 있어요.':target+' 검색 결과를 확인하고 있어요.';
 case 'review':return target+' 요청에서 기록할 범위와 동의를 확인하고 있어요.';
 case 'change':return target+'에 대한 '+(actions[event.tool]||'기록')+' 초안을 준비하고 있어요.';
 case 'cancel':return target+' 확인 대기 초안을 취소하고 있어요.';
 case 'answer':return target+(event.drafts?' 관련 확인 초안과 답변을 정리하고 있어요.':event.needsInput?' 요청에 필요한 확인 질문을 정리하고 있어요.':' 요청에 대한 답변을 정리하고 있어요.');
 case 'validate':return target+' 답변을 원문 및 요청 내용과 대조하고 있어요.';
 default:return '';
}}
// Monotonic, request-local activity timings. Polling cannot lose short stages.
function createProgress(clock=()=>performance.now()){
 const start=clock(),steps=[];let sequence=0,finishedAt=null;
 const elapsed=()=>finishedAt??Math.max(0,clock()-start);
 return {
  update(event){if(finishedAt!==null)return;const text=label(event);if(!text)return;const last=steps.at(-1);if(last?.phase===event.phase&&last.label===text)return;
   const at=elapsed();if(last){last.elapsed_ms=Math.max(0,at-last.started_ms);last.status='finished';}
   steps.push({phase:event.phase,label:text,sequence:++sequence,started_ms:at,elapsed_ms:0,status:'running'});
  },
  finish(){if(finishedAt===null){finishedAt=elapsed();const last=steps.at(-1);if(last){last.elapsed_ms=Math.max(0,finishedAt-last.started_ms);last.status='finished';}}return {version:'chat-progress-v1',...this.snapshot()};},
  snapshot(){const at=elapsed(),last=steps.at(-1);return {phase:last?.phase,label:last?.label,sequence,elapsed_ms:at,steps:steps.map(step=>({...step,elapsed_ms:step.status==='running'?Math.max(0,at-step.started_ms):step.elapsed_ms}))};}
 };
}
// Persist only bounded public summaries and completed, finite timings.
function normalizeTrace(value){
 const invalid=()=>{throw Object.assign(Error('처리 과정 또는 소요 시간 형식이 올바르지 않습니다.'),{status:400});};
 const duration=n=>typeof n==='number'&&Number.isFinite(n)&&n>=0;
 if(!value||value.version!=='chat-progress-v1'||!duration(value.elapsed_ms)||!Array.isArray(value.steps)||value.steps.length>256)invalid();
 let sequence=0,start=0;
 const steps=value.steps.map(step=>{
  if(!step||typeof step.phase!=='string'||!step.phase||step.phase.length>40||typeof step.label!=='string'||!step.label||step.label.length>500||!Number.isSafeInteger(step.sequence)||step.sequence<=sequence||!duration(step.started_ms)||step.started_ms<start||!duration(step.elapsed_ms)||step.started_ms+step.elapsed_ms>value.elapsed_ms+0.01||step.status!=='finished')invalid();
  sequence=step.sequence;start=step.started_ms;
  return {phase:step.phase,label:step.label,sequence,started_ms:start,elapsed_ms:step.elapsed_ms,status:'finished'};
 });
 return {version:'chat-progress-v1',elapsed_ms:value.elapsed_ms,steps};
}
module.exports={label,createProgress,normalizeTrace};
