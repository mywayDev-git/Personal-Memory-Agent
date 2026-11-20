'use strict';
// Only browser-local UI state lives here. No requests, model calls, or memory writes.
const previewStorageKey='plant-thought-ui-preview-v1';
const previewNotice='화면 미리보기입니다. AI 답변은 생성하지 않으며, 이 입력은 실제 기억으로 저장되지 않았어요.';
let previewThreads=[],previewActiveId=null,previewToastTimer;
const previewEmpty=(title,text)=>'<div class="preview-empty"><strong>'+safe(title)+'</strong><p>'+safe(text)+'</p></div>';
let chatSettingsPlaceholder=null,chatSettingsOpener=null;
function openChatSettings(){
  const dialog=document.getElementById('chatSettingsDialog'),settings=document.getElementById('settings');if(dialog.open)return;
  chatSettingsOpener=document.activeElement;chatSettingsPlaceholder=document.createComment('settings page position');settings.before(chatSettingsPlaceholder);document.getElementById('chatSettingsBody').append(settings);
  document.getElementById('mobileSelect').value='chat';dialog.showModal();document.getElementById('chatSettingsClose').focus({preventScroll:true});
}
function closeChatSettings(){document.getElementById('chatSettingsDialog').close();}
const chatSettingsDialog=document.getElementById('chatSettingsDialog');
chatSettingsDialog.addEventListener('close',()=>{
  if(chatSettingsPlaceholder?.isConnected)chatSettingsPlaceholder.replaceWith(document.getElementById('settings'));chatSettingsPlaceholder=null;
  const toast=document.getElementById('previewToast');if(toast&&chatSettingsDialog.contains(toast))document.body.append(toast);
  if(document.querySelector('.page.active')?.id==='chat'&&chatSettingsOpener?.isConnected)chatSettingsOpener.focus({preventScroll:true});chatSettingsOpener=null;previewRemember();
});
chatSettingsDialog.addEventListener('click',event=>{if(event.target!==chatSettingsDialog)return;const r=chatSettingsDialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)closeChatSettings();});
function previewToast(text,action){
  let el=document.getElementById('previewToast');
  if(!el){el=document.createElement('div');el.id='previewToast';el.className='preview-toast';el.setAttribute('role','status');}
  // Put interactive notifications inside the settings modal so they remain clickable.
  (chatSettingsDialog.open?chatSettingsDialog:document.body).append(el);
  el.replaceChildren();const message=document.createElement('span');message.textContent=text;el.append(message);
  const dismiss=()=>{clearTimeout(previewToastTimer);el.hidden=true;};
  const schedule=()=>{clearTimeout(previewToastTimer);previewToastTimer=setTimeout(dismiss,action?10000:4000);};
  if(action){const button=document.createElement('button');button.type='button';button.className='preview-toast-action';button.textContent=action.label;button.onclick=()=>{dismiss();action.run();};el.append(button);}
  el.onmouseenter=()=>clearTimeout(previewToastTimer);el.onmouseleave=schedule;
  el.onfocusin=()=>clearTimeout(previewToastTimer);el.onfocusout=event=>{if(!el.contains(event.relatedTarget))schedule();};
  el.hidden=false;schedule();
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
  for(const toggle of document.querySelectorAll('.preview-thread-more[aria-expanded="true"],.sidebar-group-more[aria-expanded="true"]')){
    toggle.setAttribute('aria-expanded','false');const menu=document.getElementById(toggle.getAttribute('aria-controls'));if(menu)menu.hidden=true;if(focus)toggle.focus({preventScroll:true});
  }
}
document.addEventListener('click',event=>{if(!event.target.closest('.preview-thread-row,.preview-thread-menu,.sidebar-group-more'))previewCloseThreadMenus();});
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&document.querySelector('.preview-thread-more[aria-expanded="true"],.sidebar-group-more[aria-expanded="true"]')){event.preventDefault();previewCloseThreadMenus({focus:true});}});
document.addEventListener('scroll',()=>previewCloseThreadMenus(),true);
window.addEventListener('resize',()=>previewCloseThreadMenus());
function previewPositionThreadMenu(toggle,menu){
  const anchor=toggle.getBoundingClientRect(),sidebar=toggle.closest('#chatSidebar')?.getBoundingClientRect(),width=menu.offsetWidth,height=menu.offsetHeight,gap=8;
  const right=(sidebar?.right??anchor.right)+gap,left=(sidebar?.left??anchor.left)-width-gap;
  const fitsRight=right+width<=window.innerWidth-gap,fitsLeft=left>=gap;
  menu.style.left=Math.max(gap,Math.min(fitsRight?right:fitsLeft?left:window.innerWidth-width-gap,window.innerWidth-width-gap))+'px';
  menu.style.top=Math.max(gap,Math.min(anchor.top-5,window.innerHeight-height-gap))+'px';
  menu.dataset.placement=fitsRight?'right':fitsLeft?'left':'in-viewport';
}
function previewBindHistoryMenu(more,menu){
  const openMenu=()=>{previewCloseThreadMenus();menu.hidden=false;previewPositionThreadMenu(more,menu);more.setAttribute('aria-expanded','true');};
  more.onclick=event=>{event.stopPropagation();if(more.getAttribute('aria-expanded')==='true')previewCloseThreadMenus();else{openMenu();if(event.detail===0)menu.querySelector('button').focus({preventScroll:true});}};
  more.onkeydown=event=>{if(event.key==='ArrowDown'){event.preventDefault();openMenu();menu.querySelector('button').focus({preventScroll:true});}};
  menu.addEventListener('keydown',event=>{const items=[...menu.querySelectorAll('button')],index=items.indexOf(document.activeElement);let target;if(event.key==='ArrowDown')target=(index+1)%items.length;else if(event.key==='ArrowUp')target=(index+items.length-1)%items.length;else if(event.key==='Home')target=0;else if(event.key==='End')target=items.length-1;else return;event.preventDefault();event.stopPropagation();items[target].focus();});
}
function previewDeleteGroup(name){
  if(!previewThreads.some(t=>t.group===name))return;
  previewRemember();previewCloseThreadMenus();
  for(const thread of previewThreads)if(thread.group===name)delete thread.group;
  previewCollapsedGroups.delete(name);try{sessionStorage.setItem('plant-thought-collapsed-groups-v1',JSON.stringify([...previewCollapsedGroups]));}catch{}
  previewRenderHistory();previewRemember();
  document.querySelector('#chatHistory .preview-thread.active')?.focus({preventScroll:true});
  previewToast('묶음을 삭제했어요. 대화는 목록에 그대로 남아 있어요.');
}
let previewHistoryQuery='';
const previewCollapsedGroups=new Set();
let previewRecentCollapsed=false;try{previewRecentCollapsed=sessionStorage.getItem('plant-thought-recent-collapsed-v1')==='on';}catch{}
try{const saved=JSON.parse(sessionStorage.getItem('plant-thought-collapsed-groups-v1')||'[]');if(Array.isArray(saved))for(const name of saved)if(typeof name==='string')previewCollapsedGroups.add(name);}catch{}
function previewToggleGroup(name,bar){
  const section=bar.closest('section.chat-history-section'),recent=section.dataset.historyKind==='recent',content=section.querySelector('.chat-group-content'),toggle=bar.querySelector('.sidebar-group-toggle');
  content.hidden=!content.hidden;
  if(recent)previewRecentCollapsed=content.hidden;else if(content.hidden)previewCollapsedGroups.add(name);else previewCollapsedGroups.delete(name);
  toggle.setAttribute('aria-expanded',String(!content.hidden));const label=(recent?'최근 대화':name+' 묶음')+' '+(content.hidden?'펼치기':'접기');toggle.setAttribute('aria-label',label);toggle.title=label;
  try{if(recent)sessionStorage.setItem('plant-thought-recent-collapsed-v1',content.hidden?'on':'off');else sessionStorage.setItem('plant-thought-collapsed-groups-v1',JSON.stringify([...previewCollapsedGroups]));}catch{}
  requestAnimationFrame(previewUpdateTitleFade);
}
function previewSidebarIcon(name){
  const paths={chevron:'<path d="m6 9 6 6 6-6"/>',project:'<path d="m8 3-4 3v5l-1 2 2 2v4l4 2 3-2 3 2 4-2v-4l2-2-1-2V6l-4-3-4 2-4-2ZM12 5v14"/>',filter:'<path d="M3 7h8m4 0h6M3 17h3m4 0h11"/><circle cx="13" cy="7" r="2"/><circle cx="8" cy="17" r="2"/>',more:'<circle cx="12" cy="5" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="12" cy="19" r="1"/>',plus:'<path d="M12 5v14M5 12h14"/>',compose:'<path d="m14 5 4 4M15 4a2.12 2.12 0 0 1 3 3l-8 8-4 1 1-4 8-8ZM11 4H5a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h13a2 2 0 0 0 2-2v-7"/>'};
  const icon=document.createElementNS('http://www.w3.org/2000/svg','svg');icon.setAttribute('viewBox','0 0 24 24');icon.setAttribute('aria-hidden','true');icon.innerHTML=paths[name];return icon;
}
function previewSidebarToolbar(text,kind){
  const bar=document.createElement('div');bar.className='sidebar-section-toolbar';const title=document.createElement('h3');title.textContent=text;bar.append(title);
  const actions=document.createElement('div');actions.className='sidebar-section-actions';
  const action=(icon,label,callback)=>{const b=document.createElement('button');b.type='button';b.className='sidebar-toolbar-btn';b.title=label;b.setAttribute('aria-label',label);b.append(previewSidebarIcon(icon));b.onclick=callback;actions.append(b);return b;};

  if(kind==='group'||kind==='recent'){
    const collapsed=kind==='recent'?previewRecentCollapsed:previewCollapsedGroups.has(text),label=(kind==='recent'?'최근 대화':text+' 묶음')+' '+(collapsed?'펼치기':'접기');
    const toggle=action('chevron',label,()=>previewToggleGroup(text,bar));toggle.classList.add('sidebar-group-toggle');toggle.setAttribute('aria-expanded',String(!collapsed));toggle.setAttribute('aria-controls',kind==='recent'?'chat-recent-content':'chat-group-content-'+encodeURIComponent(text));bar.append(toggle);
  }
  if(kind==='group'){
    const more=action('more',text+' 묶음 메뉴',()=>{});more.classList.add('sidebar-group-more');more.setAttribute('aria-haspopup','menu');more.setAttribute('aria-expanded','false');
    const menu=document.createElement('div');menu.className='preview-thread-menu preview-group-menu';menu.id='group-menu-'+encodeURIComponent(text);menu.hidden=true;menu.setAttribute('role','menu');menu.setAttribute('aria-label',text+' 묶음 메뉴');more.setAttribute('aria-controls',menu.id);
    const remove=document.createElement('button');remove.type='button';remove.className='preview-delete-thread';remove.setAttribute('role','menuitem');remove.textContent='묶음 삭제';remove.onclick=()=>previewDeleteGroup(text);menu.append(remove);document.body.append(menu);previewBindHistoryMenu(more,menu);
  }
  action('plus','묶음 추가',previewCreateGroup);
  if(kind==='recent')action('compose','새 대화',()=>{previewCloseHistorySearch();newChat();});
  bar.append(actions);return bar;
}
function previewFilterHistory(query=previewHistoryQuery){
  previewHistoryQuery=String(query).trim().toLocaleLowerCase('ko-KR');let visible=0;
  for(const row of document.querySelectorAll('#chatHistory .preview-thread-row')){const thread=previewThreads.find(t=>t.id===row.dataset.threadId);row.hidden=!!previewHistoryQuery&&!((thread?.title||'')+' '+(thread?.group||'')).toLocaleLowerCase('ko-KR').includes(previewHistoryQuery);if(!row.hidden)visible++;}
  for(const section of document.querySelectorAll('#chatHistory .chat-history-section'))section.hidden=!!previewHistoryQuery&&!section.querySelector('.preview-thread-row:not([hidden])');
  document.getElementById('chatHistoryEmpty').hidden=!previewHistoryQuery||visible>0;requestAnimationFrame(previewUpdateTitleFade);
}
function previewCloseHistorySearch(){const box=document.getElementById('chatHistorySearchBox');box.hidden=true;document.getElementById('chatHistorySearch').value='';previewFilterHistory('');}
function previewToggleHistorySearch(){const box=document.getElementById('chatHistorySearchBox');if(!box.hidden){previewCloseHistorySearch();return;}box.hidden=false;document.getElementById('chatHistorySearch').focus();}
function previewCreateGroup(){
  document.getElementById('newGroupDialog')?.remove();const dialog=document.createElement('dialog');dialog.id='newGroupDialog';dialog.className='chat-organize-dialog';dialog.setAttribute('aria-labelledby','newGroupTitle');
  const heading=document.createElement('h2');heading.id='newGroupTitle';heading.textContent='새 묶음';const form=document.createElement('form'),label=document.createElement('label'),input=document.createElement('input');label.textContent='묶음 이름';input.required=true;input.maxLength=60;input.placeholder='예: 업무, 일상';label.append(input);
  const error=document.createElement('p');error.className='sidebar-project-error';error.setAttribute('role','alert');const actions=document.createElement('div');actions.className='chat-organize-actions';const cancel=document.createElement('button'),save=document.createElement('button');cancel.type='button';cancel.textContent='취소';cancel.onclick=()=>dialog.close();save.type='submit';save.textContent='만들기';actions.append(cancel,save);form.append(label,error,actions);dialog.append(heading,form);document.body.append(dialog);
  form.onsubmit=event=>{event.preventDefault();const name=input.value.trim();if(!name){error.textContent='묶음 이름을 입력해 주세요.';return;}if(previewThreads.some(t=>!t.deletedAt&&t.group===name)){error.textContent='이미 있는 묶음 이름입니다.';return;}newChat();previewThread().group=name;previewRenderHistory();previewRemember();dialog.close();document.getElementById('chatInput').focus();};dialog.addEventListener('close',()=>dialog.remove(),{once:true});dialog.showModal();input.focus();
}

