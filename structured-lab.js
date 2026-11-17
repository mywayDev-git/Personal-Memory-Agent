'use strict';
const allCandidates=$('#all-candidates');
const memoryMode=$('#summary-mode'),answerPipeline=$('#answer-pipeline'),eventGraphMode=$('#event-graph-mode');
const retrievalStrategy=$('#retrieval-strategy'),chunkSearchMode=$('#chunk-search-mode');
function selectedAnswerRoute(){
 const frozen=$('#stage').value==='answer'&&runList.find(run=>run.id===$('#frozen-run').value);
 return frozen?.config?.route||$('#route').value;
}
const structuredConfig=config;
config=function(){
 const c=structuredConfig();
 if(c.route!=='R0-Full'&&allCandidates.checked)c.all_candidates=true;
 if(!['R0-Full','K1','A1'].includes(c.route)&&retrievalStrategy.value!=='single')c.retrieval_strategy=retrievalStrategy.value;
 if(['K1','A1'].includes(c.route))c.chunk_search_mode=chunkSearchMode.value;
 if(c.route==='A1'){c.attention_candidate_limit=Number($('#attention-candidates').value);c.attention_max_calls=Number($('#attention-max-calls').value);}
 if(answerPipeline.value!=='existing')c.answer_pipeline=answerPipeline.value;
 if(['M1','G1','G2'].includes(c.route)){
  if(c.route==='G1'&&eventGraphMode.value!=='existing')c.event_graph_mode=eventGraphMode.value;
  if(['G1','G2'].includes(c.route)||memoryMode.value!=='generated')c.summary_mode='extractive-v1';
  if(c.route==='M1'&&memoryMode.value==='extractive-only')c.excerpt_only=true;
  const text=$('#summary-instruction').value.trim();
  if(text)c.summary_prompt_text=text;
  c.summary_force=$('#summary-force').checked;
  const instruction=$('#metadata-instruction').value.trim();
  if(instruction)c.metadata_prompt_text=instruction;
  c.metadata_force=$('#metadata-force').checked;
 }
 return c;
};
const metadataControls=document.createElement('section');metadataControls.hidden=true;metadataControls.innerHTML='<label>검색 메타정보 지침<textarea id="metadata-instruction" rows="3" placeholder="요약에서 검색어·개체·관계·유효기간과 정확한 근거 구절을 추출합니다."></textarea></label><label class="inline"><input type="checkbox" id="metadata-force"> 저장된 메타정보 색인 다시 만들기</label>';$('#summary-controls').append(metadataControls);
try{$('#metadata-instruction').value=JSON.parse(localStorage.getItem(settingsKey)||'{}').metadata_prompt_text||'';}catch{}
$('#metadata-instruction').onchange=saveSettings;
try{allCandidates.checked=JSON.parse(localStorage.getItem(settingsKey)||'{}').all_candidates===true;}catch{}
allCandidates.onchange=()=>{saveSettings();renderStageHelp();};
try{const saved=JSON.parse(localStorage.getItem(settingsKey)||'{}');chunkSearchMode.value=['original','expanded','filtered'].includes(saved.chunk_search_mode)?saved.chunk_search_mode:'filtered';}catch{}
chunkSearchMode.onchange=()=>{saveSettings();renderStageHelp();};
try{const saved=JSON.parse(localStorage.getItem(settingsKey)||'{}');eventGraphMode.value=['linked-v2','claim-v1'].includes(saved.event_graph_mode)?saved.event_graph_mode:'existing';answerPipeline.value=['scoped-v1','chronological-v1','question-digest-v1','evidence-aligned-v1','evidence-verified-v1'].includes(saved.answer_pipeline)?saved.answer_pipeline:'existing';memoryMode.value=saved.excerpt_only===true?'extractive-only':saved.summary_mode==='extractive-v1'?'extractive-v1':'generated';retrievalStrategy.value=saved.retrieval_strategy==='decomposed-v1'?'decomposed-v1':'single';}catch{}
memoryMode.onchange=answerPipeline.onchange=eventGraphMode.onchange=retrievalStrategy.onchange=()=>{renderStageHelp();saveSettings();};
$('#frozen-run').addEventListener('change',()=>renderStageHelp());
const attentionControls=document.createElement('section');
attentionControls.id='attention-controls';attentionControls.hidden=true;attentionControls.className='control-grid';
attentionControls.innerHTML='<label>질문별 후보 구간 수<input id="attention-candidates" type="number" min="4" max="200" value="40"></label><label>구간 선택 요청 상한<input id="attention-max-calls" type="number" min="1" max="512" value="64"></label><p class="hint">기존 Qwen이 질문과 원문을 함께 읽어 역할을 선택합니다. 전용 Cross-encoder와 Attention 가중치 추출은 사용하지 않습니다. 전체 구간 조회 또는 전체 목록 질문은 후보 수 제한을 넘겨 모든 범위를 검토합니다.</p>';
$('#stage-help').before(attentionControls);
try{const saved=JSON.parse(localStorage.getItem(settingsKey)||'{}');$('#attention-candidates').value=saved.attention_candidate_limit??40;$('#attention-max-calls').value=saved.attention_max_calls??64;}catch{}
for(const id of ['attention-candidates','attention-max-calls'])$('#'+id).onchange=saveSettings;
const structuredHelp=renderStageHelp;
renderStageHelp=function(){structuredHelp();const graph=$('#route').value==='G1',multi=$('#route').value==='G2',enabled=graph||multi||$('#route').value==='M1',linked=graph&&eventGraphMode.value==='linked-v2';
 const stage=$('#stage').value,answerOnly=stage==='answer',full=selectedAnswerRoute()==='R0-Full',chunk=['K1','A1'].includes(selectedAnswerRoute());
 const attention=selectedAnswerRoute()==='A1';attentionControls.hidden=!attention;
 for(const id of ['attention-candidates','attention-max-calls'])$('#'+id).disabled=answerOnly;
 $('#top-k-label').textContent=attention?'핵심 구간 수':chunk?'Top-K 구간':'Top-K 원문';
 $('#all-candidates-caption').textContent=attention?'전체 구간 검토':chunk?'전체 구간 조회':'전체 출처 조회';
 $('#chunk-search-mode-control').hidden=!chunk;chunkSearchMode.disabled=answerOnly;
 $('#event-graph-mode-control').hidden=!graph;
 metadataControls.hidden=!enabled;$('#all-candidates-control').hidden=full;$('#summary-mode-control').hidden=!enabled||graph||multi;
 $('#answer-pipeline-control').hidden=!['answer','end_to_end'].includes(stage);
 $('#retrieval-strategy-control').hidden=full||chunk||!['retrieve','end_to_end'].includes(stage);
 $('#route').disabled=eventGraphMode.disabled=memoryMode.disabled=answerOnly;
 answerPipeline.disabled=$('#answer-pipeline-control').hidden;
 retrievalStrategy.disabled=$('#retrieval-strategy-control').hidden;
 allCandidates.disabled=full||answerOnly;
 if(!allCandidates.disabled&&allCandidates.checked&&!attention)$('#top-k').disabled=true;
 if(attention)$('#top-k').disabled=answerOnly;
 if(!enabled&&!allCandidates.disabled&&allCandidates.checked&&$('#stage').value!=='extract')$('#stage-help').textContent+=' 접근 가능한 모든 출처의 검색 후보를 조회합니다.';
 if(enabled){$('#top-k').disabled=$('#stage').value==='answer'||allCandidates.checked;$('#summary-controls').hidden=false;for(const id of ['method','structure-version'])$('#'+id).closest('label').hidden=true;for(const id of ['method','structure-version','extract-prompt','extract-text','query-prompt'])$('#'+id).disabled=true;$('#stage option[value="extract"]').textContent='전체 요약·메타정보 색인만';$('#stage option[value="end_to_end"]').textContent='전체 요약 → 전체 색인 완료 → 질문별 검색·답변';$('#stage-help').textContent=$('#stage').value==='retrieve'?'저장된 M1 요약·메타정보 색인을 사용해 검색합니다.':$('#stage').value==='answer'?'저장된 M1 검색 결과의 요약 근거로 답변합니다.':'모든 요약을 저장하고 검색어·개체·관계·유효기간 색인을 마친 뒤 질문을 순서대로 검색·답변합니다. 원본은 검색·답변에 전달하지 않습니다.';
 if(graph){
  $('#stage option[value="extract"]').textContent='전체 발췌·사건 그래프 색인만';
  $('#stage option[value="end_to_end"]').textContent='전체 발췌·그래프 색인 → 질문별 검색·답변';
  $('#stage-help').textContent=$('#stage').value==='answer'?'저장된 G1 검색 범위에 따라 답변합니다.':allCandidates.checked
   ?'접근 가능한 모든 출처의 발췌문을 후보에 포함합니다. 사건 그래프 설명은 후보 순위에 반영합니다.'
   :'사건 설명으로 상위 그래프를 찾고 연결된 원문 발췌로 답변합니다. 기존 발췌·개체·관계 색인을 재사용합니다.';
  if(eventGraphMode.value==='claim-v1')$('#stage-help').textContent+=' 검증된 Claim을 사건과 발췌 순위에 반영합니다.';
  if(linked)$('#stage-help').textContent+=' 같은 사건의 연결 근거를 저장하고, 답변 전에 별개 사건의 문장을 걸러냅니다.';
 }else if(multi){
  $('#stage option[value="extract"]').textContent='전체 발췌·다중 대상 색인만';
  $('#stage option[value="end_to_end"]').textContent='전체 발췌·색인 → 다중 대상·사실 검색·답변';
  $('#stage-help').textContent=$('#stage').value==='answer'?'저장된 G2 근거로 답변합니다.':'인물·프로젝트·대상·독립 Claim·사건 설명과 발췌문을 함께 검색합니다. 사건 후보 밖의 근거도 유지하며, 동일 이름을 자동 병합하지 않습니다. 기존 메타정보와 발췌 색인을 재사용합니다.';
 }else if(memoryMode.value==='extractive-only'){
  $('#stage option[value="extract"]').textContent='전체 발췌·임베딩만';
  $('#stage option[value="end_to_end"]').textContent='전체 발췌 → 전체 임베딩 → 질문별 검색·답변';
  $('#stage-help').textContent=$('#stage').value==='answer'?'저장된 발췌문 의미 검색 결과로 답변합니다.':'같은 발췌문을 재사용하고 의미 유사도로 검색합니다. 키워드·개체·관계·유효기간 색인은 사용하지 않습니다.';
 }else if(memoryMode.value==='extractive-v1'){
  $('#stage option[value="extract"]').textContent='전체 발췌·키워드 색인만';
  $('#stage option[value="end_to_end"]').textContent='전체 발췌 → 전체 색인 → 질문별 검색·답변';
  $('#stage-help').textContent=$('#stage').value==='retrieve'?'저장된 발췌문과 키워드 색인으로 검색합니다.':$('#stage').value==='answer'?'저장된 발췌 검색 결과로 답변합니다.':'구절 번호를 골라 발췌문을 저장하고 키워드 색인을 만든 뒤 질문을 처리합니다.';
 }
 if(allCandidates.checked&&!allCandidates.disabled&&$('#stage').value!=='extract'){
  if(!graph)$('#stage-help').textContent+=' 접근 가능한 모든 출처의 요약 구간을 조회합니다.';
  if(answerPipeline.value==='existing')$('#stage-help').textContent+=' 답변 단계에서는 전체 후보를 입력 한도에 맞춰 나눠 검토합니다.';
 }
 }
 if(chunk){
  $('#summary-controls').hidden=true;
  for(const id of ['method','structure-version'])$('#'+id).closest('label').hidden=true;
  for(const id of ['method','structure-version','extract-prompt','extract-text'])$('#'+id).disabled=true;
  $('#stage option[value="extract"]').textContent='전체 원문 구간·키워드 색인만';
  $('#stage option[value="end_to_end"]').textContent='전체 원문 구간 색인 → 구간 검색·필터 → 답변';
  $('#stage-help').textContent=attention?'K1과 같은 원문 구간 색인을 재사용한 뒤 질문별 직접·연결·조건·정정·충돌 근거를 선택합니다. 전체 구간 검토를 선택해도 답변에는 필요한 핵심 구간과 연결 근거만 전달합니다. 무관한 구간은 제외하고 불명확한 구간은 보류합니다. 연결 구간은 한 단계만 확장하며 요청 상한에 도달하면 미검토 후보를 완료로 기록하지 않습니다.':'모든 원문을 문장 경계 우선으로 나눠 키워드를 색인합니다. Top-K는 원문 구간에 적용하며, 증강 검색어는 현재 색인에서 확인한 표현만 사용합니다. 색인과 질문 증강은 모델을 호출하지 않습니다.';
  if(attention)$('#stage option[value="end_to_end"]').textContent='전체 구간 색인 → 질문별 근거 선택·연결 → 답변';
 }
 if(answerOnly){
  $('#top-k').disabled=$('#query-prompt').disabled=$('#method').disabled=$('#structure-version').disabled=true;
  const frozen=runList.find(run=>run.id===$('#frozen-run').value);
  $('#stage-help').textContent=frozen
   ?'저장된 '+routeRunName(frozen.config)+' 결과에서 같은 질문의 근거를 불러옵니다. 답변 단계만 실행합니다.'
   :'검색 결과가 저장된 실행을 선택하면 그 근거를 고정해 답변 단계만 실행합니다.';
 }
 if(!retrievalStrategy.disabled&&retrievalStrategy.value==='decomposed-v1')
  $('#stage-help').textContent+=' 복합 질문은 최대 네 항목으로 나눠 각각 검색한 뒤 근거를 통합합니다. Top-K는 각 항목에 적용합니다.';
 if(!answerPipeline.disabled){
  if(full&&answerPipeline.value!=='existing'&&!answerOnly)
   $('#stage-help').textContent='접근 가능한 전체 원문을 후보로 확보한 뒤 선택한 답변 방식으로 처리합니다.';
  if(answerPipeline.value==='scoped-v1')$('#stage-help').textContent+=' 질문의 대상과 조건을 정하고 이미 검색된 후보에서 해당 근거를 고릅니다.';
  if(answerPipeline.value==='chronological-v1')$('#stage-help').textContent+=' 검색된 근거를 기록 시각순으로 모아 한 번에 답변합니다. 입력 한도를 넘긴 문항은 실행 오류로 기록합니다.';
  if(answerPipeline.value==='question-digest-v1')$('#stage-help').textContent+=' 각 검색 근거를 질문에 맞춰 요약하고 남긴 요약을 시간순으로 모아 답변합니다.';
  if(['evidence-aligned-v1','evidence-verified-v1'].includes(answerPipeline.value))
   $('#stage-help').textContent+=' 저장된 검색 범위에서 질문 항목별 근거와 부족한 정보를 연결합니다. 불명확·미검토 근거를 구분하며 추가 검색은 수행하지 않습니다.'+
    (answerPipeline.value==='evidence-verified-v1'?' 생성된 주장 전체를 같은 로컬 모델로 다시 대조하고 지지를 확인한 주장을 답변에 남깁니다.':'');
 }
};
const structuredNative=nativeHTML;
nativeHTML=function(extraction,...args){if(['K1','A1'].includes(extraction?.config?.route))return chunkIndexHTML(extraction);const html=structuredNative(extraction,...args);if(!['M1','G1','G2'].includes(extraction?.config?.route))return html;return EventGraphViewer.panel(extraction)+html+(extraction.structured_indexes||[]).map(i=>`<article class="collection"><button class="button" data-structured-index="${esc(i.index_id)}">검색어·개체·관계·유효기간 보기</button><div class="structured-index-result"></div></article>`).join('');};
function scopedDetails(title,data){return data?`<details><summary>${esc(title)}</summary><pre>${esc(JSON.stringify(data,null,2))}</pre></details>`:'';}
function fullCandidateScopeHTML(s){
 return '<p class="hint">전체 출처 조회 · '+s.selected_sources.length+'개 출처 · '+s.evidence.length+'개 후보</p>'+
  scopedDetails('구조화 단위가 없어 원문 청크로 보완한 출처',s.unstructured_source_fallback);
}
function compoundSearchHTML(s){
 const trace=s?.compound_search;
 if(!trace)return '';
 const caption=trace.status==='DECOMPOSED'
  ?'하위 질문 '+trace.branches.length+'개 검색 · 통합 근거 '+trace.evidence_count+'개'
  :'원질문으로 검색 · '+(trace.status==='UNSAFE_SPLIT'?'조건을 보존한 분해를 확인할 수 없음':trace.status==='INVALID_PLAN'?'분해 결과 형식 오류':'분해 대상 아님');
 return '<p class="hint">'+esc(caption)+'</p>'+trace.branches.map(branch=>
  '<details><summary>'+esc(branch.id+' · '+branch.focus)+'</summary><p>'+esc(branch.query_used)+'</p>'+
  '<p>검색 근거 '+branch.candidate_count+'개 · 통합에 남은 근거 '+branch.evidence_ids.length+'개</p>'+
  '<p>'+esc(branch.evidence_ids.join(', '))+'</p>'+(branch.claim_search?'<p>일치한 Claim '+branch.claim_search.matched_count+'건</p>':'')+'</details>').join('');
}
function claimSearchHTML(s){const trace=s?.event_graph_search?.claim_search;if(!trace)return '';return '<p class="hint">G1+Claim · 일치 '+trace.matched_count+'건 · 반환 발췌에 연결된 일치 Claim '+trace.returned_claim_ids.length+'건</p>'+scopedDetails('Claim 검색 순위와 연결',trace);}
const structuredSearch=searchHTML;
searchHTML=function(s,a){if(s?.config?.route==='A1')return attentionSearchHTML(s,a);if(s?.config?.route==='K1')return chunkSearchHTML(s,a);const compound=compoundSearchHTML(s);if(!['M1','G1','G2'].includes(s?.config?.route))return compound+(s?.config?.all_candidates?fullCandidateScopeHTML(s):'')+structuredSearch(s,a)+(compound&&s.config.route!=='M0'?MemoryUsage.html(s.token_usage):'');return compound+`<div class="meta"><strong>${s.config.route==='G1'?'G1 · 사건 그래프 검색':s.config.excerpt_only?'원문 발췌만 · 의미 검색':'M1 · 구조화 요약 검색'}</strong><span>${time(s.elapsed_ms)}</span></div>${s.event_graph_search?.linking?'<p class="hint">사건 연결·근거 확인 · 연결 '+s.event_graph_search.linking.linked_count+'건 · 여러 발췌가 연결된 그래프 '+s.event_graph_search.linking.multi_excerpt_graph_count+'개</p>':''}${claimSearchHTML(s)}${EventGraphViewer.panel(s)}${scopedDetails('사건 그래프 설명·순위·근거 연결',s.event_graph_search)}${scopedDetails('질문 분석·검색 범위',s.scoped_query)}${scopedDetails('검색별 후보',s.scoped_search)}<p class="hint">${s.config.route==='G1'?(s.config.all_candidates?'접근 가능한 모든 출처를 조회하고 사건 그래프 설명을 순위에 반영했습니다.':'사건 설명으로 그래프를 고른 뒤 연결된 발췌문을 검색했습니다.'):s.config.excerpt_only?'질문과 발췌문의 의미 유사도로 순위를 정했습니다.':'요약 키워드·벡터 + 개체·관계 검색 · 관계 확장 1단계 · 명시된 날짜의 유효기간 검사'}</p>${s.config.all_candidates?`<p class="hint">전체 후보 범위 · ${s.selected_sources.length}개 출처 · ${s.evidence.length}개 구간${a||s.config.answer_pipeline==='chronological-v1'?'':' · 모델 판단은 답변 단계에서 진행'}</p>`:''}${s.evidence.map(e=>`<article class="collection"><strong>${esc(e.evidence_id)} · ${esc(e.source_id)}</strong><p class="source-quote">${esc(e.text)}</p></article>`).join('')||'<p class="notice">검색 가능한 요약 근거가 없습니다.</p>'}<details><summary>${s.config.excerpt_only?'발췌문 의미 검색 기록':'검색어·개체·관계·날짜별 검색 기록'}</summary><pre>${esc(JSON.stringify(s.structured_trace,null,2))}</pre></details>${MemoryUsage.html(s.token_usage)}`;};
const structuredAnswer=answerHTML;
function eventScopeHTML(a){
 const scope=a?.event_scope;
 if(!scope)return '';
 return '<p class="hint">사건 범위 확인 · 후보 '+scope.candidate_count+'개 검토 · 문장 '+scope.excluded.length+'개 제외</p>'+
  scopedDetails('별개 사건으로 제외한 문장과 근거',scope);
}
function candidateReviewHTML(a){
 if(a?.evidence_interpretation)return '<p class="hint">'+esc(answerPipelineName(a.config.answer_pipeline))+' · 인용 아래 근거 선택 내역에서 항목별 충족 상태와 주장 판정을 펼쳐 볼 수 있습니다.</p>';
 if(a?.question_digest){
  const digest=a.question_digest;
  return '<p class="hint">질문별 핵심 요약 답변 · 근거 '+digest.reviewed_count+'/'+digest.retrieved_count+'개 검토 · 핵심 요약 '+digest.notes.length+'개를 한 요청으로 입력</p>'+
   scopedDetails('답변에 전달한 시간순 핵심 요약',digest.notes)+scopedDetails('요약 묶음별 검토·토큰 기록',digest.batches);
 }
 if(a?.chronological_input){
  const texts=new Map(a.evidence_used.map(e=>[e.evidence_id,e.text]));
  const timeline=a.chronological_input.map(e=>({...e,text:texts.get(e.evidence_id)}));
  return '<p class="hint">시간순 근거 답변 · 근거 '+timeline.length+'개를 한 요청으로 입력</p>'+scopedDetails('모델에 전달한 시간순 근거',timeline);
 }
 const focus=a?.evidence_focus;
 if(focus?.mode==='scoped-v1')return '<p class="hint">범위 지정·근거 답변 · 후보 '+focus.reviewed_count+'/'+focus.candidate_count+'개 검토 · 답변 근거 '+a.evidence_used.length+'개</p>'+scopedDetails('답변 항목과 질문 조건',a.answer_question_plan)+scopedDetails('후보별 근거 선택과 제외 이유',focus)+scopedDetails('답변 항목별 판단',a.scoped_response);
 if(focus?.status!=='ALL_CANDIDATES_REVIEWED')return '';
 return '<p class="hint">전체 후보 '+focus.candidate_count+'개 검토 · 답변에 사용한 근거 '+a.evidence_used.length+'개'+(focus.candidate_batches>1?' · '+focus.candidate_batches+'개 묶음으로 검토':'')+'</p>';
}
answerHTML=function(a){return ['M1','G1','G2'].includes(a?.config?.route)?eventScopeHTML(a)+candidateReviewHTML(a)+structuredAnswer({...a,config:{...a.config,route:'M0'}})+MemoryUsage.html(a.token_usage):candidateReviewHTML(a)+structuredAnswer(a)+(a?.config?.route!=='M0'&&a?.token_usage?MemoryUsage.html(a.token_usage):'');};

