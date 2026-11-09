'use strict';
const $=s=>document.querySelector(s),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let token,memories=[],editing=null,working=false;
function notice(text,error=false){$('#notice').textContent=text;$('#notice').classList.toggle('error',error);}
async function api(route,body){const r=await fetch('/api/baseline'+route,{...(body!==undefined?{method:'POST',headers:{'Content-Type':'application/json','X-Memory-Lab-Token':token},body:JSON.stringify(body)}:{})});const data=await r.json();if(data.token_usage)$('#token-usage').innerHTML=MemoryUsage.html(data.token_usage);if(!r.ok){if(data.index_validation)$('#token-usage').insertAdjacentHTML('afterbegin',MemoryUsage.failure(data.index_validation,esc));throw Error(data.error||'요청 실패');}return data;}
function config(){
 const route=$('#search-route').value,scope=$('#top-k').value,mode=$('#summary-mode').value;
 return {route,...(route==='M1'&&$('#answer-pipeline').value==='scoped-v1'?{answer_pipeline:'scoped-v1'}:{}),model:$('#model').value,...(route==='M1'&&mode!=='generated'?{summary_mode:'extractive-v1',...(mode==='extractive-only'?{excerpt_only:true}:{})}:{}),...(route==='M1'&&scope==='all'?{all_candidates:true}:{top_k:Number(scope)}),...($('#instruction').value.trim()?{summary_prompt_text:$('#instruction').value.trim()}:{})};}
function syncCandidateScope(){
 const enabled=$('#search-route').value==='M1';
 $('#summary-mode-control').hidden=!enabled;
 $('#answer-pipeline-control').hidden=!enabled;
 const allOption=$('#top-k option[value="all"]');
 allOption.disabled=!enabled;
 allOption.hidden=!enabled;
 if(!enabled&&$('#top-k').value==='all')$('#top-k').value='5';
}
$('#search-route').addEventListener('change',syncCandidateScope);
syncCandidateScope();
$('#summary-mode').addEventListener('change',invalidateSearch);
$('#answer-pipeline').addEventListener('change',()=>{$('#results').innerHTML='<p class="empty">선택한 방식으로 다시 검색해 주세요.</p>';});
function invalidateSearch(){ $('#results').innerHTML='<p class="empty">기억이 변경됐습니다. 다시 검색해 주세요.</p>';}
async function task(message,fn){if(working)return;working=true;for(const b of document.querySelectorAll('button,select,textarea'))b.disabled=true;notice(message);try{await fn();}catch(e){notice(e.message,true);}finally{working=false;for(const b of document.querySelectorAll('button,select,textarea'))b.disabled=false;await loadUsage().catch(()=>{});}}
async function loadUsage(){const d=await api('/summary-memory/usage');$('#usage-history > div').innerHTML=d.operations.map(o=>'<article><p class="meta">'+esc(new Date(o.created_at).toLocaleString('ko-KR'))+'</p>'+MemoryUsage.html(o)+'</article>').join('')||'<p class="hint">저장된 토큰 기록이 없습니다.</p>';}
function clearEdit(){editing=null;$('#source').value='';$('#input-heading').textContent='어떤 기록을 기억할까요?';$('#save').textContent='요약해 저장';$('#cancel-edit').hidden=true;}
function render(){
 $('#count').textContent=memories.length;$('#memories').innerHTML=memories.map(m=>`<article class="card memory" data-key="${esc(m.memory_key)}"><span class="tag">${m.excerpt_selection?'원문 발췌':'요약 기억'} · v${esc(m.revision)}</span><div class="summary-text">${esc(m.summary)}</div><p class="metrics">원본 ${m.metrics.original_tokens.toLocaleString()} → 요약 ${m.metrics.summary_tokens.toLocaleString()}토큰 · 원본 대비 ${(m.metrics.token_ratio*100).toFixed(1)}% · 요약 처리 ${(m.metrics.elapsed_ms/1000).toFixed(1)}초</p><p class="meta">${esc(new Date(m.updated_at).toLocaleString('ko-KR'))}</p>${m.structured_index?MemoryUsage.index({units:m.structured_index.cards,excerpt_manifest:m.structured_index.excerpt_manifest},esc):''}<div class="actions"><button data-action="original">원본 검토</button><button data-action="edit">원본 수정</button><button data-action="resummarize">원본으로 다시 만들기</button><button data-action="delete" class="danger">검색에서 삭제</button></div><details class="original" hidden><summary>별도 보관 원본 · 검색·답변에 사용하지 않음</summary><p></p></details></article>`).join('')||'<div class="card empty">아직 저장된 요약이 없습니다. 첫 기록을 입력해 주세요.</div>';
}
async function refresh(){const data=await api('/summary-memory');memories=data.memories;render();}
async function search(answer){if(!$('#search-form').reportValidity())return;await task(answer?'요약을 검색해 답변하는 중입니다…':'요약문을 검색하는 중입니다…',async()=>{
 const d=await api('/summary-memory/search',{query:$('#query').value,answer,config:config()}),a=d.answer;
 $('#results').innerHTML=(a?`<div class="answer-box">${esc(a.answer)}</div><p class="hint">요약문만 근거로 답변했습니다. 원본은 읽지 않았습니다.</p>${a.citation_errors.length?'<p class="error-text">인용 검사 실패 · 답변을 검토하세요.</p>':''}${a.citations.map(c=>`<p class="hint">${esc(c.evidence_id)} · 요약 인용 «${esc(c.quote)}»</p>`).join('')}`:'')+d.retrieval.evidence.map((e,i)=>`<article class="hit"><span class="tag">${i+1} · ${esc(e.evidence_id)} · 요약문</span><p>${esc(e.text)}</p></article>`).join('')+(!d.retrieval.evidence.length?'<p class="empty">검색 가능한 요약이 없습니다.</p>':'');const focus=a?.evidence_focus;
 if(d.retrieval.config.answer_pipeline==='scoped-v1'){
  const trace={question:d.retrieval.scoped_query,search:d.retrieval.scoped_search,evidence:focus,response:a?.scoped_response};
  $('#results').insertAdjacentHTML('afterbegin',`<p class="hint">범위 지정·근거 답변</p><details><summary>질문 범위·근거·답변 판단</summary><pre>${esc(JSON.stringify(trace,null,2))}</pre></details>`);
 }
 if(focus?.mode==='scoped-v1')notice('후보 '+focus.reviewed_count+'/'+focus.candidate_count+'개 검토 · 답변 근거 '+a.evidence_used.length+'개');
 else if(focus?.status==='ALL_CANDIDATES_REVIEWED')notice('전체 후보 '+focus.candidate_count+'개 검토 · 답변 근거 '+a.evidence_used.length+'개');
 else if(d.retrieval.config.all_candidates)notice('요약 후보 '+d.retrieval.evidence.length+'개를 찾았습니다.');
 else notice('요약 '+d.retrieval.selected_sources.length+'개를 찾았습니다.');
 });}
