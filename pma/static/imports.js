// Strict UTF-8 decoding; text preview precedes an explicit, idempotent commit.
export function setupImports({api,node,action,notice}) {
  const input=document.getElementById('record-upload');
  document.getElementById('chat-upload')?.addEventListener('click',()=>input.click());
  input?.addEventListener('change',async()=>{
    const file=input.files?.[0]; input.value=''; if(!file)return;
    let preview;
    try {
      if(file.size>1024*1024 || !/\.(txt|md)$/i.test(file.name))throw Error('1MiB 이하의 .txt 또는 .md 파일을 선택해 주세요.');
      const text=new TextDecoder('utf-8',{fatal:true}).decode(await file.arrayBuffer());
      preview=await api('/imports/preview','POST',{filename:file.name,text});
    } catch(e){notice(e.message,true);return;}
    const trigger=document.activeElement,d=node('dialog',undefined,'memory-dialog import-dialog');
    const heading=node('h2','파일 가져오기');heading.id='import-heading';d.setAttribute('aria-labelledby',heading.id);
    const hint=node('p','아직 개인 기록으로 저장되지 않았습니다. 내용을 확인해 주세요.','muted');
    d.append(heading,node('p',`${preview.filename} · 기록 ${preview.chunks.length}개로 나누어 저장합니다.`),hint);
    for(const [index,part] of preview.chunks.entries()) {
      const section=node('details');section.open=index===0;
      section.append(node('summary',`기록 ${index+1} · 원문 ${part.start+1}~${part.end}자`),node('pre',part.text));d.append(section);
    }
    let committed=false,saving=false;
    d.addEventListener('cancel',e=>{if(saving)e.preventDefault();});
    const status=node('p',''),requestId=crypto.randomUUID();status.setAttribute('role','status');d.append(status);
    const close=action('취소',()=>d.close());
    const save=action('확인하고 저장',async()=>{
      close.disabled=true;saving=true;hint.textContent='원문을 저장하고 있습니다.';
      try{const result=await api('/imports/'+preview.import_id+'/commit','POST',{request_id:requestId});committed=true;d.close();notice(`${result.records.length}개 원문을 저장했습니다. 검색 준비는 자동으로 진행됩니다.`);}
      catch(e){hint.textContent='저장 결과를 확인하지 못했습니다. 같은 저장 버튼으로 다시 확인할 수 있습니다.';status.textContent=e.message;}
      finally{close.disabled=false;saving=false;}
    });d.append(save,close);d.addEventListener('close',()=>{d.remove();trigger?.focus();if(!committed)api('/imports/'+preview.import_id,'DELETE').catch(()=>{});});document.body.append(d);d.showModal();
  });
}