function graphProgressHTML(run){
 if(run.config?.route!=='G1'||!run.summary_batch)return '';
 const batch=run.summary_batch,graph=batch.graph_indexing;
 const completed=graph?.completed||0,total=graph?.total??batch.total_contexts??0;
 const status=graph?.status||'WAITING';
 const percent=total?Math.round(completed/total*1000)/10:0;
 const label=({RUNNING:'생성 중',COMPLETED:'완료',ERROR:'실패',CANCELLED:'중단',WAITING:'앞 단계 완료 대기'})[status]||status;
 return '<section data-graph-progress class="graph-build-progress" aria-label="사건 그래프 생성 진행률">'+
  '<strong>3단계 · 사건 그래프 생성 · '+esc(label)+'</strong>'+
  '<p><b>'+completed+' / '+total+'</b> 기억 범위 · '+percent+'% · 남은 범위 '+Math.max(0,total-completed)+'개</p>'+
  '<progress max="'+Math.max(1,total)+'" value="'+completed+'" aria-label="사건 그래프 준비 진행률"></progress>'+
  '<p class="hint">기억 범위별로 발췌문을 사건에 연결하고 그래프 검색을 준비합니다.</p>'+
  (graph?.error?'<p class="notice error">'+esc(graph.error)+'</p>':'')+'</section>';
}
const structuredMonitor=renderExecutionMonitor;
renderExecutionMonitor=function(run){structuredMonitor(run);const panel=$('#execution-monitor');if(!panel||!run)return;const existing=panel.querySelector('[data-usage-report]');if(existing)existing.remove();const el=document.createElement('section');el.dataset.usageReport='';el.innerHTML=MemoryUsage.html(run.token_usage);panel.append(el);if(['M1','G1','G2'].includes(run.config.route)&&run.summary_batch){const b=run.summary_batch,index=b.indexing,section=panel.querySelector('[data-summary-batch]');if(section){section.innerHTML=`<strong>1단계 · 전체 요약 ${b.completed_sources}/${b.total_sources}개 완료</strong><div class="index-progress"><strong>2단계 · ${run.config.excerpt_only?'발췌문 임베딩':'메타정보 색인'} ${index?.completed||0}/${index?.total??b.total_sources}개 · ${esc(({RUNNING:'진행 중',COMPLETED:'완료',ERROR:'실패',CANCELLED:'중단'})[index?.status]||'요약 완료 대기')}</strong><progress max="${Math.max(1,index?.total||b.total_sources)}" value="${index?.completed||0}" aria-label="구조화 색인 진행률"></progress></div>${graphProgressHTML(run)}<p class="hint">${run.config.route==='G1'?'4':'3'}단계 · 질문별 검색·답변 ${b.status==='COMPLETED'?'— 전체 준비 완료':(['ERROR','CANCELLED'].includes(b.status)?'— 준비 실패·중단으로 실행하지 않았습니다.':run.config.route==='G1'?'— 사건 그래프 생성이 끝나면 시작합니다.':'— 전체 요약과 색인이 완료될 때까지 대기합니다.')}</p>${index?.active_attempt?.attempt>1?`<p class="hint">추출 결과 검증 보완 ${index.active_attempt.attempt}/${index.active_attempt.max_attempts}회</p>`:''}${b.error?`<p class="notice error">${esc(b.error)}</p>`:''}${MemoryUsage.failure(index?.validation_failure,esc)}`;}}};
const structuredGuide=renderSelectionGuide;
renderSelectionGuide=function(){structuredGuide();if($('#route').value==='M1'){$('#selection-guide .guide-common').textContent='M1은 요약 본문에 검색어·개체·관계·유효기간을 연결합니다. 전체 요약과 색인이 완료된 뒤 질문을 처리하며, 답변에는 요약문만 전달합니다.';const cards=$('#selection-guide .guide-cards').children;selectionCatalog.groups.forEach((g,i)=>{if(['method','structure-version'].includes(g.key)&&cards[i])cards[i].hidden=true;});}};
const structuredRouteGroup=selectionCatalog.groups.find(g=>g.key==='route');if(structuredRouteGroup)structuredRouteGroup.items.push({id:'M1',name:'M1 · 구조화 요약 검색',summary:'전체 요약 → 검색어·개체·관계·유효기간 색인 → 질문별 검색·답변',detail:'요약에 근거를 연결한 검색용 메타정보를 만듭니다.',change:'요약 본문 검색에 개체·관계·유효기간을 추가',example:'특정 날짜의 프로젝트 담당자 검색',limit:'동명 개체는 출처별로 구분하며 불명확한 유효기간은 제외하지 않습니다.'});
if(structuredRouteGroup)structuredRouteGroup.items.push({id:'G1',name:'G1 · 사건 그래프 검색',summary:'사건 설명 검색 → 연결된 발췌문 검색 → 답변',detail:'같은 출처에서 확인된 사건·장소를 기준으로 발췌문을 연결합니다.',change:'발췌문에 앞서 사건 설명의 의미를 검색',example:'이사 엘리베이터 예약에 연결된 신청 기록 찾기',limit:'상위 그래프 세 개를 우선 조회하거나, 전체 출처의 발췌문을 평가할 수 있습니다.'});
document.addEventListener('click',async event=>{const b=event.target.closest('[data-structured-index]');if(!b)return;try{const data=await artifact(b.dataset.structuredIndex);b.parentElement.querySelector('.structured-index-result').innerHTML=MemoryUsage.index(data,esc);}catch(e){notify(e.message);}});
$('#route').addEventListener('change',()=>renderStageHelp());

