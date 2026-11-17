'use strict';
// Only browser-local UI state lives here. No requests, model calls, or memory writes.
const previewStorageKey='plant-thought-ui-preview-v1';
const previewNotice='화면 미리보기입니다. AI 답변은 생성하지 않으며, 이 입력은 실제 기억으로 저장되지 않았어요.';
let previewThreads=[],previewActiveId=null,previewToastTimer;
const previewEmpty=(title,text)=>'<div class="preview-empty"><strong>'+safe(title)+'</strong><p>'+safe(text)+'</p></div>';
function previewToast(text){
  let el=document.getElementById('previewToast');
  if(!el){el=document.createElement('div');el.id='previewToast';el.className='preview-toast';el.setAttribute('role','status');document.body.appendChild(el);}
  el.textContent=text;el.hidden=false;clearTimeout(previewToastTimer);previewToastTimer=setTimeout(()=>{el.hidden=true;},4000);
}
function previewThread(){return previewThreads.find(t=>t.id===previewActiveId&&!t.deletedAt);}
function previewSnapshot(){
  const current=previewThread();if(current)current.draft=document.getElementById('chatInput').value;
  return {version:1,page:document.querySelector('.page.active')?.id||'home',threads:previewThreads,activeId:previewActiveId,
    home:document.getElementById('homeSearch').value,chatDraft:document.getElementById('chatInput').value,
    record:{title:document.getElementById('recordTitle').value,date:document.getElementById('recordDate').value,body:document.getElementById('recordBody').value},
    preferences:Object.fromEntries(['semanticSearch','showSources','showCalendar','collapseDetails'].map(id=>[id,document.getElementById(id).checked])),
    archive:{query:document.getElementById('archiveInput').value,selected,view:archiveView,expanded:calendarExpanded}};
}
function previewRemember(){try{sessionStorage.setItem(previewStorageKey,JSON.stringify(previewSnapshot()));}catch{/* Private/limited browser storage must not prevent UI navigation. */}}
function previewCloseThreadMenus({focus=false}={}){
  for(const toggle of document.querySelectorAll('.preview-thread-more[aria-expanded="true"]')){
    toggle.setAttribute('aria-expanded','false');const menu=document.getElementById(toggle.getAttribute('aria-controls'));if(menu)menu.hidden=true;if(focus)toggle.focus({preventScroll:true});
  }
}
document.addEventListener('click',event=>{if(!event.target.closest('.preview-thread-row,.preview-thread-menu'))previewCloseThreadMenus();});
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&document.querySelector('.preview-thread-more[aria-expanded="true"]')){event.preventDefault();previewCloseThreadMenus({focus:true});}});
document.addEventListener('scroll',()=>previewCloseThreadMenus(),true);
window.addEventListener('resize',()=>previewCloseThreadMenus());
function previewPositionThreadMenu(toggle,menu){
  const anchor=toggle.getBoundingClientRect(),width=menu.offsetWidth,height=menu.offsetHeight;
  menu.style.left=Math.max(8,Math.min(anchor.right-width,window.innerWidth-width-8))+'px';
  const below=anchor.bottom+6,fits=below+height<=window.innerHeight-8;
  menu.style.top=(fits?below:Math.max(8,anchor.top-height-6))+'px';menu.dataset.placement=fits?'below':'above';
}
function previewRenderHistory(){
  previewCloseThreadMenus();for(const menu of document.querySelectorAll('.preview-thread-menu'))menu.remove();
  const history=document.getElementById('chatHistory'),expanded=history.querySelector('.preview-deleted-chats')?.open||false;history.replaceChildren();
  for(const thread of [...previewThreads].reverse().filter(t=>!t.deletedAt)){
    const row=document.createElement('div');row.className='preview-thread-row';row.dataset.threadId=thread.id;
    const button=document.createElement('button');button.type='button';button.className='preview-thread'+(thread.id===previewActiveId?' active':'');
    button.textContent=thread.title||'새 대화';button.setAttribute('aria-label',button.textContent+' 열기');button.onclick=()=>previewOpenThread(thread.id);
    const remove=document.createElement('button');remove.type='button';remove.className='preview-delete-thread';remove.dataset.deleteThread=thread.id;remove.textContent='삭제';remove.title='대화 삭제';remove.setAttribute('aria-label',button.textContent+' 대화 삭제');remove.onclick=()=>previewDeleteThread(thread.id);
    const more=document.createElement('button');more.type='button';more.className='preview-thread-more';more.textContent='⋯';more.title='대화 메뉴';more.setAttribute('aria-label',button.textContent+' 대화 메뉴');more.setAttribute('aria-haspopup','menu');more.setAttribute('aria-expanded','false');
    const menu=document.createElement('div');menu.className='preview-thread-menu';menu.id='thread-menu-'+thread.id;menu.hidden=true;menu.setAttribute('role','menu');menu.setAttribute('aria-label','대화 메뉴');more.setAttribute('aria-controls',menu.id);remove.setAttribute('role','menuitem');menu.append(remove);
    const openMenu=()=>{previewCloseThreadMenus();menu.hidden=false;previewPositionThreadMenu(more,menu);more.setAttribute('aria-expanded','true');};
    more.onclick=event=>{event.stopPropagation();if(more.getAttribute('aria-expanded')==='true')previewCloseThreadMenus();else{openMenu();if(event.detail===0)remove.focus({preventScroll:true});}};
    more.onkeydown=event=>{if(event.key==='ArrowDown'){event.preventDefault();openMenu();remove.focus({preventScroll:true});}};
    remove.onkeydown=event=>{if(['ArrowDown','ArrowUp','Home','End'].includes(event.key)){event.preventDefault();remove.focus({preventScroll:true});}};
    row.append(button,more);history.append(row);document.body.append(menu);
  }
  const deleted=previewThreads.filter(t=>t.deletedAt).sort((a,b)=>b.deletedAt-a.deletedAt);
  if(deleted.length){
    const details=document.createElement('details');details.className='preview-deleted-chats';details.open=expanded;
    const summary=document.createElement('summary');summary.textContent='삭제한 대화 ('+deleted.length+')';details.append(summary);
    for(const thread of deleted){const row=document.createElement('div');row.className='preview-deleted-row';const title=document.createElement('span');title.textContent=thread.title||'새 대화';title.title=title.textContent;
      const restore=document.createElement('button');restore.type='button';restore.textContent='복원';restore.dataset.restoreThread=thread.id;restore.setAttribute('aria-label',title.textContent+' 대화 복원');restore.onclick=()=>previewRestoreThread(thread.id);row.append(title,restore);details.append(row);}
    history.append(details);
  }
}
function previewDeleteThread(id){
  const thread=previewThreads.find(t=>t.id===id&&!t.deletedAt);if(!thread)return;
  previewRemember();thread.deletedAt=Date.now();
  document.dispatchEvent(new CustomEvent('plant:thread-deleted',{detail:{id}}));
  if(previewActiveId===id){
    const next=[...previewThreads].reverse().find(t=>!t.deletedAt);
    if(next){previewActiveId=next.id;previewRenderMessages();}else newChat();
  }else previewRenderHistory();
  previewRemember();previewToast('대화를 삭제했어요. 목록 아래의 삭제한 대화에서 복원할 수 있어요.');
}
function previewRestoreThread(id){
  const thread=previewThreads.find(t=>t.id===id&&t.deletedAt);if(!thread)return;
  previewRemember();delete thread.deletedAt;previewRenderHistory();previewRemember();previewToast('대화를 복원했어요.');
}
function previewRenderMessages(){
  const log=document.getElementById('conversation');log.replaceChildren();
  const thread=previewThread();
  if(!thread?.messages?.length){log.innerHTML='<div class="preview-chat-welcome"><div class="iconbox">♧</div><span class="tag">화면 미리보기 · 연결 전</span><h2>이야기가 시작되는 자리</h2><p>생각이나 질문을 자유롭게 적어보세요.<br>지금은 입력과 대화 화면의 모습만 확인할 수 있어요.</p></div>';}
  else for(const message of thread.messages){const el=document.createElement('div');el.className='preview-message '+(message.kind==='user'?'user':'notice');el.textContent=message.text;log.appendChild(el);}
  document.getElementById('chatInput').value=thread?.draft||'';updateChatInput();previewRenderHistory();
}
function previewOpenThread(id){if(!previewThreads.some(t=>t.id===id&&!t.deletedAt))return;previewRemember();previewActiveId=id;previewRenderMessages();go('chat');previewRemember();document.getElementById('chatInput').focus();}
function newChat(){
  previewRemember();const thread={id:crypto.randomUUID(),title:'새 대화',draft:'',messages:[],createdAt:new Date().toISOString()};previewThreads.push(thread);previewActiveId=thread.id;
  previewRenderMessages();go('chat');previewRemember();document.getElementById('chatInput').focus();
}
function updateDemoControls(){document.getElementById('chatSend').disabled=!document.getElementById('chatInput').value.trim();}
function sendChat(){
  const input=document.getElementById('chatInput'),text=input.value.trim();if(!text)return;
  if(!previewThread()){const thread={id:crypto.randomUUID(),title:'새 대화',draft:input.value,messages:[]};previewThreads.push(thread);previewActiveId=thread.id;}
  const thread=previewThread();thread.draft=input.value;
  if(thread.messages.at(-2)?.text!==text){thread.messages.push({kind:'user',text},{kind:'notice',text:previewNotice});thread.title=text.slice(0,28);}
  previewRenderMessages();previewRemember();input.focus();
}
function startChatFromHome(){const text=document.getElementById('homeSearch').value;if(!previewThread())newChat();else go('chat');if(text.trim()){document.getElementById('chatInput').value=text;updateChatInput();sendChat();}else document.getElementById('chatInput').focus();previewRemember();}
function addRecord(){
  const title=document.getElementById('recordTitle').value.trim(),body=document.getElementById('recordBody').value.trim(),date=document.getElementById('recordDate').value;
  const target=document.getElementById('emotion');let card=document.getElementById('recordPreview');
  if(!card){card=document.createElement('div');card.id='recordPreview';card.className='preview-record-card';card.setAttribute('role','status');target.querySelector(':scope > div').appendChild(card);}
  card.replaceChildren();const label=document.createElement('small');label.textContent='작성 미리보기 · 저장되지 않음';card.appendChild(label);
  if(!body){const p=document.createElement('p');p.textContent='미리 볼 내용을 먼저 입력해 주세요.';card.appendChild(p);document.getElementById('recordBody').focus();return;}
  const h=document.createElement('h3');h.textContent=title||'제목 없는 초안';const when=document.createElement('small');when.textContent=date||'날짜 미정';const p=document.createElement('p');p.textContent=body;card.append(h,when,p);previewRemember();card.scrollIntoView({behavior:'smooth',block:'nearest'});
}
function runSearch(reveal=false){
  if(!reveal){archiveSearchActive=false;syncArchivePanel();return;}
  archiveSearchActive=true;syncArchivePanel();document.getElementById('resultCount').textContent='연결 전';
  const query=document.getElementById('archiveInput').value.trim();document.getElementById('searchQueryCaption').textContent=query?'입력한 검색어: '+query:'검색어를 입력해 화면을 확인하세요.';
  document.getElementById('searchResults').innerHTML=previewEmpty('검색은 아직 연결되지 않았어요','기록을 조회하지 않았습니다. 검색 결과는 기능 연결 후 표시됩니다.');previewRemember();scrollToSearchResults();
}
// Empty states describe connectivity, rather than claiming that a search found no memory.
const originalRenderRecent=renderRecent;renderRecent=function(){originalRenderRecent();document.getElementById('homeRecent').innerHTML='<li>'+previewEmpty('기록을 연결할 자리','실제 기록은 아직 불러오지 않았어요.')+'</li>';};
const originalRenderSelected=renderSelected;renderSelected=function(){originalRenderSelected();document.getElementById('selectedCount').textContent='기록 연결 전';document.getElementById('selectedList').innerHTML=previewEmpty('선택한 날짜의 기록','기록 조회를 연결하면 이곳에서 확인할 수 있어요.');};
const originalRenderTimeline=renderTimeline;renderTimeline=function(){originalRenderTimeline();document.getElementById('timelineCount').textContent='기록 연결 전';document.getElementById('timelineGroups').innerHTML=previewEmpty('시간순으로 이어질 이야기','아직 실제 기록을 불러오지 않았어요.');};
const originalGo=go;go=function(id){originalGo(id);if(document.querySelector('.page.active')?.id===id){history.replaceState(null,'','#'+id);previewRemember();}};
function previewRestore(){
  let saved;try{saved=JSON.parse(sessionStorage.getItem(previewStorageKey)||'null');}catch{}
  if(saved?.version===1){
    previewThreads=Array.isArray(saved.threads)?saved.threads.filter(t=>typeof t.id==='string'&&Array.isArray(t.messages)):[];previewActiveId=saved.activeId;
    document.getElementById('homeSearch').value=saved.home||'';
    for(const [field,id]of [['title','recordTitle'],['date','recordDate'],['body','recordBody']])if(typeof saved.record?.[field]==='string')document.getElementById(id).value=saved.record[field];
    for(const id of ['semanticSearch','showSources','showCalendar','collapseDetails'])if(typeof saved.preferences?.[id]==='boolean')document.getElementById(id).checked=saved.preferences[id];
    if(/^\d{4}-\d{2}-\d{2}$/.test(saved.archive?.selected)){selected=saved.archive.selected;const parts=selected.split('-').map(Number);year=parts[0];month=parts[1]-1;}
    archiveView=saved.archive?.view==='timeline'?'timeline':'calendar';calendarExpanded=saved.archive?.expanded===true;document.getElementById('archiveInput').value=saved.archive?.query||'';
  }
  if(!previewThread()){
    const thread={id:crypto.randomUUID(),title:'새 대화',draft:typeof saved?.chatDraft==='string'?saved.chatDraft:'',messages:[]};
    previewThreads.push(thread);previewActiveId=thread.id;
  }
  previewRenderMessages();renderRecent();renderCalendar();renderTimeline();
  const requested=location.hash.slice(1),allowed=[...pages,'login','signup','recordDetail'];
  go(allowed.includes(requested)?requested:allowed.includes(saved?.page)?saved.page:'home');
}
document.addEventListener('input',event=>{if(!event.target.matches('input[type="password"],input[type="email"]'))previewRemember();});
document.addEventListener('change',event=>{if(event.target.closest('#settings')){document.getElementById('archiveCalendar').hidden=!document.getElementById('showCalendar').checked;previewRemember();}});
window.addEventListener('pagehide',previewRemember);
window.addEventListener('hashchange',()=>{const page=location.hash.slice(1);if([...pages,'login','signup'].includes(page))go(page);});
previewRestore();