function previewUpdateTitleFade(){
  for(const title of document.querySelectorAll('.preview-thread-title'))title.classList.toggle('is-overflowing',title.clientWidth>0&&title.scrollWidth>title.clientWidth);
}
const previewTitleResizeObserver=new ResizeObserver(previewUpdateTitleFade);previewTitleResizeObserver.observe(document.getElementById('chatSidebar'));
document.fonts.ready.then(previewUpdateTitleFade);
function previewRenderHomeChats(){
  const section=document.getElementById('homeRecentChats'),list=document.getElementById('homeRecentChatList');if(!section||!list)return;
  const timestamp=value=>{const time=Date.parse(value);return Number.isFinite(time)?time:0;};
  const recent=previewThreads.map((thread,index)=>({thread,index,time:Math.max(timestamp(thread.updatedAt),timestamp(thread.createdAt),timestamp(thread.messages.findLast(m=>m.createdAt)?.createdAt))})).filter(({thread})=>!thread.deletedAt&&thread.messages.some(m=>m.kind==='user'||m.kind==='assistant')).sort((a,b)=>b.time-a.time||b.index-a.index).slice(0,3);
  list.replaceChildren();section.hidden=!recent.length;
  for(const {thread}of recent){
    const button=document.createElement('button');button.type='button';button.className='home-recent-chat';button.dataset.threadId=thread.id;
    const title=thread.title||thread.messages.find(m=>m.kind==='user')?.text||'새 대화';button.title=title;button.setAttribute('aria-label',title+' 대화 이어가기');
    const text=document.createElement('span');text.className='preview-thread-title';text.textContent=title;
    const arrow=document.createElement('span');arrow.className='home-recent-chat-arrow';arrow.textContent='↗';arrow.setAttribute('aria-hidden','true');button.append(text,arrow);button.onclick=()=>previewOpenThread(thread.id);list.append(button);
  }
  requestAnimationFrame(previewUpdateTitleFade);
}
previewTitleResizeObserver.observe(document.getElementById('homeRecentChats'));

