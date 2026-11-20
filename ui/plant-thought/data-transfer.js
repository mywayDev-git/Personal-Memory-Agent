'use strict';
// Connected mode: server-backed persistence and versioned, app-owned backups.
(()=>{
 const samples=window.PlantArchiveSamples,view=window.PlantArchiveView;
 const node=(tag,text,cls)=>{const e=document.createElement(tag);if(text!=null)e.textContent=text;if(cls)e.className=cls;return e;};
 const button=(text,action)=>{const b=node('button',text);b.type='button';b.addEventListener('click',()=>Promise.resolve().then(action).catch(showError));return b;};
 const status=node('p','저장소 연결 중…','transfer-status');status.setAttribute('role','status');
 const card=node('section',null,'card transfer-settings');card.append(node('h3','데이터 관리'),node('p','이 앱의 JSON 파일로 백업하고 복원할 수 있어요. Markdown은 읽기용입니다.'),status);
 document.getElementById('settings').append(card);
 let initializing=null,storageEpoch=null,token,revision=0,personalRecords=[],ready=false,dirty=false,timer,queue=Promise.resolve(),saveFailure=null,collection='samples',locked=false,persistedThreads='';
 const modeKey='plant-thought-test-mode-v1';let testEnabled=false;
 try{testEnabled=localStorage.getItem(modeKey)==='on';}catch{}
 window.PlantTestMode=Object.freeze({get enabled(){return testEnabled;}});
 document.body.dataset.testMode=testEnabled?'on':'off';
 const testCard=node('section',null,'card test-mode-settings'),testTitle=node('h3','테스트 기능');
 const testRow=node('div',null,'setting'),testText=node('div'),testLabel=node('label','테스트 모드 켜기');testLabel.htmlFor='testModeToggle';
 const testDescription=node('p','가상 원문 199개와 질문·답변 예시, Memory Lab을 사용할 수 있어요. 상단에서 대화 버전과 기록 검색 방식을 선택할 수 있어요.','muted small');testDescription.id='testModeDescription';
 testText.append(testLabel,testDescription);
 const testToggle=node('input');testToggle.type='checkbox';testToggle.id='testModeToggle';testToggle.className='test-mode-switch';testToggle.setAttribute('role','switch');testToggle.setAttribute('aria-describedby','testModeDescription');testToggle.checked=testEnabled;testToggle.disabled=false;
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
 function applyTestMode(next,persistSetting=true){
  if(locked)throw Error('자료 처리가 끝난 뒤 모드를 바꿔 주세요.');
  const before=testEnabled,previousCollection=collection;
  try{testEnabled=next;switchCollection(next?'samples':'personal');syncMode();}
  catch(error){testEnabled=before;try{switchCollection(previousCollection);}catch{}syncMode();throw error;}
  if(persistSetting)try{localStorage.setItem(modeKey,next?'on':'off');}catch{previewToast('모드는 바뀌었지만 이 브라우저에 설정을 보관하지 못했어요.');}
 }
 testToggle.addEventListener('change',()=>{
  try{
   applyTestMode(testToggle.checked);
   const pending=previewThreads.some(t=>!t.deletedAt&&t.messages.some(m=>m.kind==='assistant'&&m.status==='pending'&&!m.archived));
   previewToast((testEnabled?'테스트 모드를 켰어요.':'테스트 모드를 껐어요. 개인 자료함으로 돌아왔습니다.')+(pending?' 진행 중인 답변은 기존 자료함으로 처리됩니다.':''));
   if(!ready)void initialize();
  }catch(error){testToggle.checked=testEnabled;showError(error);}
 });
 window.addEventListener('storage',event=>{if(event.key!==modeKey||!['on','off'].includes(event.newValue)||locked)return;try{applyTestMode(event.newValue==='on',false);}catch(error){showError(error);}});
 syncMode();
 const reconnect=button('저장소 다시 연결',async()=>{await initialize();});reconnect.hidden=true;card.append(reconnect);
 const dialog=node('dialog',null,'transfer-dialog');dialog.setAttribute('aria-label','자료 내보내기와 불러오기');document.body.append(dialog);
 const picker=node('input');picker.type='file';picker.accept='.json,application/json';picker.hidden=true;document.body.append(picker);
 const collectionSelect=node('select');collectionSelect.setAttribute('aria-label','자료함 선택');for(const [value,label]of [['samples','가상 예시 자료함'],['personal','개인 자료함']]){const o=node('option',label);o.value=value;collectionSelect.append(o);}
 const summary=node('span',null,'transfer-collection-summary');
 const collectionBar=node('div',null,'transfer-collection');collectionBar.append(node('span','테스트 모드','test-mode-badge'),node('label','자료함 '),collectionSelect,summary);document.querySelector('body>header').after(collectionBar);
 function showError(error){status.textContent=error.message||'자료 처리에 실패했습니다.';status.classList.add('is-error');previewToast(status.textContent);}
 function available(){if(!ready)throw Error('저장소 연결을 확인한 뒤 다시 시도해 주세요.');if(locked)throw Error('불러오기를 마친 뒤 다시 시도해 주세요.');}
 function lock(value){locked=value;for(const e of document.querySelectorAll('.page,.transfer-collection'))e.inert=value;}
 const send=sendChat;sendChat=function(){if(!ready||locked){previewToast('저장소 연결 또는 자료 처리가 끝나면 질문을 보낼 수 있어요.');return;}send();};
 async function api(route,body){const response=await fetch('/api/library/'+route,{method:'POST',headers:{'Content-Type':'application/json','X-Library-Token':token},body:JSON.stringify({...body,storage_epoch:storageEpoch})});const data=await response.json();if(!response.ok)throw Error(data.error||'자료를 처리하지 못했습니다.');return data;}
 function setStatus(text){status.textContent=text;status.classList.remove('is-error');}
 function threadSnapshot(){previewSnapshot();return JSON.parse(JSON.stringify(previewThreads));}
 function persist(){
  clearTimeout(timer);if(!ready||locked)return queue;
  queue=queue.catch(()=>{}).then(async()=>{
   if(locked)return;
   if(saveFailure)throw saveFailure;if(!dirty)return;
   const threads=threadSnapshot(),serialized=JSON.stringify(threads);dirty=false;if(serialized===persistedThreads)return;setStatus('대화 저장 중…');
   try{const data=await api('save',{revision,threads});revision=data.revision;persistedThreads=JSON.stringify(threads.filter(t=>!(data.purgedThreadIds||[]).includes(t.id)));applyPurgedThreads(data.purgedThreadIds);setStatus('이 기기에 저장됨 · '+data.threads.length+'개 대화 · '+data.records.length+'개 기록');}
   catch(error){dirty=true;saveFailure=error;showError(error);throw error;}
  });queue.catch(()=>{});return queue;
 }
 function applyPurgedThreads(ids=[]){
  if(!previewThreads.some(t=>ids.includes(t.id)))return;
  previewThreads=previewThreads.filter(t=>!ids.includes(t.id));
  if(!previewThread()){previewActiveId=previewThreads.find(t=>!t.deletedAt)?.id||null;document.getElementById('chatInput').value=previewThread()?.draft||'';}
  previewRenderMessages();remember();
 }
 const remember=previewRemember;
 previewRemember=function(){if(window.PlantDataResetting)return;remember();if(ready&&!locked){dirty=JSON.stringify(previewThreads)!==persistedThreads;if(dirty){clearTimeout(timer);timer=setTimeout(()=>persist(),450);}}};
 async function flush(){available();await persist();if(saveFailure)throw saveFailure;while(dirty)await persist();}
 async function refreshRecords(){const response=await fetch('/api/library/state',{cache:'no-store'});if(!response.ok)throw Error('기록 상태를 확인하지 못했습니다.');const data=await response.json();revision=data.revision;personalRecords=data.records;switchCollection(collection);}
 async function recordOperation(action){available();clearTimeout(timer);await flush();locked=true;try{return await action();}finally{try{await refreshRecords();}finally{locked=false;if(dirty)persist();}}}
 async function purgeDeletedThreads(ids){
  available();
  if(!ids.length||ids.some(id=>!previewThreads.some(t=>t.id===id&&t.deletedAt)))throw Error('삭제한 대화만 완전히 삭제할 수 있습니다.');
  // Do not save anything before purging trash. Finish only an already-sent request.
  locked=true;clearTimeout(timer);
  try{
   await queue.catch(()=>{});
   if(ids.some(id=>!previewThreads.some(t=>t.id===id&&t.deletedAt)))throw Error('대화 상태가 바뀌었습니다. 삭제할 대화를 다시 확인해 주세요.');
   const data=await api('thread-purge',{revision,threadIds:ids});revision=data.revision;
   const purged=data.purgedThreadIds||ids,baseline=persistedThreads?JSON.parse(persistedThreads):data.threads;
   applyPurgedThreads(purged);persistedThreads=JSON.stringify(baseline.filter(t=>!purged.includes(t.id)));
   dirty=JSON.stringify(threadSnapshot())!==persistedThreads;remember();setStatus('삭제한 대화를 완전히 삭제했어요. · 대화 '+data.threads.length+'개 · 개인 기록 '+data.records.length+'개');
  }finally{locked=false;}
 }
 previewPermanentlyDeleteThread=id=>purgeDeletedThreads([id]);
 previewPermanentlyDeleteThreads=ids=>purgeDeletedThreads(ids);
 function clearForReset(epoch,reload=true){
  window.PlantDataResetting=true;
  clearTimeout(timer);dirty=false;saveFailure=null;ready=false;lock(true);previewThreads=[];previewActiveId=null;personalRecords=[];
  for(const field of ['chatInput','homeSearch','recordTitle','recordDate','recordBody','archiveInput']){const input=document.getElementById(field);if(input)input.value='';}
  for(const name of ['sessionStorage','localStorage'])try{const storage=window[name];for(const key of Object.keys(storage))if(key.startsWith('plant-thought')||key.startsWith('memory-lab.'))storage.removeItem(key);}catch{}
  let tabMarked=false;storageEpoch=epoch;if(epoch){try{sessionStorage.setItem('plant-thought-storage-epoch',epoch);tabMarked=true;}catch{}try{localStorage.setItem('plant-thought-data-epoch',epoch);}catch{}}
  if(reload){window.history.replaceState(null,'','/'+(!tabMarked&&epoch?'?reset_state='+encodeURIComponent(epoch):'')+'#settings');location.reload();}
 }
 window.PlantLibraryPersistence=Object.freeze({get ready(){return ready&&!locked;},flush,recordOperation,epoch:()=>storageEpoch,async beginReset(){if(ready)await flush();lock(true);clearTimeout(timer);},endReset(){if(ready)lock(false);},clearForReset});
 window.addEventListener('storage',event=>{if(event.key==='plant-thought-data-epoch'&&event.newValue&&storageEpoch&&event.newValue!==storageEpoch)clearForReset(event.newValue,true);});
 document.addEventListener('plant:record-drafts-ready',()=>{window.PlantRecordDrafts?.reconcile?.(personalRecords);if(ready)previewRemember();});
 function personalCollection(){const active=personalRecords.filter(r=>!r.deleted_at);return {version:1,dataset:'personal-library',synthetic:false,default_profile:'personal',title:'개인 자료함',profiles:[{id:'personal',label:'개인 자료함',record_count:active.length,question_count:0}],records:active.map(r=>({...r,profile:'personal',imported_at:null})),examples:[],record_count:active.length,question_count:0,provenance:{files:{}}};}
 function switchCollection(next){
  next=next==='samples'&&testEnabled?'samples':'personal';
  collection=next;collectionSelect.value=next;document.body.dataset.libraryCollection=next;
  view.setCollection(next==='personal'?personalCollection():samples);
  if(next==='personal' && document.querySelector('.page.active')?.id==='archive')view.showPersonalRecords();
  summary.textContent=next==='personal'?'원문 '+personalRecords.filter(r=>!r.deleted_at).length+'개 · AI 검색 '+personalRecords.filter(r=>r.search_enabled&&!r.deleted_at).length+'개':'가상 예시 '+samples.record_count+'개';
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
 const actions=node('div',null,'transfer-actions');actions.append(button('전체 백업',()=>exportDialog()),button('불러오기',importFile),button('개인 기록 검색 설정',async()=>{await flush();const d=modal('AI 검색에 포함할 개인 기록');const ids=selectRows(d,personalRecords.filter(r=>!r.deleted_at),personalRecords.filter(r=>r.search_enabled&&!r.deleted_at).map(r=>r.id));d.append(button('검색 설정 저장',async()=>{await flush();const data=await api('search-settings',{revision,recordIds:ids()});revision=data.revision;personalRecords=data.records;switchCollection(collection);dialog.close();setStatus('개인 자료함의 검색 설정을 저장했어요.');}));}),button('저장 다시 시도',async()=>{if(!ready){await initialize();return;}saveFailure=null;await flush();}));card.append(actions);
 const detailEdit=document.getElementById('detailEdit'),detailExport=document.getElementById('detailExport'),detailDelete=document.getElementById('detailDelete'),detailNote=document.getElementById('recordActionNote');
 function syncRecordActions(){
  const r=view.detailRecord();detailEdit.disabled=!ready||!r;detailExport.disabled=!ready||!r;detailDelete.disabled=!ready||!r||collection==='samples';
  detailEdit.title=collection==='samples'?'개인 사본으로 수정':'기록 수정';detailDelete.title=collection==='samples'?'가상 예시 원본은 삭제할 수 없습니다.':'기록 삭제';
  detailNote.hidden=!r||collection!=='samples';detailNote.textContent='가상 예시 원본입니다. 수정하면 개인 자료함에 사본을 저장합니다.';
 }
 async function changeRecord(route,r,fields){
  available();await flush();locked=true;
  try{const data=await api(route,{revision,recordId:r.id,expectedRevision:r.revision,...fields});revision=data.revision;personalRecords=data.records;window.PlantRecordDrafts?.reconcile?.(personalRecords);switchCollection('personal');return data;}
  finally{locked=false;if(dirty)persist();}
 }
 function dialogError(d,error){let message=d.querySelector('.record-dialog-error');if(!message){message=node('p',null,'record-dialog-error');message.setAttribute('role','alert');d.append(message);}message.textContent=error.message;}
 detailExport.addEventListener('click',()=>{const r=view.detailRecord();if(r)exportDialog('archive',[r.id]).catch(showError);});
 detailEdit.addEventListener('click',()=>{
  try{
   available();const r=view.detailRecord();if(!r)return;const copy=collection==='samples',d=modal(copy?'기록 사본 수정':'기록 수정'),form=node('form',null,'record-edit-form');
   const field=(labelText,input)=>{const label=node('label',labelText);label.append(input);form.append(label);return input;};
   const title=field('제목',node('input'));title.value=r.title;title.maxLength=1000;
   const date=field('기록일',node('input'));date.type='date';date.value=r.date?.slice(0,10)||'';
   const body=field('내용',node('textarea'));body.value=r.body;body.required=true;body.maxLength=200000;
   if(copy)form.append(node('p','개인 자료함에 수정한 사본을 저장합니다.'));
   const actions=node('div',null,'transfer-actions'),cancel=button('취소',()=>d.close()),submit=node('button',copy?'개인 사본 저장':'수정 저장');submit.type='submit';actions.append(cancel,submit);form.append(actions);d.append(form);
   const editor=window.PlantMarkdownEditor.mount(body,{label:'기록 내용',placeholder:'기록 내용을 마크다운으로 수정해 보세요.'});body.required=false;d.addEventListener('close',()=>editor?.destroy(),{once:true});
   form.addEventListener('submit',async event=>{event.preventDefault();submit.disabled=true;cancel.disabled=true;title.disabled=date.disabled=body.disabled=true;
    try{const fields={record:{title:title.value.trim(),body:body.value,date:date.value||null,...(copy?{origin_id:r.id,search_enabled:true}:{})}};if(!fields.record.body.trim())throw Error('기록 내용을 입력해 주세요.');
     const data=await changeRecord(copy?'record':'record-update',r,fields),saved=copy?data.records.at(-1):data.records.find(x=>x.id===r.id);view.showRecord(saved.id);d.close();setStatus(copy?'수정한 사본을 개인 자료함에 저장했어요.':'기록을 수정했어요.');previewToast(status.textContent);
    }catch(error){dialogError(d,error);}finally{submit.disabled=false;cancel.disabled=false;title.disabled=date.disabled=body.disabled=false;}
   });
  }catch(error){showError(error);}
 });
 detailDelete.addEventListener('click',()=>{
  try{available();const r=view.detailRecord();if(!r||collection==='samples')return;const d=modal('기록 삭제');d.append(node('p','“'+r.title+'” 기록을 삭제할까요? 삭제한 기록은 설정의 데이터 관리에서 복원할 수 있어요.'));
   const submit=button('삭제',async()=>{submit.disabled=true;try{await changeRecord('record-delete',r);d.close();go('archive');setStatus('기록을 삭제했어요. 설정에서 복원할 수 있어요.');previewToast(status.textContent);}catch(error){dialogError(d,error);}finally{submit.disabled=false;}});submit.className='record-delete';d.append(submit);
  }catch(error){showError(error);}
 });
 async function showDeletedRecords(){
  available();const d=modal('삭제한 기록'),deleted=personalRecords.filter(r=>r.deleted_at);if(!deleted.length)d.append(node('p','삭제한 기록이 없습니다.'));
  for(const r of deleted){const row=node('div',null,'record-trash-row'),restore=button('복원',async()=>{restore.disabled=true;try{await changeRecord('record-restore',r);previewToast('기록을 복원했어요.');await showDeletedRecords();}catch(error){dialogError(d,error);}finally{restore.disabled=false;}});row.append(node('span',r.title||'제목 없음'),restore);d.append(row);}
 }
 actions.append(button('삭제한 기록',showDeletedRecords));
 document.addEventListener('plant:record-opened',syncRecordActions);document.addEventListener('plant:collection-changed',syncRecordActions);syncRecordActions();
 const archiveActions=node('div',null,'transfer-actions');archiveActions.append(button('내보내기',()=>exportDialog('archive')),button('이 기록 내보내기',()=>{const id=view.selectedId();if(!id)throw Error('내보낼 기록을 선택해 주세요.');return exportDialog('archive',[id]);}),button('불러오기',importFile));(document.querySelector('#archive .archive-toolbar-secondary')||document.querySelector('#archive .archive-toolbar')).append(archiveActions);
 const history=previewRenderHistory;
 previewRenderHistory=function(){history();for(const menu of document.querySelectorAll('.preview-thread-menu:not(.preview-group-menu)')){const threadId=menu.id.slice('thread-menu-'.length);const b=button('이 대화 내보내기',()=>{previewCloseThreadMenus();return exportDialog('chat',[threadId]);});b.className='transfer-thread-export';b.setAttribute('role','menuitem');menu.insertBefore(b,menu.querySelector('.preview-delete-thread'));menu.addEventListener('keydown',event=>{const items=[...menu.querySelectorAll('button')];const index=items.indexOf(document.activeElement);let target;if(event.key==='ArrowDown')target=(index+1)%items.length;else if(event.key==='ArrowUp')target=(index+items.length-1)%items.length;else if(event.key==='Home')target=0;else if(event.key==='End')target=items.length-1;else return;event.preventDefault();event.stopPropagation();items[target].focus();},true);}};
 document.addEventListener('plant:open-draft-record',event=>{
  const record=personalRecords.find(r=>r.id===event.detail.recordId&&!r.deleted_at);if(!record){previewToast('저장한 기록을 찾을 수 없어요. 삭제한 기록은 설정에서 확인해 주세요.');return;}switchCollection('personal');view.showRecord(record.id);
 });
 let savingRecord=false;
 addRecord=async function(){
  if(savingRecord)return;savingRecord=true;if(saveRecordButton)saveRecordButton.disabled=true;
  const fields=['recordTitle','recordDate','recordBody'].map(id=>document.getElementById(id)),previousDisabled=fields.map(field=>field.disabled);
  const [title,date,body]=fields.map(field=>field.value);fields.forEach(field=>field.disabled=true);
  try{
   if(!body.trim())throw Error('기록 내용을 입력해 주세요.');const drafts=await window.PlantLoadRecordDrafts(),source=drafts.origin();await flush();
   const result=await api('record',{revision,record:{title,body,date:date||today,search_enabled:true},...(source?{draftSource:source}:{})}),saved=result.records.find(r=>r.id===result.record_id)||result.records.at(-1);
   revision=result.revision;personalRecords=result.records;drafts.saved(source,saved);document.getElementById('recordBody').value='';document.getElementById('recordTitle').value='';document.getElementById('recordDate').value=saved.date;switchCollection('personal');view.showRecordInCalendar(saved.id);previewRemember();setStatus('개인 자료함에 기록을 저장했어요.');previewToast(result.reused?'이미 저장한 기록을 달력에서 열었어요.':'기록을 저장했어요. 선택한 날짜의 달력에서 확인하세요.');
  }catch(error){showError(error);previewRemember();}finally{savingRecord=false;fields.forEach((field,i)=>field.disabled=previousDisabled[i]);if(saveRecordButton)saveRecordButton.disabled=false;}
 };
 const note=document.querySelector('#emotion .notice');if(note)note.textContent='저장하면 개인 자료함과 AI 검색에 반영하고, 해당 날짜의 달력으로 이동합니다.';
 const saveRecordButton=document.querySelector('#emotion button.primary');if(saveRecordButton)saveRecordButton.textContent='저장하고 달력에서 보기 ↗';
 document.addEventListener('plant:collection-changed',()=>{const select=document.getElementById('archiveProfile');select.disabled=collection==='personal';});
 // Keep the browser's close warning while a server write is still pending.
 window.addEventListener('beforeunload',event=>{if(dirty||saveFailure){event.preventDefault();event.returnValue='';}});
 function initialize(){
  if(initializing)return initializing;
  reconnect.hidden=false;reconnect.disabled=true;reconnect.textContent='저장소 연결 확인 중…';
  initializing=loadLibrary().finally(()=>{initializing=null;reconnect.disabled=false;reconnect.hidden=ready;reconnect.textContent='저장소 다시 연결';});return initializing;
 }
 window.addEventListener('online',()=>{if(!ready&&!locked)void initialize();});
 async function loadLibrary(){
  try{if(window.PlantChatRecovery?.busy())throw Error('답변 생성을 마친 뒤 저장소에 다시 연결해 주세요.');const response=await fetch('/api/library/state',{cache:'no-store',signal:AbortSignal.timeout(15000)});if(!response.ok)throw Error('저장소에 연결하지 못했습니다. 모드 전환은 가능하며, 아래에서 다시 연결할 수 있어요.');const data=await response.json();token=data.token;revision=data.revision;personalRecords=data.records;
   let tabEpoch=null;try{tabEpoch=sessionStorage.getItem('plant-thought-storage-epoch');}catch{}
   if(data.storage_reset_count>0&&tabEpoch!==data.storage_epoch&&new URL(location.href).searchParams.get('reset_state')!==data.storage_epoch){clearForReset(data.storage_epoch,true);return;}
   storageEpoch=data.storage_epoch;try{sessionStorage.setItem('plant-thought-storage-epoch',storageEpoch);localStorage.setItem('plant-thought-data-epoch',storageEpoch);}catch{}
   const local=threadSnapshot().filter(t=>!(data.purgedThreadIds||[]).includes(t.id)&&(t.messages.length||String(t.draft||'').trim()));persistedThreads=JSON.stringify(data.threads);previewThreads=data.threads.slice();
   // Use one thread per ID. Recover newer messages/drafts in that thread instead of creating copies.
   for(const thread of local){const index=previewThreads.findIndex(saved=>saved.id===thread.id);if(index<0)previewThreads.push(window.PlantChatState.reconcileThread(null,thread));else previewThreads[index]=window.PlantChatState.reconcileThread(previewThreads[index],thread);}
   window.PlantRecordDrafts?.reconcile?.(personalRecords);
   for(const thread of previewThreads)window.PlantChatState.interruptPending(thread);
   if(!previewThread())previewActiveId=previewThreads.find(t=>!t.deletedAt)?.id||null;
   document.getElementById('chatInput').value=previewThread()?.draft||'';
   if(!previewThreads.length&&!(data.storage_reset_count>0))newChat();
   ready=true;saveFailure=null;testToggle.disabled=false;let previous;try{previous=sessionStorage.getItem('plant-thought-library-collection');}catch{}switchCollection(testEnabled&&previous!=='personal'?'samples':'personal');
   dirty=true;await persist();setStatus('이 기기에 저장됨 · 대화 '+previewThreads.length+'개 · 개인 기록 '+personalRecords.length+'개');document.dispatchEvent(new Event('plant:library-ready'));
  }catch(error){showError(error);}
 }
 switchCollection(testEnabled?'samples':'personal');
 const navigate=go;go=function(id){
  navigate(id==='memorylab'&&!testEnabled?'settings':id);
  if(id==='archive' && collection==='personal')view.showPersonalRecords();
  if(document.querySelector('.page.active')?.id==='chat')document.dispatchEvent(new Event('plant:chat-visible'));
 };
 if(!testEnabled&&document.querySelector('.page.active')?.id==='memorylab')go('settings');
 previewRenderHistory();initialize();
})();
