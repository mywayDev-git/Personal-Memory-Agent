'use strict';
// Read original availability; explicit preparation controls build the selected search index.
(()=>{
  const collection=window.PlantArchiveSamples;if(!collection)return;
  const node=(tag,text,cls)=>{const el=document.createElement(tag);if(text!=null)el.textContent=text;if(cls)el.className=cls;return el;};
  const names={unchecked:'확인 전',checking:'확인 중',ready:'사용 가능',error:'상태 확인 실패'};
  const entries=new Map();let scopeKey='',scope=null,filter='all',dialogRecord=null,returnFocus=null,serviceChecked=0,serviceBusy=false;
  const isArchive=()=>document.querySelector('.page.active')?.id==='archive';
  const entry=()=>entries.get(scopeKey);
  const recordMap=new Map(collection.records.map(r=>[r.id,r]));
  const overview=node('section',null,'archive-readiness-overview');overview.id='archiveReadinessOverview';overview.hidden=true;overview.setAttribute('role','dialog');overview.setAttribute('aria-label','기록 준비 상태');
  const compact=node('button','기록 준비 상태 · 확인 전','archive-readiness-compact');compact.type='button';compact.setAttribute('aria-label','기록 준비 상태 보기');compact.setAttribute('aria-haspopup','dialog');compact.setAttribute('aria-expanded','false');compact.setAttribute('aria-controls',overview.id);
  const toolbarMain=node('div',null,'archive-toolbar-main'),viewSwitch=document.querySelector('#archive .archive-view-switch');viewSwitch.before(toolbarMain);toolbarMain.append(viewSwitch,compact);
  const dismiss=node('button','닫기','archive-readiness-dismiss');dismiss.type='button';dismiss.setAttribute('aria-label','기록 준비 상태 닫기');dismiss.addEventListener('click',()=>closeOverview(true));
  function closeOverview(focus=false){overview.hidden=true;compact.setAttribute('aria-expanded','false');if(focus)compact.focus({preventScroll:true});}
  function positionOverview(){const anchor=compact.getBoundingClientRect(),width=overview.offsetWidth,height=overview.offsetHeight;overview.style.left=Math.max(12,Math.min(anchor.left,innerWidth-width-12))+'px';const below=anchor.bottom+8;overview.style.top=(below+height<=innerHeight-12?below:Math.max(12,anchor.top-height-8))+'px';}
  compact.addEventListener('click',()=>{if(!overview.hidden){closeOverview();return;}overview.hidden=false;compact.setAttribute('aria-expanded','true');positionOverview();refreshPreparation();dismiss.focus({preventScroll:true});});
  document.addEventListener('click',event=>{if(!overview.hidden&&!overview.contains(event.target)&&!compact.contains(event.target))closeOverview();});
  document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!overview.hidden){event.preventDefault();closeOverview(true);}});
  document.addEventListener('focusin',event=>{if(!overview.hidden&&!overview.contains(event.target)&&!compact.contains(event.target))closeOverview();});
  document.addEventListener('scroll',event=>{if(!overview.hidden&&!overview.contains(event.target))closeOverview();},true);
  window.addEventListener('resize',()=>closeOverview());
  const heading=node('div',null,'archive-readiness-heading'),headingText=node('div');headingText.append(node('h2','기록 준비 상태'),node('p','검색에 사용할 수 있는 기록인지 확인합니다. 답변의 근거가 충분한지는 질문마다 달라요.'));
  const service=node('button','AI 상태 확인 전','archive-service-state');service.type='button';service.addEventListener('click',()=>checkService(true));heading.append(headingText,service,dismiss);
  const contextLabel=node('p',null,'archive-readiness-context');
  const controls=node('div',null,'archive-readiness-controls'),filters=node('div',null,'archive-readiness-filters');filters.setAttribute('role','group');filters.setAttribute('aria-label','기록 준비 상태 필터');
  const filterButtons=new Map();for(const [key,label]of [['all','전체'],...Object.entries(names)]){const button=node('button',label);button.type='button';button.dataset.readinessFilter=key;button.addEventListener('click',()=>{filter=key;render();});filterButtons.set(key,button);filters.append(button);}
  const refresh=node('button','다시 확인','archive-readiness-refresh');refresh.type='button';refresh.addEventListener('click',()=>{checkRecords();checkService(true);});controls.append(filters,refresh);
  const note=node('p',null,'archive-readiness-note');note.setAttribute('role','status');
  overview.append(heading,contextLabel,controls,note);document.body.append(overview);
  const preparation=node('section',null,'archive-preparation');preparation.setAttribute('aria-label','기록 준비');
  const preparationTitle=node('h3','기록 준비'),preparationHelp=node('p','선택한 자료함 전체를 그래프 검색에 사용할 수 있도록 준비합니다. 대화와 원문은 바뀌지 않습니다.');
  const preparationLabel=node('label','준비할 방식'),preparationSelect=node('select');preparationSelect.setAttribute('aria-label','기록 준비 방식');
  for(const [id,label]of [['G1-linked','사건 연결과 근거 확인'],['G1','사건별 정리'],['G1-claim','주장과 근거 정리'],['G2','여러 대상과 사실 정리']]){const option=node('option',label);option.value=id;preparationSelect.append(option);}
  const selectedMode=window.PlantChatSearch?.current();preparationSelect.value=[...preparationSelect.options].some(o=>o.value===selectedMode)?selectedMode:'G1-linked';preparationLabel.append(preparationSelect);
  const preparationState=node('p','준비 상태를 확인해 주세요.','archive-preparation-state');preparationState.setAttribute('role','status');
  const preparationButtons=node('div',null,'archive-preparation-actions'),prepare=node('button','기록 준비'),stop=node('button','준비 중지');prepare.type=stop.type='button';stop.hidden=true;preparationButtons.append(prepare,stop);preparation.append(preparationTitle,preparationHelp,preparationLabel,preparationState,preparationButtons);overview.append(preparation);
  let preparationResult=null,preparationError='',preparationBusy=false,preparationChecking=false,preparationToken=null;
  const preparationTarget=()=>({collection:window.PlantArchiveSamples?.synthetic===false?'personal':'samples',mode:preparationSelect.value});
  function renderPreparation(){
    const result=preparationResult,busy=['queued','indexing'].includes(result?.status),chatBusy=previewThreads.some(t=>!t.deletedAt&&t.messages.some(m=>m.kind==='assistant'&&m.status==='pending'&&!m.archived));
    const labels={not_prepared:'준비 전',stale:'갱신 필요',queued:'준비 대기',indexing:'준비 중',ready:'준비 완료',failed:'준비 실패',cancelled:'준비 중지됨'};
    preparationState.textContent=preparationError||(preparationChecking&&!result?'준비 상태 확인 중…':result?(labels[result.status]||'확인 필요')+' · '+(result.indexed_count||0)+' / '+result.source_count+'개 기록'+(result.error?' · '+result.error:''):'준비 상태를 확인해 주세요.');
    preparationState.dataset.state=preparationError?'failed':result?.status||'unchecked';
    prepare.hidden=busy;stop.hidden=!busy;prepare.disabled=preparationBusy||preparationChecking||chatBusy;stop.disabled=preparationBusy;preparationSelect.disabled=preparationBusy||busy;
    prepare.textContent=result?.status==='ready'?'기록 다시 준비':['failed','cancelled','stale'].includes(result?.status)?'기록 다시 준비':'기록 준비';
    preparationHelp.textContent=chatBusy?'대화 생성을 마친 뒤 기록을 준비할 수 있어요.':'선택한 자료함 전체를 그래프 검색에 사용할 수 있도록 준비합니다. 대화와 원문은 바뀌지 않습니다.';
    if(result)compact.textContent='기록 준비 상태 · '+(labels[result.status]||'확인 필요');
    if(!overview.hidden)positionOverview();
  }
  async function refreshPreparation(){
    if(preparationChecking)return;preparationChecking=true;renderPreparation();const target=preparationTarget(),key=JSON.stringify(target);
    try{const response=await fetch('/api/baseline/chat-index-status?'+new URLSearchParams(target),{cache:'no-store',signal:AbortSignal.timeout(15000)}),result=await response.json();if(!response.ok)throw Error(result.error||'기록 준비 상태를 확인하지 못했습니다.');if(key!==JSON.stringify(preparationTarget()))return;preparationResult=result;preparationError='';}
    catch(error){if(key===JSON.stringify(preparationTarget()))preparationError=error.message;}
    finally{preparationChecking=false;renderPreparation();}
  }
  async function preparationAction(action){
    if(preparationBusy)return;preparationBusy=true;preparationError='';renderPreparation();
    try{
      if(action==='prepare'&&previewThreads.some(t=>!t.deletedAt&&t.messages.some(m=>m.kind==='assistant'&&m.status==='pending'&&!m.archived)))throw Error('대화 생성을 마친 뒤 다시 시도해 주세요.');
      const target=preparationTarget();if(!preparationToken){const response=await fetch('/api/baseline/bootstrap',{cache:'no-store',signal:AbortSignal.timeout(15000)});if(!response.ok)throw Error('로컬 AI 연결을 확인해 주세요.');preparationToken=(await response.json()).token;}
      const response=await fetch('/api/baseline/chat-index/'+action,{method:'POST',headers:{'Content-Type':'application/json','X-Memory-Lab-Token':preparationToken},body:JSON.stringify(target),signal:AbortSignal.timeout(15000)}),result=await response.json();if(!response.ok){if(response.status===403)preparationToken=null;throw Error(result.error||'기록 준비 요청을 처리하지 못했습니다.');}
      await refreshPreparation();
    }catch(error){preparationError=error.message;}finally{preparationBusy=false;renderPreparation();}
  }
  preparationSelect.addEventListener('change',()=>{preparationResult=null;preparationError='';refreshPreparation();});prepare.onclick=()=>preparationAction('prepare');stop.onclick=()=>preparationAction('cancel');
  refresh.addEventListener('click',()=>refreshPreparation());
  const preparationTimer=setInterval(()=>{if(!overview.hidden||['queued','indexing'].includes(preparationResult?.status))refreshPreparation();},2000);window.addEventListener('pagehide',()=>clearInterval(preparationTimer),{once:true});
  const dialog=node('dialog',null,'archive-readiness-dialog');dialog.setAttribute('aria-label','기록 준비 상태 상세');document.body.append(dialog);
  dialog.addEventListener('click',event=>{if(event.target===dialog){const rect=dialog.getBoundingClientRect();if(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom)dialog.close();}});
  dialog.addEventListener('close',()=>{dialogRecord=null;if(returnFocus?.isConnected)returnFocus.focus({preventScroll:true});});
  document.addEventListener('click',event=>{const badge=event.target.closest('[data-readiness-record]');if(!badge)return;event.preventDefault();dialogRecord=badge.dataset.readinessRecord;returnFocus=badge;renderDialog();dialog.showModal();});
  function statusFor(id){const state=entry();if(!state||state.phase!=='done')return {status:state?.phase==='error'?'error':state?.phase==='checking'?'checking':'unchecked',reason:state?.error||(state?.phase==='checking'?'전체 원문 버전과 검색 가능 여부를 확인하고 있습니다.':'전체 원문의 준비 상태를 아직 확인하지 않았습니다.')};return state.items.get(id)||{status:'error',reason:'현재 원문을 상태 조회 결과에서 찾지 못했습니다.'};}
  function hydrate(){
    for(const list of [document.getElementById('selectedList'),document.getElementById('searchResults')]){
      const items=[...list.querySelectorAll('.archive-record-item')];let shown=0;
      if(list.id==='searchResults'){
        for(const item of items){item.hidden=false;item.classList.remove('has-readiness');const badge=item.querySelector('[data-readiness-record]');if(badge)badge.hidden=true;}
        const empty=list.querySelector('.archive-readiness-filter-empty');if(empty)empty.hidden=true;continue;
      }
      for(const item of items){const badge=item.querySelector('[data-readiness-record]'),data=statusFor(badge.dataset.readinessRecord);badge.hidden=false;item.classList.add('has-readiness');const label=names[data.status];if(badge.textContent!==label)badge.textContent=label;badge.className='archive-readiness-badge is-'+data.status;badge.setAttribute('aria-label',recordMap.get(badge.dataset.readinessRecord)?.title+' · '+label+' 상세');badge.title='기록 준비 상태 상세 보기';item.hidden=filter!=='all'&&data.status!==filter;if(!item.hidden)shown++;}
      let empty=list.querySelector('.archive-readiness-filter-empty');if(items.length&&!shown&&filter!=='all'){if(!empty){empty=node('p','현재 날짜 또는 검색 결과에 이 상태의 기록이 없습니다.','archive-readiness-filter-empty');list.append(empty);}empty.hidden=false;}else if(empty)empty.hidden=true;
    }
  }
  function render(){
    if(!scope)return;const state=entry(),all=collection.records,counts={all:all.length,unchecked:0,checking:0,ready:0,error:0};
    for(const record of all)counts[statusFor(record.id).status]++;
    const sample=collection.examples.find(q=>q.id===scope.questionId),profile=collection.profiles.find(p=>p.id===scope.profile);
    contextLabel.textContent='개발용·확인용 전체 원문 '+all.length+'개';contextLabel.title=scope.questionId;
    for(const [key,button]of filterButtons){button.textContent=(key==='all'?'전체':names[key])+' '+counts[key];button.setAttribute('aria-pressed',String(filter===key));}
    refresh.disabled=state.phase==='checking';refresh.textContent=state.phase==='checking'?'확인 중…':'다시 확인';
    note.textContent=state.phase==='done'?'마지막 확인 '+formatTime(state.result.checked_at)+' · 전체 원문이 검색 대상입니다. 필터는 준비 상태만 구분합니다.':state.phase==='checking'?'전체 원문 버전과 검색 가능 여부를 확인하고 있습니다.':state.phase==='error'?state.error:'아직 상태를 확인하지 않았습니다.';
    compact.textContent='기록 준비 상태 · '+(state.phase==='done'?counts.ready+'/'+counts.all:names[state.phase==='error'?'error':state.phase==='checking'?'checking':'unchecked'])+(filter!=='all'?' · '+names[filter]:'');
    compact.title=state.phase==='done'?'사용 가능 '+counts.ready+'개 / 전체 '+counts.all+'개 · 눌러 상세 상태와 필터 보기':'눌러 기록 준비 상태와 다시 확인 보기';
    hydrate();renderPreparation();if(!overview.hidden)positionOverview();if(dialog.open)renderDialog();
  }
  function formatTime(value){if(!value)return '확인 전';return new Intl.DateTimeFormat('ko-KR',{timeZone:'Asia/Seoul',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(new Date(value));}
  function renderDialog(){
    const source=recordMap.get(dialogRecord);if(!source)return;const state=entry(),data=statusFor(source.id),focused=document.activeElement?.dataset.readinessAction;dialog.replaceChildren();
    const head=node('div',null,'archive-readiness-dialog-head'),close=node('button','닫기');close.type='button';close.dataset.readinessAction='close';close.addEventListener('click',()=>dialog.close());head.append(node('h2','기록 준비 상태'),close);
    const badge=node('span',names[data.status],'archive-readiness-status is-'+data.status),facts=node('dl',null,'archive-readiness-facts');
    const checked=state.phase==='done';for(const [label,value]of [['원문 확인',checked?(data.original_checked?'확인됨':'확인 필요'):names[data.status]],['원문 버전','v'+source.revision],['검색 사용 버전',data.search_revision?'v'+data.search_revision:names[data.status]],['검색 범위','전체 '+collection.record_count+'개 원문'],['마지막 확인',state.result?.checked_at?formatTime(state.result.checked_at):'확인 전']]){const row=node('div');row.append(node('dt',label),node('dd',value));facts.append(row);}
    const retry=node('button','다시 확인','archive-readiness-refresh');retry.type='button';retry.dataset.readinessAction='retry';retry.disabled=state.phase==='checking';retry.addEventListener('click',()=>checkRecords());
    dialog.append(head,node('h3',source.title),badge,node('p',data.reason,'archive-readiness-reason'),facts,retry);
    if(dialog.open&&focused)dialog.querySelector('[data-readiness-action="'+focused+'"]')?.focus({preventScroll:true});
  }
  function showDetail(id,button){dialogRecord=id;returnFocus=button;renderDialog();if(!dialog.open)dialog.showModal();}
  document.addEventListener('click',event=>{const button=event.target.closest('[data-readiness-record]');if(button){event.preventDefault();showDetail(button.dataset.readinessRecord,button);}});
  async function checkRecords(){
    if(!scope||(window.PlantTestMode&&!window.PlantTestMode.enabled)||!window.PlantArchiveSamples.synthetic)return;const key=scopeKey,state=entry(),version=++state.version;state.phase='checking';state.error=null;render();
    try{
      const query=new URLSearchParams({profile:scope.profile,example_id:scope.questionId});
      const response=await fetch('/api/archive/readiness?'+query,{cache:'no-store',signal:AbortSignal.timeout(15000)}),result=await response.json();if(!response.ok)throw Error(result.error||'기록 준비 상태를 확인하지 못했습니다.');
      if(result.profile!==state.scope.profile||result.example_id!==state.scope.questionId||!Array.isArray(result.records)||!Number.isFinite(Date.parse(result.checked_at)))throw Error('선택한 사례와 상태 응답이 일치하지 않습니다. 다시 확인해 주세요.');
      for(const file of ['sources.json','questions.json','contexts.json'])if(result.source_files?.[file]!==collection.provenance.files[file])throw Error('화면의 자료와 현재 원문 버전이 다릅니다. 최신 예시 자료를 불러온 후 다시 확인해 주세요.');
      const expected=collection.records;if(result.records.length!==expected.length||expected.some(record=>!result.records.some(item=>item.record_id===record.id&&item.revision===record.revision&&['ready','error'].includes(item.status))))throw Error('현재 원문 목록과 상태 조회 결과가 일치하지 않습니다.');
      if(state.version!==version)return;state.phase='done';state.result=result;state.items=new Map(result.records.map(item=>[item.record_id,item]));
    }catch(error){if(state.version!==version)return;state.phase='error';state.error=error.name==='TimeoutError'?'상태 확인 시간이 초과됐습니다. 다시 확인해 주세요.':error.name==='TypeError'?'상태 조회에 연결하지 못했습니다. 기록이 준비되지 않았다는 뜻은 아닙니다. 다시 확인해 주세요.':error.name==='SyntaxError'?'상태 응답을 읽지 못했습니다. 다시 확인해 주세요.':error.message;}
    if(scopeKey===key)render();
  }
  async function checkService(force=false){
    if(serviceBusy||(!force&&Date.now()-serviceChecked<30000))return;serviceBusy=true;service.textContent='AI 상태 확인 중';service.dataset.state='checking';
    try{const response=await fetch('/api/chat/bootstrap',{cache:'no-store',signal:AbortSignal.timeout(18000)});if(!response.ok)throw Error();const result=await response.json();service.textContent=result.ready?'AI 응답 가능':'AI 연결 확인 필요';service.dataset.state=result.ready?'ready':'error';service.title=result.ready?'로컬 AI 서버가 준비되어 있습니다. 다시 누르면 상태를 확인합니다.':result.note;}
    catch{service.textContent='AI 상태 확인 실패';service.dataset.state='error';service.title='다시 눌러 AI 연결 상태를 확인하세요. 기록 준비 상태와 별개입니다.';}finally{serviceChecked=Date.now();serviceBusy=false;}
  }
  function sync(){
    if((window.PlantTestMode&&!window.PlantTestMode.enabled)||!window.PlantArchiveSamples.synthetic){if(dialog.open)dialog.close();closeOverview();return;}
    const next=previewSnapshot().sampleArchive;if(!next?.profile||!next.questionId)return;const key=next.profile+':'+next.questionId;
    if(key!==scopeKey){if(dialog.open)dialog.close();scope={profile:next.profile,questionId:next.questionId};scopeKey=key;filter='all';if(!entries.has(key))entries.set(key,{phase:'unchecked',scope:{...scope},items:new Map(),version:0});}
    render();if(isArchive()){if(entry().phase==='unchecked')checkRecords();checkService();}
  }
  document.addEventListener('plant:archive-context',sync);
  document.addEventListener('plant:archive-show-all',()=>{filter='all';render();});
  const drawSelected=renderSelected;renderSelected=function(){drawSelected();hydrate();};
  const search=runSearch;runSearch=function(...args){search(...args);hydrate();};
  const navigate=go;go=function(id){navigate(id);if(id==='archive')sync();else closeOverview();};
  sync();
})();
