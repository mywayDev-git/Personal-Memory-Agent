'use strict';
// Connected mode only; preview.cjs never loads this script.
(()=>{
  const el=id=>document.getElementById(id),state=window.PlantChatState;
  let token=null,bootstrapPromise=null,ready=false,modelActionBusy=false;
  const controllers=new Map();
  const stageName={context:'대화 맥락 확인',scope:'기록 범위 확인',retrieval:'원문 검색',connection:'AI 연결',model:'AI 응답 생성',validation:'답변 검증'};
  const actionName={committed:'기록 반영 완료',cancelled:'취소 완료',multi_result:'작업별 결과',answer:'답변',partial_answer:'부분 확인',abstain:'확인 불가',clarify:'확인 질문',report_conflict:'기록 충돌',deny:'전제 확인',draft:'기록 초안 · 저장되지 않음',empathy:'감정 나누기',advice:'작은 제안'};
  const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;if(cls)n.className=cls;return n;};
  const operationBusy=new Set();
  async function operationRequest(route,body){await bootstrap();const response=await fetch('/api/chat/'+route,{method:'POST',headers:{'Content-Type':'application/json','X-Plant-Token':token},body:JSON.stringify(body)});const data=await response.json();if(!response.ok)throw Object.assign(Error(data.error||'기록 처리를 확인하지 못했습니다.'),{status:response.status});return data;}
  function proposalList(result){return result.proposals||(result.proposal?[result.proposal]:[]);}
  function receiptFor(result,p){return result.executions?.find(r=>r.proposal_id===p.id)||(result.execution?.proposal_id===p.id?result.execution:null);}
  function applyReceipt(thread,receipt){
   for(const message of thread.messages){if(!message.result)continue;const result=message.result,ps=proposalList(result);const p=ps.find(p=>p.id===receipt.proposal_id);if(!p)continue;p.status=receipt.status;delete p.operationError;
    if(result.action_trace?.version==='goal-actions-v1'){
     const executions=[...(result.executions||[]).filter(r=>r.proposal_id!==receipt.proposal_id),receipt];
     for(const step of result.action_trace.steps)if(step.proposal_id===p.id)step.status=receipt.status==='succeeded'?'committed':'cancelled';
     const waiting=ps.some(p=>p.status==='pending')||result.action_trace.steps.some(s=>['needs_input','failed'].includes(s.status));
     for(const value of [result.map_context,thread.mapContext])for(const part of value?.parts||[])if(part.id===result.task_id)part.status=waiting?'waiting':'closed';
     for(const part of result.dialogue_trace?.parts||[])if(part.id===result.task_id)part.status=waiting?'waiting':'closed';
     message.result={...result,executions,stored:executions.some(r=>r.status==='succeeded'&&r.operation==='create')};
    }else{message.result={...result,execution:receipt,answer:receipt.message,stored:receipt.operation==='create'&&receipt.status==='succeeded',action:receipt.status==='cancelled'?'cancelled':'committed'};}
   }
  }
  async function executeProposal(thread,message,p,decision){if(operationBusy.size||thread.deletedAt||message.archived)return;operationBusy.add(p.id);previewRenderMessages();
   try{await window.PlantLibraryPersistence.recordOperation(async()=>{
    const input={thread_id:thread.id,proposal_id:p.id,version:p.version,operation_id:p.operation_id,decision};let receipt;
    try{receipt=await operationRequest('operation',input);}catch(error){if(error.status)throw error;const status=await operationRequest('operation-status',input);if(!status.receipt)throw Error('실행 결과를 아직 확인하지 못했어요. 같은 버튼으로 결과를 다시 확인할 수 있어요.');receipt=status.receipt;}
    applyReceipt(thread,receipt);
   });}catch(error){p.operationError=error.message;}finally{operationBusy.delete(p.id);previewRemember();if(previewActiveId===thread.id)previewRenderMessages();}
  }
  function proposalCard(result,thread,message,p){const card=node('section',null,'chat-action-proposal');card.append(node('strong',p.status==='succeeded'?'반영된 기록 · 개인 자료함':p.status==='cancelled'?'취소한 초안':({create:'기록 초안 · 개인 자료함',update:'기록 수정',delete:'기록 삭제',restore:'기록 복원'})[p.operation]));
   if(p.before){const details=node('details');details.append(node('summary','대상 · '+p.before.title+' · v'+p.expected_revision),node('pre',p.before.body));card.append(details);}
   if(p.after)card.append(node('p',p.after.title),node('pre',p.after.body));
   const receipt=receiptFor(result,p);
   if(receipt){card.append(node('p',receipt.message,'chat-action-status'));if(receipt.status==='succeeded'&&p.operation!=='delete'){const link=node('button','기록 열기');link.type='button';link.addEventListener('click',()=>{const index=records.findIndex(r=>r.sampleId===receipt.record_id);if(index>=0)openRecord(index);else previewToast('서재 보관소에서 개인 자료함을 선택해 주세요.');});card.append(link);}}
   else if(!message.archived){const actions=node('div',null,'transfer-actions');for(const [label,decision]of [[({create:'기록하기',update:'수정 반영',delete:'삭제 확인',restore:'복원 확인'})[p.operation],'confirm'],['취소','cancel']]){const b=node('button',operationBusy.has(p.id)?'처리 확인 중…':label);b.type='button';b.disabled=operationBusy.size>0||thread.deletedAt||pending(thread)||p.status!=='pending';if(p.operation==='delete'&&decision==='confirm'){b.style.background='#a43d35';b.style.color='white';}b.addEventListener('click',()=>{if(p.operation==='create'&&decision==='confirm'){editRecordDraft(state.recordDraft(thread,message,{...result,proposals:[p],proposal:undefined},seoulDate()));return;}executeProposal(thread,message,p,decision);});actions.append(b);}card.append(actions);}
   if(p.operationError)card.append(node('p',p.operationError,'ai-error-message'));return card;
  }
  function appendActionRetry(parent,result,thread,message){
    const trace=result.action_trace;if(!trace?.reply_error&&!trace?.steps?.some(s=>s.status==='failed'))return;
    const retry=node('button','실패한 단계 다시 준비','ai-retry');retry.type='button';retry.disabled=message.archived||thread.deletedAt||pending(thread);retry.addEventListener('click',()=>run(thread,message));parent.append(retry);
  }
  const currentScope=()=>state.scope(previewThread(),previewSnapshot().sampleArchive);
  const pending=thread=>thread?.messages.some(m=>m.kind==='assistant'&&m.status==='pending'&&!m.archived);
  const connectionBadge=document.querySelector('.preview-strip');
  function connectionStatus(status,label,detail){connectionBadge.dataset.state=status;connectionBadge.querySelector('strong').textContent=label;connectionBadge.title=detail;connectionBadge.setAttribute('aria-label',label+' · '+detail+' · 연결 상태와 모델 관리 열기');}
  async function bootstrap(force=false){
    if(force)bootstrapPromise=null;
    if(!bootstrapPromise){
      connectionStatus('checking','AI 확인 중','로컬 AI 연결을 확인하고 있어요.');
      bootstrapPromise=fetch('/api/chat/bootstrap',{cache:'no-store'}).then(async response=>{
        if(!response.ok)throw Error('연결 정보를 불러오지 못했습니다.');const data=await response.json();token=data.token;ready=data.ready;
        connectionStatus(ready?'connected':'offline',ready?'로컬 AI 연결':'AI 연결 확인',ready?(data.model||'로컬 모델')+' · 선택한 자료함의 원문에서 검색해 답변합니다.':data.note||'로컬 AI에 연결하지 못했습니다.');return data;
      }).catch(error=>{bootstrapPromise=null;ready=false;connectionStatus('error','AI 연결 실패',error.message);throw error;});
    }
    return bootstrapPromise;
  }
  let connectionDialog=null,connectionSnapshot=null,connectionError='',connectionChecking=false,connectionChecked=null;
  connectionBadge.setAttribute('aria-haspopup','dialog');connectionBadge.setAttribute('aria-controls','aiConnectionDialog');
  async function modelApi(route,body,accessToken){
    const response=await fetch('/api/baseline/'+route,{cache:'no-store',signal:AbortSignal.timeout(15000),...(body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Memory-Lab-Token':accessToken},body:JSON.stringify(body)})});
    const data=await response.json();if(!response.ok)throw Error(data.error||'모델 연결 정보를 확인하지 못했습니다.');return data;
  }
  const chatWorking=()=>previewThreads.some(t=>!t.deletedAt&&pending(t));
  function modelWorking(snapshot){return !!snapshot?.busy||snapshot?.setup?.status==='RUNNING'||snapshot?.runtime?.terminating===true;}
  function renderConnectionPanel(){
    if(!connectionDialog)return;
    const generation=connectionSnapshot?.runtime?.states?.generation,working=modelWorking(connectionSnapshot),model=connectionSnapshot?.runtime?.models?.find(m=>m.id===generation?.model_id);
    const stopped=['stopped','idle','not_started'].includes(generation?.status);
    const label=connectionChecking?'확인 중':modelActionBusy?'모델 연결 처리 중':working?'다른 작업 처리 중':ready?'연결됨':stopped?'모델 꺼짐':generation?.status==='starting'?'모델 준비 중':connectionError?'연결 확인 실패':'연결되지 않음';
    el('aiConnectionState').textContent=label;el('aiConnectionState').dataset.connected=String(ready&&!working&&!modelActionBusy&&!connectionChecking);
    el('aiConnectionModel').textContent=model?.name||'Qwen3.5 4B';
    el('aiConnectionChecked').textContent=connectionChecked?connectionChecked.toLocaleTimeString('ko-KR'):'아직 확인하지 않았어요';
    el('aiConnectionNote').textContent=connectionError||(chatWorking()?'대화 생성 중입니다. 응답을 마친 뒤 모델을 제어할 수 있어요.':working?'다른 모델 작업을 마친 뒤 다시 시도해 주세요.':ready?'이 컴퓨터의 로컬 모델에 연결되어 있어요.':stopped?'모델이 꺼져 있어요. 다시 연결을 누르면 모델을 켭니다.':'다시 연결을 눌러 로컬 모델을 확인해 주세요.');
    const disabled=modelActionBusy||connectionChecking||working||chatWorking();el('aiReconnect').disabled=disabled;el('aiModelStop').disabled=disabled||!generation||!['ready','starting'].includes(generation.status);el('aiConnectionRefresh').disabled=modelActionBusy||connectionChecking;
    el('aiReconnect').textContent=modelActionBusy&&connectionDialog.dataset.action==='reconnect'?'연결 중…':'다시 연결';el('aiModelStop').textContent=modelActionBusy&&connectionDialog.dataset.action==='stop'?'끄는 중…':'모델 끄기';
    if(stopped&&!modelActionBusy&&!connectionChecking)connectionStatus('offline','AI 꺼짐','로컬 모델이 꺼져 있습니다. 연결 상태 창에서 다시 켤 수 있어요.');
  }
  async function refreshConnectionPanel(){
    connectionChecking=true;connectionError='';renderConnectionPanel();
    const [runtimeResult,chatResult]=await Promise.allSettled([modelApi('status'),bootstrap(true)]);
    connectionSnapshot=runtimeResult.status==='fulfilled'?runtimeResult.value:null;connectionChecked=new Date();
    if(runtimeResult.status==='rejected')connectionError=runtimeResult.reason.message;
    else if(chatResult.status==='rejected')connectionError=chatResult.reason.message;
    else if(!ready&&connectionSnapshot.setup?.status==='ERROR')connectionError=connectionSnapshot.setup.error||'모델을 준비하지 못했습니다.';
    connectionChecking=false;renderConnectionPanel();return connectionSnapshot;
  }
  async function controlModel(action){
    if(modelActionBusy||connectionChecking||chatWorking())return;
    modelActionBusy=true;connectionDialog.dataset.action=action;connectionError='';renderConnectionPanel();
    try{
      const access=await modelApi('bootstrap');if(modelWorking(access)||chatWorking())throw Error('진행 중인 작업을 마친 뒤 다시 시도해 주세요.');
      if(action==='stop'){
        await modelApi('runtime/stop',{},access.token);await refreshConnectionPanel();
        if(connectionSnapshot?.runtime?.states?.generation?.status!=='stopped')throw Error('모델 종료 상태를 확인하지 못했습니다. 상태를 새로고침해 주세요.');
      }else{
        await refreshConnectionPanel();
        if(!ready){
          if(modelWorking(connectionSnapshot))throw Error('다른 모델 작업을 마친 뒤 다시 시도해 주세요.');
          await modelApi('runtime/start',{model:'qwen35-4b-q4',route:'R0-Full'},access.token);
          let connected=false;
          for(let attempt=0;attempt<120;attempt++){
            await new Promise(resolve=>setTimeout(resolve,1000));const snapshot=await modelApi('status');connectionSnapshot=snapshot;connectionChecked=new Date();renderConnectionPanel();
            if(snapshot.setup?.status==='ERROR'||snapshot.setup?.status==='CANCELLED')throw Error(snapshot.setup.error||'모델 연결이 중단됐습니다.');
            if(snapshot.runtime?.states?.generation?.status==='ready'&&!modelWorking(snapshot)){await refreshConnectionPanel();if(ready){connected=true;break;}}
          }
          if(!connected)throw Error('모델 준비 시간이 길어지고 있어요. 잠시 후 상태를 새로고침해 주세요.');
        }
      }
    }catch(error){connectionError=error.message||'모델 연결 작업에 실패했습니다.';}
    finally{modelActionBusy=false;renderConnectionPanel();}
  }
  function openConnectionPanel(){
    if(!connectionDialog){
      connectionDialog=node('dialog',null,'ai-connection-dialog');connectionDialog.id='aiConnectionDialog';connectionDialog.setAttribute('aria-labelledby','aiConnectionTitle');
      connectionDialog.innerHTML='<div class="ai-connection-heading"><h2 id="aiConnectionTitle">로컬 AI 연결</h2><button type="button" id="aiConnectionClose" aria-label="연결 상태 닫기">×</button></div><p class="ai-connection-state" id="aiConnectionState" role="status"></p><dl class="ai-connection-summary"><div><dt>모델</dt><dd id="aiConnectionModel"></dd></div><div><dt>실행 위치</dt><dd>이 컴퓨터 · 로컬 실행</dd></div><div><dt>마지막 확인</dt><dd id="aiConnectionChecked"></dd></div></dl><p id="aiConnectionNote" class="ai-connection-note" aria-live="polite"></p><div class="ai-connection-actions"><button type="button" id="aiReconnect">다시 연결</button><button type="button" id="aiModelStop">모델 끄기</button></div><div class="ai-connection-footer"><span>모델을 꺼도 대화와 기록은 유지됩니다.</span><button type="button" id="aiConnectionRefresh">상태 새로고침</button></div>';
      document.body.append(connectionDialog);el('aiConnectionClose').onclick=()=>connectionDialog.close();el('aiReconnect').onclick=()=>controlModel('reconnect');el('aiModelStop').onclick=()=>controlModel('stop');el('aiConnectionRefresh').onclick=()=>refreshConnectionPanel();
      connectionDialog.addEventListener('close',()=>connectionBadge.focus({preventScroll:true}));connectionDialog.addEventListener('click',event=>{if(event.target!==connectionDialog)return;const r=connectionDialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)connectionDialog.close();});
      new MutationObserver(()=>{if(connectionDialog.open)renderConnectionPanel();}).observe(el('conversation'),{childList:true,subtree:true});
    }
    if(!connectionDialog.open)connectionDialog.showModal();el('aiConnectionClose').focus({preventScroll:true});if(!modelActionBusy)refreshConnectionPanel();
  }
  connectionBadge.addEventListener('click',openConnectionPanel);

  function sourceLink(citation,label='기록 열기',className='ai-source-open',reference={}){
    const button=node('button',label,className);button.type='button';button.addEventListener('click',()=>{
      const source=window.PlantArchiveSamples.records.find(r=>r.id===citation.source_id&&r.revision===citation.revision&&r.body.slice(citation.start,citation.end)===citation.quote);if(!source){previewToast('현재 자료함에 같은 버전의 인용 원문이 없습니다. 인용 문구는 대화에 보존되어 있어요.');return;}
      window.PlantArchiveView.showRecord(source.id,{threadId:reference.threadId||previewActiveId,requestId:reference.requestId,citations:reference.citations||[citation],scrollTop:el('chatScroll')?.scrollTop||0});
    });return button;
  }
  function evidenceDetails(result,message){
    // One entry per original; keep every distinct quoted passage from that original.
    const grouped=new Map();
    for(const citation of result.citations){
      const key=citation.source_id+'@'+citation.revision;
      if(!grouped.has(key))grouped.set(key,{citation,quotes:new Set()});
      grouped.get(key).quotes.add(citation.quote);
    }
    const details=node('details',null,'ai-sources');details.open=message.evidenceExpanded===true;
    details.append(node('summary','참고한 기록 '+grouped.size+'개'));
    const list=node('div',null,'ai-sources-list');
    for(const {citation,quotes}of grouped.values()){
      const source=window.PlantArchiveSamples.records.find(r=>r.id===citation.source_id);
      const entry=sourceLink(citation,null,'ai-evidence-entry',{citations:result.citations,threadId:result.thread_id,requestId:result.request_id});
      entry.setAttribute('aria-label',citation.title+' 원문 열기');
      const heading=node('span',null,'ai-evidence-heading');
      const created=source?.created_at||source?.metadata?.created_at;
      if(created&&!Number.isNaN(Date.parse(created))){
        const date=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(created));
        const time=node('time',date,'ai-evidence-date');time.dateTime=created;heading.append(time);
      }
      heading.append(node('span',citation.title,'ai-evidence-title'));
      entry.append(heading,node('span',[...quotes].join('\n'),'ai-evidence-quote'));list.append(entry);
    }
    details.append(list,node('small',(result.scope.mode==='personal'?'개인 자료함 원문 ':result.scope.mode==='all-originals'?'가상 예시 원문 ':'이전 응답의 원문 ')+result.scope.accessible_count+'개에서 확인한 근거','ai-response-meta'));
    details.addEventListener('toggle',()=>{message.evidenceExpanded=details.open;previewRemember();});
    return details;
  }
  function copyAnswer(text){
    const button=node('button',null,'ai-copy-answer');button.type='button';
    button.setAttribute('aria-label','AI 답변 복사');button.title='답변을 마크다운 형식으로 복사';
    const icon=document.createElementNS('http://www.w3.org/2000/svg','svg');
    icon.setAttribute('viewBox','0 0 24 24');icon.setAttribute('width','14');icon.setAttribute('height','14');icon.setAttribute('fill','none');icon.setAttribute('stroke','currentColor');icon.setAttribute('stroke-width','1.6');icon.setAttribute('aria-hidden','true');
    const outline=document.createElementNS('http://www.w3.org/2000/svg','path');outline.setAttribute('d','M8 8h12v12H8z M16 8V4H4v12h4');icon.append(outline);
    const label=node('span','복사');button.append(icon,label);let resetTimer;
    button.addEventListener('click',async()=>{
      if(button.disabled)return;clearTimeout(resetTimer);button.disabled=true;
      try{
        await navigator.clipboard.writeText(text);
        label.textContent='복사됨';button.classList.add('is-copied');previewToast('답변을 복사했어요.');
      }catch{
        label.textContent='다시 복사';button.classList.remove('is-copied');previewToast('답변을 복사하지 못했어요. 다시 눌러 주세요.');
      }finally{button.disabled=false;}
      resetTimer=setTimeout(()=>{label.textContent='복사';button.classList.remove('is-copied');},2200);
    });
    return button;
  }

  function recordEditorValues(){return {title:el('recordTitle').value,date:el('recordDate').value,body:el('recordBody').value};}
  function editRecordDraft(draft,append=true){
    if(!draft.body.trim())return;
    const next=state.mergeRecordDraft(recordEditorValues(),draft,append);
    el('recordTitle').value=next.title;el('recordDate').value=next.date;el('recordBody').value=next.body;
    el('recordPreview')?.remove();previewRemember();go('emotion');el('recordBody').focus({preventScroll:true});
    previewToast('대화의 초안을 옮겼어요. 내용을 수정한 뒤 기록해 주세요.');
  }
  function recordDraftPanel(result,thread,message){
    const draft=state.recordDraft(thread,message,result,seoulDate()),card=node('section',null,'chat-record-draft');
    card.setAttribute('aria-label','대화 기록 초안');card.tabIndex=-1;
    card.append(node('strong','기록 초안 · 저장 전'),node('h3',draft.title),node('p',draft.date,'chat-record-draft-date'),node('pre',draft.body));
    card.append(node('p','선택한 대화에서 준비한 초안입니다. 감정 갈무리에서 내용을 수정한 뒤 저장하세요.','chat-record-draft-note'));
    let appendInput=null;
    const current=recordEditorValues();
    if(current.title.trim()||current.body.trim()){
      const label=node('label','작성 중인 기록에 이어 쓰기','chat-record-draft-merge');appendInput=node('input');appendInput.type='checkbox';appendInput.checked=true;label.prepend(appendInput);card.append(label);
      card.append(node('p','선택을 해제하면 이 초안으로 새로 작성합니다.','chat-record-draft-note'));
    }
    const actions=node('div',null,'transfer-actions'),proceed=node('button','기록하기'),cancel=node('button','취소');proceed.type=cancel.type='button';
    proceed.addEventListener('click',()=>editRecordDraft(draft,appendInput?appendInput.checked:true));
    cancel.addEventListener('click',()=>{const opener=card.previousElementSibling?.querySelector('.ai-record-draft');card.remove();opener?.setAttribute('aria-expanded','false');opener?.focus({preventScroll:true});});
    actions.append(proceed,cancel);card.append(actions);return card;
  }
  function recordDraftButton(result,thread,message,actions){
    const button=node('button','기록하기','ai-record-draft');button.type='button';button.setAttribute('aria-expanded','false');button.title='이 대화로 기록 초안 만들기';button.disabled=!!thread.deletedAt;
    button.addEventListener('click',()=>{
      let card=actions.nextElementSibling;
      if(card?.classList.contains('chat-record-draft')){card.remove();button.setAttribute('aria-expanded','false');return;}
      card=recordDraftPanel(result,thread,message);actions.after(card);button.setAttribute('aria-expanded','true');card.focus({preventScroll:true});card.scrollIntoView({behavior:'smooth',block:'nearest'});
    });return button;
  }

  function submitContextChoice(thread,text,options={}){
    if(thread.deletedAt||pending(thread))return;
    const submission=state.submission(thread,currentScope(),{text,inspect:window.PlantTestMode?.enabled===true,...options}),message={kind:'assistant',status:'pending',submission,createdAt:new Date().toISOString()};
    thread.messages.push({kind:'user',text,requestId:submission.request_id,createdAt:new Date().toISOString()},message);run(thread,message);
  }
  function renderResult(body,header,result,thread,message){
    if(result.model!=='Plant Thought'&&result.context_info?.topic&&['continue','return'].includes(result.context_info.relation))body.append(node('p','앞서 이야기한 '+result.context_info.topic+' 맥락을 이어서 확인했어요.','chat-context-note'));
    if(result.parts){
      header.append(node('span','작업별 결과','ai-response-state'));
      for(const [i,part]of result.parts.entries()){
        const section=node('section',null,'chat-result-part'),partHeader=node('div',null,'ai-response-header');partHeader.append(node('strong',(i+1)+'. '+part.text));section.append(partHeader);
        if(part.status==='success')renderResult(section,partHeader,part.result,thread,message);
        else{section.append(node('p',part.error,'ai-error-message'));const retry=node('button','실패한 작업 재시도','ai-retry');retry.type='button';retry.disabled=pending(thread);retry.addEventListener('click',()=>run(thread,message));section.append(retry);}
        body.append(section);
      }return;
    }
    const answer=node('div',null,'ai-answer');const displayAction=result.execution?(result.execution.status==='cancelled'?'cancelled':'committed'):result.action;if(displayAction!=='answer')header.append(node('span',actionName[displayAction]||'답변','ai-response-state'));
    if(window.PlantMarkdown)answer.innerHTML=window.PlantMarkdown.render(result.answer);else answer.textContent=result.answer;
    const actions=node('div',null,'ai-answer-actions');if(result.citations.length)actions.append(sourceLink(result.citations[0],'기록 열기','ai-source-open',{citations:result.citations,threadId:result.thread_id,requestId:result.request_id}));actions.append(recordDraftButton(result,thread,message,actions),copyAnswer(result.answer));body.append(answer,actions);
    if(result.citations.length)body.append(evidenceDetails(result,message));
    const searchDetails=window.PlantSearchResult?.(result);if(searchDetails)body.append(searchDetails);
    if(result.recording?.status==='draft'&&result.action!=='draft'){
      const details=node('details',null,'chat-recording-preview');details.append(node('summary','기록 초안 보완 · '+result.recording.date+' · 저장 전'));
      details.append(node('p','사용자가 표현한 경험과 느낌'));for(const text of result.recording.statements)details.append(node('blockquote',text));body.append(details);
    }
    for(const choice of result.context_info?.choices||[]){const button=node('button',choice.label,'chat-context-choice');button.type='button';button.disabled=pending(thread);button.addEventListener('click',()=>submitContextChoice(thread,message.submission.text,choice.pending?{pendingTarget:choice.id}:{selection:choice.id}));body.append(button);}
  }
  previewRenderMessages=function(){
    const log=el('conversation'),thread=previewThread();log.replaceChildren();
    document.querySelector('.chat-ongoing-instructions')?.remove();
    const mode=currentScope().collectionId||'samples',activeContext=['v2','v3'].includes(window.PlantChatVersion?.current())?thread?.mapContext?.flow:thread?.context,directives=['v2','v3'].includes(window.PlantChatVersion?.current())&&thread?.messages.findLast(m=>m.status==='success'&&m.result)?.result.action_trace?.version==='goal-actions-v1'?[]:activeContext?.directives?.filter(d=>d.scope===mode)||[];
    if(directives.length){const strip=node('div',null,'chat-ongoing-instructions');strip.setAttribute('aria-label','이 대화의 지속 지시');
      for(const d of directives){const label=d.type==='record'?(d.value==='enabled'?'기록 초안 이어가기 켜짐':'기록 초안 이어가기 꺼짐'):(d.value==='brief'?'짧은 답변':'기본 답변 길이');strip.append(node('span',label));}
      strip.append(node('small','현재 대화에 적용'));document.querySelector('#chat .chat-input-area').prepend(strip);
    }
    if(!thread?.messages.length){const welcome=node('div',null,'preview-chat-welcome');welcome.append(node('div','♧','iconbox'),node('span','로컬 AI · 원문 근거 대화','tag'),node('h2','이야기가 시작되는 자리'),node('p',window.PlantArchiveSamples.synthetic?'플로팅에서 예시 질문을 선택하거나 직접 물어보세요. 가상 원문 199개에서 검색해 답합니다.':'떠오르는 생각이나 기억을 들려주세요. 개인 자료함에서 검색에 포함한 기록을 찾아 답합니다.'));log.append(welcome);}
    for(const message of thread?.messages||[]){
      if(message.kind==='user'){log.append(node('div',message.text,'bubble user'));continue;}
      if(message.kind!=='assistant'){if(message.kind==='notice')log.append(node('div',message.text,'preview-message notice'));continue;}
      const card=node('article',null,'ai-response');card.setAttribute('aria-label','AI 응답');card.dataset.requestId=message.submission.request_id;
      const avatar=node('span','♧','ai-response-avatar');avatar.setAttribute('aria-hidden','true');
      const body=node('div',null,'ai-response-body'),header=node('div',null,'ai-response-header');
      const brand=node('span','Plant Thought','ai-response-brand');header.append(brand,node('span',['v2','v3'].includes(message.submission.analysis_version)?(message.submission.analysis_version==='v3'?'V3 · 카테고리 대화':'V2 · 문맥 목표와 행동'):'V1','chat-version-label'));const searchInfo=window.PlantSearchModes.describe(message.submission,message.result,message.status),searchLabel=node('span',searchInfo.label,'chat-search-label');searchLabel.title=searchInfo.title;searchLabel.setAttribute('aria-label','기록 검색: '+searchInfo.label);header.append(searchLabel);body.append(header);card.append(avatar,body);
      if(message.archived&&message.status!=='success'){body.append(node('p','가져온 대화의 중단된 요청입니다. 자동으로 재실행하지 않습니다.'),node('p',message.error||''));}
      else if(message.status==='pending'){card.setAttribute('role','status');const pendingLabel=node('p','대화 문맥에서 목표와 필요한 행동을 준비하고 있어요.','ai-pending');pendingLabel.dataset.requestId=message.submission.request_id;body.append(pendingLabel);if(message.result?.action_trace?.version==='goal-actions-v1'){for(const p of state.recordActionProposals(message.result,message,thread))body.append(proposalCard(message.result,thread,message,p));}}
      else if(['error','cancelled'].includes(message.status)){
        const cancelled=message.status==='cancelled';
        card.classList.add(cancelled?'ai-cancelled':'ai-error');card.setAttribute('role',cancelled?'status':'alert');
        body.append(node('strong',cancelled?'응답 수신을 중단했어요.':(stageName[message.stage]||'AI 처리')+'에 실패했어요.','ai-error-label'),node('p',message.error,'ai-error-message'));
        const retry=node('button','재시도','ai-retry');retry.type='button';retry.addEventListener('click',()=>run(thread,message));retry.disabled=pending(thread);body.append(retry);if(message.result?.action_trace?.version==='goal-actions-v1'){body.append(node('p','이전에 준비한 작업은 유지됩니다.'));for(const p of state.recordActionProposals(message.result,message,thread))body.append(proposalCard(message.result,thread,message,p));}
      }else if(message.result){
        renderResult(body,header,message.result,thread,message);if(message.result.action_trace?.version==='goal-actions-v1')appendActionRetry(body,message.result,thread,message);for(const p of state.recordActionProposals(message.result,message,thread))body.append(proposalCard(message.result,thread,message,p));
      }
      log.append(card);
    }
    const waiting=activeContext?.pending.filter(p=>p.status==='awaiting_confirmation'&&p.scope===(currentScope().collectionId||'samples'))||[];
    if(waiting.length){const details=node('details',null,'chat-pending-tasks');details.append(node('summary','확인 대기 초안 '+waiting.length+'개'));
      for(const task of waiting){const row=node('div',null,'chat-pending-task');row.append(node('p',task.proposal));const cancel=node('button','이 초안 취소');cancel.type='button';cancel.disabled=pending(thread);cancel.addEventListener('click',()=>submitContextChoice(thread,'그 작업 취소해줘',{pendingTarget:task.id}));row.append(cancel);details.append(row);}log.append(details);}
    el('chatInput').value=thread?.draft||'';updateChatInput();previewRenderHistory();
  };
  updateDemoControls=function(){
    const button=el('chatSend'),busy=!!pending(previewThread());button.disabled=!busy&&!el('chatInput').value.trim();button.dataset.state=busy?'stop':'send';
    button.setAttribute('aria-label',busy?'응답 생성 중지':'질문 보내기');button.setAttribute('aria-busy',String(busy));button.title=busy?'응답 생성 중지':'질문 보내기';
    button.innerHTML=busy?'<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="7" y="7" width="10" height="10" rx="1.5"/></svg>':'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 18V6m-6 6 6-6 6 6"/></svg>';
  };
  function stopGeneration(){
    const thread=previewThread();if(!thread)return;
    for(const message of thread.messages)if(message.kind==='assistant'&&message.status==='pending'&&!message.archived){
      const id=message.submission.request_id,request=controllers.get(id);
      if(token)fetch('/api/chat/cancel',{method:'POST',headers:{'Content-Type':'application/json','X-Plant-Token':token},body:JSON.stringify({request_id:id,thread_id:thread.id})}).catch(()=>{});
      message.status='cancelled';message.stage='cancelled';message.error='사용자가 응답 생성을 중지했습니다. 같은 질문을 재시도할 수 있어요.';
      request?.controller.abort();controllers.delete(id);
    }
    previewRemember();previewRenderMessages();el('chatInput').focus();
  }
  el('chatSend').onclick=()=>{if(pending(previewThread()))stopGeneration();else sendChat();};
  document.addEventListener('input',event=>{if(event.target!==el('chatInput'))return;const thread=previewThread();if(thread){thread.draft=event.target.value;thread.inputVersion=(thread.inputVersion||0)+1;}previewRemember();});
  document.addEventListener('plant:question-selected',event=>{const thread=previewThread();if(thread){thread.sampleScope={profile:event.detail.profile,questionId:event.detail.questionId};previewRemember();}});
  document.addEventListener('plant:thread-deleted',event=>{
    for(const [id,request]of controllers)if(request.threadId===event.detail.id)request.controller.abort();
    const thread=previewThreads.find(t=>t.id===event.detail.id);
    for(const message of thread?.messages||[])if(message.kind==='assistant'&&message.status==='pending'&&!message.archived){message.status='cancelled';message.error='대화를 삭제하여 응답 수신을 중단했습니다. 복원 후 재시도할 수 있어요.';}
  });
  function watchSearch(message,controller){
    if(!message.submission.search_mode||message.submission.search_mode==='legacy')return ()=>{};
    let stopped=false,polling=false;
    const poll=async()=>{if(stopped||polling||controller.signal.aborted)return;polling=true;try{
      const response=await fetch('/api/baseline/chat-search-status?id='+encodeURIComponent(message.submission.request_id),{signal:controller.signal});
      if(!response.ok)return;const {job}=await response.json();if(!job||stopped)return;
      for(const label of document.querySelectorAll('.ai-pending[data-request-id]'))if(label.dataset.requestId===message.submission.request_id)label.textContent=job.label+' · '+job.progress;
    }catch{}finally{polling=false;}};
    const timer=setInterval(poll,1500);return ()=>{stopped=true;clearInterval(timer);};
  }
  async function run(thread,message){
    if(modelActionBusy){if(message.status==='pending'){message.status='error';message.stage='connection';message.error='모델 연결 작업을 마친 뒤 재시도해 주세요.';previewRemember();if(previewActiveId===thread.id)previewRenderMessages();}else previewToast('모델 연결 작업을 마친 뒤 재시도해 주세요.');return;}
    if(message.archived||thread.deletedAt||controllers.has(message.submission.request_id))return;
    if(window.PlantTestMode&&!window.PlantTestMode.enabled&&message.submission.collection_id!=='personal'){previewToast('이 요청은 가상 예시를 사용합니다. 설정에서 테스트 기능을 켠 뒤 재시도해 주세요.');return;}
    if(pending(thread)&&message.status!=='pending')return;
    thread.contextRequest=message.submission.request_id;
    const controller=new AbortController();controllers.set(message.submission.request_id,{threadId:thread.id,controller});
    message.status='pending';delete message.error;if(!message.result?.parts&&message.result?.action_trace?.version!=='goal-actions-v1')delete message.result;delete message.inspection;
    if(previewActiveId===thread.id)previewRenderMessages();previewRemember();scrollChatToBottom();
    const stopWatching=watchSearch(message,controller);
    try{
      await bootstrap();
      if(['v2','v3'].includes(message.submission.analysis_version))await window.PlantLibraryPersistence?.flush();
      if(thread.deletedAt||controller.signal.aborted)return;
      const response=await fetch('/api/chat/respond',{method:'POST',headers:{'Content-Type':'application/json','X-Plant-Token':token},body:JSON.stringify(message.submission),signal:message.submission.search_mode&&message.submission.search_mode!=='legacy'?controller.signal:AbortSignal.any([AbortSignal.timeout(570000),controller.signal])});
      let result;try{result=await response.json();}catch{throw Object.assign(Error('AI 응답을 읽지 못했습니다.'),{stage:'validation'});}
      if(thread.deletedAt||controller.signal.aborted)return;
      if(!response.ok){if(response.status===403){token=null;bootstrapPromise=null;}throw Object.assign(Error(result.error||'AI 요청에 실패했습니다.'),{stage:result.stage||'connection',inspection:result.inspection});}
      if(result.request_id!==message.submission.request_id||result.thread_id!==thread.id||typeof result.answer!=='string'||!Array.isArray(result.citations))throw Object.assign(Error('응답이 제출한 작업과 일치하지 않습니다.'),{stage:'validation'});
      message.result=result;for(const receipt of result.executions||[])applyReceipt(thread,receipt);message.status='success';state.applyContext(thread,message.submission,result.context,result.map_context);thread.updatedAt=new Date().toISOString();ready=true;
    }catch(error){if(thread.deletedAt||controller.signal.aborted)return;message.status='error';message.stage=error.stage||'connection';message.error=error.name==='TimeoutError'?'응답을 기다리는 시간이 초과됐습니다. 같은 질문을 재시도할 수 있어요.':error.message;if(error.inspection)message.inspection=error.inspection;}
    finally{stopWatching();if(controllers.get(message.submission.request_id)?.controller===controller)controllers.delete(message.submission.request_id);}
    if(previewActiveId===thread.id){previewRenderMessages();if(document.querySelector('.page.active')?.id==='chat')scrollChatToBottom();}
    previewRemember();
  }
  sendChat=function(){
    if(modelActionBusy){previewToast('모델 연결 작업을 마친 뒤 질문을 보내 주세요.');return;}
    const input=el('chatInput');if(!input.value.trim()||pending(previewThread()))return;
    if(!previewThread())newChat();const thread=previewThread();thread.draft=input.value;
    const scope=currentScope();if(!['v2','v3'].includes(window.PlantChatVersion?.current())&&scope?.collectionId!=='personal'&&!scope?.questionId){previewToast('플로팅에서 질문 사례를 먼저 선택해 주세요.');return;}
    const submission=state.submission(thread,scope,{inspect:window.PlantTestMode?.enabled===true}),message={kind:'assistant',status:'pending',submission,createdAt:new Date().toISOString()};
    thread.messages.push({kind:'user',text:submission.text,requestId:submission.request_id,createdAt:new Date().toISOString()},message);if(!thread.titleEdited)thread.title=submission.text.trim().slice(0,28);
    // Consume only the accepted submission; response completion never edits the next draft.
    thread.draft='';thread.inputVersion=(thread.inputVersion||0)+1;input.value='';updateChatInput();
    run(thread,message);input.focus();
  };
  for(const thread of previewThreads)for(const message of thread.messages){
    if(message.kind==='assistant'&&message.status==='error'&&message.error==='대화를 삭제하여 응답 수신을 중단했습니다. 복원 후 재시도할 수 있어요.')message.status='cancelled';
    if(message.kind==='assistant'&&message.status==='pending'&&!message.archived){message.status='error';message.stage='connection';message.error='화면이 새로 열려 이전 처리 결과를 확인해야 합니다. 같은 제출본으로 재시도해 주세요.';}
  }
  el('chatSend').setAttribute('aria-label','질문 보내기');
  const note=document.querySelector('#chat .chat-disclaimer');if(note)note.textContent='현재 자료함에서 원문을 찾아 답합니다. 대화 내용은 보관소 기록으로 자동 추가되지 않습니다.';
  previewRenderMessages();bootstrap().catch(()=>{});
})();