$('#save-form').addEventListener('submit',event=>{event.preventDefault();if(!$('#save-form').reportValidity())return;const current=editing,text=$('#source').value;task('원본을 보관하고 요약·검색 준비 중입니다…',async()=>{await api('/summary-memory/save',{text,...(current?{key:current.memory_key,expected:current.summary_artifact_id}:{}),config:config()});if($('#source').value===text)clearEdit();await refresh();invalidateSearch();notice('요약을 저장했습니다. 원본은 검토·재요약용으로 별도 보관했습니다.');});});
$('#cancel-edit').onclick=clearEdit;$('#search-form').onsubmit=e=>{e.preventDefault();search(false);};$('#answer').onclick=()=>search(true);$('#refresh').onclick=()=>task('저장된 요약을 불러오는 중입니다…',async()=>{await refresh();notice('저장된 요약을 불러왔습니다.');});
$('#memories').addEventListener('click',event=>{const button=event.target.closest('[data-action]');if(!button)return;const card=button.closest('[data-key]'),m=memories.find(m=>m.memory_key===card.dataset.key);if(!m)return;task('기억을 처리하는 중입니다…',async()=>{
 const action=button.dataset.action;
 if(action==='original'||action==='edit'){const d=await api('/summary-memory/original?key='+encodeURIComponent(m.memory_key));if(action==='original'){const detail=card.querySelector('details.original');detail.hidden=false;detail.open=true;detail.querySelector('p').textContent=d.source.text;notice('검토용 원본입니다. 검색·답변에 사용하지 않습니다.');}else{editing=m;$('#source').value=d.source.text;$('#input-heading').textContent='원본을 수정하고 다시 요약합니다.';$('#save').textContent='수정 후 요약 저장';$('#cancel-edit').hidden=false;$('#source').focus();$('#save-form').scrollIntoView({behavior:'smooth',block:'center'});notice('저장에 성공하면 새 요약으로 교체합니다.');}return;}
 if(action==='resummarize'){notice('보관된 원본으로 재요약하는 중입니다…');await api('/summary-memory/resummarize',{key:m.memory_key,expected:m.summary_artifact_id,config:config()});}
 if(action==='delete'){await api('/summary-memory/delete',{key:m.memory_key,expected:m.summary_artifact_id});if(editing?.memory_key===m.memory_key)clearEdit();}
 await refresh();invalidateSearch();notice(action==='delete'?'검색에서 제외했습니다. 보관된 기록은 유지됩니다.':'새 요약과 검색 준비를 완료했습니다.');
 });});
async function init(){try{const boot=await api('/bootstrap');token=boot.token;$('#model').innerHTML=boot.runtime.models.filter(m=>m.role==='generation').map(m=>`<option value="${esc(m.id)}">${esc(m.name)}</option>`).join('');await refresh();await loadUsage();notice('원본은 별도 보관하고, 요약문만 검색·답변에 사용합니다.');}catch(e){notice(e.message,true);}}
init();


