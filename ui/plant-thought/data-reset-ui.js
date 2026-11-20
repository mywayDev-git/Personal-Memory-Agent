'use strict';
(()=>{
 const node=(tag,text,cls)=>{const e=document.createElement(tag);if(text!=null)e.textContent=text;if(cls)e.className=cls;return e;};
 const card=node('section',null,'card data-reset-settings'),heading=node('h3','데이터 전체 삭제'),description=node('p','이 기기에 저장된 대화·개인 기록·초안·휴지통과 Memory Lab 실행 기록·검색 색인을 삭제합니다.'),open=node('button','데이터 전체 삭제','data-reset-danger');
 open.type='button';card.append(heading,description,open);document.getElementById('settings').append(card);
 const dialog=node('dialog',null,'transfer-dialog data-reset-dialog');dialog.setAttribute('aria-labelledby','dataResetTitle');document.body.append(dialog);
 let working=false,partiallyCleared=false,uncertain=false;
 dialog.addEventListener('close',()=>{if((partiallyCleared||uncertain)&&!working)location.reload();});
 dialog.addEventListener('cancel',event=>{if(working)event.preventDefault();});
 open.addEventListener('click',async()=>{
  open.disabled=true;partiallyCleared=false;uncertain=false;dialog.replaceChildren();const title=node('h2','모든 앱 데이터를 삭제할까요?');title.id='dataResetTitle';
  const note=node('p','삭제할 데이터를 확인하고 있습니다.','data-reset-note'),error=node('p',null,'data-reset-error');error.setAttribute('role','alert');
  const close=node('button','취소');close.type='button';close.onclick=()=>{if(!working)dialog.close();};dialog.append(title,note,error,close);dialog.showModal();
  try{
   await window.PlantLibraryPersistence.flush();
   const response=await fetch('/api/data-reset/preview',{cache:'no-store',signal:AbortSignal.timeout(20000)}),preview=await response.json();if(!response.ok)throw Error(preview.error||'삭제 범위를 확인하지 못했습니다.');
   note.textContent='삭제 후 앱에서 복구할 수 없습니다. 필요한 데이터는 설정의 전체 백업으로 먼저 내보낼 수 있습니다.';
   const list=node('ul');for(const text of ['대화 '+preview.counts.threads+'개 · 개인 기록 '+preview.counts.records+'개 (휴지통 포함)','기록 초안 '+preview.counts.drafts+'개와 작성 중인 입력·수정 이력·대화 맥락','Memory Lab 실행 기록 '+(preview.lab?.runs??'확인 불가')+'개와 생성된 색인·근거 파일','이 브라우저의 앱 설정과 저장된 화면 상태'])list.append(node('li',text));
   const keep=node('p','기본 예시 원문 199개, 설치 모델, 코드와 이미 내보낸 백업 파일은 유지합니다.','data-reset-keep');
   const label=node('label','확인하려면 아래에 ‘전체 삭제’를 입력하세요.','data-reset-confirm'),input=node('input');input.type='text';input.autocomplete='off';input.spellcheck=false;input.setAttribute('aria-label','전체 삭제 확인 문구');label.append(input);
   const submit=node('button','모든 데이터 영구 삭제','data-reset-danger');submit.type='button';submit.disabled=true;
   input.addEventListener('input',()=>{submit.disabled=input.value!=='전체 삭제'||!preview.available||working;});
   const actions=node('div',null,'transfer-actions');close.remove();actions.append(close,submit);dialog.append(list,keep,label,actions);
   if(!preview.available)error.textContent=preview.note;
   const resetId=crypto.randomUUID();
   async function outcome(){const response=await fetch('/api/data-reset/status?id='+encodeURIComponent(resetId),{cache:'no-store',signal:AbortSignal.timeout(15000)});if(!response.ok)throw Error('삭제 결과를 확인하지 못했습니다.');return response.json();}
   submit.onclick=async()=>{
    if(working||input.value!=='전체 삭제')return;working=true;submit.disabled=true;close.disabled=true;input.disabled=true;error.textContent='';note.textContent='진행 중인 작업을 정리하고 데이터를 삭제하고 있습니다…';
    try{
     if(uncertain){
      const state=await outcome();
      if(state.status==='completed'){window.PlantLibraryPersistence.clearForReset(state.storage_epoch,true);return;}
      if(state.status==='partial'){partiallyCleared=true;uncertain=false;window.PlantLibraryPersistence.clearForReset(state.storage_epoch,false);throw Object.assign(Error('남은 데이터 정리를 다시 시도해 주세요.'),{partial:true});}
      if(state.status==='running')throw Object.assign(Error('삭제 처리 중입니다. 잠시 후 결과를 다시 확인해 주세요.'),{uncertain:true});
      uncertain=false;throw Error('삭제가 시작되지 않았습니다. 다시 시도하거나 창을 다시 열어 주세요.');
     }
     await window.PlantLibraryPersistence.beginReset();
     const result=await fetch('/api/data-reset',{method:'POST',headers:{'Content-Type':'application/json','X-Data-Reset-Token':preview.token},body:JSON.stringify({reset_id:resetId,revision:preview.revision,storage_epoch:preview.storage_epoch,confirmation:input.value})});
     const data=await result.json();if(!result.ok){if(data.partial){partiallyCleared=true;window.PlantLibraryPersistence.clearForReset(data.storage_epoch,false);}throw Object.assign(Error(data.error||'전체 삭제를 완료하지 못했습니다.'),{partial:data.partial});}
     if(data.deleted!==true)throw Error('삭제 완료를 확인하지 못했습니다.');
     window.PlantLibraryPersistence.clearForReset(data.storage_epoch,true);
    }catch(failure){
     if(!failure.partial&&!failure.uncertain)try{const state=await outcome();if(state.status==='completed'){window.PlantLibraryPersistence.clearForReset(state.storage_epoch,true);return;}if(state.status==='partial'){partiallyCleared=true;window.PlantLibraryPersistence.clearForReset(state.storage_epoch,false);failure.partial=true;}else if(state.status==='running')failure.uncertain=true;}catch{failure.uncertain=true;}
     uncertain=!!failure.uncertain;
     error.textContent=(failure.partial?'개인 데이터는 삭제됐지만 나머지 정리가 끝나지 않았습니다. 다시 눌러 완료해 주세요.\n':'')+failure.message;note.textContent='전체 삭제가 완료되지 않았습니다.';if(!uncertain)window.PlantLibraryPersistence.endReset();working=false;submit.disabled=false;close.disabled=false;input.disabled=false;submit.textContent=uncertain?'삭제 결과 확인':'전체 삭제 다시 시도';}
   };
   input.focus();
  }catch(failure){error.textContent=failure.message;note.textContent='데이터는 삭제하지 않았습니다.';}
  finally{open.disabled=false;}
 });
})();