function chunkIndexHTML(extraction){
 return '<p class="hint">원문 구간·키워드 색인 · 모델 호출 0회 · 구간 위치는 원문 기준입니다.</p>'+
  extraction.records.map(record=>'<article class="collection"><strong>'+esc(record.source_id)+'</strong>'+
   '<p>'+record.chunk_count+'개 구간 · '+(record.reused?'색인 재사용':'색인 준비 완료')+'</p>'+
   '<button class="button" data-raw-chunk-index="'+esc(record.index_id)+'">구간과 키워드 보기</button>'+
   '<div data-raw-chunk-detail></div></article>').join('');
}

function chunkSearchHTML(search,answer){
 const trace=search.chunk_keyword_search;
 if(!trace)return '<p class="empty">구간 검색 기록이 없습니다.</p>';
 return '<div class="meta"><strong>K1 · 원문 구간 키워드 검색</strong><span>'+time(search.elapsed_ms)+'</span></div>'+
  '<p class="hint">색인 '+trace.total_chunks+'개 구간 · 검색 후보 '+trace.matched_chunks+'개 · 선택 '+search.evidence.length+
   '개 구간 · 모델·임베딩 검색 호출 0회</p>'+
  '<p>원질문 · '+esc(search.query_original)+'</p>'+
  '<details open><summary>질문별 검색어 · '+trace.branches.length+'회 검색</summary>'+
  trace.branches.map(branch=>'<p><strong>'+esc(branch.id)+'</strong> '+esc(branch.query_used)+
   ' · 후보 '+branch.candidate_count+'개</p>').join('')+'</details>'+
  '<p class="hint">조건으로 제외 '+trace.filter.excluded.length+'개 · 범위를 확정할 수 없어 유지 '+trace.filter.uncertain_kept.length+'개</p>'+
  scopedDetails('키워드 증강과 조건 필터 기록',trace)+providedScopeHTML(search,answer)+
  search.evidence.map(item=>'<article class="collection"><strong>'+esc(item.evidence_id+' · '+item.source_id)+'</strong>'+
   '<p class="source-quote">'+esc(item.text)+'</p><small>원문 v'+item.revision+' · ['+item.start+', '+item.end+')</small></article>').join('')+
  MemoryUsage.html(search.token_usage);
}

