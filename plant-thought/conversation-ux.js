'use strict';
// Use only the existing message, source and action styles.
const uxTabId=crypto.randomUUID();
const uxWriteIds=new Map();
let uxPending=null,uxChoice=null,uxTurnScope=null,uxNextSearch=null,uxTurnRefs=[],uxTarget=null;
let uxDetailViewToken=0;
const uxSession=()=>uxTabId+':'+(chatHistoryState.activeId||'writer');
function uxRequest(action,payload={}){
 return demoRequest('ux/'+action,{...payload,session_id:payload.session_id||uxSession()});
}
function uxActions(reply){
 const actions=document.createElement('div');actions.className='chat-followups';reply.after(actions);return actions;
}
function uxRecordFields(text){
 const m=text.match(/^제목: ([^\r\n]+)\r?\n기록일: (\d{4}-\d{2}-\d{2})\r?\n감정: ([^\r\n]*)(?:\r?\n일정 시각: [^\r\n]*)?(?:\r?\n태그: [^\r\n]*)?\r?\n\r?\n([\s\S]*)$/);
 return m?{title:m[1],date:m[2],mood:m[3],body:m[4],type:'일기'}:{title:'기록',date:today,body:text,type:'기록'};
}
async function uxPersist(record,text){
 let requestId=record.uxRequestId||uxWriteIds.get(text);
 if(!requestId){requestId=crypto.randomUUID();uxWriteIds.set(text,requestId);}
 record.uxRequestId=requestId;
 const sessionId=record.uxSessionId||(record.uxSessionId=uxSession());
 let result;
 try{result=await uxRequest('save',{request_id:requestId,text,session_id:sessionId});}
 catch(error){
  try{result=await uxRequest('status',{operation_id:requestId,session_id:sessionId});}
  catch{error.uxOperation={id:requestId,session_id:sessionId};error.message='저장 결과를 확인하지 못했어요. 다시 시도하면 같은 작업의 상태부터 확인할게요.';throw error;}
 }
 if(result.state==='committed'){uxWriteIds.delete(text);return result;}
 const error=Error(result.state==='running'?'아직 저장 중이에요. 잠시 뒤 상태를 다시 확인해 주세요.':result.error||'기록을 저장하지 못했어요. 입력 내용은 유지했어요.');
 error.uxOperation={id:requestId,session_id:sessionId};throw error;
}
async function uxPlan(body,clarification,knownIntent){
 uxTurnScope=null;uxTurnRefs=[];
 const choice=uxChoice;uxChoice=null;
 const result=await uxRequest('plan',{
  text:body,decision_id:choice?.decision_id||clarification?.decision_id,choice_id:choice?.choice_id,
  pending_operation_id:uxPending?.session_id===uxSession()?uxPending.id:undefined,
  target_key:uxTarget||clarification?.edit_target_key||undefined,edit_request:clarification?.edit_request,intent_hint:knownIntent,
 });
 if(uxPending&&!['confirm','cancel'].includes(result.intent)){
  const old=uxPending;uxPending=null;old.actions?.remove();messageActions.delete(old.reply);
  await uxRequest('cancel',{operation_id:old.id,session_id:old.session_id}).catch(()=>{});
 }
 uxTarget=null;
 if(result.scope_id)uxTurnScope=result.scope_id;
 return result;
}
function uxShowChoices(reply,plan){
 const state={kind:'ux',text:plan.original_text||'',decision_id:plan.decision_id,choices:plan.choices||[],edit_target_key:plan.edit_target_key,edit_request:plan.edit_request};
 pendingClarification=state;
 if(!state.choices.length)return;
 const actions=uxActions(reply);
 for(const choice of state.choices){
  addChatAction(actions,choice.label,'',()=>{
   if(demoBusy||pendingClarification?.decision_id!==state.decision_id)return;
   uxChoice={decision_id:state.decision_id,choice_id:choice.id};
   return handleChatInput(choice.label);
  });
 }
 messageActions.set(reply,{type:'ux-choices',state});
}
async function uxHandlePlan(plan,reply,text){
 if(plan.intent==='unclear'&&plan.clarification_kind==='ux'){
  reply.textContent=plan.clarification;chatStatus.textContent='추가 답변을 기다리고 있어요.';uxShowChoices(reply,{...plan,original_text:text});return true;
 }
 if(plan.intent==='edit'){
  reply.textContent='“'+plan.record.title+'” 기록을 이렇게 바꿀까요?\n\n변경 전\n'+plan.before+'\n\n변경 후\n'+plan.after;
  reply.dataset.uxRefs=JSON.stringify(plan.refs||[]);
  chatStatus.textContent='변경 전·후를 확인하고 수정 반영 또는 취소를 선택해 주세요.';
  uxShowOperation(reply,{id:plan.operation_id,session_id:uxSession(),date:plan.record.date});return true;
 }
 if(plan.intent==='confirm'){
  const pending=uxPending;uxPending=null;
  await uxFinishOperation(plan.operation_id,pending?.session_id||uxSession(),reply,pending);return true;
 }
 if(plan.intent==='cancel'){
  const pending=uxPending;uxPending=null;
  const state=await uxRequest('cancel',{operation_id:plan.operation_id,session_id:pending?.session_id||uxSession()});
  pending?.actions?.remove();
  reply.textContent=state.state==='cancelled'?'수정 작업을 취소했어요. 기록은 바꾸지 않았어요.':'이미 반영되었거나 처리 중인 작업이에요. 저장 상태를 다시 확인해 주세요.';
  chatStatus.textContent=state.state==='cancelled'?'수정 취소':'저장 상태를 확인해 주세요.';
  return true;
 }
 return false;
}
function uxShowOperation(reply,state){
 const actions=uxActions(reply),draft={...state,reply,actions};
 uxPending=draft;messageActions.set(reply,{type:'ux-edit',state});
 const valid=()=>uxPending===draft&&draft.session_id===uxSession();
 addChatAction(actions,'수정 반영','',()=>{
  if(demoBusy||!valid())return;
  addBubble('user','이 수정 내용을 반영해 주세요.');
  return withDemoRequest(async()=>{
   const response=addBubble('bot','수정 내용을 저장하고 있어요…');
   await uxFinishOperation(draft.id,draft.session_id,response,draft);
   rememberCompletedTurn('이 수정 내용을 반영해 주세요.',response.textContent);
  }).catch(error=>{chatStatus.textContent=error.message;});
 });
 addChatAction(actions,'취소','',()=>{
  if(demoBusy||!valid())return;
  addBubble('user','수정하지 않을게요.');
  return withDemoRequest(async()=>{
   const state=await uxRequest('cancel',{operation_id:draft.id,session_id:draft.session_id});
   const response=addBubble('bot',state.state==='cancelled'?'수정을 취소했어요. 기록은 바꾸지 않았어요.':'이미 반영되었거나 처리 중인 작업이에요.');
   draft.actions.remove();messageActions.delete(draft.reply);uxPending=null;
   chatStatus.textContent=state.state==='cancelled'?'수정 취소':'저장 상태를 확인해 주세요.';
   rememberCompletedTurn('수정하지 않을게요.',response.textContent);
  }).catch(error=>{chatStatus.textContent=error.message;});
 });
}
async function uxFinishOperation(id,sessionId,reply,draft){
 let result;
 try{result=await uxRequest('commit',{operation_id:id,session_id:sessionId});}
 catch(error){
  try{result=await uxRequest('status',{operation_id:id,session_id:sessionId});}
  catch{result={state:'unknown',error:'수정 결과를 확인하지 못했어요.'};}
 }
 if(result.state==='committed'){
  draft?.actions?.remove();if(draft)messageActions.delete(draft.reply);
  uxPending=null;await restoreArchive();
  reply.textContent='수정을 반영했어요.';
  chatStatus.textContent='수정 완료';
  reply.dataset.uxRefs=JSON.stringify([{key:result.memory.memory_key,version:result.memory.summary_artifact_id}]);
  uxTurnRefs=JSON.parse(reply.dataset.uxRefs);
  uxAddRecordLinks(reply,uxTurnRefs);
 }else{
  chatStatus.textContent='수정 상태를 확인해 주세요.';
  reply.textContent=result.error||(result.state==='running'?'아직 처리 중이에요. 잠시 뒤 상태를 확인해 주세요.':'수정 결과를 확인하지 못했어요.');
  if(result.state==='conflict'){
   draft?.actions?.remove();uxPending=null;
   const actions=uxActions(reply);
   addChatAction(actions,'기록 열기','',()=>uxOpenKey(draft?.key||JSON.parse(draft?.reply?.dataset.uxRefs||'[]')[0]?.key));
  }else{
   const actions=uxActions(reply);
   addChatAction(actions,'다시 시도','',()=>{actions.remove();return withDemoRequest(()=>uxFinishOperation(id,sessionId,reply,draft)).catch(error=>{chatStatus.textContent=error.message;});});
  }
 }
 formatReplies();scrollChatToBottom();
}
async function uxSaveExplicit(record,reply){
 const memory=await persistDemoRecord(record,reply);
 reply.textContent='기록을 저장했어요. '+record.date+' 기록에서 확인할 수 있어요.';
 chatStatus.textContent='저장 완료';
 uxTurnRefs=[{key:memory.memory_key,version:memory.summary_artifact_id}];
 reply.dataset.uxRefs=JSON.stringify(uxTurnRefs);
 uxAddRecordLinks(reply,uxTurnRefs);
}
async function uxSearch(payload){
 const next=uxNextSearch;uxNextSearch=null;
 const result=await uxRequest('search',{...payload,scope_id:next?.scope_id||uxTurnScope,expand:next?.expand===true});
 uxTurnRefs=result.refs||[];
 return result;
}
function uxAfterAnswer(query,reply,result){
 const refs=result.refs||[];
 reply.dataset.uxRefs=JSON.stringify(refs);uxTurnRefs=refs;
 if(result.user_correction){
  const note=document.createElement('p');note.className='muted small';
  note.textContent='동행인 등 정정한 표현은 이번 대화에서 알려주신 내용이며, 펼쳐 보는 인용은 변경 전 저장 기록이에요.';
  reply.after(note);
 }
 uxAddRecordLinks(reply,refs);
 if(result.coverage?.can_expand&&['abstain','partial_answer'].includes(result.answer?.action)){
  const scope=uxTurnScope,actions=uxActions(reply);
  addChatAction(actions,'추가로 찾아보기','',()=>{
   if(demoBusy)return;
   return withDemoRequest(async()=>{
    addBubble('user','이 질문의 관련 기록을 더 찾아줘: '+query);
    const answer=addBubble('bot','관련 기록을 더 확인하고 있어요…'),progress=startChatProgress(answer,'검색 범위를 넓히고 있어요…');
    try{uxNextSearch={expand:true,scope_id:scope};await answerInChat(query,answer,progress);rememberCompletedTurn('관련 기록 추가 조회: '+query,answer.textContent);}
    catch(error){answer.textContent='추가 조회를 완료하지 못했어요. '+error.message;uxRetry(answer,query,error);}
    finally{progress.stop();formatReplies();}
   });
  });
  if(result.answer?.action==='abstain'){
   const note=document.createElement('p');note.className='muted small';
   note.textContent='현재 선택된 일부 기록에서 확인한 결과예요. 관련 기록을 더 찾아볼 수 있어요.';reply.after(note);
  }
 }
}
function uxAddRecordLinks(reply,refs){
 if(!refs.length)return;
 const actions=uxActions(reply);
 for(const r of refs.slice(0,3)){
  const record=records.find(item=>item.memoryKey===r.key);
  addChatAction(actions,refs.length===1?'기록 열기':(record?.title||'참고 기록')+' 열기','',()=>uxOpenKey(r.key,r.version));
 }
}
async function uxOpenKey(key,version,origin='chat'){
 if(!key)return;
 try{
  const {source,summary_id}=await demoJson('/summary-memory/original?key='+encodeURIComponent(key));
  if(version&&summary_id!==version){await restoreArchive();chatStatus.textContent='근거 기록이 변경됐어요. 최신 기록을 열었어요.';}
  const r=uxRecordFields(source.text);
  document.getElementById('detailTitle').textContent=r.title;
  document.getElementById('detailDate').textContent=r.date+' · 기록';
  document.getElementById('detailBody').textContent=r.body;go('recordDetail');uxDetailEdit(key,summary_id,origin);
 }catch(error){await restoreArchive();chatStatus.textContent='기록을 열지 못했어요. '+error.message;}
}
function uxDetailEdit(key,version,origin='archive'){
 const viewToken=++uxDetailViewToken;
 const back=document.querySelector('#recordDetail .record-detail > button');
 back.textContent=origin==='chat'?'← 사색 대화로 돌아가기':'← 서재 보관소로 돌아가기';
 back.onclick=()=>{go(origin==='chat'?'chat':'archive');if(origin==='chat')chatInput.focus();};
 const card=document.querySelector('#recordDetail .card');
 for(const old of card.querySelectorAll('.chat-followups,.ux-detail-status'))old.remove();
 const actions=document.createElement('div');actions.className='chat-followups';card.append(actions);
 addChatAction(actions,'수정하기','',()=>{
  if(demoBusy)return;
  uxTarget=key;go('chat');
  addBubble('bot','이 기록에서 어느 부분을 어떻게 바꿀까요? 바꿀 내용을 입력하면 변경 전·후를 보여드릴게요.');
  chatInput.focus();
 });
 addChatAction(actions,'기억 삭제','',()=>{
  if(demoBusy||viewToken!==uxDetailViewToken)return;
  const notice=document.createElement('p');notice.className='muted small ux-detail-status';
  notice.textContent='이 기억을 삭제할까요? 삭제하면 보관소와 기억 조회에서 제외됩니다.';card.append(notice);
  actions.replaceChildren();
  const request={request_id:crypto.randomUUID(),key,expected:version,session_id:uxSession()};
  const current=()=>viewToken===uxDetailViewToken;
  const retry=message=>{
   if(!current())return;
   notice.textContent=message;actions.replaceChildren();
   addChatAction(actions,'다시 시도','',submit);
  };
  const submit=async()=>{
   if(demoBusy||!current())return;
   demoBusy=true;updateDemoControls();notice.textContent='기억을 삭제하고 있어요…';actions.replaceChildren();
   try{
    let result;
    try{result=await uxRequest('delete',request);}
    catch(error){
     try{result=await uxRequest('status',{operation_id:request.request_id,session_id:request.session_id});}
     catch{throw error;}
    }
    if(result.state==='committed'&&result.deleted_key===key){
     for(let i=records.length-1;i>=0;i--)if(records[i].memoryKey===key)records.splice(i,1);
     uxScrubHistory();refreshRecords();
     if(current()){
      document.getElementById('detailTitle').textContent='기억을 삭제했어요.';
      document.getElementById('detailDate').textContent='';document.getElementById('detailBody').textContent='';
      notice.textContent='이 기억은 보관소와 기억 조회에서 제외됐어요.';
     }
     await restoreArchive();
    }else if(result.state==='conflict'){
     if(current()){
      notice.textContent=result.error||'기억이 변경됐어요. 최신 내용을 다시 확인해 주세요.';
      addChatAction(actions,'최신 기록 열기','',()=>uxOpenKey(key,undefined,origin));
     }
    }else retry(result.error||(result.state==='running'?'아직 처리 중이에요. 다시 시도하면 같은 삭제 작업의 상태를 확인해요.':'삭제 결과를 확인하지 못했어요.'));
   }catch(error){retry('삭제 결과를 확인하지 못했어요. '+error.message);}
   finally{demoBusy=false;updateDemoControls();}
  };
  addChatAction(actions,'삭제하기','',submit);
  addChatAction(actions,'취소','',()=>{if(!demoBusy&&current())uxDetailEdit(key,version,origin);});
 });
}
function uxRetry(reply,body,error){
 const actions=uxActions(reply);
 addChatAction(actions,'다시 시도','',()=>{
  if(demoBusy)return;
  actions.remove();
  if(error.uxOperation){
   return withDemoRequest(async()=>{
    const op=error.uxOperation;
    const state=await uxRequest('status',{operation_id:op.id,session_id:op.session_id});
    if(state.state==='committed'){
     await restoreArchive();reply.textContent='기록이 저장된 것을 확인했어요.';
     uxAddRecordLinks(reply,[{key:state.memory.memory_key,version:state.memory.summary_artifact_id}]);formatReplies();
    }else if(state.state==='running'){reply.textContent='아직 저장 중이에요. 잠시 뒤 다시 확인해 주세요.';uxRetry(reply,body,error);}
    else await uxFinishOperation(op.id,op.session_id,reply,null);
   }).catch(e=>{reply.textContent=e.message;uxRetry(reply,body,error);});
  }
  return handleChatInput(body);
 });
 messageActions.set(reply,{type:'ux-retry',body,operation:error.uxOperation||null});
}
function uxRestoreAction(reply,action){
 if(action?.type==='ux-choices'&&pendingClarification?.decision_id===action.state.decision_id)uxShowChoices(reply,action.state);
 if(action?.type==='ux-edit'){
  uxRequest('status',{operation_id:action.state.id,session_id:action.state.session_id}).then(op=>{
   if(op.state==='prepared'||op.state==='failed')uxShowOperation(reply,action.state);
   else if(op.state==='committed')uxAddRecordLinks(reply,[{key:op.memory.memory_key,version:op.memory.summary_artifact_id}]);
  }).catch(()=>{});
 }
 if(action?.type==='ux-retry')uxRetry(reply,action.body,{uxOperation:action.operation});
}
function uxScrubHistory(){
 const valid=new Map(records.map(r=>[r.memoryKey,r.version]));
 function invalid(refs){return refs?.some(r=>valid.get(r.key)!==r.version);}
 for(const thread of chatHistoryState.threads){
  thread.context=(thread.context||[]).filter(m=>!invalid(m.refs));
  for(const message of thread.messages||[])if(invalid(message.refs)){
   message.text='이 답변의 근거 기록이 변경되었거나 현재 사용할 수 없어 다시 조회가 필요해요.';message.notes=[];message.action=null;message.refs=[];
  }
 }
 for(const content of conversation.querySelectorAll('.bot-content')){
  let refs=[];try{refs=JSON.parse(content.dataset.uxRefs||'[]');}catch{}
  if(invalid(refs)){
   content.textContent='이 답변의 근거 기록이 변경되었거나 현재 사용할 수 없어 다시 조회가 필요해요.';
   delete content.dataset.formatted;delete content.dataset.messageText;content.dataset.uxRefs='[]';
   messageActions.delete(content);
   for(const node of content.parentElement?.querySelectorAll('.message-sources,.chat-followups')||[])node.remove();
  }
 }
}
const uxOriginalRemember=rememberCompletedTurn;
rememberCompletedTurn=function(question,answer){
 uxOriginalRemember(question,answer);
 const thread=chatHistoryState.threads.find(t=>t.id===chatHistoryState.activeId);
 if(thread)for(const item of (thread.context||[]).slice(-2))item.refs=[...uxTurnRefs];
};
const uxOriginalRememberChat=rememberChat;
rememberChat=function(){
 uxOriginalRememberChat();
 const thread=chatHistoryState.threads.find(t=>t.id===chatHistoryState.activeId);
 if(thread)thread.uxPending=uxPending?{id:uxPending.id,session_id:uxPending.session_id}:null;
};
const uxOriginalOpenChat=openChat;
openChat=function(thread){
 uxPending=null;uxTarget=null;uxTurnScope=null;uxTurnRefs=[];
 if(!thread)return uxOriginalOpenChat(thread);
 return uxRequest('access').then(({records:allowed})=>{
  const map=new Map(allowed.map(r=>[r.key,r.version]));
  thread.context=(thread.context||[]).filter(m=>!(m.refs||[]).some(r=>map.get(r.key)!==r.version));
  for(const m of thread.messages||[])if((m.refs||[]).some(r=>map.get(r.key)!==r.version)){m.text='이 답변의 근거 기록이 변경되었거나 현재 사용할 수 없어 다시 조회가 필요해요.';m.notes=[];m.action=null;m.refs=[];}
  uxOriginalOpenChat(thread);closeChatSidebar();
 }).catch(error=>{chatStatus.textContent='대화의 근거 상태를 확인하지 못했어요. '+error.message;});
};
const uxOriginalOpenRecord=openRecord;
openRecord=function(index){uxOriginalOpenRecord(index);const record=records[index];if(record?.memoryKey)uxDetailEdit(record.memoryKey,record.version,'archive');};
