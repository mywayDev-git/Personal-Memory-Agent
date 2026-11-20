'use strict';
// Drafts remain separate from records until the editor's explicit save succeeds.
(()=>{
 const state=window.PlantChatState,key='plant-thought-record-editor-v1',el=id=>document.getElementById(id);
 const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;if(cls)n.className=cls;return n;};
 let origin=null;try{const value=JSON.parse(sessionStorage.getItem(key));if(value?.thread_id&&value?.draft_id)origin=value;}catch{}
 function setOrigin(value){origin=value;try{if(value)sessionStorage.setItem(key,JSON.stringify(value));else sessionStorage.removeItem(key);}catch{}}
 const same=(a,b)=>a?.thread_id===b?.thread_id&&a?.draft_id===b?.draft_id;
 const source=(thread,draft)=>({thread_id:thread.id,draft_id:draft.id});
 const values=()=>({title:el('recordTitle').value,date:el('recordDate').value,body:el('recordBody').value});
 const entry=ref=>previewThreads.find(t=>t.id===ref?.thread_id)?.recordDrafts?.find(d=>d.id===ref?.draft_id);
 function ensure(thread,message,result,proposal){const count=thread.recordDrafts?.length||0,draft=state.ensureRecordDraft(thread,message,result,proposal);if(thread.recordDrafts.length!==count)previewRemember();return draft;}
 function showSaved(draft){document.dispatchEvent(new CustomEvent('plant:open-draft-record',{detail:{recordId:draft.recordId}}));}
 function edit(thread,draft,append=true){
  if(draft.status==='saved'){showSaved(draft);return;}
  const ref=source(thread,draft);if(!same(origin,ref)){
   const next=state.mergeRecordDraft(values(),draft,append);el('recordTitle').value=next.title;el('recordDate').value=next.date;el('recordBody').value=next.body;
   Object.assign(draft,next);setOrigin(ref);
  }
  el('recordPreview')?.remove();previewRemember();go('emotion');el('recordBody').focus({preventScroll:true});previewToast(' 초안을 옮겼어요. 내용을 수정한 뒤 기록해 주세요.'.trim());
 }
 function markdownPreview(text){const preview=node('div',null,'record-markdown-preview ai-answer');if(window.PlantMarkdown)preview.innerHTML=window.PlantMarkdown.render(text);else preview.textContent=text;return preview;}
 function panel(thread,message,result,proposal){
  const draft=ensure(thread,message,result,proposal),card=node('section',null,'chat-record-draft');card.dataset.draftId=draft.id;card.setAttribute('aria-label','대화 기록 초안');card.tabIndex=-1;
  card.append(node('strong',draft.status==='saved'?'저장한 기록':'기록 초안 · 저장 전'),node('h3',draft.title),node('p',draft.date,'chat-record-draft-date'),markdownPreview(draft.body));
  if(draft.status==='saved'){
   const open=node('button','저장한 기록 보기');open.type='button';open.onclick=()=>showSaved(draft);card.append(open);return card;
  }
  card.append(node('p','감정 갈무리에서 제목·날짜·내용을 수정한 뒤 저장할 수 있어요.','chat-record-draft-note'));
  let appendInput;const current=values();
  if(!same(origin,source(thread,draft))&&(current.title.trim()||current.body.trim())){
   const label=node('label','작성 중인 기록에 이어 쓰기','chat-record-draft-merge');appendInput=node('input');appendInput.type='checkbox';appendInput.checked=true;label.prepend(appendInput);card.append(label,node('p','선택을 해제하면 이 초안으로 새로 작성합니다.','chat-record-draft-note'));
  }
  const actions=node('div',null,'transfer-actions'),proceed=node('button','기록하기'),cancel=node('button','닫기');proceed.type=cancel.type='button';proceed.onclick=()=>edit(thread,draft,appendInput?appendInput.checked:true);
  cancel.onclick=()=>{draft.dismissed=true;previewRemember();card.remove();};actions.append(proceed,cancel);card.append(actions);return card;
 }
 function candidates(thread,message,result){return state.recordDraftProposals(thread,message,result);}
 function automatic(body,actions,thread,message,result){
  const proposals=candidates(thread,message,result);
  if(proposals.length){for(const p of proposals){const draft=ensure(thread,message,result,p);
   if(result.action_trace?.plan?.review_proposal_ids?.includes(p.id)&&!(draft.reviewedRequestIds||[]).includes(result.request_id)){draft.dismissed=false;draft.reviewedRequestIds=[...(draft.reviewedRequestIds||[]),result.request_id];previewRemember();}
   if(!draft.dismissed)body.append(panel(thread,message,result,p));
  }}
  else{const draft=thread.recordDrafts?.find(d=>d.id==='turn-'+(result.request_id||message.submission.request_id));if(draft&&!draft.dismissed)body.append(panel(thread,message,result));}
 }
 function button(result,thread,message,actions){
  const prepared=candidates(thread,message,result)[0],draftId=prepared?'proposal-'+prepared.id:'turn-'+(result.request_id||message.submission.request_id),savedDraft=thread.recordDrafts?.find(d=>d.id===draftId&&d.status==='saved');const b=node('button',savedDraft?'저장한 기록 보기':'기록하기','ai-record-draft');b.type='button';b.title='이 대화로 기록 초안 만들기';b.disabled=!!thread.deletedAt;
  b.onclick=()=>{
   const proposals=candidates(thread,message,result);let firstCard;
   for(const p of proposals.length?proposals:[undefined]){
    const draft=ensure(thread,message,result,p);if(draft.status==='saved'&&proposals.length<2){showSaved(draft);return;}draft.dismissed=false;
    let card=[...actions.parentElement.querySelectorAll(':scope > .chat-record-draft')].find(n=>n.dataset.draftId===draft.id);
    if(!card){card=panel(thread,message,result,p);actions.parentElement.append(card);}firstCard??=card;
   }
   previewRemember();firstCard?.focus({preventScroll:true});firstCard?.scrollIntoView({behavior:'smooth',block:'nearest'});
  };return b;
 }
 function saved(ref,record){const draft=entry(ref);if(draft)Object.assign(draft,{title:record.title,body:record.body,date:record.date,status:'saved',recordId:record.id,dismissed:false});if(same(origin,ref))setOrigin(null);}
 function reconcile(records){for(const record of records)if(record.chat_draft){const draft=entry(record.chat_draft);if(draft)Object.assign(draft,{title:record.title,body:record.body,date:record.date,status:'saved',recordId:record.id});}}
 document.addEventListener('input',event=>{
  if(!origin||!['recordTitle','recordBody','recordDate'].includes(event.target.id))return;const draft=entry(origin);if(draft&&draft.status!=='saved'){Object.assign(draft,values());previewRemember();}
 });
 window.PlantRecordDrafts=Object.freeze({panel,button,automatic,candidates,edit,origin:()=>origin?{...origin}:null,saved,reconcile});
})();
