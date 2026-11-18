'use strict';
// Connected mode: server-backed persistence and versioned, app-owned backups.
(()=>{
 const samples=window.PlantArchiveSamples,view=window.PlantArchiveView;
 const node=(tag,text,cls)=>{const e=document.createElement(tag);if(text!=null)e.textContent=text;if(cls)e.className=cls;return e;};
 const button=(text,action)=>{const b=node('button',text);b.type='button';b.addEventListener('click',()=>Promise.resolve().then(action).catch(showError));return b;};
 const status=node('p','저장소 연결 중…','transfer-status');status.setAttribute('role','status');
 const card=node('section',null,'card transfer-settings');card.append(node('h3','데이터 관리'),node('p','이 앱의 JSON 파일로 백업하고 복원할 수 있어요. Markdown은 읽기용입니다.'),status);
 document.getElementById('settings').append(card);
 let token,revision=0,personalRecords=[],ready=false,dirty=false,timer,queue=Promise.resolve(),saveFailure=null,collection='samples',locked=false,persistedThreads='';
 const modeKey='plant-thought-test-mode-v1';let testEnabled=false;
 try{testEnabled=localStorage.getItem(modeKey)==='on';}catch{}
 window.PlantTestMode=Object.freeze({get enabled(){return testEnabled;}});
 document.body.dataset.testMode=testEnabled?'on':'off';
 const testCard=node('section',null,'card test-mode-settings'),testTitle=node('h3','테스트 기능');
 const testRow=node('div',null,'setting'),testText=node('div'),testLabel=node('label','테스트 모드 켜기');testLabel.htmlFor='testModeToggle';
 const testDescription=node('p','가상 원문 199개와 질문·답변 예시, Memory Lab을 사용할 수 있어요.','muted small');testDescription.id='testModeDescription';
 testText.append(testLabel,testDescription);
 const testToggle=node('input');testToggle.type='checkbox';testToggle.id='testModeToggle';testToggle.className='test-mode-switch';testToggle.setAttribute('role','switch');testToggle.setAttribute('aria-describedby','testModeDescription');testToggle.checked=testEnabled;testToggle.disabled=true;
 const modeStatus=node('p',null,'test-mode-status');modeStatus.setAttribute('role','status');
 testRow.append(testText,testToggle);testCard.append(testTitle,testRow,modeStatus);document.querySelector('#settings > .card').before(testCard);
 for(const e of [document.querySelector('#nav .nav-lab-mark')?.closest('button'),document.querySelector('#mobileSelect option[value="memorylab"]')])if(e)e.dataset.testOnly='';
 function syncMode(){
  document.body.dataset.testMode=testEnabled?'on':'off';testToggle.checked=testEnabled;
  modeStatus.textContent=testEnabled?'테스트 모드 켜짐 · 가상 예시로 기능을 확인할 수 있어요.':'일반 모드 · 개인 자료함의 기록으로 대화합니다.';
  modeStatus.classList.toggle('is-enabled',testEnabled);
  const option=document.querySelector('#mobileSelect option[value="memorylab"]');if(option){option.hidden=!testEnabled;option.disabled=!testEnabled;}
  document.dispatchEvent(new CustomEvent('plant:test-mode-changed',{detail:{enabled:testEnabled}}));
 }
 testToggle.addEventListener('change',()=>{
  try{
   available();
   if(previewThreads.some(t=>!t.deletedAt&&t.messages.some(m=>m.kind==='assistant'&&m.status==='pending'&&!m.archived)))throw Error('진행 중인 AI 응답을 받은 뒤 모드를 바꿔 주세요.');
   testEnabled=testToggle.checked;syncMode();switchCollection(testEnabled?'samples':'personal');
   try{localStorage.setItem(modeKey,testEnabled?'on':'off');}catch{previewToast('모드는 바뀌었지만 이 브라우저에 설정을 보관하지 못했어요.');return;}
   previewToast(testEnabled?'테스트 모드를 켰어요.':'테스트 모드를 껐어요. 개인 자료함으로 돌아왔습니다.');
  }catch(error){testToggle.checked=testEnabled;showError(error);}
 });
 syncMode();
 const dialog=node('dialog',null,'transfer-dialog');dialog.setAttribute('aria-label','자료 내보내기와 불러오기');document.body.append(dialog);
 const picker=node('input');picker.type='file';picker.accept='.json,application/json';picker.hidden=true;document.body.append(picker);
 const collectionSelect=node('select');collectionSelect.setAttribute('aria-label','자료함 선택');for(const [value,label]of [['samples','가상 예시 자료함'],['personal','개인 자료함']]){const o=node('option',label);o.value=value;collectionSelect.append(o);}
 const summary=node('span',null,'transfer-collection-summary');
 const collectionBar=node('div',null,'transfer-collection');collectionBar.append(node('span','테스트 모드','test-mode-badge'),node('label','자료함 '),collectionSelect,summary);document.querySelector('body>header').after(collectionBar);
 function showError(error){status.textContent=error.message||'자료 처리에 실패했습니다.';status.classList.add('is-error');previewToast(status.textContent);}
 function available(){if(!ready)throw Error('저장소 연결을 확인한 뒤 다시 시도해 주세요.');if(locked)throw Error('불러오기를 마친 뒤 다시 시도해 주세요.');}
 function lock(value){locked=value;for(const e of document.querySelectorAll('.page,.transfer-collection'))e.inert=value;}
 const send=sendChat;sendChat=function(){if(!ready||locked){previewToast('저장소 연결 또는 자료 처리가 끝나면 질문을 보낼 수 있어요.');return;}send();};
 async function api(route,body){const response=await fetch('/api/library/'+route,{method:'POST',headers:{'Content-Type':'application/json','X-Library-Token':token},body:JSON.stringify(body)});const data=await response.json();if(!response.ok)throw Error(data.error||'자료를 처리하지 못했습니다.');return data;}
 function setStatus(text){status.textContent=text;status.classList.remove('is-error');}
 function threadSnapshot(){previewSnapshot();return JSON.parse(JSON.stringify(previewThreads));}
 function persist(){
  clearTimeout(timer);if(!ready||locked)return queue;
  queue=queue.catch(()=>{}).then(async()=>{
   if(saveFailure)throw saveFailure;if(!dirty)return;
   const threads=threadSnapshot(),serialized=JSON.stringify(threads);dirty=false;if(serialized===persistedThreads)return;setStatus('대화 저장 중…');
   try{const data=await api('save',{revision,threads});revision=data.revision;persistedThreads=serialized;setStatus('이 기기에 저장됨 · '+data.threads.length+'개 대화 · '+data.records.length+'개 기록');}
   catch(error){dirty=true;saveFailure=error;showError(error);throw error;}
  });queue.catch(()=>{});return queue;
 }
 const remember=previewRemember;
 previewRemember=function(){remember();if(ready&&!locked){dirty=JSON.stringify(previewThreads)!==persistedThreads;if(dirty){clearTimeout(timer);timer=setTimeout(()=>persist(),450);}}};
 async function flush(){available();await persist();if(saveFailure)throw saveFailure;while(dirty)await persist();}
 window.PlantLibraryPersistence=Object.freeze({flush});
 function personalCollection(){return {version:1,dataset:'personal-library',synthetic:false,default_profile:'personal',title:'개인 자료함',profiles:[{id:'personal',label:'개인 자료함',record_count:personalRecords.length,question_count:0}],records:personalRecords.map(r=>({...r,profile:'personal',imported_at:null})),examples:[],record_count:personalRecords.length,question_count:0,provenance:{files:{}}};}
 function switchCollection(next){
  next=next==='samples'&&testEnabled?'samples':'personal';
  collection=next;collectionSelect.value=next;document.body.dataset.libraryCollection=next;
  view.setCollection(next==='personal'?personalCollection():samples);
  summary.textContent=next==='personal'?'원문 '+personalRecords.length+'개 · AI 검색 '+personalRecords.filter(r=>r.search_enabled).length+'개':'가상 예시 '+samples.record_count+'개';
  document.querySelector('#archive .lead').textContent=next==='personal'?'불러오거나 작성한 개인 기록을 날짜별로 살펴보세요.':'가상 기록을 달력과 목록으로 살펴보세요.';
  const calendarNote=document.querySelector('#archiveCalendar p.notice');if(calendarNote)calendarNote.textContent='● 현재 자료함의 기록일을 표시합니다. 사건 날짜는 본문에서 확인하세요.';
  previewRenderMessages();try{sessionStorage.setItem('plant-thought-library-collection',next);}catch{}
 }
 collectionSelect.addEventListener('change',()=>{if(locked){collectionSelect.value=collection;return;}switchCollection(collectionSelect.value);});
 function modal(title){if(dialog.open)dialog.close();dialog.replaceChildren();const head=node('div',null,'transfer-heading');head.append(node('h2',title),button('닫기',()=>dialog.close()));dialog.append(head);dialog.showModal();return dialog;}
 function check(label,checked=true){const wrap=node('label',null,'transfer-check'),input=node('input');input.type='checkbox';input.checked=checked;wrap.append(input,node('span',label));return {wrap,input};}
 function selectRows(parent,rows,selectedIds){const list=node('div',null,'transfer-items'),checks=[];for(const row of rows){const c=check(row.title||'제목 없음',!selectedIds||selectedIds.includes(row.id));c.input.dataset.id=row.id;list.append(c.wrap);checks.push(c.input);}parent.append(list);const actions=node('div',null,'transfer-actions');actions.append(button('모두 선택',()=>checks.forEach(c=>c.checked=true)),button('선택 해제',()=>checks.forEach(c=>c.checked=false)));parent.append(actions);return ()=>checks.filter(c=>c.checked).map(c=>c.dataset.id);}
 function download(text,name,type){const url=URL.createObjectURL(new Blob([text],{type})),a=node('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}
 async function exportDialog(kind='full',selectedIds){
  available();const d=modal(kind==='chat'?'대화 내보내기':kind==='archive'?'서재 보관소 내보내기':'전체 백업');
  d.append(node('p',kind==='full'?'대화와 개인 자료함을 함께 백업합니다.':kind==='archive'?(collection==='samples'?'현재 가상 예시 자료함을 내보냅니다.':'현재 개인 자료함을 내보냅니다.'):'내보낼 대화를 선택하세요.'));
  const deleted=check('삭제한 대화 포함',false),drafts=check('작성 중인 초안 포함',true);let threadIds,recordIds;
  if(kind!=='archive'){
   const host=node('div');d.append(deleted.wrap,drafts.wrap,host);
   const render=()=>{host.replaceChildren();threadIds=selectRows(host,previewThreads.filter(t=>deleted.input.checked||!t.deletedAt),selectedIds);};deleted.input.addEventListener('change',render);render();
  }
  if(kind==='archive')recordIds=selectRows(d,window.PlantArchiveSamples.records,selectedIds);
  const output=node('select');output.setAttribute('aria-label','내보내기 형식');for(const [value,label]of [['json','JSON · 복원용 백업'],['md','Markdown · 읽기용']]){const o=node('option',label);o.value=value;output.append(o);}d.append(output);
  const submit=button('파일로 내보내기',async()=>{
   submit.disabled=true;try{await flush();const tids=threadIds?.(),rids=recordIds?.();if(kind==='chat'&&!tids.length||kind==='archive'&&!rids.length)throw Error('내보낼 자료를 하나 이상 선택해 주세요.');
    const result=await api('export',{kind,threadIds:tids,recordIds:rids,collection:kind==='full'?'personal':collection,includeDeleted:deleted.input.checked,includeDrafts:drafts.input.checked,markdown:output.value==='md'});
    const stamp=new Date().toISOString().replace(/[:.]/g,'-');download(output.value==='md'?result.markdown:JSON.stringify(result.backup),'plant-thought-'+kind+'-'+stamp+'.'+output.value,output.value==='md'?'text/markdown;charset=utf-8':'application/json');dialog.close();previewToast('선택한 자료를 파일로 내보냈어요.');
   }finally{submit.disabled=false;}
  });d.append(submit);
 }
 function importFile(){available();picker.value='';picker.click();}
 picker.addEventListener('change',async()=>{
  const file=picker.files[0];if(!file)return;
  try{
   await flush();if(previewThreads.some(t=>t.messages.some(m=>m.kind==='assistant'&&m.status==='pending'&&!m.archived)))throw Error('AI 응답을 받은 뒤 불러오기를 시작해 주세요.');
   if(file.size>20*1024*1024)throw Error('20MB 이하의 JSON 파일을 선택해 주세요.');let backup;try{backup=JSON.parse(await file.text());}catch{throw Error('JSON 파일을 읽을 수 없습니다. 이 앱의 백업 파일을 선택해 주세요.');}
   const inspected=await api('inspect',{backup});const d=modal('불러오기 미리보기');d.append(node('p',file.name));
   for(const [kind,label]of [['threads','대화'],['records','보관소 기록']]){const plan=inspected.plan[kind];d.append(node('h3',label+' · 추가 '+plan.add.length+' · 중복 '+plan.duplicate.length+' · 충돌 '+plan.conflict.length));if(plan.conflict.length)d.append(node('p','충돌 자료: '+plan.conflict.map(r=>r.title).join(', ')));}
   const conflict=node('select');conflict.setAttribute('aria-label','충돌 처리');for(const [value,label]of [['keep','충돌 시 기존 자료 유지'],['copy','충돌 자료를 별도 사본으로 추가']]){const o=node('option',label);o.value=value;conflict.append(o);}d.append(conflict);
   const search=check('새로 불러온 보관소 기록을 AI 검색에 포함',false);d.append(search.wrap,node('p','대화만 불러와도 보관소 기록으로 바뀌지 않습니다. 중단된 AI 요청은 재실행하지 않습니다.'));
   const submit=button('확인한 자료 불러오기',async()=>{
    submit.disabled=true;try{await flush();if(revision!==inspected.revision)throw Error('미리보기 이후 대화가 변경되었습니다. 파일을 다시 선택해 주세요.');lock(true);
     const result=await api('import',{revision,backup,options:{conflicts:conflict.value,searchEnabled:search.input.checked}});revision=result.revision;personalRecords=result.records;previewThreads=result.threads;
     if(!previewThread()){previewActiveId=previewThreads.find(t=>!t.deletedAt)?.id||null;}dirty=false;persistedThreads=JSON.stringify(previewThreads);
     // Do not let the old input overwrite a restored draft during snapshotting.
     document.getElementById('chatInput').value=previewThread()?.draft||'';
     switchCollection(result.counts.records?'personal':collection);previewRenderMessages();remember();dialog.close();
     setStatus('불러옴 · 대화 '+result.counts.threads+'개 · 기록 '+result.counts.records+'개 · 건너뜀 '+result.counts.skipped+'개');previewToast(status.textContent);
    }finally{lock(false);submit.disabled=false;}
   });d.append(submit);
  }catch(error){showError(error);}
 });
 const actions=node('div',null,'transfer-actions');actions.append(button('전체 백업',()=>exportDialog()),button('백업 불러오기',importFile),button('개인 기록 검색 설정',async()=>{await flush();const d=modal('AI 검색에 포함할 개인 기록');const ids=selectRows(d,personalRecords,personalRecords.filter(r=>r.search_enabled).map(r=>r.id));d.append(button('검색 설정 저장',async()=>{await flush();const data=await api('search-settings',{revision,recordIds:ids()});revision=data.revision;personalRecords=data.records;switchCollection(collection);dialog.close();setStatus('개인 자료함의 검색 설정을 저장했어요.');}));}),button('저장 다시 시도',async()=>{saveFailure=null;await flush();}));card.append(actions);
 const chatActions=node('div',null,'transfer-actions');chatActions.append(button('대화 내보내기',()=>exportDialog('chat')),button('불러오기',importFile));document.getElementById('chatHistory').before(chatActions);
 const archiveActions=node('div',null,'transfer-actions');archiveActions.append(button('내보내기',()=>exportDialog('archive')),button('이 기록 내보내기',()=>{const id=view.selectedId();if(!id)throw Error('내보낼 기록을 선택해 주세요.');return exportDialog('archive',[id]);}),button('불러오기',importFile));document.querySelector('#archive .archive-toolbar').append(archiveActions);
 const history=previewRenderHistory;
 previewRenderHistory=function(){history();for(const menu of document.querySelectorAll('.preview-thread-menu')){const threadId=menu.id.slice('thread-menu-'.length);const b=button('이 대화 내보내기',()=>{previewCloseThreadMenus();return exportDialog('chat',[threadId]);});b.className='transfer-thread-export';b.setAttribute('role','menuitem');menu.prepend(b);menu.addEventListener('keydown',event=>{const items=[...menu.querySelectorAll('button')];const index=items.indexOf(document.activeElement);let target;if(event.key==='ArrowDown')target=(index+1)%items.length;else if(event.key==='ArrowUp')target=(index+items.length-1)%items.length;else if(event.key==='Home')target=0;else if(event.key==='End')target=items.length-1;else return;event.preventDefault();event.stopPropagation();items[target].focus();},true);}};
 addRecord=async function(){
  try{await flush();const title=document.getElementById('recordTitle').value,body=document.getElementById('recordBody').value,date=document.getElementById('recordDate').value||null;if(!body.trim())throw Error('기록 내용을 입력해 주세요.');
   const result=await api('record',{revision,record:{title,body,date,search_enabled:true}});revision=result.revision;personalRecords=result.records;switchCollection('personal');document.getElementById('recordBody').value='';document.getElementById('recordTitle').value='';previewRemember();setStatus('개인 자료함에 기록을 저장했어요.');previewToast(status.textContent);
  }catch(error){showError(error);}
 };
 const note=document.querySelector('#emotion .notice');if(note)note.textContent='저장을 누르면 이 기기의 개인 자료함에 기록을 저장하고 AI 검색에 포함합니다.';
 const saveRecordButton=document.querySelector('#emotion button.primary');if(saveRecordButton)saveRecordButton.textContent='개인 자료함에 저장 ↗';
 document.addEventListener('plant:collection-changed',()=>{const select=document.getElementById('archiveProfile');select.disabled=collection==='personal';});
 // Keep the browser's close warning while a server write is still pending.
 window.addEventListener('beforeunload',event=>{if(dirty||saveFailure){event.preventDefault();event.returnValue='';}});
 async function initialize(){
  try{const response=await fetch('/api/library/state',{cache:'no-store'});if(!response.ok)throw Error('저장소에 연결하지 못했습니다.');const data=await response.json();token=data.token;revision=data.revision;personalRecords=data.records;
   const local=threadSnapshot().filter(t=>t.messages.length||t.draft.trim());previewThreads=data.threads;
   // Migrate only unknown sessions; differing saved copies remain available as separate conversations.
   const content=t=>JSON.stringify({draft:t.draft,messages:t.messages.map(m=>({kind:m.kind,text:m.text,status:m.status,answer:m.result?.answer,request:m.submission?.request_id}))});
   let migrated=false;for(const t of local){const old=previewThreads.find(s=>s.id===t.id);if(!old){previewThreads.push(t);migrated=true;}else if(content(old)!==content(t)){t.id=crypto.randomUUID();t.title+=' · 이전 탭 사본';for(const m of t.messages)if(m.kind==='assistant'){m.submission.thread_id=t.id;if(m.result)m.result.thread_id=t.id;}window.PlantConversationContext.rebind(t,t.id);previewThreads.push(t);migrated=true;}}
   for(const t of previewThreads)for(const m of t.messages)if(m.kind==='assistant'&&m.status==='pending'&&!m.archived){m.status='error';m.stage='connection';m.error='이전 처리 결과를 확인하지 못했습니다. 재시도할 수 있어요.';migrated=true;}
   if(!previewThread())previewActiveId=previewThreads.find(t=>!t.deletedAt)?.id||null;
   document.getElementById('chatInput').value=previewThread()?.draft||'';
   if(!previewThreads.length)newChat();
   ready=true;testToggle.disabled=false;let previous;try{previous=sessionStorage.getItem('plant-thought-library-collection');}catch{}switchCollection(testEnabled&&previous!=='personal'?'samples':'personal');
   dirty=true;await persist();setStatus('이 기기에 저장됨 · 대화 '+previewThreads.length+'개 · 개인 기록 '+personalRecords.length+'개');
  }catch(error){showError(error);}
 }
 switchCollection(testEnabled?'samples':'personal');
 const navigate=go;go=function(id){navigate(id==='memorylab'&&!testEnabled?'settings':id);};
 if(!testEnabled&&document.querySelector('.page.active')?.id==='memorylab')go('settings');
 previewRenderHistory();initialize();
})();