const chunkSpans=spansFor;
spansFor=function(result,sourceId){
 if(!['K1','A1'].includes(result?.stages?.retrieval?.config?.route))return chunkSpans(result,sourceId);
 return result.stages.retrieval.evidence.filter(item=>item.source_id===sourceId).map(item=>({...item,role:'evidence'}));
};

function evidenceInterpretationDetailsHTML(answer,openNodes){
 const t=answer?.evidence_interpretation;
 if(!t)return '';
 if(t.status==='ARITHMETIC_BYPASS')return '<p class="hint">'+esc(t.note)+'</p>';
 const label=v=>({full:'충족',partial:'부분 충족',missing:'부족',conflict:'충돌',
  support:'지지 근거',refute:'반대 근거',context:'연결·조건 근거',uncertain:'연결 불명확',
  different_scope:'다른 사건·대상',SUPPORTED:'지지 확인',REFUTED:'반박됨',
  INSUFFICIENT:'근거 불충분',CONFLICT:'충돌',NOT_REVIEWED:'미검토',
  COMPLETED:'검토 완료',INCOMPLETE:'일부 미검토',NOT_REQUESTED:'검증 선택 안 함',
  NO_CLAIMS:'검증할 주장 없음',PENDING:'검증 대기'})[v]||v;
 const manifest=new Map((t.evidence_manifest||[]).map(s=>[s.sentence_id,s]));
 let proofIndex=0;
 const node=(id,css)=>'<details class="'+css+'" data-interpretation-node="'+esc(id)+'"'+(openNodes?.has(id)?' open':'')+'>';
 const proofHTML=ids=>(ids||[]).map(id=>{
  const s=manifest.get(id);
  return node('proof-'+proofIndex++,'interpretation-proof')+'<summary>'+esc(id)+(s?' · '+esc(s.source_id):'')+'</summary>'+
   (s?'<blockquote>'+esc(s.text)+'</blockquote><p class="hint">위치 ['+esc(s.start)+', '+esc(s.end)+') · '+esc(s.origin||'저장 근거')+'</p>':'<p class="hint">해당 문장 본문은 연결된 검색 산출물에서 확인할 수 있습니다.</p>')+'</details>';
 }).join('');
 const coverage=t.coverage||[],drafts=t.draft_claims||[],checks=new Map((t.claim_checks||[]).map(c=>[c.claim_id,c]));
 return node('panel','interpretation-panel')+'<summary>항목별 근거·충분성·최종 주장 검토</summary>'+
  '<p class="hint">저장된 검색 근거만 사용 · 검토 '+(t.scope?.reviewed_sentence_ids?.length||0)+'/'+(t.scope?.candidate_sentences||0)+'문장 · '+
  (t.scope?.complete?'범위 검토 완료':'미검토 범위 있음')+' · 최종 주장 '+esc(label(t.verification?.status||'PENDING'))+'</p>'+
  '<p class="hint">판정은 같은 로컬 모델의 근거 대조 결과입니다. 출처 신뢰성과 현실의 사실 여부를 독립적으로 검증했다는 뜻은 아닙니다.</p>'+
  '<div class="interpretation-table-scroll"><table class="interpretation-table"><thead><tr><th>질문 항목</th><th>최종 충족 상태</th><th>부족한 정보</th></tr></thead><tbody>'+
  coverage.map(slot=>'<tr><td>'+esc(slot.need)+'</td><td>'+esc(label(slot.final_sufficiency||slot.sufficiency))+'</td><td>'+esc((slot.missing_information||[]).join(' · ')||'기록 없음')+'</td></tr>').join('')+
  '</tbody></table></div>'+
  coverage.map(slot=>node('slot-'+slot.id,'interpretation-slot')+'<summary>'+esc(slot.id+' · '+slot.need)+' — 근거 연결 보기</summary>'+
   '<p class="hint">필요한 정보: '+esc((slot.required_information||[]).join(' · ')||'항목 자체의 근거')+'</p>'+
   (t.observations||[]).filter(n=>n.slot_id===slot.id).map(n=>'<article><p><strong>'+esc(label(n.relation))+'</strong> · '+esc(n.finding)+'</p><p class="hint">'+esc(n.reason)+'</p>'+proofHTML(n.sentence_ids)+'</article>').join('')+'</details>').join('')+
  node('claims','interpretation-claims')+'<summary>답변 주장 '+drafts.length+'개 · 판정·제외 사유</summary>'+
  drafts.map(claim=>{
   const check=checks.get(claim.id),retained=(t.final_claims||[]).some(c=>c.id===claim.id);
   return '<article><p><strong>'+esc(claim.id)+'</strong> · '+esc(claim.text)+'</p><p class="hint">'+
    (check?esc(label(check.verdict))+' · '+(retained?'최종 답변에 남김':'최종 답변에서 제외')+' · '+esc(check.reason):'최종 검증 선택 안 함 · '+(retained?'답변에 사용':'미사용'))+
    '</p>'+(check?.unsupported_parts?.length?'<p class="hint">미지원 부분: '+esc(check.unsupported_parts.join(' · '))+'</p>':'')+
    proofHTML(uniqueInterpretationIds([...(claim.sentence_ids||[]),...(check?.support_ids||[]),...(check?.counter_ids||[])]))+
    (claim.calculation?scopedDetails('코드 계산 입력·결과',claim.calculation):'')+'</article>';
  }).join('')+'</details>'+
  ((t.synthesis_omitted||[]).length?scopedDetails('입력 한도로 종합에서 빠진 해석 항목',t.synthesis_omitted):'')+
  (t.warnings?.length?scopedDetails('처리 제한·형식 확인 기록',t.warnings):'')+
  scopedDetails('미검토 문장 ID',t.scope?.unreviewed_sentence_ids||[])+
  scopedDetails('단계별 요청·누적 예산', {limits:t.limits,accounting:t.accounting,requests:t.requests})+
  (t.error?'<p class="notice error">'+esc(t.error)+'</p>':'')+'</details>';
}
function uniqueInterpretationIds(ids){return [...new Set(ids)];}
const chunkMonitor=renderExecutionMonitor;
renderExecutionMonitor=function(run){
 chunkMonitor(run);
 const panel=$('#execution-monitor'),batch=run?.chunk_keyword_batch;
 if(!panel)return;
 panel.querySelector('[data-chunk-keyword-progress]')?.remove();
 if(batch){
  const section=document.createElement('section');
  section.dataset.chunkKeywordProgress='';section.className='index-progress';
  section.innerHTML='<strong>원문 구간·키워드 색인 '+batch.completed_sources+'/'+batch.total_sources+'개 원문</strong>'+
   '<progress max="'+Math.max(1,batch.total_sources)+'" value="'+batch.completed_sources+'" aria-label="원문 구간 키워드 색인 진행률"></progress>'+
   '<p class="hint">구간 '+batch.total_chunks+'개 · 재사용 원문 '+batch.reused_sources+'개 · 색인 모델 호출 0회</p>';
  panel.prepend(section);
 }
};
if(structuredRouteGroup)structuredRouteGroup.items.push({
 id:'K1',name:'K1 · 원문 구간 키워드 검색',summary:'원문 전체 구간 색인 → 키워드 증강 → 구간 검색·조건 필터',
 detail:'원문을 구간으로 나누고 원문에서 확인한 키워드를 저장합니다.',change:'Top-K 선택 단위를 원문 구간으로 변경',
 example:'같은 실험의 변경 이유와 결과가 있는 구간 찾기',limit:'확정되지 않은 대상·기간은 후보로 유지합니다. 증강 표현은 색인에 존재할 때만 사용합니다.'
});
document.addEventListener('click',async event=>{
 const button=event.target.closest('[data-raw-chunk-index]');
 if(!button)return;
 const detail=button.parentElement.querySelector('[data-raw-chunk-detail]');
 try{
  const index=await artifact(button.dataset.rawChunkIndex);
  detail.innerHTML=index.units.map(unit=>'<details><summary>['+unit.start+', '+unit.end+') · '+esc(unit.id)+'</summary>'+
   '<p class="source-quote">'+esc(unit.text)+'</p><p class="hint">키워드 · '+esc(unit.keywords.map(keyword=>keyword.text).join(' · '))+'</p></details>').join('');
 }catch(error){detail.textContent=error.message;}
});