function previewRenameThread(id){
  const thread=previewThreads.find(t=>t.id===id&&!t.deletedAt);if(!thread)return;
  previewCloseThreadMenus();document.getElementById('chatRenameDialog')?.remove();
  const dialog=document.createElement('dialog');dialog.id='chatRenameDialog';dialog.className='chat-organize-dialog';dialog.setAttribute('aria-labelledby','chatRenameTitle');
  const heading=document.createElement('h2');heading.id='chatRenameTitle';heading.textContent='대화 제목 변경';
  const form=document.createElement('form'),label=document.createElement('label'),input=document.createElement('input');label.textContent='대화 제목';input.value=thread.title||'새 대화';input.required=true;input.maxLength=1000;label.append(input);
  const error=document.createElement('p');error.className='sidebar-project-error';error.setAttribute('role','alert');
  const actions=document.createElement('div');actions.className='chat-organize-actions';const cancel=document.createElement('button'),save=document.createElement('button');cancel.type='button';cancel.textContent='취소';cancel.onclick=()=>dialog.close();save.type='submit';save.textContent='저장';actions.append(cancel,save);form.append(label,error,actions);dialog.append(heading,form);document.body.append(dialog);
  form.onsubmit=event=>{event.preventDefault();const name=input.value.trim();if(!name){error.textContent='대화 제목을 입력해 주세요.';input.focus();return;}if(thread.deletedAt||!previewThreads.includes(thread)){error.textContent='이 대화를 찾을 수 없습니다.';return;}
    previewRemember();thread.title=name;thread.titleEdited=true;thread.updatedAt=new Date().toISOString();previewRenderHistory();previewRemember();dialog.close();previewToast('대화 제목을 변경했어요.');};
  dialog.addEventListener('close',()=>{dialog.remove();[...document.querySelectorAll('.preview-thread-row')].find(row=>row.dataset.threadId===id)?.querySelector('.preview-thread-more')?.focus({preventScroll:true});},{once:true});dialog.showModal();input.focus();input.select();
}

