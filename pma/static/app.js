import {setupChat} from './chat.js';
import {explanation, auditView, correctionView} from './search-explanation.js';
const $ = id => document.getElementById(id);
let csrf = '', editing = null, tab = 'records', cursor = null, trashCursor = null, authorized = false;
const statuses = {queued:'기억 정리 대기',processing:'기억 정리 중',ready:'검색 가능',ready_empty:'추출된 기억 없음',failed:'처리 실패',trashed:'휴지통'};
function node(tag, text, cls) { const el=document.createElement(tag); if(text!==undefined)el.textContent=text; if(cls)el.className=cls; return el; }
function notice(text, error=false) { $('notice').hidden=!text; $('notice').textContent=text; $('notice').classList.toggle('error',error); }
async function api(path, method='GET', data) {
  const headers={}; if(method!=='GET'){headers['Content-Type']='application/json';if(csrf)headers['X-CSRF-Token']=csrf;}
  const response=await fetch('/api/v1'+path,{method,headers,body:data===undefined?undefined:JSON.stringify(data),credentials:'same-origin'});
  if(response.status===204)return null;
  const body=await response.json(); if(response.status===401)throw new Error('접속 인증이 필요합니다. 일반 주소만 열면 기록이 표시되지 않습니다. 실행기가 자동으로 연 브라우저 탭을 사용해 주세요.'); if(!response.ok)throw new Error(body.error?.message||'요청을 처리하지 못했습니다.'); return body;
}
function action(text, fn, cls='secondary') {const b=node('button',text,cls);b.type='button';b.addEventListener('click',async()=>{b.disabled=true;try{await fn();}catch(e){notice(e.message,true);}finally{b.disabled=false;}});return b;}
function renderAnswerSources(host, result) {
  const tags=node('div',undefined,'search-tags');
  for(const keyword of result.search_keywords || []) tags.append(node('span',keyword,'search-tag'));
  host.append(node('p','검색에 사용한 키워드','muted'),tags);
  const citedIds = new Set(result.items.flatMap(item => item.citations));
  const cited = result.results.filter(source => citedIds.has(source.id));
  const candidates = result.results.filter(source => !citedIds.has(source.id));
  const audit=auditView({node,action,api},result.search_audit,citedIds);if(audit)host.append(audit);
  function appendSource(container, source) {
    const details = node('details');
    details.append(node('summary', source.content));
    const why=explanation(node,source);if(why)details.append(why);
    for (const evidence of source.evidence) {const quote=node('blockquote');quote.append(node('mark',evidence.quote,'evidence-highlight'));details.append(quote);}
    details.append(action('기록 열기', () => openRecord(source.record_id), 'link'));
    container.append(details);
  }
  if (cited.length) {
    const section = node('section', undefined, 'answer-sources');
    section.append(node('h3', '답변 근거'), node('p', '답변에서 실제로 인용한 기록입니다.', 'muted'));
    for (const source of cited) appendSource(section, source);
    host.append(section);
  }
  if (candidates.length) {
    const section = node('details', undefined, 'search-candidates');
    section.append(node('summary', `검색 후보 ${candidates.length}개`),
      node('p', '검색 중 찾았지만 답변에서 인용하지 않은 기록입니다. 질문과 관련이 적은 기록도 포함될 수 있습니다.', 'muted'));
    for (const source of candidates) appendSource(section, source);
    host.append(section);
  }
}
function renderConnections(host, links) {
  if (!links?.length) return;
  const section=node('section',undefined,'connections');
  section.append(node('h3','추정되는 연결'),node('p','기록 사이의 연결은 추론이며, 확인된 사실과 구분됩니다.','muted'));
  for (const link of links) {
    const box=node('div',undefined,'memory');
    box.append(node('p',link.explanation));
    if(link.identity_uncertain)box.append(node('p','같은 이름의 인물을 연결했습니다. 동명이인일 수 있습니다.','muted'));
    for(let i=0;i<link.evidence.length;i++) {
      const m=link.evidence[i]; box.append(node('p',m.content));
      for(const e of m.evidence) box.append(node('blockquote',e.quote));
      box.append(action('연결된 원문 확인',()=>openRecord(link.records[i]),'link'));
    }
    box.append(action('이 연결 해제',async()=>{await api('/relations/'+link.id,'DELETE');box.remove();clearAnswer();notice('연결을 해제했습니다. 같은 근거로 다시 만들지 않습니다.');},'secondary'));
    section.append(box);
  }
  host.append(section);
}
function clearAnswer(){ $('answer').replaceChildren();$('answer').hidden=true; }
function setTab(name){tab=name;for(const el of document.querySelectorAll('.tab'))el.hidden=el.id!==name;for(const b of document.querySelectorAll('[data-tab]')){b.classList.toggle('active',b.dataset.tab===name);if(b.dataset.tab===name)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');}$('heading').textContent={chat:'AI 대화',records:'나의 기록',questions:'기억에 질문하기',trash:'휴지통',failures:'처리 실패 목록'}[name];if(authorized&&name==='failures')loadFailures().catch(e=>notice(e.message,true));if(authorized&&['records','trash'].includes(name))loadList(name==='trash').catch(e=>notice(e.message,true));}
function resetEditor(){editing=null;$('editor-title').textContent='오늘, 무엇을 기억할까요?';$('save').textContent='기록 저장';$('record-text').value='';const d=new Date();d.setMinutes(d.getMinutes()-d.getTimezoneOffset());$('reference-time').value=d.toISOString().slice(0,16);$('char-count').textContent='0 / 4,000';}
async function loadList(trash=false, append=false){
  const c=trash?trashCursor:cursor;const data=await api('/records?state='+(trash?'trash':'active')+(append&&c?'&cursor='+encodeURIComponent(c):''));
  const target=$(trash?'trash-list':'record-list');if(!append)target.replaceChildren();
  if(!data.items.length&&!append)target.append(node('p',trash?'휴지통이 비어 있습니다.':'첫 기록을 남겨 보세요. 당신의 경험이 이곳에 쌓입니다.','empty'));
  for(const r of data.items){const row=node('div',undefined,'record');const meta=node('div',undefined,'meta');meta.append(node('span',new Date(r.updated_at).toLocaleString('ko-KR')),node('span',statuses[r.status]||r.status,'badge '+(r.status==='failed'?'failed':'')));row.append(meta,node('p',r.preview,'preview'));const buttons=node('div',undefined,'actions');
    if(trash){row.append(node('p',new Date(r.purge_at).toLocaleDateString('ko-KR')+'까지 복원 가능','muted'));buttons.append(action('복원',async()=>{await api('/records/'+r.id+'/restore','POST',{});clearAnswer();await loadList(true);notice('복원했습니다. 기억을 다시 정리합니다.');}),action('영구 삭제',async()=>{if(!confirm('원문과 수정 이력을 영구 삭제할까요? 복원할 수 없습니다.'))return;await api('/records/'+r.id+'/purge','DELETE');clearAnswer();$('detail').hidden=true;await loadList(true);notice('영구 삭제했습니다.');},'danger'));}
    else {buttons.append(action('열기',()=>openRecord(r.id)),action('수정',()=>edit(r.id)),action('삭제',async()=>{if(!confirm('기록을 삭제하면 이 기록을 근거로 쓴 AI 답변과 인용도 영구 삭제됩니다. 나머지 대화는 남습니다. 계속할까요?'))return;await api('/records/'+r.id,'DELETE');clearAnswer();$('detail').hidden=true;if(editing?.id===r.id)resetEditor();await loadList();notice('휴지통으로 옮겼습니다. 30일 안에 복원할 수 있습니다.');},'link'));if(r.status==='failed')buttons.append(action('재시도',async()=>{await api('/records/'+r.id+'/retry','POST',{});await loadList();}));}
    row.append(buttons);target.append(row);
  }if(trash)trashCursor=data.next_cursor;else cursor=data.next_cursor;$(trash?'trash-more':'more').hidden=!data.next_cursor;
}
async function edit(id){const r=await api('/records/'+id);editing=r;setTab('records');$('editor-title').textContent='기록 수정 · 버전 '+r.version;$('save').textContent='수정 저장';$('record-text').value=r.text;let t='';if(r.reference_time){const d=new Date(r.reference_time);d.setMinutes(d.getMinutes()-d.getTimezoneOffset());t=d.toISOString().slice(0,16);}$('reference-time').value=t;$('char-count').textContent=r.text.length+' / 4,000';$('record-text').focus();}
async function openRecord(id){const r=await api('/records/'+id);setTab('records');const box=$('detail-content');box.replaceChildren(node('p',statuses[r.status]+' · 버전 '+r.version,'muted'),node('p',r.text,'source'));if(r.status==='failed')box.append(node('p','원문은 보존되어 있습니다. '+reason(r.error_code)[0]+' · '+reason(r.error_code)[1],'muted'));for(const m of r.memories){const item=node('div',undefined,'memory');item.append(node('p',m.content));for(const e of m.evidence)item.append(node('blockquote',e.quote));box.append(item);}if(r.processing_details?.provenance){const audit=node('details');audit.append(node('summary','날짜 근거·구간 처리 정보'),node('pre',JSON.stringify(r.processing_details,null,2)));box.append(audit);}const history=node('details');history.append(node('summary','수정 이력 보기'));history.addEventListener('toggle',async()=>{if(!history.open||history.dataset.loaded)return;try{const data=await api('/records/'+id+'/revisions');for(const v of data.items){const entry=node('div',undefined,'memory');entry.append(node('p','버전 '+v.version+' · '+new Date(v.created_at).toLocaleString('ko-KR'),'muted'),node('p',v.text,'source'));if(v.version!==r.version&&r.state==='active')entry.append(action('이 내용으로 되돌리기',async()=>{await api('/records/'+id+'/revert','POST',{version:v.version,expected_version:r.version});clearAnswer();await openRecord(id);await loadList();notice('새 버전으로 되돌렸습니다. 기억을 다시 정리합니다.');}));history.append(entry);}history.dataset.loaded='1';}catch(e){notice(e.message,true);}});box.append(history);if(r.facts_status==='pending')box.append(node('p','관계 검색 정보를 구축 중입니다.','muted'));const connections=await api('/relations?record_id='+encodeURIComponent(id));renderConnections(box,connections.items);$('detail').hidden=false;$('detail').scrollIntoView({behavior:'smooth',block:'start'});}
async function health(){const h=await api('/health');const generation=h.models.generation==='ready'?'연결됨':'준비 필요';const embedding=h.models.embedding==='ready'?'연결됨':'준비 필요';$('health').textContent=`기억 AI ${generation} · 검색 AI ${embedding}`;}
let processingBusy=false;
async function processingProgress(){
  if(processingBusy)return;processingBusy=true;
  try{
    const p=await api('/processing');
    $('processing-count').textContent='남은 작업 '+p.remaining+'개';
    $('processing-summary').textContent='대기 '+p.queued+' · 처리 중 '+p.processing+' · 완료 '+p.completed+' · 실패 '+p.failed+' / 전체 '+p.total+'개';
    $('processing-bar').max=p.total||1;$('processing-bar').value=p.completed+p.failed;
    const phases={extract:'기억 추출 중',embed:'검색 벡터 생성 중',save:'기억·관계 저장 중'};
    const running=p.recent.find(r=>r.id===p.current?.job_id);
    $('processing-current').textContent=running?(phases[p.current.phase]||'처리 중')+' · '+p.current.elapsed_seconds+'초\n'+running.preview:(p.remaining?'다음 기록 처리 대기 중':'대기 중인 작업이 없습니다.')+(p.failed?' 실패한 기록은 별도 재시도가 필요합니다.':'');
    const labels={running:'처리 중',succeeded:'완료',failed:'실패'};
    const errors={MODEL_UNAVAILABLE:'모델 연결 실패',MODEL_TIMEOUT:'응답 시간 초과',MODEL_TRUNCATED:'모델 응답 잘림',EXTRACTION_INVALID:'기억 추출 검증 실패'};
    if(p.worker_paused)$('processing-current').textContent='모델 연결 복구 대기 중 · 새 기록 처리를 잠시 멈췄습니다.';
    if(p.current?.chunks_total)$('processing-current').textContent+='\n구간 '+p.current.chunks_completed+' / '+p.current.chunks_total+' 완료 · '+p.current.chunk;
    $('processing-log').replaceChildren();
    for(const entry of p.recent){
      const li=node('li');li.append(node('span',new Date(entry.updated_at).toLocaleTimeString('ko-KR')+' · '+labels[entry.status],entry.status==='failed'?'processing-error':''),node('p',entry.preview));
      if(entry.status==='failed')li.append(node('small',errors[entry.error_code]||'처리 실패 · 원문은 보존됩니다.'));
      $('processing-log').append(li);
    }
    if(!p.recent.length)$('processing-log').append(node('li','아직 처리 이력이 없습니다.'));
    $('processing-updated').textContent=new Date().toLocaleTimeString('ko-KR')+' 갱신 · 3초 간격';
  }catch(e){$('processing-updated').textContent='갱신 실패 · 표시된 수치는 이전 상태입니다. '+e.message;}
  finally{processingBusy=false;}
}
let failedItems=[], retryBusy=false;
const failureReasons={
  MODEL_UNAVAILABLE:['모델 통신 오류','기억 AI 또는 검색 AI와 통신하지 못했습니다. 서버가 연결된 상태에서 재처리하세요.'],
  MODEL_TIMEOUT:['응답 시간 초과','정해진 시간 안에 모델 응답을 받지 못했습니다. 모델 부하를 확인하고 재처리하세요.'],
  EXTRACTION_INVALID:['처리 결과 오류 · 상세 미확인','기존 코드는 추출 검증·응답 잘림·벡터 오류 등 여러 예외를 이 코드로 저장했습니다. 이 기록의 정확한 원인은 저장된 코드만으로 확정할 수 없습니다.'],
  EVIDENCE_MISMATCH:['원문 근거 불일치','AI가 선택한 근거가 원문 또는 처리 대상 구간과 일치하지 않습니다.'],
  INVALID_EXTRACTION_SCHEMA:['추출 형식 검증 실패','구조화된 기억이 필드 규칙을 위반했습니다. 아래 진단 정보에서 필드와 규칙을 확인하세요.'],
  INTERNAL_PROCESSING_ERROR:['내부 처리 오류','분류되지 않은 처리 오류입니다. 단계와 시도 이력을 확인해야 합니다.'],
  MODEL_HTTP_ERROR:['모델 서버 응답 오류','모델 서버가 오류 상태를 반환했습니다. 서버 상태를 확인하세요.'],
  MODEL_TRUNCATED:['모델 응답 잘림','AI가 일부 구간의 처리를 끝내지 못했습니다. 완료된 구간은 보관되며 나머지를 재처리할 수 있습니다.'],
  CONTEXT_LIMIT:['모델 입력 길이 초과','자동 분할 후에도 일부 구간이 처리 가능한 길이를 넘었습니다. 원문은 보존되며 재처리할 수 있습니다.'],
  MODEL_INVALID_JSON:['AI 응답 형식 오류','AI 응답을 구조화된 기억으로 읽지 못했습니다. 재처리해 주세요.'],
  EMBEDDING_NOT_CONFIGURED:['검색 모델 설정 누락','임베딩 모델 설정을 먼저 확인해야 합니다.']
};
function reason(code){return failureReasons[code]||['처리 오류 · 상세 미확인','저장된 정보만으로 원인을 설명할 수 없습니다. 원문은 보존되어 있습니다.'];}
async function loadFailures(){
  failedItems=(await api('/failures')).items;
  const selected=$('failure-filter').value, counts={};
  for(const item of failedItems)counts[item.error_code]=(counts[item.error_code]||0)+1;
  $('failure-filter').replaceChildren(new Option('전체 원인',''));$('failure-groups').replaceChildren();
  for(const [code,count] of Object.entries(counts)){
    $('failure-filter').append(new Option(reason(code)[0]+' · '+count+'개',code));
    $('failure-groups').append(action(reason(code)[0]+' '+count+'개',()=>{$('failure-filter').value=code;renderFailures();}));
  }
  if(Object.hasOwn(counts,selected))$('failure-filter').value=selected;
  renderFailures();
}
function visibleFailures(){return failedItems.filter(r=>!$('failure-filter').value||r.error_code===$('failure-filter').value);}
function renderFailures(){
  const items=visibleFailures();$('failure-summary').textContent='현재 실패 '+failedItems.length+'개 · 표시 '+items.length+'개';
  $('failure-retry').disabled=retryBusy||!items.length;$('failure-retry').textContent='표시된 실패 '+items.length+'개 재처리';
  $('failure-list').replaceChildren();
  for(const r of items){
    const [title,description]=reason(r.error_code), box=node('article',undefined,'record');
    box.append(node('h3',title),node('p',description),node('p',new Date(r.updated_at).toLocaleString('ko-KR')+' · 버전 '+r.version+' · '+(r.error_code||'UNKNOWN'),'muted'),node('p',r.text,'source'));
    const diagnostics=node('details');diagnostics.append(node('summary','진단 정보·재처리 이력'),node('pre',JSON.stringify(r.history||r.diagnostic||{message:'과거 상세 정보 없음'},null,2)));box.append(diagnostics);
    const buttons=node('div',undefined,'actions');buttons.append(action('이 기록 재처리',()=>retryFailures([r.job_id])),action('원문·수정 이력 확인',()=>openRecord(r.record_id)));box.append(buttons);$('failure-list').append(box);
  }
  if(!items.length)$('failure-list').append(node('p','표시할 실패 기록이 없습니다.','empty'));
}
async function retryFailures(ids){
  if(retryBusy)return;retryBusy=true;$('failure-retry').disabled=true;
  try{
    let queued=0,skipped=0;
    for(let i=0;i<ids.length;i+=500){const result=await api('/failures/retry','POST',{job_ids:ids.slice(i,i+500)});queued+=result.queued;skipped+=result.skipped;}
    $('failure-notice').textContent=queued+'개를 재처리 대기열에 추가했습니다.'+(skipped?' 이미 변경되거나 처리 중인 '+skipped+'개는 건너뛰었습니다.':'');
    clearAnswer();await Promise.all([loadFailures(),processingProgress()]);
  }finally{retryBusy=false;renderFailures();}
}
$('show-failures').addEventListener('click',()=>setTab('failures'));
$('failure-filter').addEventListener('change',renderFailures);
$('failure-refresh').addEventListener('click',()=>loadFailures().catch(e=>notice(e.message,true)));
$('failure-retry').addEventListener('click',()=>retryFailures(visibleFailures().map(r=>r.job_id)).catch(e=>notice(e.message,true)));
$('record-form').addEventListener('submit',async e=>{e.preventDefault();$('save').disabled=true;try{const data={text:$('record-text').value,reference_time:$('reference-time').value?new Date($('reference-time').value).toISOString():null};if(editing){data.expected_version=editing.version;await api('/records/'+editing.id,'PATCH',data);}else await api('/records','POST',data);resetEditor();clearAnswer();$('detail').hidden=true;await loadList();notice('원문을 저장했습니다. AI가 기억을 정리합니다.');}catch(err){notice(err.message,true);}finally{$('save').disabled=false;}});
let correctionEnabled=true;
$('question').addEventListener('input',()=>{correctionEnabled=true;});
$('question-form').addEventListener('submit',async e=>{e.preventDefault();$('ask').disabled=true;clearAnswer();const started=performance.now();const timer=setInterval(()=>notice('기록 검색·답변 생성 중 · '+((performance.now()-started)/1000).toFixed(1)+'초'),250);notice('기록 검색·답변 생성 중 · 0.0초');try{const d=new Date();const today=[d.getFullYear(),String(d.getMonth()+1).padStart(2,'0'),String(d.getDate()).padStart(2,'0')].join('-');const data={question:$('question').value,today:today,correction_enabled:correctionEnabled};correctionEnabled=true;if($('date-from').value||$('date-to').value)data.filters={date_from:$('date-from').value||null,date_to:$('date-to').value||null};const result=await api('/answers','POST',data);const box=$('answer');box.hidden=false;box.append(node('h2','기록에 근거한 답변'),node('p','검색·답변 완료 · '+((performance.now()-started)/1000).toFixed(1)+'초','chat-timing'));if(result.clarification)box.append(node('p',result.clarification));if(result.facts_pending)box.append(node('p','일부 기록의 검색 정보를 구축 중이므로 결과가 완전하지 않을 수 있습니다.','muted'));if(result.status==='unsupported_intent')box.append(node('p','전체 횟수나 순위를 집계하는 질문은 아직 지원하지 않습니다. 특정 경험을 질문해 주세요.'));else if(result.status==='insufficient_evidence')box.append(node('p','답변을 뒷받침할 충분한 기록을 찾지 못했습니다.'));for(const item of result.items){const p=node('p',undefined,'answer-item');p.append(node('span',item.claim_kind==='inference'?'추정되는 연결 · ':'기록의 사실 · ','badge'));p.append(document.createTextNode(' '+item.text));for(const cid of item.citations){const source=result.results.find(r=>r.id===cid);if(source)p.append(action('원문 확인',()=>openRecord(source.record_id),'citation'));}box.append(p);}if(result.filters.date_from||result.filters.date_to)box.append(node('p',`적용 기간: ${result.filters.date_from||'제한 없음'} ~ ${result.filters.date_to||'제한 없음'}`,'muted'));const correction=correctionView(node,result.query_correction,{originalQuery:data.question,evidence:result.results||[],retry:action('원문으로만 다시 검색',()=>{ $('question').value=data.question; $('date-from').value=data.filters?.date_from||''; $('date-to').value=data.filters?.date_to||''; correctionEnabled=false;$('question-form').requestSubmit();})});if(correction)box.append(correction);renderAnswerSources(box,result);renderConnections(box,result.connections);notice('');}catch(err){notice(err.message,true);}finally{clearInterval(timer);$('ask').disabled=false;}});
for(const b of document.querySelectorAll('[data-tab]'))b.addEventListener('click',()=>setTab(b.dataset.tab));
$('new-record').addEventListener('click',resetEditor);$('refresh').addEventListener('click',()=>loadList().catch(e=>notice(e.message,true)));$('more').addEventListener('click',()=>loadList(false,true).catch(e=>notice(e.message,true)));$('trash-more').addEventListener('click',()=>loadList(true,true).catch(e=>notice(e.message,true)));$('close-detail').addEventListener('click',()=>{$('detail').hidden=true;});$('check-health').addEventListener('click',()=>health().catch(e=>notice(e.message,true)));$('record-text').addEventListener('input',()=>{$('char-count').textContent=$('record-text').value.length+' / 4,000';});
$('today').textContent=new Date().toLocaleDateString('ko-KR',{year:'numeric',month:'long',day:'numeric'});resetEditor();
try{const token=new URLSearchParams(location.hash.slice(1)).get('token');history.replaceState(null,'',location.pathname);const session=token?await api('/session','POST',{token}):await api('/session');csrf=session.csrf;authorized=true;await Promise.all([loadList(),health(),processingProgress()]);}catch(e){notice(e.message,true);}
setInterval(()=>{if(authorized&&tab==='records'&&!cursor)loadList().catch(()=>{});},5000);

setInterval(()=>{if(authorized&&!document.hidden)processingProgress();},3000);
document.addEventListener("visibilitychange",()=>{if(authorized&&!document.hidden)processingProgress();});

setupChat({api,node,action,notice,today:()=>{const d=new Date();return [d.getFullYear(),String(d.getMonth()+1).padStart(2,'0'),String(d.getDate()).padStart(2,'0')].join('-');}});
setTab('chat');
if (authorized) document.querySelector('[data-tab="chat"]').click();
