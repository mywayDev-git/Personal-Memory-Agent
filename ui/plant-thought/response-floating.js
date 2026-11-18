'use strict';
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else api.mount(root);})(typeof window==='undefined'?null:window,function(){
 function selectResponse(thread,selection='latest'){
  const messages=thread&&!thread.deletedAt?(thread.messages||[]).filter(m=>m.kind==='assistant'&&m.submission?.request_id):[];
  const selected=selection==='latest'?null:messages.find(m=>m.submission.request_id===selection);
  const message=selected||messages.at(-1)||null;
  return {messages,message,selection:selected?selection:'latest',index:message?messages.indexOf(message):-1};
 }
 function isVisible(page,enabled){return page==='chat'&&enabled===true;}
 function mount(win){
  const doc=win.document,inspector=win.PlantResponseInspector;if(!inspector||doc.getElementById('responseInspectorHost'))return;
  const node=(tag,text,cls)=>{const e=doc.createElement(tag);if(text!=null)e.textContent=text;if(cls)e.className=cls;return e;};
  const host=node('div',null,'response-inspector-host');host.id='responseInspectorHost';host.hidden=true;
  const panel=node('section',null,'response-floating-panel');panel.id='responseFloatingPanel';panel.hidden=true;panel.setAttribute('role','dialog');panel.setAttribute('aria-label','요청·응답 정보');
  const header=node('div',null,'response-floating-header'),titleBox=node('div');titleBox.append(node('span','테스트 모드','response-floating-eyebrow'),node('h2','요청·응답 정보'));
  const dismiss=node('button','접기','response-floating-close');dismiss.type='button';dismiss.setAttribute('aria-label','요청·응답 정보 패널 접기');header.append(titleBox,dismiss);
  const controls=node('div',null,'response-floating-controls'),selectLabel=node('label','확인할 응답');selectLabel.htmlFor='responseFloatingSelection';
  const select=node('select');select.id='responseFloatingSelection';select.setAttribute('aria-label','확인할 응답');
  const context=node('p',null,'response-floating-context');controls.append(selectLabel,select,context);
  const body=node('div',null,'response-floating-body');body.id='responseFloatingBody';panel.append(header,controls,body);
  const launcher=node('button',null,'response-floating-launcher');launcher.id='responseInspectorToggle';launcher.type='button';launcher.setAttribute('aria-controls',panel.id);launcher.setAttribute('aria-expanded','false');launcher.setAttribute('aria-label','요청·응답 정보 패널 열기');
  const icon=node('span','{ }','response-floating-icon');icon.setAttribute('aria-hidden','true');const copy=node('span',null,'response-floating-copy'),summary=node('span','응답을 받으면 확인할 수 있어요.');copy.append(node('strong','요청·응답 정보'),summary);launcher.append(icon,copy);
  host.append(panel,launcher);doc.body.append(host);
  const storageKey='plant-thought-response-floating-v1';let saved;try{saved=JSON.parse(win.sessionStorage.getItem(storageKey)||'null');}catch{}
  let open=saved?.open===true,selection='latest',threadId=null,lastMessage=null,lastResult=null,lastStatus=null,lastError=null,optionSignature='';
  function save(){try{win.sessionStorage.setItem(storageKey,JSON.stringify({version:1,open}));}catch{}}
  function close(focus=false){open=false;panel.hidden=true;launcher.setAttribute('aria-expanded','false');launcher.setAttribute('aria-label','요청·응답 정보 패널 열기');save();if(focus&&!host.hidden)launcher.focus();}
  function render(force=false){
   const thread=win.previewThread?.();if(thread?.id!==threadId){threadId=thread?.id||null;selection='latest';force=true;}
   const current=selectResponse(thread,selection);selection=current.selection;
   const message=current.message;summary.textContent=message?(selection==='latest'?'최신 응답':'선택한 응답')+' · '+inspector.describe(message).stage:'응답을 받으면 확인할 수 있어요.';
   if(!open)return;
   const signature=JSON.stringify([threadId,selection,current.messages.map(m=>[m.submission.request_id,m.status,m.submission.text])]);
   if(signature!==optionSignature){
    const latest=node('option','최신 응답 따라가기');latest.value='latest';
    const options=[latest,...current.messages.map((m,index)=>{const text=m.submission.text.replace(/\s+/g,' ').slice(0,64),option=node('option',(index+1)+'. '+text+' · '+({pending:'응답 중',success:'완료',error:'실패',cancelled:'중단'}[m.status]||'확인 전'));option.value=m.submission.request_id;return option;}).reverse()];
    select.replaceChildren(...options);select.value=selection;select.disabled=!current.messages.length;optionSignature=signature;
   }
   context.textContent=message?(thread.title||'새 대화')+' · '+(current.index+1)+'번째 응답':'현재 대화에 확인할 AI 응답이 없습니다.';
   if(!force&&message===lastMessage&&message?.result===lastResult&&message?.status===lastStatus&&message?.error===lastError)return;
   const same=message===lastMessage,scroll=same?body.scrollTop:0;
   const expanded=same?new Set([...body.querySelectorAll('details[open]')].map(e=>e.querySelector('summary')?.textContent)):new Set();
   body.replaceChildren();
   if(message){
    const card=[...doc.querySelectorAll('#conversation .ai-response')].find(e=>e.dataset.requestId===message.submission.request_id);
    const receipt=inspector.render(doc,message,card?.querySelector('.ai-answer')||null,true);
    const content=receipt?.querySelector('.ai-inspection-content');if(content){body.append(content);for(const e of body.querySelectorAll('details'))if(expanded.has(e.querySelector('summary')?.textContent))e.open=true;}
   }else{body.append(node('div','질문을 보내면 요청 의도, 지정한 답변 형식, 실제 응답과 검증 결과를 여기에서 확인할 수 있어요.','response-floating-empty'));}
   body.scrollTop=scroll;lastMessage=message;lastResult=message?.result;lastStatus=message?.status;lastError=message?.error;
  }
  function sync(){
   const allowed=isVisible(doc.querySelector('.page.active')?.id,win.PlantTestMode?.enabled);host.hidden=!allowed;
   if(!win.PlantTestMode?.enabled&&open)close();
   if(!allowed)return;
   panel.hidden=!open;launcher.setAttribute('aria-expanded',String(open));launcher.setAttribute('aria-label',open?'요청·응답 정보 패널 접기':'요청·응답 정보 패널 열기');
   render();
  }
  launcher.addEventListener('click',()=>{if(open){close();return;}open=true;panel.hidden=false;launcher.setAttribute('aria-expanded','true');launcher.setAttribute('aria-label','요청·응답 정보 패널 접기');render(true);save();dismiss.focus();});
  dismiss.addEventListener('click',()=>close(true));
  select.addEventListener('change',()=>{selection=select.value;render(true);});
  host.addEventListener('keydown',event=>{if(event.key==='Escape'&&open){event.preventDefault();event.stopPropagation();close(true);}},true);
  doc.addEventListener('plant:test-mode-changed',sync);
  const draw=win.previewRenderMessages;win.previewRenderMessages=function(...args){const result=draw.apply(this,args);sync();return result;};
  const navigate=win.go;win.go=function(...args){const result=navigate.apply(this,args);sync();return result;};
  sync();
 }
 return {selectResponse,isVisible,mount};
});