function attentionSearchHTML(search,answer){
 const trace=search.question_attention;
 if(!trace)return '<p class="notice">A1 선택 기록이 없습니다.</p>';
 const roleNames={direct:'직접 근거',support:'연결 근거',condition:'조건·미확인',correction:'정정',conflict:'충돌',irrelevant:'질문과 무관',unrelated:'별개 사건',unknown:'관련 범위 불명확'};
 const byId=new Map(trace.decisions.map(row=>[row.chunk_id,row]));
 return '<div class="meta"><strong>A1 · 질문 조건부 원문 선택</strong><span>'+time(search.elapsed_ms)+'</span></div>'+
 '<p class="hint">기존 Qwen 기반 선택 · 전용 Cross-encoder와 Attention 가중치 추출은 사용하지 않습니다.</p>'+
 '<p>초기 후보 '+trace.initial_candidates+'개 · 추가 연결 '+trace.expansion.length+'개 · 검토 '+trace.reviewed_count+'개 · 선택 '+search.evidence.length+'개</p>'+
 '<p>이번 선택 요청 '+trace.model_calls+'회 · 캐시 재사용 '+trace.cache_hits+'묶음 · 전체 범위 검토 '+(trace.scope_complete?'완료':'아님')+'</p>'+
 '<p class="hint">불명확하여 보류 '+(trace.deferred_ids?.length||0)+'개 · 무관하여 제외 '+(trace.excluded_irrelevant_ids?.length||0)+'개 · 전체 검토 후에도 답변 근거는 별도로 선택합니다.</p>'+
 scopedDetails('후보별 역할·연결·제외와 처리 기록',trace)+
 search.evidence.map(item=>'<article class="collection"><strong>'+esc(item.evidence_id+' · '+item.source_id)+'</strong>'+
 '<p class="hint">'+esc(roleNames[byId.get(item.unit_id)?.role]||'미확인')+' · 관련성 순위 '+(byId.get(item.unit_id)?.score??0)+'/3</p>'+
 '<p class="source-quote">'+esc(item.text)+'</p><small>원문 v'+item.revision+' · ['+item.start+', '+item.end+')</small></article>').join('')+
 scopedDetails('K1 후보 검색 기록',search.chunk_keyword_search)+MemoryUsage.html(search.token_usage);
}
const attentionAnswerHTML=answerHTML;
answerHTML=function(answer){return (answer?.attention_packing?scopedDetails('A1 입력 예산·누락 근거',answer.attention_packing):'')+attentionAnswerHTML(answer);};
if(structuredRouteGroup)structuredRouteGroup.items.push({
 id:'A1',name:'A1 · 질문 조건부 원문 선택',summary:'K1 구간 후보 → 질문별 역할 선택 → 연결 근거 1단계 → 답변',
 detail:'설치된 Qwen을 선택기로 재사용합니다. 직접 근거·연결·조건·정정·충돌을 구분합니다.',
 change:'키워드 순위 뒤에 질문 조건부 선택 추가',example:'견적 총액과 이미 지급한 금액을 함께 선택',
 limit:'전용 Cross-encoder가 아니며 선택 점수는 Attention 가중치나 정답 확률이 아닙니다.'
});

// G2 uses the existing workbench controls and details layout.
if(structuredRouteGroup)structuredRouteGroup.items.push({id:'G2',name:'G2 · 다중 대상·사실 검색',summary:'인물·프로젝트·대상·독립 Claim·사건·발췌 검색 결합',detail:'기존 발췌·메타정보 색인을 재사용하고, 사건 후보로 제한하지 않는 검색 경로를 추가합니다.',change:'사건 설명은 순위 신호로 사용하고 독립 사실과 대상 검색을 함께 반영',example:'사건명이 없는 작업 환경 선호, 프로젝트 담당자와 관련 문서 찾기',limit:'이름 일치는 동일인 확정이 아닙니다. 명시된 시간·부정·상태와 근거를 보존하며 의미 정답은 별도 검토합니다.'});
const multiAnchorSearchHTML=searchHTML;
searchHTML=function(s,a){const base=multiAnchorSearchHTML(s,a);return base+(s?.multi_anchor_search?scopedDetails('G2 · 검색 출발점과 근거 추적',s.multi_anchor_search):'');};
