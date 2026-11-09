'use strict';
const allCandidates=$('#all-candidates');
const memoryMode=$('#summary-mode'),answerPipeline=$('#answer-pipeline');
const structuredConfig=config;
config=function(){const c=structuredConfig();if(c.route==='M1'){if(answerPipeline.value!=='existing')c.answer_pipeline=answerPipeline.value;if(allCandidates.checked)c.all_candidates=true;if(memoryMode.value!=='generated')c.summary_mode='extractive-v1';if(memoryMode.value==='extractive-only')c.excerpt_only=true;const text=$('#summary-instruction').value.trim();if(text)c.summary_prompt_text=text;c.summary_force=$('#summary-force').checked;const instruction=$('#metadata-instruction').value.trim();if(instruction)c.metadata_prompt_text=instruction;c.metadata_force=$('#metadata-force').checked;}return c;};
const metadataControls=document.createElement('section');metadataControls.hidden=true;metadataControls.innerHTML='<label>검색 메타정보 지침<textarea id="metadata-instruction" rows="3" placeholder="요약에서 검색어·개체·관계·유효기간과 정확한 근거 구절을 추출합니다."></textarea></label><label class="inline"><input type="checkbox" id="metadata-force"> 저장된 메타정보 색인 다시 만들기</label>';$('#summary-controls').append(metadataControls);
try{$('#metadata-instruction').value=JSON.parse(localStorage.getItem(settingsKey)||'{}').metadata_prompt_text||'';}catch{}
$('#metadata-instruction').onchange=saveSettings;
try{allCandidates.checked=JSON.parse(localStorage.getItem(settingsKey)||'{}').all_candidates===true;}catch{}
allCandidates.onchange=()=>{saveSettings();renderStageHelp();};
try{const saved=JSON.parse(localStorage.getItem(settingsKey)||'{}');answerPipeline.value=['scoped-v1','chronological-v1','question-digest-v1'].includes(saved.answer_pipeline)?saved.answer_pipeline:'existing';memoryMode.value=saved.excerpt_only===true?'extractive-only':saved.summary_mode==='extractive-v1'?'extractive-v1':'generated';}catch{}
memoryMode.onchange=answerPipeline.onchange=()=>{renderStageHelp();saveSettings();};
const structuredHelp=renderStageHelp;
renderStageHelp=function(){structuredHelp();const enabled=$('#route').value==='M1';
 for(const value of ['chronological-v1','question-digest-v1']){
  const option=answerPipeline.querySelector('option[value="'+value+'"]');
  option.disabled=memoryMode.value==='generated';
  if(option.disabled&&answerPipeline.value===value)answerPipeline.value='existing';
 }metadataControls.hidden=!enabled;$('#all-candidates-control').hidden=!enabled;$('#summary-mode-control').hidden=!enabled;$('#answer-pipeline-control').hidden=!enabled;allCandidates.disabled=$('#stage').value==='answer';if(enabled){$('#top-k').disabled=allCandidates.checked||allCandidates.disabled;$('#summary-controls').hidden=false;for(const id of ['method','structure-version'])$('#'+id).closest('label').hidden=true;for(const id of ['method','structure-version','extract-prompt','extract-text','query-prompt'])$('#'+id).disabled=true;$('#stage option[value="extract"]').textContent='전체 요약·메타정보 색인만';$('#stage option[value="end_to_end"]').textContent='전체 요약 → 전체 색인 완료 → 질문별 검색·답변';$('#stage-help').textContent=$('#stage').value==='retrieve'?'저장된 M1 요약·메타정보 색인을 사용해 검색합니다.':$('#stage').value==='answer'?'저장된 M1 검색 결과의 요약 근거로 답변합니다.':'모든 요약을 저장하고 검색어·개체·관계·유효기간 색인을 마친 뒤 질문을 순서대로 검색·답변합니다. 원본은 검색·답변에 전달하지 않습니다.';
 if(memoryMode.value==='extractive-only'){
  $('#stage option[value="extract"]').textContent='전체 발췌·임베딩만';
  $('#stage option[value="end_to_end"]').textContent='전체 발췌 → 전체 임베딩 → 질문별 검색·답변';
  $('#stage-help').textContent=$('#stage').value==='answer'?'저장된 발췌문 의미 검색 결과로 답변합니다.':'같은 발췌문을 재사용하고 의미 유사도로 검색합니다. 키워드·개체·관계·유효기간 색인은 사용하지 않습니다.';
 }else if(memoryMode.value==='extractive-v1'){
  $('#stage option[value="extract"]').textContent='전체 발췌·키워드 색인만';
  $('#stage option[value="end_to_end"]').textContent='전체 발췌 → 전체 색인 → 질문별 검색·답변';
  $('#stage-help').textContent=$('#stage').value==='retrieve'?'저장된 발췌문과 키워드 색인으로 검색합니다.':$('#stage').value==='answer'?'저장된 발췌 검색 결과로 답변합니다.':'구절 번호를 골라 발췌문을 저장하고 키워드 색인을 만든 뒤 질문을 처리합니다.';
 }
 if(answerPipeline.value==='scoped-v1'&&$('#stage').value!=='extract')$('#stage-help').textContent+=' 질문의 대상과 조건을 먼저 정하고, 원질문을 포함해 최대 세 번 검색한 뒤 같은 범위의 근거로 답변합니다.';
 if(answerPipeline.value==='chronological-v1'&&$('#stage').value!=='extract')
  $('#stage-help').textContent+=' 검색된 발췌문을 기록 시각순으로 모아 한 번에 답변합니다. 입력 한도를 넘긴 문항은 실행 오류로 기록합니다.';
 if(answerPipeline.value==='question-digest-v1'&&$('#stage').value!=='extract')
  $('#stage-help').textContent+=' 각 발췌문의 핵심을 질문에 맞춰 요약하고, 남긴 요약을 시간순으로 모두 묶어 답변합니다.';
 if(allCandidates.checked&&!allCandidates.disabled&&answerPipeline.value!=='chronological-v1')$('#stage-help').textContent+=' 검색 조건을 통과한 모든 요약 구간을 후보로 모아 답변 단계에서 검토합니다.';
 }};