function previewRenderHistory(){
  const chatTitle=document.querySelector('.chat-title'),currentTitle=previewThread()?.title||'새 대화';if(chatTitle){chatTitle.textContent=currentTitle;chatTitle.title=currentTitle;chatTitle.setAttribute('aria-label','현재 대화: '+currentTitle);}
  previewCloseThreadMenus();for(const menu of document.querySelectorAll('.preview-thread-menu'))menu.remove();
  const history=document.getElementById('chatHistory');
  history.replaceChildren();
  const activeThreads=[...previewThreads].reverse().filter(t=>!t.deletedAt),sections=new Map();
  const sectionFor=thread=>{
    const key=thread.pinned?'pinned':thread.group?'group:'+thread.group:'other';
    if(sections.has(key))return sections.get(key);
    const section=document.createElement('section');section.className='chat-history-section';
    if(thread.group&&!thread.pinned){
      section.dataset.group=thread.group;const content=document.createElement('div');content.className='chat-group-content';content.id='chat-group-content-'+encodeURIComponent(thread.group);content.hidden=previewCollapsedGroups.has(thread.group);section.append(previewSidebarToolbar(thread.group,'group'),content);
    }else if(thread.pinned){const title=document.createElement('h3');title.textContent='고정한 대화';section.append(title);}
    else{section.dataset.historyKind='recent';const content=document.createElement('div');content.className='chat-group-content';content.id='chat-recent-content';content.hidden=previewRecentCollapsed;section.append(previewSidebarToolbar('최근','recent'),content);}
    sections.set(key,section);return section;
  };
  for(const thread of activeThreads){
    const row=document.createElement('div');row.className='preview-thread-row';row.dataset.threadId=thread.id;
    row.dataset.pinned=String(thread.pinned===true);row.classList.toggle('is-active',thread.id===previewActiveId);
    const button=document.createElement('button');button.type='button';button.className='preview-thread'+(thread.id===previewActiveId?' active':'');
    const titleText=document.createElement('span');titleText.className='preview-thread-title';titleText.textContent=thread.title||'새 대화';button.append(titleText);button.title=titleText.textContent;button.setAttribute('aria-label',button.textContent+' 열기');button.onclick=()=>previewOpenThread(thread.id);if(thread.id===previewActiveId)button.setAttribute('aria-current','true');
    const remove=document.createElement('button');remove.type='button';remove.className='preview-delete-thread';remove.dataset.deleteThread=thread.id;remove.textContent='삭제';remove.title='대화 삭제';remove.setAttribute('aria-label',button.textContent+' 대화 삭제');remove.onclick=()=>previewDeleteThread(thread.id);
    const more=document.createElement('button');more.type='button';more.className='preview-thread-more';more.textContent='⋯';more.title='대화 메뉴';more.setAttribute('aria-label',button.textContent+' 대화 메뉴');more.setAttribute('aria-haspopup','menu');more.setAttribute('aria-expanded','false');
    const menu=document.createElement('div');menu.className='preview-thread-menu';menu.id='thread-menu-'+thread.id;menu.hidden=true;menu.setAttribute('role','menu');menu.setAttribute('aria-label','대화 메뉴');more.setAttribute('aria-controls',menu.id);remove.setAttribute('role','menuitem');
    const pin=document.createElement('button');pin.type='button';pin.className='preview-thread-action';pin.setAttribute('role','menuitem');pin.textContent=thread.pinned?'고정 해제':'대화 고정';pin.title=thread.pinned?'목록 상단에서 고정 해제':'대화 목록 상단에 고정';pin.onclick=()=>{previewRemember();thread.pinned=!thread.pinned;previewRenderHistory();previewRemember();previewToast(thread.pinned?'대화를 목록 상단에 고정했어요.':'대화 고정을 해제했어요.');};
    const group=document.createElement('button');group.type='button';group.className='preview-thread-action';group.setAttribute('role','menuitem');group.textContent='묶음으로 이동';group.onclick=()=>previewGroupThread(thread.id);
    const rename=document.createElement('button');rename.type='button';rename.className='preview-thread-action';rename.setAttribute('role','menuitem');rename.textContent='제목 변경';rename.onclick=()=>previewRenameThread(thread.id);
    menu.append(rename,pin,group,remove);
    previewBindHistoryMenu(more,menu);
    row.append(button,more);const section=sectionFor(thread);(section.querySelector('.chat-group-content')||section).append(row);document.body.append(menu);
  }
  if(sections.has('pinned'))history.append(sections.get('pinned'));
  for(const name of new Set(activeThreads.map(t=>t.group).filter(Boolean)))sectionFor({group:name,pinned:false});
  for(const [key,section]of sections)if(key.startsWith('group:'))history.append(section);
  if(sections.has('other'))history.append(sections.get('other'));
  else history.append(sectionFor({}));
  previewRenderChatManagement();
  previewRenderDeletedChats();
  previewRenderHomeChats();
  previewFilterHistory();
}
let previewManagedQuery='';const previewManagedSelection=new Set();
function previewRenderChatManagement(){
  const node=(tag,text,cls)=>{const element=document.createElement(tag);if(text!=null)element.textContent=text;if(cls)element.className=cls;return element;};
  let card=document.getElementById('chatManagementSettings');
  if(!card){
    card=node('section',null,'card chat-management-settings');card.id='chatManagementSettings';card.setAttribute('aria-labelledby','chatManagementTitle');
    const heading=node('h3','대화 관리');heading.id='chatManagementTitle';const description=node('p','선택한 대화를 휴지통으로 이동합니다. 삭제한 대화에서 다시 복원할 수 있어요.','muted small');
    const header=node('div',null,'chat-management-heading'),remove=node('button','선택한 대화 휴지통으로 이동','chat-management-remove');remove.id='trashSelectedChats';remove.type='button';remove.onclick=()=>previewDeleteThreads([...previewManagedSelection]);header.append(heading,remove);
    const search=node('input');search.id='settingsChatSearch';search.type='search';search.placeholder='제목으로 대화 검색';search.setAttribute('aria-label','관리할 대화 검색');search.oninput=()=>{previewManagedQuery=search.value;previewRenderChatManagement();};
    const toolbar=node('div',null,'chat-management-toolbar'),label=node('label'),all=node('input'),allText=node('span','전체 선택'),count=node('span',null,'chat-management-count');all.id='selectAllSettingsChats';all.type='checkbox';allText.id='settingsChatSelectLabel';label.append(all,allText);count.id='settingsChatSelectionCount';count.setAttribute('role','status');toolbar.append(label,count);
    const list=node('div',null,'chat-management-list');list.id='settingsChatList';list.setAttribute('aria-label','휴지통으로 이동할 대화');card.append(header,description,search,toolbar,list);
    const deleted=document.getElementById('deletedChatSettings');if(deleted)deleted.before(card);else document.getElementById('settings').append(card);
  }
  const active=previewThreads.filter(t=>!t.deletedAt),ids=new Set(active.map(t=>t.id));for(const id of previewManagedSelection)if(!ids.has(id))previewManagedSelection.delete(id);
  const query=previewManagedQuery.trim().toLocaleLowerCase('ko-KR'),visible=[...active].reverse().filter(t=>!query||(t.title||'새 대화').toLocaleLowerCase('ko-KR').includes(query));
  const all=document.getElementById('selectAllSettingsChats'),list=document.getElementById('settingsChatList'),scroll=list.scrollTop||0;list.replaceChildren();document.getElementById('settingsChatSearch').value=previewManagedQuery;
  document.getElementById('settingsChatSelectLabel').textContent=query?'검색 결과 전체 선택':'전체 선택';
  const refreshSelection=()=>{const selected=visible.filter(t=>previewManagedSelection.has(t.id)).length;all.checked=visible.length>0&&selected===visible.length;all.indeterminate=selected>0&&selected<visible.length;all.disabled=!visible.length;document.getElementById('settingsChatSelectionCount').textContent='선택 '+previewManagedSelection.size+'개 · 전체 '+active.length+'개';document.getElementById('trashSelectedChats').disabled=!previewManagedSelection.size;};
  const inputs=[];
  for(const thread of visible){
    const row=node('label',null,'chat-management-row'),input=node('input'),title=node('span',thread.title||'새 대화','chat-management-title');input.type='checkbox';input.checked=previewManagedSelection.has(thread.id);input.dataset.selectThread=thread.id;input.setAttribute('aria-label',(thread.title||'새 대화')+' 대화 선택');
    input.onchange=()=>{if(input.checked)previewManagedSelection.add(thread.id);else previewManagedSelection.delete(thread.id);refreshSelection();};inputs.push(input);row.append(input,title);list.append(row);
  }
  if(!visible.length)list.append(node('p',active.length?'검색 결과가 없습니다.':'관리할 대화가 없습니다.','muted small'));
  all.onchange=()=>{for(const thread of visible){if(all.checked)previewManagedSelection.add(thread.id);else previewManagedSelection.delete(thread.id);}for(const input of inputs)input.checked=previewManagedSelection.has(input.dataset.selectThread);refreshSelection();};refreshSelection();list.scrollTop=scroll;
}
function previewDeleteThreads(ids){
  const wanted=new Set(ids),targets=previewThreads.filter(t=>!t.deletedAt&&wanted.has(t.id));if(!targets.length)return;
  previewRemember();const at=Date.now(),deletedIds=targets.map(t=>t.id);for(const thread of targets)thread.deletedAt=at;
  for(const id of deletedIds){previewManagedSelection.delete(id);document.dispatchEvent(new CustomEvent('plant:thread-deleted',{detail:{id}}));}
  if(deletedIds.includes(previewActiveId)){const next=[...previewThreads].reverse().find(t=>!t.deletedAt);previewActiveId=next?.id||null;document.getElementById('chatInput').value=next?.draft||'';previewRenderMessages();}else previewRenderHistory();
  previewRemember();previewToast('대화 '+targets.length+'개를 휴지통으로 이동했어요.',{label:'복원',run:()=>previewRestoreThreads(deletedIds)});
}
function previewRestoreThreads(ids){
  const wanted=new Set(ids),targets=previewThreads.filter(t=>t.deletedAt&&wanted.has(t.id));if(!targets.length)return;
  previewRemember();for(const thread of targets)delete thread.deletedAt;previewRenderHistory();previewRemember();previewToast('대화 '+targets.length+'개를 복원했어요.');
}
function previewRenderDeletedChats(){
  let card=document.getElementById('deletedChatSettings');
  if(!card){card=document.createElement('section');card.id='deletedChatSettings';card.className='card deleted-chat-settings';card.setAttribute('aria-labelledby','deletedChatTitle');const heading=document.createElement('h3');heading.id='deletedChatTitle';heading.textContent='삭제한 대화';const note=document.createElement('p');note.className='muted small';note.textContent='삭제한 대화를 복원하거나 완전히 삭제할 수 있어요.';const header=document.createElement('div');header.className='deleted-chat-heading';const clear=document.createElement('button');clear.id='purgeDeletedChats';clear.type='button';clear.className='preview-permanent-delete';clear.textContent='전체 삭제';clear.setAttribute('aria-label','삭제한 대화 전체 완전 삭제');clear.onclick=()=>previewConfirmPurgeThread();header.append(heading,clear);const list=document.createElement('div');list.id='deletedChatList';card.append(header,note,list);document.getElementById('settings').append(card);}
  const list=document.getElementById('deletedChatList'),deleted=previewThreads.filter(t=>t.deletedAt).sort((a,b)=>b.deletedAt-a.deletedAt);list.replaceChildren();
  document.getElementById('purgeDeletedChats').disabled=!deleted.length;
  if(!deleted.length){const empty=document.createElement('p');empty.className='muted small';empty.textContent='삭제한 대화가 없습니다.';list.append(empty);return;}
  for(const thread of deleted){const row=document.createElement('div');row.className='preview-deleted-row';const title=document.createElement('span');title.textContent=thread.title||'새 대화';title.title=title.textContent;const restore=document.createElement('button');restore.type='button';restore.textContent='복원';restore.dataset.restoreThread=thread.id;restore.setAttribute('aria-label',title.textContent+' 대화 복원');restore.onclick=()=>previewRestoreThread(thread.id);const purge=document.createElement('button');purge.type='button';purge.textContent='완전 삭제';purge.className='preview-permanent-delete';purge.dataset.purgeThread=thread.id;purge.setAttribute('aria-label',title.textContent+' 대화 완전 삭제');purge.onclick=()=>previewConfirmPurgeThread(thread.id);row.append(title,restore,purge);list.append(row);}
}
async function previewPermanentlyDeleteThreads(ids){
  if(!ids.length||ids.some(id=>!previewThreads.some(t=>t.id===id&&t.deletedAt)))throw Error('삭제한 대화만 완전히 삭제할 수 있습니다.');
  previewThreads=previewThreads.filter(t=>!ids.includes(t.id));previewRenderHistory();previewRemember();
}
async function previewPermanentlyDeleteThread(id){
  if(!previewThreads.some(t=>t.id===id&&t.deletedAt))throw Error('삭제한 대화만 완전히 삭제할 수 있습니다.');
  previewThreads=previewThreads.filter(t=>t.id!==id);previewRenderHistory();previewRemember();
}
function previewConfirmPurgeThread(id){
  const targets=previewThreads.filter(t=>t.deletedAt&&(id===undefined||t.id===id));if(!targets.length)return;
  const bulk=id===undefined,ids=targets.map(t=>t.id);
  document.getElementById('chatPurgeDialog')?.remove();
  const dialog=document.createElement('dialog');dialog.id='chatPurgeDialog';dialog.className='chat-organize-dialog chat-purge-dialog';dialog.setAttribute('aria-labelledby','chatPurgeTitle');dialog.setAttribute('aria-describedby','chatPurgeWarning');
  const heading=document.createElement('h2');heading.id='chatPurgeTitle';heading.textContent=bulk?'삭제한 대화를 모두 지울까요?':'대화를 완전히 삭제할까요?';
  const title=document.createElement('p');title.className='chat-purge-thread-title';title.textContent=bulk?'삭제한 대화 '+targets.length+'개':targets[0].title||'새 대화';
  const warning=document.createElement('p');warning.id='chatPurgeWarning';warning.textContent=bulk?'현재 삭제한 대화 '+targets.length+'개와 해당 메시지를 완전히 삭제합니다. 삭제 후에는 복원할 수 없습니다.':'이 대화와 메시지를 완전히 삭제합니다. 삭제 후에는 복원할 수 없습니다.';
  const note=document.createElement('p');note.textContent='사용 중인 대화, 별도로 저장한 개인 기록과 내보낸 백업 파일은 유지됩니다.';
  const error=document.createElement('p');error.className='chat-purge-error';error.setAttribute('role','alert');error.hidden=true;
  const actions=document.createElement('div');actions.className='chat-organize-actions';
  const cancel=document.createElement('button');cancel.type='button';cancel.textContent='취소';cancel.autofocus=true;cancel.onclick=()=>dialog.close();
  const remove=document.createElement('button');remove.type='button';remove.className='preview-permanent-delete';remove.textContent='완전 삭제';
  let busy=false;dialog.addEventListener('cancel',event=>{if(busy)event.preventDefault();});
  remove.onclick=async()=>{if(busy)return;busy=true;cancel.disabled=remove.disabled=true;remove.textContent='삭제 중…';error.hidden=true;try{if(bulk)await previewPermanentlyDeleteThreads(ids);else await previewPermanentlyDeleteThread(id);dialog.close();previewToast(bulk?'삭제한 대화 '+targets.length+'개를 모두 삭제했어요.':'대화를 완전히 삭제했어요.');}catch(e){error.textContent=e.message||'삭제하지 못했습니다. 다시 시도해 주세요.';error.hidden=false;}finally{busy=false;cancel.disabled=remove.disabled=false;remove.textContent='완전 삭제';}};
  actions.append(cancel,remove);dialog.append(heading,title,warning,note,error,actions);document.body.append(dialog);
  dialog.addEventListener('close',()=>{dialog.remove();(bulk?document.getElementById('purgeDeletedChats'):(document.querySelector('[data-purge-thread="'+id+'"]')||document.getElementById('purgeDeletedChats')))?.focus();},{once:true});dialog.showModal();cancel.focus();
}
function previewGroupThread(id){
  previewCloseThreadMenus();const thread=previewThreads.find(t=>t.id===id&&!t.deletedAt);if(!thread)return;
  document.getElementById('chatGroupDialog')?.remove();
  const dialog=document.createElement('dialog');dialog.id='chatGroupDialog';dialog.className='chat-organize-dialog';dialog.setAttribute('aria-labelledby','chatGroupTitle');
  const heading=document.createElement('h2');heading.id='chatGroupTitle';heading.textContent='대화 묶음';
  const form=document.createElement('form'),label=document.createElement('label'),input=document.createElement('input'),list=document.createElement('datalist');
  label.textContent='묶음 이름';input.value=thread.group||'';input.maxLength=60;input.placeholder='예: 프로젝트, 일상';input.setAttribute('list','chatGroupNames');list.id='chatGroupNames';
  for(const name of new Set(previewThreads.filter(t=>!t.deletedAt).map(t=>t.group).filter(Boolean))){const option=document.createElement('option');option.value=name;list.append(option);}
  label.append(input);const help=document.createElement('p');help.textContent='기존 묶음을 선택하거나 새 이름을 입력하세요. 비워 두면 최근 대화로 이동합니다.';
  const actions=document.createElement('div');actions.className='chat-organize-actions';const cancel=document.createElement('button');cancel.type='button';cancel.textContent='취소';cancel.onclick=()=>dialog.close();const save=document.createElement('button');save.type='submit';save.textContent='이동';actions.append(cancel,save);
  form.append(label,list,help,actions);dialog.append(heading,form);document.body.append(dialog);dialog.addEventListener('close',()=>{dialog.remove();document.querySelector('.preview-thread-row[data-thread-id="'+id+'"] .preview-thread-more')?.focus();},{once:true});
  form.onsubmit=event=>{event.preventDefault();previewRemember();thread.group=input.value.trim();previewRenderHistory();previewRemember();dialog.close();previewToast(thread.group?'대화를 '+thread.group+' 묶음으로 옮겼어요.':'최근 대화로 옮겼어요.');};dialog.showModal();input.focus();
}
function previewDeleteThread(id){
  const thread=previewThreads.find(t=>t.id===id&&!t.deletedAt);if(!thread)return;
  previewRemember();thread.deletedAt=Date.now();
  document.dispatchEvent(new CustomEvent('plant:thread-deleted',{detail:{id}}));
  if(previewActiveId===id){
    const next=[...previewThreads].reverse().find(t=>!t.deletedAt);
    if(next){previewActiveId=next.id;document.getElementById('chatInput').value=next.draft||'';previewRenderMessages();}else newChat();
  }else previewRenderHistory();
  previewRemember();previewToast('대화를 삭제했어요.',{label:'복원',run:()=>previewRestoreThread(id)});
}
function previewRestoreThread(id){
  const thread=previewThreads.find(t=>t.id===id&&t.deletedAt);if(!thread)return;
  previewRemember();delete thread.deletedAt;previewRenderHistory();previewRemember();previewToast('대화를 복원했어요.',{label:'대화로 이동',run:()=>{
    if(chatSettingsDialog.open){chatSettingsDialog.addEventListener('close',()=>previewOpenThread(id),{once:true});closeChatSettings();}
    else previewOpenThread(id);
  }});
}
function previewRenderMessages(){
  const log=document.getElementById('conversation');log.replaceChildren();
  const thread=previewThread();
  if(!thread?.messages?.length){log.innerHTML='<div class="preview-chat-welcome"><div class="iconbox">♧</div><span class="tag">화면 미리보기 · 연결 전</span><h2>이야기가 시작되는 자리</h2><p>생각이나 질문을 자유롭게 적어보세요.<br>지금은 입력과 대화 화면의 모습만 확인할 수 있어요.</p></div>';}
  else for(const message of thread.messages){const el=document.createElement('div');el.className='preview-message '+(message.kind==='user'?'user':'notice');el.textContent=message.text;log.appendChild(el);}
  document.getElementById('chatInput').value=thread?.draft||'';updateChatInput();previewRenderHistory();
}
function previewOpenThread(id){const thread=previewThreads.find(t=>t.id===id&&!t.deletedAt);if(!thread)return;previewRemember();previewActiveId=id;document.getElementById('chatInput').value=thread.draft||'';previewRenderMessages();go('chat');previewRemember();document.getElementById('chatInput').focus();}
function newChat(){
  previewCloseHistorySearch();
  previewRemember();const thread={id:crypto.randomUUID(),title:'새 대화',draft:'',messages:[],createdAt:new Date().toISOString()};previewThreads.push(thread);previewActiveId=thread.id;
  document.getElementById('chatInput').value='';previewRenderMessages();go('chat');previewRemember();document.getElementById('chatInput').focus();
}
function updateDemoControls(){document.getElementById('chatSend').disabled=!document.getElementById('chatInput').value.trim();}
function sendChat(){
  const input=document.getElementById('chatInput'),text=input.value.trim();if(!text)return;
  if(!previewThread()){const thread={id:crypto.randomUUID(),title:'새 대화',draft:input.value,messages:[]};previewThreads.push(thread);previewActiveId=thread.id;}
  const thread=previewThread();thread.draft=input.value;
  if(thread.messages.at(-2)?.text!==text){thread.messages.push({kind:'user',text},{kind:'notice',text:previewNotice});if(!thread.titleEdited)thread.title=text.slice(0,28);}
  previewRenderMessages();previewRemember();input.focus();
}
function startChatFromHome(){const text=document.getElementById('homeSearch').value;newChat();if(text.trim()){document.getElementById('chatInput').value=text;updateChatInput();sendChat();}else document.getElementById('chatInput').focus();previewRemember();}
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
const originalGo=go;go=function(id){originalGo(id);if(document.querySelector('.page.active')?.id===id){history.replaceState(null,'','#'+id);if(id==='home')previewRenderHomeChats();previewRemember();}};
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
