'use strict';
// Static sample browsing only. No model/API calls or writes to the memory store.
(()=>{
  let collection=window.PlantArchiveSamples;
  if(!collection)return;
  const el=id=>document.getElementById(id);
  const collectionBar=document.querySelector('.archive-dataset-bar'),collectionStrip=document.createElement('div');
  collectionStrip.className='sample-collection-strip';collectionStrip.append(collectionBar);document.querySelector('body>header').prepend(collectionStrip);
  let sourceMap=new Map(collection.records.map(r=>[r.id,r]));
  let questionMap=new Map(collection.examples.map(q=>[q.id,q]));
  let profile=collection.default_profile,recordId=null,questionId=null,exampleMode='all',exampleQuery='',searchRecordId=null,detailRecordId=null;
  let detailContext=null;
  const archiveStorageKey='plant-thought-archive-samples-v1';
  let previousState;try{previousState=JSON.parse(sessionStorage.getItem(archiveStorageKey)||'null');}catch{}
  const normal=text=>String(text||'').normalize('NFKC').toLocaleLowerCase('ko-KR').replace(/\s+/g,' ').trim();
  const currentProfile=()=>collection.profiles.find(p=>p.id===profile);
  const currentQuestions=()=>collection.examples.filter(q=>q.profile===profile);
  const selectedRecord=()=>sourceMap.get(recordId);
  const selectedQuestion=()=>questionMap.get(questionId);
  const localTime=value=>value&&Number.isFinite(Date.parse(value))?new Intl.DateTimeFormat('ko-KR',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(value)):'기록 시각 없음';
  const actionName=action=>({answer:'답변 예시',partial_answer:'부분 답변',abstain:'확인 불가',clarify:'확인 질문',deny:'부정 확인',report_conflict:'기록 충돌'}[action]||'참고 예시');
  function textNode(tag,text,className){const node=document.createElement(tag);node.textContent=text;if(className)node.className=className;return node;}
  function makeButton(text,callback,className){const button=textNode('button',text,className);button.type='button';button.addEventListener('click',callback);return button;}
  function empty(target,title,text){target.replaceChildren();const box=document.createElement('div');box.className='archive-empty-state';box.append(textNode('strong',title),textNode('p',text));target.appendChild(box);}
  function remember(){try{sessionStorage.setItem(archiveStorageKey,JSON.stringify({version:1,profile,recordId,questionId,exampleMode,exampleQuery,selected,detailRecordId,detailContext,collectionId:collection.synthetic?'samples':'personal'}));}catch{}previewRemember();document.dispatchEvent(new CustomEvent('plant:archive-context',{detail:{profile,questionId}}));}
  const showAll=makeButton('원문 전체 보기',()=>{el('archiveInput').value='';document.dispatchEvent(new Event('plant:archive-show-all'));runSearch(true);},'archive-show-all');showAll.id='archiveShowAll';el('filters').append(showAll);
  function bodyExcerpt(body,query){
    const text=String(body),at=query?text.toLocaleLowerCase('ko-KR').indexOf(query.toLocaleLowerCase('ko-KR')):-1;
    const start=at<0?0:Math.max(0,at-12),end=Math.min(text.length,Math.max(start+120,at+query.length+45));
    return (start?'…':'')+text.slice(start,end)+(end<text.length?'…':'');
  }
  const baseSnapshot=previewSnapshot;
  previewSnapshot=function(){return {...baseSnapshot(),sampleArchive:{version:1,profile,recordId,questionId,exampleMode,exampleQuery,selected,detailRecordId,collectionId:collection.synthetic?'samples':'personal'}};};

  function renderInfo(){
    const p=currentProfile(),record=selectedRecord(),q=selectedQuestion();
    const facts=[['질문 예시 구분',p.label+(collection.synthetic?' · 가상 자료':' · 개인 자료함')],['전체 원문',collection.record_count+'개'],['질문·답변 예시',p.question_count+'개 · 항상 펼쳐 보기'],['기록 시각',record?localTime(record.created_at):'기록 선택 전']];
    if(q){facts.push(['선택 예시',q.id],['사례 기준 시각',localTime(q.reference_time)]);}
    const target=el('archiveDataFacts');target.replaceChildren();
    for(const [label,value]of facts){const row=document.createElement('div');row.append(textNode('dt',label),textNode('dd',value));target.appendChild(row);}
    const identity=el('archiveRecordIdentity');identity.replaceChildren();
    if(record){identity.append(textNode('span','기록 '+record.id+' · v'+record.revision));
      if(q){const supported=q.record_ids.includes(record.id);identity.append(textNode('span',supported?'선택 예시에 연결된 근거 기록 · 전체 검색에 포함':'전체 원문 검색에 포함된 기록','archive-scope-state'));}
    }else identity.append(textNode('span','날짜별 목록에서 기록을 선택해 주세요.'));
  }
  function openSource(id,{scroll=false}={}){
    const record=sourceMap.get(id);if(!record)return;
    recordId=id;archiveSearchActive=false;
    if(record.date)selectArchiveDate(record.date,false);else{renderInfo();renderExamples();}
    // Selecting a sample updates its context without leaving home or chat.
    if(scroll)el('archiveSidePanel').scrollIntoView({behavior:'smooth',block:'nearest'});
    remember();
  }
  function showFullSource(id,context=null){
    const record=sourceMap.get(id);if(!record)return;detailRecordId=id;
    detailContext=context&&typeof context.threadId==='string'&&Array.isArray(context.citations)&&(!context.recordId||context.recordId===id)?{...context,recordId:id}:null;
    openSource(id);el('detailTitle').textContent=record.title;el('detailBody').replaceChildren();
    for(const part of window.PlantRecordEvidence.segments(record,detailContext?.citations||[])){
      if(part.highlighted){const mark=textNode('mark',part.text,'record-evidence-highlight');mark.tabIndex=-1;mark.setAttribute('aria-label','대화에서 참고한 구간');el('detailBody').append(mark);}else el('detailBody').append(document.createTextNode(part.text));
    }
    const highlighted=!!el('detailBody').querySelector('mark');el('detailEvidenceNote').hidden=!detailContext;el('detailEvidenceNote').textContent=highlighted?'대화에서 참고한 구간을 표시했어요.':'현재 기록에서 일치하는 참고 구간을 찾지 못했어요.';
    el('detailBack').textContent=detailContext?'← 대화로 돌아가기':'← 서재 보관소로 돌아가기';
    el('detailDate').textContent=(record.date||'날짜 미상')+' · '+collection.profiles.find(p=>p.id===record.profile).label+(collection.synthetic?' · 가상 원문 · v':' · 개인 자료함 · v')+record.revision;
    go('recordDetail');remember();document.dispatchEvent(new CustomEvent('plant:record-opened'));
    if(highlighted)requestAnimationFrame(()=>{if(document.querySelector('.page.active')?.id!=='recordDetail'||detailRecordId!==id)return;const mark=el('detailBody').querySelector('mark');if(mark){const bounds=mark.getBoundingClientRect(),headerBottom=document.querySelector('body>header').getBoundingClientRect().bottom;if(bounds.top<headerBottom+16||bounds.bottom>window.innerHeight-16)mark.scrollIntoView({block:'center'});mark.focus({preventScroll:true});}});
  }
  returnFromRecord=function(){
    if(!detailContext){go('archive');return;}
    const origin=detailContext,thread=previewThreads.find(t=>t.id===origin.threadId&&!t.deletedAt);
    if(thread)previewOpenThread(thread.id);else{go('chat');previewToast('원래 대화를 찾을 수 없어 대화 목록으로 돌아왔어요.');}
    if(thread)requestAnimationFrame(()=>requestAnimationFrame(()=>{if(document.querySelector('.page.active')?.id==='chat'&&previewActiveId===thread.id){const scroll=el('chatScroll');if(scroll&&Number.isFinite(origin.scrollTop))scroll.scrollTop=origin.scrollTop;}}));
  };
  function focusQuestion(id){
    const q=questionMap.get(id);if(!q||q.profile!==profile)return;questionId=id;
    const first=q.record_ids.find(sourceId=>sourceMap.get(sourceId)?.profile===profile);
    if(first)openSource(first);else{renderInfo();renderExamples();remember();}
  }
  function useQuestion(q){
    focusQuestion(q.id);
    go('chat');
    const input=el('chatInput');input.value=q.question;
    document.dispatchEvent(new CustomEvent('plant:question-selected',{detail:{profile,questionId:q.id}}));
    input.dispatchEvent(new Event('input',{bubbles:true}));
    input.focus({preventScroll:true});
    input.setSelectionRange(input.value.length,input.value.length);
  }
  async function copyQuestion(q,button){
    try{await navigator.clipboard.writeText(q.question);button.textContent='복사했어요';previewToast('질문을 복사했어요. AI 요청은 실행하지 않았습니다.');}
    catch{previewToast('복사할 질문을 선택해 주세요.');const range=document.createRange();range.selectNodeContents(button.closest('.archive-qa-card').querySelector('.archive-question-text'));const selection=window.getSelection();selection.removeAllRanges();selection.addRange(range);}
  }
  function renderExamples(){
    const p=currentProfile(),all=currentQuestions(),query=normal(exampleQuery);
    const related=all.filter(q=>q.record_ids.includes(recordId));
    let visible=exampleMode==='related'?related:all;
    if(query)visible=visible.filter(q=>normal(q.question+' '+q.answer+' '+q.family+' '+q.id).includes(query));
    el('archiveExampleCount').textContent=String(visible.length);
    el('archiveAllExamples').setAttribute('aria-pressed',String(exampleMode==='all'));
    el('archiveRelatedExamples').setAttribute('aria-pressed',String(exampleMode==='related'));
    el('archiveRelatedExamples').textContent='선택 기록 관련 '+related.length;
    el('archiveExamplesScope').textContent=p.label+' '+all.length+'개 중 '+visible.length+'개 표시'+(exampleMode==='related'?' · 선택 기록의 명시적 근거 연결':' · 질문과 답변 모두 펼침');
    const list=el('archiveExampleList'),scroll=list.scrollTop;list.replaceChildren();
    if(!visible.length){empty(list,'해당하는 예시가 없어요',exampleMode==='related'?'이 기록에 직접 연결된 질문이 없습니다. 전체 예시에서 다른 질문을 볼 수 있어요.':'검색어를 바꾸거나 비워서 전체 예시를 확인해 보세요.');return;}
    for(const q of visible){
      const card=document.createElement('article');card.className='archive-qa-card'+(q.id===questionId?' is-selected':'');card.setAttribute('role','listitem');card.dataset.questionId=q.id;
      const variantName={base:'기본',paraphrase:'질문 바꿈',distractor:'방해 기록 추가',contrast:'조건 변경'}[q.variant];
      const head=document.createElement('div');head.className='archive-qa-card-top';head.append(textNode('span',String(all.indexOf(q)+1).padStart(2,'0'),'archive-qa-number'),textNode('span',q.family+(variantName?' · '+variantName:''),'archive-qa-family'),textNode('span',actionName(q.expected_action),'archive-qa-action'));
      const question=document.createElement('div');question.className='archive-qa-row';const questionButton=makeButton(q.question,()=>useQuestion(q),'archive-question-text');questionButton.title='사색 대화 입력창에 넣기';question.append(textNode('span','Q','archive-qa-letter'),questionButton);
      const answer=document.createElement('div');answer.className='archive-qa-row archive-answer-row';const answerBody=document.createElement('div');answerBody.append(textNode('span','참고 답변','archive-reference-label'),textNode('p',q.answer||'문장형 답변이 지정되지 않은 사례입니다.','archive-answer-text'));answer.append(textNode('span','A','archive-qa-letter'),answerBody);
      card.append(head,question,answer);
      if(q.dialogue){const turn=q.dialogue.turn||'?';card.append(textNode('p',turn===1?'이어지는 대화의 첫 질문입니다.':'이어지는 대화 '+turn+'번째 질문 · 앞선 턴과 함께 확인하는 예시입니다.','archive-context-note'));}
      const evidence=document.createElement('div');evidence.className='archive-evidence-links';evidence.append(textNode('span','연결 근거 '+q.record_ids.length+'개','archive-evidence-label'));
      q.record_ids.forEach((id,index)=>{const record=sourceMap.get(id);if(!record)return;const link=makeButton((index+1)+'. '+(record.date?record.date.slice(5).replace('-','.')+' ':'')+record.title,()=>{questionId=q.id;showFullSource(id);},'archive-evidence-link');link.title=record.id+' · v'+record.revision;link.dataset.sourceId=id;evidence.appendChild(link);});
      if(!q.record_ids.length)evidence.append(textNode('span','직접 연결된 원문 근거 없음','archive-no-evidence'));
      card.appendChild(evidence);
      const controls=document.createElement('div');controls.className='archive-qa-controls';
      const focus=makeButton('대화에 질문 넣기',()=>useQuestion(q),'archive-focus-question');
      const copy=makeButton('질문 복사',()=>copyQuestion(q,copy),'archive-copy-question');controls.append(focus,copy);card.appendChild(controls);list.appendChild(card);
    }
    list.scrollTop=scroll;
  }
  function followRecordDate(source,{search=false}={}){
    if(!/^\d{4}-\d{2}-\d{2}$/.test(source.date||''))return;
    const [nextYear,nextMonth]=source.date.split('-').map(Number),sameMonth=year===nextYear&&month===nextMonth-1,dateChanged=selected!==source.date;
    selected=source.date;year=nextYear;month=nextMonth-1;
    // Refresh the calendar and hidden day list, while preserving the clicked search node.
    if(!sameMonth)renderCalendar();
    else{updateCalendarSelection();if(search||dateChanged)renderSelected();updateTimelineSelection();}
    if(archiveView==='timeline'){
      const timeline=el('archiveTimeline'),group=[...timeline.querySelectorAll('.timeline-group')].find(row=>row.dataset.date===source.date);
      if(group){const top=timeline.scrollTop+group.getBoundingClientRect().top-timeline.getBoundingClientRect().top;timeline.scrollTo({top:Math.max(0,top-12),behavior:'smooth'});}
    }
  }
  function selectRecordRow(id,{search=false}={}){
    const source=sourceMap.get(id);if(!source)return;if(search)searchRecordId=id;
    recordId=id;followRecordDate(source,{search});
    // Keep the clicked node intact so double-click still opens the exact source.
    for(const row of document.querySelectorAll('#selectedList [data-record-id],#searchResults [data-record-id]')){
      const selected=row.dataset.recordId===(row.closest('#searchResults')?searchRecordId:recordId);row.classList.toggle('is-selected',selected);row.setAttribute('aria-pressed',String(selected));
    }
    renderInfo();renderExamples();remember();
  }
  function makeRecordRow(record,{search=false}={}){
    const button=makeButton('',()=>selectRecordRow(record.sampleId,{search}),'archive-record-row'+(record.sampleId===(search?searchRecordId:recordId)?' is-selected':'')+(search?' is-search':''));
    button.dataset.recordId=record.sampleId;button.dataset.sourceProfile=sourceMap.get(record.sampleId).profile;
    button.setAttribute('aria-pressed',String(record.sampleId===(search?searchRecordId:recordId)));
    button.setAttribute('aria-label',collection.profiles.find(p=>p.id===sourceMap.get(record.sampleId).profile).label+' · '+record.title+' · 클릭하면 해당 날짜로 이동, 더블클릭으로 원문 전체 보기');
    button.title='한 번 클릭: 해당 날짜로 이동 · 더블클릭 또는 Enter: 원문 전체 보기';
    button.addEventListener('dblclick',event=>{event.preventDefault();showFullSource(record.sampleId);});
    button.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();showFullSource(record.sampleId);}});
    button.appendChild(textNode('small',collection.profiles.find(p=>p.id===sourceMap.get(record.sampleId).profile).label+(search?' · '+record.date:'')+(sourceMap.get(record.sampleId).synthetic?' · 가상 원문':' · 개인 기록')));
    button.append(textNode('span',record.title,'archive-record-row-title'),textNode('span',search?bodyExcerpt(record.body,el('archiveInput').value.trim()):record.body,'archive-record-row-body'),textNode('span','더블클릭으로 원문 전체 보기 ↗','archive-record-row-open'));
    const item=document.createElement('div');item.className='archive-record-item';
    if(search){item.dataset.unrestrictedSearch='true';item.append(button);return item;}
    const badge=textNode('button','확인 전','archive-readiness-badge');badge.type='button';badge.hidden=true;badge.dataset.readinessRecord=record.sampleId;
    item.append(button,badge);return item;
  }
  function renderTimelinePreview(){
    const record=selectedRecord(),panel=el('archiveTimelinePreview');panel.dataset.recordId=record?.id||'';
    el('archiveTimelinePreviewTitle').textContent=record?.title||'원문을 선택해 주세요';
    el('archiveTimelinePreviewMeta').textContent=record?(record.date||'날짜 미상')+' · '+collection.profiles.find(p=>p.id===record.profile).label+' · v'+record.revision:'왼쪽 시간순 목록에서 원문을 선택해 주세요.';
    const body=record?.body||'',limit=450;
    el('archiveTimelinePreviewBody').textContent=body.length>limit?body.slice(0,limit).trimEnd()+'…':body;
    el('archiveTimelinePreviewNote').textContent=record?(body.length>limit?'긴 원문은 앞부분을 짧게 보여드립니다.':'선택한 원문 내용입니다.'):'';
    el('archiveTimelinePreviewOpen').disabled=!record;
    for(const row of document.querySelectorAll('.timeline-record[data-record-id]')){const active=row.dataset.recordId===record?.id;row.classList.toggle('is-selected',active);row.setAttribute('aria-pressed',String(active));row.closest('.timeline-entry').classList.toggle('is-record-selected',active);}
  }
  el('archiveTimelinePreviewOpen').addEventListener('click',()=>{const record=selectedRecord();if(record)showFullSource(record.id);});
  renderSelected=function(){
    syncArchivePanel();const dayRecords=records.filter(r=>r.date===selected);
    const parts=selected.split('-').map(Number);el('selectedDate').textContent=parts[0]+'년 '+parts[1]+'월 '+parts[2]+'일';
    el('selectedCount').textContent=dayRecords.length?'현재 자료함 원문 '+dayRecords.length+'개':'이 날짜에 표시할 가상 원문이 없어요';
    if(!dayRecords.some(r=>r.sampleId===recordId))recordId=dayRecords[0]?.sampleId||null;
    const list=el('selectedList');list.replaceChildren();
    for(const record of dayRecords)list.appendChild(makeRecordRow(record));
    if(!dayRecords.length)empty(list,'다른 날짜도 살펴보세요','달력의 점이 있는 날짜를 선택하면 예시 원문을 볼 수 있어요.');
    renderTimelinePreview();
    renderInfo();renderExamples();remember();
  };
  renderTimeline=function(){originalRenderTimeline();renderTimelinePreview();};
  renderRecent=function(){originalRenderRecent();};
  openRecord=function(index){const record=records[index];if(record)showFullSource(record.sampleId);};
  selectArchiveRecordDate=function(index){const record=records[index];if(record)openSource(record.sampleId);};
  runSearch=function(reveal=false, scroll=true){
    if(!reveal){archiveSearchActive=false;syncArchivePanel();return;}
    archiveSearchActive=true;syncArchivePanel();const text=el('archiveInput').value.trim(),query=normal(text);
    const allSources=collection.records.map(record=>({sampleId:record.id,title:record.title,body:record.body,date:record.date||'날짜 미상',type:record.synthetic?'가상 원문':'개인 기록'}));
    const matches=allSources.filter(record=>!query||normal(searchFilter==='exact'?record.body:searchFilter==='semantic'?record.title:record.title+' '+record.body).includes(query));
    el('resultCount').textContent=matches.length+'개 원문';const mode=searchFilter==='exact'?'원문 전체':searchFilter==='semantic'?'제목':'제목·원문 전체';el('searchQueryCaption').textContent='현재 자료함 전체 '+collection.record_count+'개 원문의 '+mode+(text?'에서 “'+text+'” 검색':' 보기');
    const target=el('searchResults');target.replaceChildren();
    for(const record of matches)target.appendChild(makeRecordRow(record,{search:true}));
    if(!matches.length){
      if(!collection.synthetic && !collection.records.length)empty(target,'저장된 개인 기록이 없어요','기록을 작성하거나 대화의 기록 초안을 확인해 저장하면 여기에 표시됩니다.');
      else empty(target,'일치하는 원문이 없어요','검색어를 바꿔 다시 찾아보세요.');
    }
    remember();if(scroll)scrollToSearchResults();
  };
  function applyProfile(next,restore=false){
    const keepSearch=archiveSearchActive,searchText=el('archiveInput').value,priorDate=selected,priorRecord=sourceMap.get(recordId);
    profile=collection.profiles.some(p=>p.id===next)?next:collection.default_profile;
    const p=currentProfile();el('archiveProfile').value=profile;el('archiveRecordTotal').textContent=collection.record_count;el('archiveQuestionTotal').textContent=p.question_count;showAll.textContent='원문 전체 보기 '+collection.record_count;el('archiveInput').placeholder='현재 자료함 전체 '+collection.record_count+'개 원문 검색';
    records.splice(0,records.length,...collection.records.map(r=>({sampleId:r.id,profile:r.profile,profileLabel:collection.profiles.find(p=>p.id===r.profile).label,title:r.title,body:r.body,date:r.date||'날짜 미상',type:r.synthetic?'가상 원문':'개인 기록'})));
    const candidate=restore?questionMap.get(previousState?.questionId):null;
    questionId=(candidate?.profile===profile?candidate:currentQuestions()[0])?.id||null;
    const savedRecord=restore?sourceMap.get(previousState?.recordId):null;
    recordId=(restore?savedRecord?.id:priorRecord?.id)||selectedQuestion()?.record_ids.find(id=>sourceMap.has(id))||records[0]?.sampleId||null;
    const date=restore&&/^\d{4}-\d{2}-\d{2}$/.test(previousState?.selected)?previousState.selected:!restore&&priorRecord?priorDate:sourceMap.get(recordId)?.date;
    if(date){selected=date;const [y,m]=date.split('-').map(Number);year=y;month=m-1;}
    if(!restore){exampleMode='all';exampleQuery='';el('archiveExampleQuery').value='';if(!keepSearch)el('archiveInput').value='';}
    archiveSearchActive=false;renderCalendar();renderTimeline();renderRecent();remember();
    if(keepSearch){el('archiveInput').value=searchText;runSearch(true);}
  }
  el('archiveProfile').addEventListener('change',event=>applyProfile(event.target.value));
  el('archiveAllExamples').addEventListener('click',()=>{exampleMode='all';el('archiveExampleList').scrollTop=0;renderExamples();remember();});
  el('archiveRelatedExamples').addEventListener('click',()=>{exampleMode='related';el('archiveExampleList').scrollTop=0;renderExamples();remember();});
  el('archiveExampleQuery').addEventListener('input',event=>{exampleQuery=event.target.value;el('archiveExampleList').scrollTop=0;renderExamples();remember();});
  el('archiveJumpExamples').addEventListener('click',()=>{el('archiveExamples').scrollIntoView({behavior:'smooth',block:'start'});el('archiveExampleQuery').focus({preventScroll:true});});
  if(previousState?.version===1){exampleMode=previousState.exampleMode==='related'?'related':'all';exampleQuery=previousState.exampleQuery||'';el('archiveExampleQuery').value=exampleQuery;}
  detailRecordId=sourceMap.has(previousState?.detailRecordId)?previousState.detailRecordId:null;
  window.PlantArchiveView={
    selectedId:()=>recordId,
    detailRecord:()=>sourceMap.get(detailRecordId)||null,
    showRecord:showFullSource,
    showRecordInCalendar(id){
      const record=sourceMap.get(id);if(!record)return;
      go('archive');archiveView='calendar';calendarExpanded=false;archiveSearchActive=false;el('archiveInput').value='';recordId=id;
      selectArchiveDate(record.date||today,false);syncArchiveView();remember();
      requestAnimationFrame(()=>{if(document.querySelector('.page.active')?.id!=='archive')return;el('archiveWorkspace').scrollIntoView({block:'start',behavior:'smooth'});const row=[...el('selectedList').querySelectorAll('[data-record-id]')].find(node=>node.dataset.recordId===id);row?.focus({preventScroll:true});});
    },
    showPersonalRecords(){
      if(collection.synthetic)return;
      el('archiveInput').value='';
      runSearch(true,false);
    },
    setCollection(next){
      const nextCollectionId=next.synthetic?'samples':'personal';
      const keepDetailContext=collection.synthetic===next.synthetic?detailContext:previousState?.collectionId===nextCollectionId?previousState.detailContext:null;
      const keepDetail=(collection.synthetic===next.synthetic?detailRecordId:null)||(previousState?.collectionId===nextCollectionId?previousState.detailRecordId:null);
      collection=next;window.PlantArchiveSamples=next;sourceMap=new Map(next.records.map(r=>[r.id,r]));questionMap=new Map(next.examples.map(q=>[q.id,q]));
      el('archiveProfile').replaceChildren(...next.profiles.map(p=>{const o=document.createElement('option');o.value=p.id;o.textContent=p.label;return o;}));
      recordId=null;questionId=null;detailRecordId=null;detailContext=keepDetailContext;applyProfile(next.default_profile);
      el('archiveJumpExamples').hidden=!next.examples.length;
      document.dispatchEvent(new CustomEvent('plant:collection-changed'));
      if(document.querySelector('.page.active')?.id==='recordDetail'){
        if(keepDetail&&sourceMap.has(keepDetail))showFullSource(keepDetail,keepDetailContext);
      }
    }
  };
  applyProfile(previousState?.profile||profile,true);
  if(document.querySelector('.page.active')?.id==='recordDetail'&&(detailRecordId||selectedRecord()))showFullSource(detailRecordId||recordId,previousState?.detailContext);
})();
