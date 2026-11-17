function arithmeticTask(text){
 const tail=String(text).split(/[,，;；!?？]\s*/u).map(s=>s.trim()).filter(Boolean).at(-1)?.replace(/[.!?？]+$/u,'').replace(/\s+/gu,'')||'';
 const n='-?\\d+(?:\\.\\d+)?',ending='(?:얼마(?:야|인가요|니)?|몇(?:이야|인가요)?|결과(?:는)?|계산해줘|알려줘)?';
 return new RegExp('^'+n+'(?:에|와|과|에서)'+n+'(?:를|을)?(?:더하면|더해줘|빼면|빼줘|곱하면|곱해줘|나누면|나눠줘)'+ending+'$','u').test(tail)||new RegExp('^'+n+'[+*/×÷-]'+n+'(?:은|는|=)?'+ending+'$','u').test(tail);
}
function applySummaryDialogue(context,run,accessible){
 context.summary_generated_conversation=[];const trace=[];if(!context.dialogue)return trace;
 const allowed=new Set(accessible.map(s=>s.id+':'+s.revision));
 for(const id of context.dialogue.depends_on){
  const result=run.results.find(r=>r.question_id===id),answer=result?.stages.answer;
  if(!answer||typeof answer.answer!=='string')throw Object.assign(Error('앞 턴의 실제 답변이 없어 후속 턴을 실행하지 않았습니다: '+id),{blocked:true,code:'DIALOGUE.PREREQUISITE'});
  const refs=[...new Map((answer.citations||[]).filter(c=>c.source_id).map(c=>[c.source_id+':'+(c.revision||1),{source_id:c.source_id,revision:c.revision||1}])).values()];
  const eligible=!(answer.citation_errors||[]).length&&refs.every(r=>allowed.has(r.source_id+':'+r.revision))&&(refs.length||['abstain','clarify'].includes(answer.action)||arithmeticTask(result.question));
  trace.push({question_id:id,answer:answer.answer,source_refs:refs,included:!!eligible,origin:'actual_generated_summary_answer'});
  if(eligible)context.summary_generated_conversation.push({role:'user',text:result.question},{role:'assistant',text:answer.answer,source_refs:refs});
 }
 context.summary_generated_conversation=context.summary_generated_conversation.slice(-8);context.conversation=context.summary_generated_conversation;return trace;
}
function needsHistory(text){return /(그\s*(사람|것|곳|때|건|내용|일|인계)|그러면|그럼|거기|방금)/u.test(text);}
function contextualQuery(text,context){if(!needsHistory(text))return text;const history=context.summary_generated_conversation||[],last=history.at(-1),question=history.at(-2);if(last?.role!=='assistant'||question?.role!=='user')return text;return text+'\n직전 질문: '+question.text+'\n직전 실제 답변: '+last.text;}
module.exports={arithmeticTask,applySummaryDialogue,contextualQuery,needsHistory};
