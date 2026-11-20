'use strict';
// Immutable submission snapshots keep retries and late responses separate from current drafts.
(function(root){
  const context=typeof module==='object'&&module.exports?require('./conversation-context.js'):root.PlantConversationContext;
  const maps=typeof module==='object'&&module.exports?require('./dialogue-map.js'):root.PlantDialogueMap;
  function freeze(value){if(value&&typeof value==='object'){Object.values(value).forEach(freeze);Object.freeze(value);}return value;}
  // Actual server proposals determine presentation; user wording is never reclassified here.
  function recordActionProposals(result){
    const proposals=result?.proposals||(result?.proposal?[result.proposal]:[]),operations=new Set(['create','update','delete','restore']),seen=new Set();
    return proposals.filter(p=>p&&operations.has(p.operation)&&p.id&&!seen.has(p.id)&&seen.add(p.id));
  }


  function recordDraft(thread,message,result=message?.result,date,selectedProposal){
    const text=String(message?.submission?.text||'').trim(),proposal=selectedProposal||recordActionProposals(result,message,thread).find(p=>p.operation==='create'&&p.status==='pending'&&p.after?.body?.trim());
    const title=proposal?.after.title?.trim()||text.split('\n')[0].slice(0,100)||thread?.title||'대화에서 남긴 기록';
    const answer=String(result?.answer||'').trim();
    const body=proposal?.after.body?.trim()||[text?'나의 이야기\n'+text:'',answer?'AI와 나눈 내용\n'+answer:''].filter(Boolean).join('\n\n');
    const dates=typeof module==='object'&&module.exports?require('./diary-dates.js'):{isDiaryDate,seoulDate};
    const suggested=proposal?.after.date||result?.recording?.date;
    return {title,body,date:dates.isDiaryDate(suggested)?suggested:dates.isDiaryDate(date)?date:dates.seoulDate()};
  }
  function mergeRecordDraft(current,draft,append=true){
    if(!append)return {...draft};
    const body=String(current.body||'');
    return {title:current.title?.trim()?current.title:draft.title,date:body.trim()&&current.date?current.date:draft.date,
      body:!body.trim()?draft.body:body===draft.body||body.endsWith('\n\n'+draft.body)?body:body+'\n\n'+draft.body};
  }


  function recordDraftProposals(thread,message,result=message?.result){
    return recordActionProposals(result).filter(p=>p.operation==='create'&&p.status==='pending'&&p.after?.body?.trim());
  }

  function ensureRecordDraft(thread,message,result=message?.result,proposal){
    const draftId=proposal?'proposal-'+proposal.id:'turn-'+(result?.request_id||message.submission.request_id);
    thread.recordDrafts??=[];let draft=thread.recordDrafts.find(d=>d.id===draftId);
    if(!draft){draft={id:draftId,...recordDraft(thread,message,result,undefined,proposal),status:'draft',dismissed:false};thread.recordDrafts.push(draft);}
    return draft;
  }

  // Reconcile one conversation by its immutable request IDs, never by forking it.
  const clone=value=>JSON.parse(JSON.stringify(value));
  const stamp=value=>Number.isFinite(Date.parse(value))?Date.parse(value):0;
  function interrupted(message){return message?.kind==='assistant'&&!message.archived&&(message.status==='pending'||message.status==='error'&&(message.stage==='interrupted'||[
    '화면이 새로 열려 이전 처리 결과를 확인해야 합니다. 같은 제출본으로 재시도해 주세요.',
    '이전 처리 결과를 확인하지 못했습니다. 재시도할 수 있어요.'
  ].includes(message.error)));}
  function interruptPending(thread){for(const message of thread.messages)if(message.kind==='assistant'&&message.status==='pending'&&!message.archived){message.status='error';message.stage='interrupted';message.error='중단된 마지막 답변을 이어서 확인할 수 있어요.';}return thread;}
  function interruptedRequest(thread){
    if(!thread||thread.deletedAt)return null;
    const turns=thread.messages.filter(m=>m.kind==='user'||m.kind==='assistant'),last=turns.at(-1),user=turns.at(-2);
    if(!interrupted(last)||!last.submission?.request_id||last.submission.thread_id!==thread.id||user?.kind!=='user')return null;
    if(user.requestId?user.requestId!==last.submission.request_id:user.text!==last.submission.text)return null;
    return last;
  }
  function messageKeys(messages){const seen=new Map();return messages.map((message,index)=>{
    const next=messages[index+1],request=message.submission?.request_id||message.requestId||(message.kind==='user'&&next?.kind==='assistant'&&next.submission?.text===message.text?next.submission.request_id:'');
    const base=request?message.kind+':'+request:JSON.stringify([message.kind,message.createdAt||'',message.text||'']),count=seen.get(base)||0;seen.set(base,count+1);return base+'@'+count;
  });}
  function reconcileThread(saved,local){
    if(!saved)return clone(local);if(saved.id!==local.id)throw Error('서로 다른 대화를 합칠 수 없습니다.');
    const thread=clone(saved);if(thread.deletedAt)return thread;
    const serverKeys=messageKeys(thread.messages),positions=new Map(serverKeys.map((key,index)=>[key,index]));
    const localKeys=messageKeys(local.messages);
    for(const [index,message]of local.messages.entries()){
      const key=localKeys[index],position=positions.get(key);
      if(position===undefined){positions.set(key,thread.messages.length);thread.messages.push(clone(message));continue;}
      const current=thread.messages[position];if(message.kind!=='assistant'||current.archived)continue;
      // A completed server reply wins. Local completion/explicit stop beats a stale pending state.
      if(current.status==='success')continue;
      if(message.status==='success'&&message.result&&message.submission?.text===current.submission?.text){thread.messages[position]=clone(message);continue;}
      if(current.status==='cancelled')continue;
      if(message.status==='cancelled'||interrupted(current)&&!interrupted(message)&&message.status==='error')thread.messages[position]=clone(message);
    }
    const localVersion=local.inputVersion||0,savedVersion=saved.inputVersion||0,newer=localVersion>savedVersion||localVersion===savedVersion&&stamp(local.updatedAt)>=stamp(saved.updatedAt);
    thread.inputVersion=Math.max(localVersion,savedVersion);if(newer)thread.draft=local.draft||'';
    if(newer&&local.titleEdited){thread.title=local.title;thread.titleEdited=true;}
    thread.updatedAt=stamp(local.updatedAt)>stamp(saved.updatedAt)?local.updatedAt:saved.updatedAt;
    for(const field of ['context','mapContext'])if(local[field]&&(local[field].revision||0)>(thread[field]?.revision||0))thread[field]=clone(local[field]);
    const last=thread.messages.findLast(m=>m.kind==='assistant');if(last?.submission)thread.contextRequest=last.submission.request_id;
    const drafts=new Map((thread.recordDrafts||[]).map(d=>[d.id,d]));for(const draft of local.recordDrafts||[])if(!drafts.has(draft.id)||drafts.get(draft.id).status!=='saved'&&(draft.status==='saved'||newer))drafts.set(draft.id,clone(draft));if(drafts.size)thread.recordDrafts=[...drafts.values()];
    return thread;
  }
  const api={
    reconcileThread,interruptPending,interruptedRequest,
    recordDraftProposals,ensureRecordDraft,
    recordDraft,mergeRecordDraft,
    recordActionProposals,
    applyContext(thread,submission,value,mapValue){return ['v2','v3'].includes(submission.analysis_version)?maps.apply(thread,submission,mapValue,context):context.apply(thread,submission,value);},
    scope(thread,fallback){if(fallback?.collectionId==='personal')return fallback;const submitted=thread?.messages.findLast(m=>m.submission)?.submission;if(thread?.sampleScope?.collectionId==='personal'||submitted?.collection_id==='personal')return fallback;return thread?.sampleScope||(submitted?{profile:submitted.profile,questionId:submitted.example_id}:fallback);},
    submission(thread,scope,options={}){
      const version=options.version||root?.PlantChatVersion?.current()||'v1',map=['v2','v3'].includes(version)?maps.snapshot(thread,context):null;
      return Object.freeze({request_id:crypto.randomUUID(),thread_id:thread.id,...(root?.PlantLibraryPersistence?.epoch?{storage_epoch:root.PlantLibraryPersistence.epoch()}:{}),text:options.text??thread.draft,input_version:thread.inputVersion||0,profile:scope.profile,example_id:scope.questionId||'',collection_id:scope.collectionId||'samples',history:Object.freeze(thread.messages.filter(m=>m.kind==='user').slice(-4).map(m=>m.text)),context:freeze(['v2','v3'].includes(version)?map.flow||context.empty(thread.id):context.snapshot(thread,scope)),...(['v2','v3'].includes(version)?{analysis_version:version,map_context:freeze(map),conversation_ids:Object.freeze(maps.turns(thread,scope.collectionId||'samples').map(t=>t.id))}:{}),...(options.selection?{context_selection:options.selection}:{}),...(options.pendingTarget?{pending_target:options.pendingTarget}:{}),...(options.inspect===true?{inspect:true,...(root?.PlantChatSearch?{search_mode:root.PlantChatSearch.current()}:{})}:{})});
    },
    complete(thread,submission){const unchanged=!thread.deletedAt&&thread.id===submission.thread_id&&thread.draft===submission.text&&(thread.inputVersion||0)===submission.input_version;if(unchanged)thread.draft='';return unchanged;},
  };
  if(typeof module==='object'&&module.exports)module.exports=api;else root.PlantChatState=api;
})(typeof window==='undefined'?null:window);
