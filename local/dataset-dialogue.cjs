const {safeConversation}=require('./core.cjs');
function validateDialogueSelection(ds,ids,stage){
 const byQuestion=new Map(ds.questions.questions.map(q=>[q.id,q])),contexts=new Map(ds.contexts.contexts.map(c=>[c.id,c]));
 for(const [i,id]of ids.entries()){const c=contexts.get(byQuestion.get(id)?.context_id);if(!c?.dialogue)continue;if(stage!=='end_to_end')throw Error('실제 후속 대화는 전체 실행 단계에서 앞 턴과 함께 실행하세요.');for(const dep of c.dialogue.depends_on)if(!ids.slice(0,i).includes(dep))throw Error('앞 턴을 먼저 함께 선택해야 합니다: '+dep);}
}
function applyDialogue(context,run,accessible){
 if(!context.dialogue)return [];
 const turns=[],trace=[];
 for(const id of context.dialogue.depends_on){const r=run.results.find(r=>r.question_id===id),a=r?.stages.answer;if(!a||typeof a.answer!=='string')throw Object.assign(Error('앞 턴 답변이 없어 후속 턴을 실행하지 않았습니다: '+id),{blocked:true,code:'DIALOGUE.PREREQUISITE'});
  const refs=[...new Map((a.citations||[]).filter(c=>c.source_id).map(c=>[c.source_id,{source_id:c.source_id,revision:c.revision||1}])).values()];
  turns.push({role:'user',text:r.question},{role:'assistant',text:a.answer,source_refs:refs});trace.push({question_id:id,status:r.status,answer:a.answer,source_refs:refs});
 }
 context.conversation=safeConversation({...context,conversation:[...context.conversation,...turns]},accessible);return trace;
}
function dialogueSummaries(ds,results){
 const contexts=new Map(ds.contexts.contexts.map(c=>[c.id,c])),grouped=new Map();
 for(const q of ds.questions.questions){const d=contexts.get(q.context_id)?.dialogue;if(d){if(!grouped.has(d.id))grouped.set(d.id,[]);grouped.get(d.id).push(q.id);}}
 return [...grouped].map(([id,questions])=>{const rows=results.filter(r=>questions.includes(r.question_id));return {id,question_ids:questions,expected_turns:questions.length,executed_turns:rows.length,status:rows.some(r=>['FAIL','ERROR','BLOCKED','VALIDATION_FAILED'].includes(r.status))?'FAIL':rows.some(r=>r.status==='NOT_APPLICABLE')?'NOT_APPLICABLE':'PENDING_REVIEW',semantic_status:'PENDING_REVIEW',citation_fail_turns:rows.filter(r=>r.stages?.answer?.assessment?.axes?.citation?.status==='FAIL').map(r=>r.question_id),note:'마지막 정답만으로 전체 대화 통과를 만들지 않습니다. 각 턴의 의미 판정은 사람 검토 대상입니다.'};}).filter(g=>g.executed_turns);
}
module.exports={validateDialogueSelection,applyDialogue,dialogueSummaries};
