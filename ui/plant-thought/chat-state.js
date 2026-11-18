'use strict';
// Immutable submission snapshots keep retries and late responses separate from current drafts.
(function(root){
  const context=typeof module==='object'&&module.exports?require('./conversation-context.js'):root.PlantConversationContext;
  const maps=typeof module==='object'&&module.exports?require('./dialogue-map.js'):root.PlantDialogueMap;
  function freeze(value){if(value&&typeof value==='object'){Object.values(value).forEach(freeze);Object.freeze(value);}return value;}
  // Presentation guard only: this never changes plans, proposals, or stored data.
  function recordRequest(text){
    const active=String(text||'').normalize('NFKC').replace(/```[\s\S]*?(?:```|$)|~~~[\s\S]*?(?:~~~|$)/g,' ').replace(/^\s*>.*$/gm,' ').replace(/`[^`\n]*`|"[^"\n]*"|'[^'\n]*'|“[^”]*”|‘[^’]*’|「[^」]*」|『[^』]*』/g,' ');
    return active.split(/[.!?。！？\n]+/).some(clause=>{
      const text=clause.trim();
      return /(?:저장|기록|메모|기억|수정|정정|변경|삭제|제거|복원|취소)\s*(?:해\s*(?:줘|주세요|둬|놔|두세요|놓으세요|줄래(?:요)?|주실래(?:요)?|주시겠어요)|하세요|해라|하자)/.test(text)
        ||/(?:고쳐|바꿔|지워|되돌려)\s*(?:줘|주세요|줄래(?:요)?)/.test(text)
        ||/(?:저장|기록|메모|기억|수정|정정|변경|삭제|제거|복원)\s*(?:하고\s*싶(?:어|어요|습니다)|할래(?:요)?|할게(?:요)?)/.test(text)
        ||/^(?:저장|기록|메모|기억|수정|정정|변경|삭제|제거|복원|취소)(?:해)?$/.test(text)
        ||/^(?:please\s+)?(?:save|store|remember|record|update|edit|delete|remove|restore)\b/i.test(text);
    });
  }
  function recordActionProposals(result,message,thread){
    const proposals=result?.proposals||(result?.proposal?[result.proposal]:[]),operations=new Set(['create','update','delete','restore']);
    const requested=recordRequest(message?.submission?.text),taskId=result?.action_trace?.plan?.task_id;
    const at=thread?.messages?.indexOf(message)??-1,earlier=thread?.messages?.slice(0,at<0?thread.messages.length:at)||[];
    const continued=!!taskId&&earlier.some(m=>m.kind==='assistant'&&m.result?.task_id===taskId&&(recordRequest(m.submission?.text)||m.result.action==='draft'));
    return proposals.filter(p=>{
      if(!operations.has(p.operation))return false;
      const receipt=result.executions?.find(r=>r.proposal_id===p.id)||(result.execution?.proposal_id===p.id?result.execution:null);
      return !!receipt||requested||continued||['draft','committed','cancelled'].includes(result.action)||result.recording?.status==='draft';
    });
  }

  const api={
    recordActionProposals,
    applyContext(thread,submission,value,mapValue){return ['v2','v3'].includes(submission.analysis_version)?maps.apply(thread,submission,mapValue,context):context.apply(thread,submission,value);},
    scope(thread,fallback){if(fallback?.collectionId==='personal')return fallback;const submitted=thread?.messages.findLast(m=>m.submission)?.submission;if(thread?.sampleScope?.collectionId==='personal'||submitted?.collection_id==='personal')return fallback;return thread?.sampleScope||(submitted?{profile:submitted.profile,questionId:submitted.example_id}:fallback);},
    submission(thread,scope,options={}){
      const version=options.version||root?.PlantChatVersion?.current()||'v1',map=['v2','v3'].includes(version)?maps.snapshot(thread,context):null;
      return Object.freeze({request_id:crypto.randomUUID(),thread_id:thread.id,text:options.text??thread.draft,input_version:thread.inputVersion||0,profile:scope.profile,example_id:scope.questionId||'',collection_id:scope.collectionId||'samples',history:Object.freeze(thread.messages.filter(m=>m.kind==='user').slice(-4).map(m=>m.text)),context:freeze(['v2','v3'].includes(version)?map.flow||context.empty(thread.id):context.snapshot(thread,scope)),...(['v2','v3'].includes(version)?{analysis_version:version,map_context:freeze(map),conversation_ids:Object.freeze(maps.turns(thread,scope.collectionId||'samples').map(t=>t.id))}:{}),...(options.selection?{context_selection:options.selection}:{}),...(options.pendingTarget?{pending_target:options.pendingTarget}:{}),...(options.inspect===true?{inspect:true}:{})});
    },
    complete(thread,submission){const unchanged=!thread.deletedAt&&thread.id===submission.thread_id&&thread.draft===submission.text&&(thread.inputVersion||0)===submission.input_version;if(unchanged)thread.draft='';return unchanged;},
  };
  if(typeof module==='object'&&module.exports)module.exports=api;else root.PlantChatState=api;
})(typeof window==='undefined'?null:window);
