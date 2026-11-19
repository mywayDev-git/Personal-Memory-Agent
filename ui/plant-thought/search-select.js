'use strict';
(()=>{
 const modes=window.PlantSearchModes;if(!modes)return;
 const key='plant-thought-search-mode-v1';let selected='R0';
 try{const saved=localStorage.getItem(key);if(modes.get(saved))selected=saved;}catch{}
 const container=document.querySelector('.chat-version-bar>div');if(!container)return;
 const label=document.createElement('label'),select=document.createElement('select'),description=document.createElement('span');
 label.textContent='기록 검색';label.htmlFor='chatSearchModeSelect';select.id='chatSearchModeSelect';select.setAttribute('aria-label','테스트할 기록 검색 방식');
 for(const mode of modes.modes){const option=document.createElement('option');option.value=mode.id;option.textContent=mode.label;select.append(option);}
 description.className='chat-search-description';description.id='chatSearchModeDescription';select.setAttribute('aria-describedby',description.id);
 container.append(label,select,description);
 window.PlantChatSearch=Object.freeze({current:()=>window.PlantTestMode?.enabled===true?selected:'legacy'});
 const busy=()=>typeof previewThreads!=='undefined'&&previewThreads.some(t=>!t.deletedAt&&t.messages.some(m=>m.kind==='assistant'&&m.status==='pending'&&!m.archived));
 function sync(){select.value=selected;select.disabled=busy();description.textContent=modes.get(selected).description+' 다음 질문부터 적용';}
 select.addEventListener('change',()=>{if(busy()){sync();return;}selected=select.value;try{localStorage.setItem(key,selected);}catch{}sync();});
 document.addEventListener('plant:test-mode-changed',sync);
 new MutationObserver(()=>{select.disabled=busy();}).observe(document.getElementById('conversation'),{childList:true,subtree:true});sync();
 window.PlantSearchResult=function(result){
  const trace=result.retrieval_trace;if(!trace)return null;
  const details=document.createElement('details');details.className='chat-search-result';details.dataset.testOnly='';
  const heading=document.createElement('summary');heading.textContent='기록 검색 · '+(modes.get(trace.mode)?.label||trace.mode)+' · '+(trace.status==='skipped'?'검색하지 않음':trace.status==='failed'?'실패':result.scope.retrieved_count+'개 근거');details.append(heading);
  const searches=trace.searches||[trace];
  for(const search of searches){
   const line=document.createElement('p');line.textContent=search.status==='failed'?'검색 실패: '+search.error:search.query?('검색어: '+search.query+' · 전체 '+(search.accessible_count??result.scope.accessible_count)+'개 중 '+(search.selected_source_ids?.length??0)+'개 원문 · '+(search.elapsed_ms??0)+'ms'):'이 요청에는 기록 검색을 실행하지 않았습니다.';details.append(line);
   if(search.preparation_reused!=null){const note=document.createElement('small');note.textContent=search.preparation_reused?(search.index_policy==='on_record_change'?'기록 변경 시 준비한 색인을 사용했습니다. 검색 중 색인 생성은 없습니다.':'준비된 색인을 재사용했습니다.'):'필요한 색인 준비를 포함해 실행했습니다.';details.append(note);}
   if(search.summary_expanded_to_originals){const note=document.createElement('p');note.textContent='검색에는 요약·발췌를 사용했고, 답변은 선택된 원문을 확인했습니다. Memory Lab의 요약만 답변 조건과는 다릅니다.';details.append(note);}
   if(search.retrieval_artifact_id){const link=document.createElement('a');link.href='/api/baseline/artifacts/'+search.retrieval_artifact_id;link.target='_blank';link.rel='noopener';link.textContent='검색 산출물 전체 보기 ↗';details.append(link);}
  }
  return details;
 };
})();
