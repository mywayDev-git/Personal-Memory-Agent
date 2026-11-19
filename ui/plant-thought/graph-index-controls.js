'use strict';
(()=>{
 const container=document.querySelector('.chat-version-bar>div');if(!container||!window.PlantSearchModes)return;
 const tools=document.createElement('div');tools.className='chat-graph-index';tools.hidden=true;
 const status=document.createElement('span');status.className='chat-graph-index-state';status.setAttribute('role','status');
 const prepare=document.createElement('button');prepare.type='button';prepare.textContent='색인 준비';
 const cancel=document.createElement('button');cancel.type='button';cancel.textContent='준비 중지';cancel.hidden=true;
 tools.append(status,prepare,cancel);container.append(tools);
 let token=null,refreshing=false,actionBusy=false,selection='',sequence=0;
 const current=()=>({mode:window.PlantChatSearch?.current()||'legacy',collection:window.PlantArchiveSamples?.synthetic===false?'personal':'samples'});
 const applicable=()=>window.PlantTestMode?.enabled===true&&['G1','G2'].includes(window.PlantSearchModes.get(current().mode)?.route);
 async function api(action,value){
  if(!token){const response=await fetch('/api/baseline/bootstrap',{signal:AbortSignal.timeout(15000)});if(!response.ok)throw Error('Memory Lab 연결을 확인해 주세요.');token=(await response.json()).token;}
  const response=await fetch('/api/baseline/chat-index/'+action,{method:'POST',headers:{'Content-Type':'application/json','X-Memory-Lab-Token':token},body:JSON.stringify(value),signal:AbortSignal.timeout(15000)});
  const result=await response.json();if(!response.ok){if(response.status===403)token=null;throw Error(result.error||'색인 작업을 처리하지 못했습니다.');}return result;
 }
 async function refresh(){
  const enabled=applicable();tools.hidden=!enabled;if(!enabled||refreshing)return;
  const selected=current(),key=selected.collection+':'+selected.mode,version=sequence;refreshing=true;
  try{
   const response=await fetch('/api/baseline/chat-index-status?'+new URLSearchParams(selected),{cache:'no-store',signal:AbortSignal.timeout(15000)});const result=await response.json();if(!response.ok)throw Error(result.error||'색인 상태를 확인하지 못했습니다.');
   if(version!==sequence||key!==current().collection+':'+current().mode)return;
   status.dataset.state=result.status;
   status.textContent=result.status==='ready'?'색인 준비 완료 · '+result.source_count+'개 원문':result.status==='queued'?'색인 갱신 대기':result.status==='indexing'?result.progress:result.status==='failed'?'색인 준비 실패':result.status==='cancelled'?'색인 준비 중지':result.status==='stale'?'기록이 바뀌어 색인 갱신이 필요합니다.':'검색 전에 색인을 한 번 준비해 주세요.';
   status.title=result.error||'새 기록·수정·삭제는 저장 후 색인을 갱신합니다. 검색 시에는 새로 만들지 않습니다.';
   const busy=['queued','indexing'].includes(result.status);prepare.hidden=busy||result.status==='ready';cancel.hidden=!busy;prepare.disabled=actionBusy;cancel.disabled=actionBusy;
   prepare.textContent=['failed','cancelled','stale'].includes(result.status)?'색인 다시 준비':'색인 준비';
  }catch(error){if(version===sequence){status.textContent=error.message;status.dataset.state='failed';prepare.hidden=false;cancel.hidden=true;}}
  finally{refreshing=false;}
 }
 async function changed(){
  sequence++;selection='';tools.hidden=!applicable();if(!applicable())return;
  const selected=current(),key=selected.collection+':'+selected.mode;
  try{await api('enable',selected);selection=key;}catch(error){status.textContent=error.message;}
  await refresh();
 }
 async function run(action){if(actionBusy)return;actionBusy=true;prepare.disabled=true;cancel.disabled=true;try{await api(action,current());}catch(error){status.textContent=error.message;status.dataset.state='failed';}finally{actionBusy=false;await refresh();}}
 prepare.addEventListener('click',()=>run('prepare'));cancel.addEventListener('click',()=>run('cancel'));
 document.getElementById('chatSearchModeSelect').addEventListener('change',changed);
 for(const event of ['plant:test-mode-changed','plant:collection-changed'])document.addEventListener(event,changed);
 const timer=setInterval(()=>{if(applicable()){const selected=current();if(selection!==selected.collection+':'+selected.mode)void changed();else void refresh();}},3000);
 window.addEventListener('pagehide',()=>clearInterval(timer),{once:true});if(window.PlantTestMode)void changed();
})();
