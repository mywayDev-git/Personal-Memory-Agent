'use strict';
// Connected mode only; preview.cjs never loads this script.
(()=>{
  const el=id=>document.getElementById(id),state=window.PlantChatState;
  let token=null,bootstrapPromise=null,ready=false;
  const controllers=new Map();
  const stageName={context:'대화 맥락 확인',scope:'기록 범위 확인',retrieval:'원문 검색',connection:'AI 연결',model:'AI 응답 생성',validation:'답변 검증'};
  const actionName={cancelled:'취소 완료',multi_result:'작업별 결과',answer:'답변',partial_answer:'부분 확인',abstain:'확인 불가',clarify:'확인 질문',report_conflict:'기록 충돌',deny:'전제 확인',draft:'기록 초안 · 저장되지 않음',empathy:'감정 나누기',advice:'작은 제안'};
  const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;if(cls)n.className=cls;return n;};
  const currentScope=()=>state.scope(previewThread(),previewSnapshot().sampleArchive);
  const pending=thread=>thread?.messages.some(m=>m.kind==='assistant'&&m.status==='pending'&&!m.archived);
  function scopeLabel(){document.querySelector('.chat-topbar-label').textContent=(ready?'로컬 AI':'AI 연결 확인')+' · '+(window.PlantArchiveSamples.synthetic?'가상 예시 ':'개인 자료함 ')+window.PlantArchiveSamples.record_count+'개';}
  async function bootstrap(){
    if(!bootstrapPromise)bootstrapPromise=fetch('/api/chat/bootstrap',{cache:'no-store'}).then(async response=>{if(!response.ok)throw Error('연결 정보를 불러오지 못했습니다.');const data=await response.json();token=data.token;ready=data.ready;const strip=document.querySelector('.preview-strip');strip.querySelector('strong').textContent=ready?'로컬 AI 연결':'AI 연결 확인 필요';strip.querySelector('div>span:last-child').textContent=ready?'Qwen3.5 4B · 선택한 자료함의 원문에서 검색해 답변합니다.':data.note;scopeLabel();return data;}).catch(error=>{bootstrapPromise=null;ready=false;document.querySelector('.preview-strip strong').textContent='AI 연결 실패';document.querySelector('.preview-strip div>span:last-child').textContent=error.message;throw error;});
    return bootstrapPromise;
  }
  function sourceLink(citation,label='기록 열기',className='ai-source-open'){
    const button=node('button',label,className);button.type='button';button.addEventListener('click',()=>{
      const source=window.PlantArchiveSamples.records.find(r=>r.id===citation.source_id&&r.revision===citation.revision&&r.body.slice(citation.start,citation.end)===citation.quote);if(!source){previewToast('현재 자료함에 같은 버전의 인용 원문이 없습니다. 인용 문구는 대화에 보존되어 있어요.');return;}
      const index=records.findIndex(r=>r.sampleId===source.id);if(index>=0)openRecord(index);
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
    const details=node('details',null,'ai-sources');details.open=message.evidenceExpanded!==false;
    details.append(node('summary','참고한 기록 '+grouped.size+'개'));
    const list=node('div',null,'ai-sources-list');
    for(const {citation,quotes}of grouped.values()){
      const source=window.PlantArchiveSamples.records.find(r=>r.id===citation.source_id);
      const entry=sourceLink(citation,null,'ai-evidence-entry');
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
    const answer=node('div',null,'ai-answer');if(result.action!=='answer')header.append(node('span',actionName[result.action]||'답변','ai-response-state'));
    if(window.PlantMarkdown)answer.innerHTML=window.PlantMarkdown.render(result.answer);else answer.textContent=result.answer;
    const actions=node('div',null,'ai-answer-actions');if(result.citations.length)actions.append(sourceLink(result.citations[0]));actions.append(copyAnswer(result.answer));body.append(answer,actions);
    if(result.citations.length)body.append(evidenceDetails(result,message));
    if(result.recording?.status==='draft'&&result.action!=='draft'){
      const details=node('details',null,'chat-recording-preview');details.append(node('summary','기록 초안 보완 · '+result.recording.date+' · 저장 전'));
      details.append(node('p','사용자가 표현한 경험과 느낌'));for(const text of result.recording.statements)details.append(node('blockquote',text));body.append(details);
    }
    for(const choice of result.context_info?.choices||[]){const button=node('button',choice.label,'chat-context-choice');button.type='button';button.disabled=pending(thread);button.addEventListener('click',()=>submitContextChoice(thread,message.submission.text,choice.pending?{pendingTarget:choice.id}:{selection:choice.id}));body.append(button);}
  }
  previewRenderMessages=function(){
    const log=el('conversation'),thread=previewThread();log.replaceChildren();
    document.querySelector('.chat-ongoing-instructions')?.remove();
    const mode=currentScope().collectionId||'samples',directives=thread?.context?.directives?.filter(d=>d.scope===mode)||[];
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
      const brand=node('span','Plant Thought','ai-response-brand');header.append(brand);body.append(header);card.append(avatar,body);
      if(message.archived&&message.status!=='success'){body.append(node('p','가져온 대화의 중단된 요청입니다. 자동으로 재실행하지 않습니다.'),node('p',message.error||''));}
      else if(message.status==='pending'){card.setAttribute('role','status');body.append(node('p','요청과 대화 맥락을 확인하고 답변을 만드는 중이에요.','ai-pending'));}
      else if(['error','cancelled'].includes(message.status)){
        const cancelled=message.status==='cancelled';
        card.classList.add(cancelled?'ai-cancelled':'ai-error');card.setAttribute('role',cancelled?'status':'alert');
        body.append(node('strong',cancelled?'응답 수신을 중단했어요.':(stageName[message.stage]||'AI 처리')+'에 실패했어요.','ai-error-label'),node('p',message.error,'ai-error-message'));
        const retry=node('button','재시도','ai-retry');retry.type='button';retry.addEventListener('click',()=>run(thread,message));retry.disabled=pending(thread);body.append(retry);
      }else if(message.result){
        renderResult(body,header,message.result,thread,message);
      }
      log.append(card);
    }
    const waiting=thread?.context?.pending.filter(p=>p.status==='awaiting_confirmation'&&p.scope===(currentScope().collectionId||'samples'))||[];
    if(waiting.length){const details=node('details',null,'chat-pending-tasks');details.append(node('summary','확인 대기 초안 '+waiting.length+'개'));
      for(const task of waiting){const row=node('div',null,'chat-pending-task');row.append(node('p',task.proposal));const cancel=node('button','이 초안 취소');cancel.type='button';cancel.disabled=pending(thread);cancel.addEventListener('click',()=>submitContextChoice(thread,'그 작업 취소해줘',{pendingTarget:task.id}));row.append(cancel);details.append(row);}log.append(details);}
    el('chatInput').value=thread?.draft||'';updateChatInput();previewRenderHistory();scopeLabel();
  };
  updateDemoControls=function(){el('chatSend').disabled=!el('chatInput').value.trim()||pending(previewThread());el('chatSend').setAttribute('aria-busy',String(!!pending(previewThread())));};
  document.addEventListener('input',event=>{if(event.target!==el('chatInput'))return;const thread=previewThread();if(thread){thread.draft=event.target.value;thread.inputVersion=(thread.inputVersion||0)+1;}scopeLabel();previewRemember();});
  document.addEventListener('plant:question-selected',event=>{const thread=previewThread();if(thread){thread.sampleScope={profile:event.detail.profile,questionId:event.detail.questionId};scopeLabel();previewRemember();}});
  document.addEventListener('plant:thread-deleted',event=>{
    for(const [id,request]of controllers)if(request.threadId===event.detail.id)request.controller.abort();
    const thread=previewThreads.find(t=>t.id===event.detail.id);
    for(const message of thread?.messages||[])if(message.kind==='assistant'&&message.status==='pending'&&!message.archived){message.status='cancelled';message.error='대화를 삭제하여 응답 수신을 중단했습니다. 복원 후 재시도할 수 있어요.';}
  });
  async function run(thread,message){
    if(message.archived||thread.deletedAt||controllers.has(message.submission.request_id))return;
    if(window.PlantTestMode&&!window.PlantTestMode.enabled&&message.submission.collection_id!=='personal'){previewToast('이 요청은 가상 예시를 사용합니다. 설정에서 테스트 기능을 켠 뒤 재시도해 주세요.');return;}
    if(pending(thread)&&message.status!=='pending')return;
    thread.contextRequest=message.submission.request_id;
    const controller=new AbortController();controllers.set(message.submission.request_id,{threadId:thread.id,controller});
    message.status='pending';delete message.error;if(!message.result?.parts)delete message.result;delete message.inspection;
    if(previewActiveId===thread.id)previewRenderMessages();previewRemember();scrollChatToBottom();
    try{
      await bootstrap();
      if(thread.deletedAt||controller.signal.aborted)return;
      const response=await fetch('/api/chat/respond',{method:'POST',headers:{'Content-Type':'application/json','X-Plant-Token':token},body:JSON.stringify(message.submission),signal:AbortSignal.any([AbortSignal.timeout(570000),controller.signal])});
      let result;try{result=await response.json();}catch{throw Object.assign(Error('AI 응답을 읽지 못했습니다.'),{stage:'validation'});}
      if(thread.deletedAt||controller.signal.aborted)return;
      if(!response.ok){if(response.status===403){token=null;bootstrapPromise=null;}throw Object.assign(Error(result.error||'AI 요청에 실패했습니다.'),{stage:result.stage||'connection',inspection:result.inspection});}
      if(result.request_id!==message.submission.request_id||result.thread_id!==thread.id||typeof result.answer!=='string'||!Array.isArray(result.citations))throw Object.assign(Error('응답이 제출한 작업과 일치하지 않습니다.'),{stage:'validation'});
      message.result=result;message.status='success';state.applyContext(thread,message.submission,result.context);thread.updatedAt=new Date().toISOString();ready=true;
    }catch(error){if(thread.deletedAt||controller.signal.aborted)return;message.status='error';message.stage=error.stage||'connection';message.error=error.name==='TimeoutError'?'응답을 기다리는 시간이 초과됐습니다. 같은 질문을 재시도할 수 있어요.':error.message;if(error.inspection)message.inspection=error.inspection;}
    finally{controllers.delete(message.submission.request_id);}
    if(previewActiveId===thread.id){previewRenderMessages();if(document.querySelector('.page.active')?.id==='chat')scrollChatToBottom();}
    previewRemember();
  }
  sendChat=function(){
    const input=el('chatInput');if(!input.value.trim()||pending(previewThread()))return;
    if(!previewThread())newChat();const thread=previewThread();thread.draft=input.value;
    const scope=currentScope();if(scope?.collectionId!=='personal'&&!scope?.questionId){previewToast('플로팅에서 질문 사례를 먼저 선택해 주세요.');return;}
    const submission=state.submission(thread,scope,{inspect:window.PlantTestMode?.enabled===true}),message={kind:'assistant',status:'pending',submission,createdAt:new Date().toISOString()};
    thread.messages.push({kind:'user',text:submission.text,requestId:submission.request_id,createdAt:new Date().toISOString()},message);thread.title=submission.text.trim().slice(0,28);
    // Consume only the accepted submission; response completion never edits the next draft.
    thread.draft='';thread.inputVersion=(thread.inputVersion||0)+1;input.value='';updateChatInput();
    run(thread,message);input.focus();
  };
  const previousGo=go;go=function(id){previousGo(id);if(id==='chat')scopeLabel();};
  for(const thread of previewThreads)for(const message of thread.messages){
    if(message.kind==='assistant'&&message.status==='error'&&message.error==='대화를 삭제하여 응답 수신을 중단했습니다. 복원 후 재시도할 수 있어요.')message.status='cancelled';
    if(message.kind==='assistant'&&message.status==='pending'&&!message.archived){message.status='error';message.stage='connection';message.error='화면이 새로 열려 이전 처리 결과를 확인해야 합니다. 같은 제출본으로 재시도해 주세요.';}
  }
  el('chatSend').setAttribute('aria-label','질문 보내기');
  const note=document.querySelector('#chat .chat-disclaimer');if(note)note.textContent='현재 자료함에서 원문을 찾아 답합니다. 대화 내용은 보관소 기록으로 자동 추가되지 않습니다.';
  previewRenderMessages();bootstrap().catch(()=>{});
})();
