'use strict';
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else api.mount(root);})(typeof window==='undefined'?null:window,function(){
 function selectMap(thread,selection='latest'){
  const messages=thread&&!thread.deletedAt?(thread.messages||[]).filter(m=>m.kind==='assistant'&&m.result?.dialogue_trace&&m.submission?.request_id):[];
  const selected=selection==='latest'?null:messages.find(m=>m.submission.request_id===selection);return {messages,message:selected||messages.at(-1)||null,selection:selected?selection:'latest'};
 }
 function mount(win){
  const doc=win.document,node=(tag,text,cls)=>{const e=doc.createElement(tag);if(text!=null)e.textContent=text;if(cls)e.className=cls;return e;};
  const host=node('div',null,'dialogue-map-host');host.id='dialogueMapHost';
  const panel=node('section',null,'dialogue-floating-panel');panel.id='dialogueFloatingPanel';panel.setAttribute('role','dialog');panel.setAttribute('aria-label','대화 지도');
  const header=node('div',null,'dialogue-floating-header'),titles=node('div');titles.append(node('small','V2 · LLM'),node('h2','대화 지도'));
  const close=node('button','접기','dialogue-floating-close');close.type='button';close.setAttribute('aria-label','대화 지도 패널 접기');header.append(titles,close);
  const controls=node('div',null,'dialogue-floating-controls'),label=node('label','지도 기준 응답');label.htmlFor='dialogueFloatingSelection';const select=node('select');select.id='dialogueFloatingSelection';select.setAttribute('aria-label','지도 기준 응답');const context=node('p');controls.append(label,select,context);
  const body=node('div',null,'dialogue-floating-body');panel.append(header,controls,body);
  const launcher=node('button',null,'dialogue-floating-launcher');launcher.id='dialogueMapToggle';launcher.type='button';launcher.setAttribute('aria-controls',panel.id);launcher.title='대화 지도';launcher.append(node('span','지도','dialogue-floating-icon'));host.append(panel,launcher);doc.body.append(host);
  const key='plant-thought-dialogue-floating-v1';let saved;try{saved=JSON.parse(win.sessionStorage.getItem(key)||'null');}catch{}
  let open=saved?.open!==false,selection='latest',threadId=null,lastResult=null,signature='';
  function save(){try{win.sessionStorage.setItem(key,JSON.stringify({open}));}catch{}}
  function render(force=false){
   const thread=win.previewThread?.();if(thread?.id!==threadId){threadId=thread?.id||null;selection='latest';force=true;}
   const current=selectMap(thread,selection);selection=current.selection;const message=current.message;
   const next=JSON.stringify([threadId,selection,current.messages.map(m=>[m.submission.request_id,m.submission.text])]);
   if(signature!==next){const latest=node('option','최신 지도 따라가기');latest.value='latest';select.replaceChildren(latest,...current.messages.map((m,i)=>{const option=node('option',(i+1)+'. '+m.submission.text.replace(/\s+/g,' ').slice(0,55));option.value=m.submission.request_id;return option;}).reverse());select.value=selection;select.disabled=!current.messages.length;signature=next;}
   context.textContent=message?(selection==='latest'?'최신 응답':'선택한 응답')+' · '+message.submission.text.replace(/\s+/g,' ').slice(0,70)+' · '+message.result.dialogue_trace.parts.length+'개 파트'+(thread.messages.some(m=>m.status==='pending')?' · 새 분석 중, 이전 지도 표시':''):'현재 대화에 준비된 지도가 없습니다.';
   if(!open||!force&&message?.result===lastResult)return;
   const scroll=force?0:body.scrollTop,expanded=new Set([...body.querySelectorAll('details[open]')].map(e=>e.querySelector('summary')?.textContent));body.replaceChildren();
   if(message){const content=win.PlantDialogueMapContent(message.result);content.open=true;body.append(content);for(const detail of body.querySelectorAll('.chat-augmented-input'))detail.open=expanded.has(detail.querySelector('summary')?.textContent);}
   else body.append(node('p','V2로 대화하면 시간순 파트 요약, 현재 선택한 대상과 연결 원문을 여기서 확인할 수 있어요.','dialogue-floating-empty'));
   body.scrollTop=scroll;lastResult=message?.result;
  }
  function sync(){host.hidden=!['home','chat','archive'].includes(doc.querySelector('.page.active')?.id);panel.hidden=!open;launcher.setAttribute('aria-expanded',String(open));launcher.setAttribute('aria-label',open?'대화 지도 패널 접기':'대화 지도 패널 열기');if(!host.hidden)render();win.PlantFloatingWindows?.schedule();}
  function setOpen(value){open=value;sync();save();if(value){render(true);win.PlantFloatingWindows?.focus(panel.id);close.focus({preventScroll:true});}}
  launcher.addEventListener('click',()=>setOpen(!open));close.addEventListener('click',()=>{setOpen(false);launcher.focus({preventScroll:true});});select.addEventListener('change',()=>{selection=select.value;render(true);});
  win.PlantDialogueFloating={open(requestId){selection=requestId||'latest';setOpen(true);}};
  const draw=win.previewRenderMessages;win.previewRenderMessages=function(...args){const result=draw.apply(this,args);sync();return result;};
  const navigate=win.go;win.go=function(...args){const result=navigate.apply(this,args);sync();return result;};
  win.PlantFloatingWindows?.register({panel,launcher,host,width:420,label:'대화 지도',closeButton:close});sync();
 }
 return {selectMap,mount};
});