const structuredNative=nativeHTML;
nativeHTML=function(extraction,...args){const html=structuredNative(extraction,...args);if(extraction?.config?.route!=='M1')return html;return html+(extraction.structured_indexes||[]).map(i=>`<article class="collection"><button class="button" data-structured-index="${esc(i.index_id)}">검색어·개체·관계·유효기간 보기</button><div class="structured-index-result"></div></article>`).join('');};
function scopedDetails(title,data){return data?`<details><summary>${esc(title)}</summary><pre>${esc(JSON.stringify(data,null,2))}</pre></details>`:'';}
const structuredSearch=searchHTML;
searchHTML=function(s,a){if(s?.config?.route!=='M1')return structuredSearch(s,a);return `<div class="meta"><strong>${s.config.excerpt_only?'원문 발췌만 · 의미 검색':'M1 · 구조화 요약 검색'}</strong><span>${answerPipelineName(s.config.answer_pipeline)} · ${time(s.elapsed_ms)}</span></div>${scopedDetails('질문 분석·검색 범위',s.scoped_query)}${scopedDetails('검색별 후보',s.scoped_search)}<p class="hint">${s.config.excerpt_only?'질문과 발췌문의 의미 유사도로 순위를 정했습니다.':'요약 키워드·벡터 + 개체·관계 검색 · 관계 확장 1단계 · 명시된 날짜의 유효기간 검사'}</p>${s.config.all_candidates?`<p class="hint">전체 후보 범위 · 요약 구간 ${s.evidence.length}개${a||s.config.answer_pipeline==='chronological-v1'?'':' · 모델 판단은 답변 단계에서 진행'}</p>`:''}${s.evidence.map(e=>`<article class="collection"><strong>${esc(e.evidence_id)} · ${esc(e.source_id)}</strong><p class="source-quote">${esc(e.text)}</p></article>`).join('')||'<p class="notice">검색 가능한 요약 근거가 없습니다.</p>'}<details><summary>${s.config.excerpt_only?'발췌문 의미 검색 기록':'검색어·개체·관계·날짜별 검색 기록'}</summary><pre>${esc(JSON.stringify(s.structured_trace,null,2))}</pre></details>${MemoryUsage.html(s.token_usage)}`;};
const structuredAnswer=answerHTML;
function candidateReviewHTML(a){
 if(a?.question_digest){
  const digest=a.question_digest;
  return '<p class="hint">질문별 핵심 요약 답변 · 발췌문 '+digest.reviewed_count+'/'+digest.retrieved_count+'개 검토 · 핵심 요약 '+digest.notes.length+'개를 한 요청으로 입력</p>'+
   scopedDetails('답변에 전달한 시간순 핵심 요약',digest.notes)+scopedDetails('요약 묶음별 검토·토큰 기록',digest.batches);
 }
 if(a?.chronological_input){
  const texts=new Map(a.evidence_used.map(e=>[e.evidence_id,e.text]));
  const timeline=a.chronological_input.map(e=>({...e,text:texts.get(e.evidence_id)}));
  return '<p class="hint">시간순 발췌 답변 · 발췌문 '+timeline.length+'개를 한 요청으로 입력</p>'+scopedDetails('모델에 전달한 시간순 발췌문',timeline);
 }
 const focus=a?.evidence_focus;
 if(focus?.mode==='scoped-v1')return '<p class="hint">범위 지정·근거 답변 · 후보 '+focus.reviewed_count+'/'+focus.candidate_count+'개 검토 · 답변 근거 '+a.evidence_used.length+'개</p>'+scopedDetails('후보별 근거 선택과 제외 이유',focus)+scopedDetails('답변 항목별 판단',a.scoped_response);
 if(focus?.status!=='ALL_CANDIDATES_REVIEWED')return '';
 return '<p class="hint">전체 후보 '+focus.candidate_count+'개 검토 · 답변에 사용한 요약 구간 '+a.evidence_used.length+'개'+(focus.candidate_batches>1?' · '+focus.candidate_batches+'개 묶음으로 검토':'')+'</p>';
}
answerHTML=function(a){return a?.config?.route==='M1'?candidateReviewHTML(a)+structuredAnswer({...a,config:{...a.config,route:'M0'}})+MemoryUsage.html(a.token_usage):structuredAnswer(a);};
const structuredMonitor=renderExecutionMonitor;
renderExecutionMonitor=function(run){structuredMonitor(run);const panel=$('#execution-monitor');if(!panel||!run)return;const existing=panel.querySelector('[data-usage-report]');if(existing)existing.remove();const el=document.createElement('section');el.dataset.usageReport='';el.innerHTML=MemoryUsage.html(run.token_usage);panel.append(el);if(run.config.route==='M1'&&run.summary_batch){const b=run.summary_batch,index=b.indexing,section=panel.querySelector('[data-summary-batch]');if(section){section.innerHTML=`<strong>1단계 · 전체 요약 ${b.completed_sources}/${b.total_sources}개 완료</strong><div class="index-progress"><strong>2단계 · ${run.config.excerpt_only?'발췌문 임베딩':'메타정보 색인'} ${index?.completed||0}/${index?.total??b.total_sources}개 · ${esc(({RUNNING:'진행 중',COMPLETED:'완료',ERROR:'실패',CANCELLED:'중단'})[index?.status]||'요약 완료 대기')}</strong><progress max="${Math.max(1,index?.total||b.total_sources)}" value="${index?.completed||0}" aria-label="구조화 색인 진행률"></progress></div><p class="hint">3단계 · 질문별 검색·답변 ${b.status==='COMPLETED'?'— 전체 준비 완료':(['ERROR','CANCELLED'].includes(b.status)?'— 준비 실패·중단으로 실행하지 않았습니다.':'— 전체 요약과 색인이 완료될 때까지 대기합니다.')}</p>${index?.active_attempt?.attempt>1?`<p class="hint">추출 결과 검증 보완 ${index.active_attempt.attempt}/${index.active_attempt.max_attempts}회</p>`:''}${b.error?`<p class="notice error">${esc(b.error)}</p>`:''}${MemoryUsage.failure(index?.validation_failure,esc)}`;}}};
const structuredGuide=renderSelectionGuide;
renderSelectionGuide=function(){structuredGuide();if($('#route').value==='M1'){$('#selection-guide .guide-common').textContent='M1은 요약 본문에 검색어·개체·관계·유효기간을 연결합니다. 전체 요약과 색인이 완료된 뒤 질문을 처리하며, 답변에는 요약문만 전달합니다.';const cards=$('#selection-guide .guide-cards').children;selectionCatalog.groups.forEach((g,i)=>{if(['method','structure-version'].includes(g.key)&&cards[i])cards[i].hidden=true;});}};
const structuredRouteGroup=selectionCatalog.groups.find(g=>g.key==='route');if(structuredRouteGroup)structuredRouteGroup.items.push({id:'M1',name:'M1 · 구조화 요약 검색',summary:'전체 요약 → 검색어·개체·관계·유효기간 색인 → 질문별 검색·답변',detail:'요약에 근거를 연결한 검색용 메타정보를 만듭니다.',change:'요약 본문 검색에 개체·관계·유효기간을 추가',example:'특정 날짜의 프로젝트 담당자 검색',limit:'동명 개체는 출처별로 구분하며 불명확한 유효기간은 제외하지 않습니다.'});
document.addEventListener('click',async event=>{const b=event.target.closest('[data-structured-index]');if(!b)return;try{const data=await artifact(b.dataset.structuredIndex);b.parentElement.querySelector('.structured-index-result').innerHTML=MemoryUsage.index(data,esc);}catch(e){notify(e.message);}});
$('#route').addEventListener('change',()=>renderStageHelp());
