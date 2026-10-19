// Text-only memory dialogs share the host's authenticated API helper.
export function setupMemory({api, node, action, notice}) {
  const types = {user_statement:'사용자 진술',preference:'선호',event:'사건',project_decision:'결정',plan:'계획',proposal:'AI 제안',hypothesis:'가설',correction:'정정',conversation_summary:'대화 요약'};
  const statuses = {committed:'저장됨 · 검색 처리 대기',indexing:'저장됨 · 검색 처리 중',searchable:'검색 가능',index_failed:'저장됨 · 검색 처리 실패',inactive:'이전 버전 또는 삭제됨'};
  let selected = new Set(), sessionId = null;
  const fail = e => notice(e.message, true);
  function dialog(title) {
    const trigger=document.activeElement;
    const d = node('dialog', undefined, 'memory-dialog');
    const heading = node('h2', title); heading.id = 'memory-heading-' + crypto.randomUUID();
    d.setAttribute('aria-labelledby', heading.id); d.append(heading);
    const close = action('닫기', () => d.close()); d.append(close);
    d.addEventListener('close', () => {d.remove();if(trigger?.isConnected)trigger.focus();}); document.body.append(d); d.showModal();
    return d;
  }
  function preview(candidate) {
    const d = dialog('기억에 저장');
    d.append(node('p','내용을 확인하고 저장을 누르면 기존 기억과 자동으로 비교합니다.'));
    const options=node('details'); options.append(node('summary','유형·프로젝트·시점 설정 (선택)')); d.append(options);
    const source = node('details'); source.append(node('summary','출처 확인'), node('p',candidate.epistemic_status === 'ai_proposed' ? 'AI가 생성한 제안입니다.' : '사용자가 진술한 내용입니다.'),node('pre',candidate.content),node('p','대화: '+(candidate.session_id || '기존 기억 정정')+' / 메시지: '+candidate.message_ids.join(', ')));
    d.append(source);
    const text = node('textarea'); text.value = candidate.content; text.maxLength = 3500; text.rows = 7;
    const label = node('label','저장할 내용'); label.append(text); d.append(label);
    const select = node('select'); select.setAttribute('aria-label','기억 유형');
    for (const [key,title] of Object.entries(types)) {
      if (candidate.epistemic_status === 'ai_proposed' && !['proposal','hypothesis','conversation_summary'].includes(key)) continue;
      const option=node('option', title); option.value=key; select.append(option);
    }
    select.value=candidate.memory_type;
    const typeLabel=node('label','기억 유형'); typeLabel.append(select); options.append(typeLabel);
    const scope=node('input');scope.value=candidate.project_scope || '';scope.maxLength=200;const scopeLabel=node('label','프로젝트 범위 (선택)');scopeLabel.append(scope);options.append(scopeLabel);
    const eventTime=node('input');eventTime.value=candidate.event_time || '';eventTime.maxLength=100;const timeLabel=node('label','사건 시점 (원문에 있을 때만)');timeLabel.append(eventTime);options.append(timeLabel);
    const resolution=node('select'); resolution.setAttribute('aria-label','기존 기억 처리');
    for (const [value,label] of [['add','비교 후 선택해 주세요'],['add_confirmed','기존 기억 유지 · 별도 기억 추가'],['correct','선택한 이전 기억의 새 버전으로 정정']]) {
      if (value==='correct' && !candidate.supersedes_memory_id) continue;
      const opt=node('option',label); opt.value=value; resolution.append(opt);
    }
    resolution.value=candidate.supersedes_memory_id?'correct':'add';
    const linked=new Set();
    const comparisons=node('section'); d.append(comparisons);
    function renderComparisons(items) {
    comparisons.replaceChildren(); linked.clear();
    for (const comparison of items) {
      const detail=node('details'); detail.open=true;
      detail.append(node('summary',({exact_duplicate:'원문 중복',semantic_duplicate:'의미 중복',supporting:'근거 보강',complementary:'보완',temporal_update:'시간에 따른 변화',correction:'정정',contradiction:'충돌',unrelated:'별개 기록',needs_review:'차이 확인 필요'})[comparison.relation]),node('pre',comparison.content));
      detail.append(action('기존 기억 보기',()=>show(comparison.memory_id).catch(fail)));
      if (!candidate.supersedes_memory_id) detail.append(action('이 기억을 정정',async()=>{
        try { const next=await api('/memory/candidates/'+candidate.candidate_id+'/target','POST',{content:text.value,memory_id:comparison.memory_id,expected_version:comparison.record_version}); d.close(); preview(next); } catch(e){fail(e);}
      }));
      if(['supporting','complementary','temporal_update'].includes(comparison.relation)){const box=node('input');box.type='checkbox';const label=node('label','이 기억과 연결');label.prepend(box);box.addEventListener('change',()=>box.checked?linked.add(comparison.memory_id):linked.delete(comparison.memory_id));detail.append(label);}
      comparisons.append(detail);
    }
    }
    renderComparisons(candidate.comparisons || []);
    const resolutionLabel=node('label','기존 기억 처리'); resolutionLabel.append(resolution); d.append(resolutionLabel); resolutionLabel.hidden=true;
    const status=node('p','승인 전에는 개인 기억으로 등록되지 않습니다.'); status.setAttribute('role','status'); d.append(status);
    let requestId=crypto.randomUUID(), review=null;
    const save=action('저장',async()=>{
      save.disabled=true;
      const controls=[text,select,scope,eventTime,resolution];
      controls.forEach(control=>control.disabled=true);
      try {
        if(!review) {
          status.textContent='기존 기억과 자동 비교 중…';
          review=await api('/memory/candidates/'+candidate.candidate_id+'/review','POST',{content:text.value,memory_type:select.value,project_scope:scope.value,event_time:eventTime.value,candidate_version:candidate.candidate_version});
          renderComparisons(review.comparisons || []);
        }
        if(review.status!=='complete') {review=null;status.textContent='비교를 완료하지 못했습니다. 저장을 눌러 다시 시도해 주세요.';return;}
        if(review.comparisons.some(c=>['exact_duplicate','semantic_duplicate'].includes(c.relation))) {
          status.textContent='이미 저장된 내용입니다. 기존 기억을 확인하거나 내용을 수정해 주세요.';return;
        }
        if(review.comparisons.some(c=>c.relation!=='unrelated') && resolution.value==='add') {
          resolutionLabel.hidden=false;status.textContent='관련된 기존 기억이 있습니다. 아래 처리 방법을 선택한 뒤 저장해 주세요.';return;
        }
        status.textContent='저장 중…';
        await api('/memory/candidates/'+candidate.candidate_id+'/commit','POST',{approved:true,request_id:requestId,candidate_version:candidate.candidate_version,content:text.value,memory_type:select.value,project_scope:scope.value,event_time:eventTime.value,resolution:resolution.value,review_id:review.review_id,link_memory_ids:[...linked]});
        d.close(); notice('기억에 저장했습니다. 검색 준비는 자동으로 진행됩니다.');
      } catch(e) {status.textContent=e.message; review=null;}
      finally {save.disabled=false;controls.forEach(control=>control.disabled=false);}
    });
    for(const control of [text,select,scope,eventTime]) control.addEventListener('input',()=>{review=null;requestId=crypto.randomUUID();resolution.value=candidate.supersedes_memory_id?'correct':'add';resolutionLabel.hidden=true;status.textContent='저장하면 변경한 내용을 자동으로 비교합니다.';});
    d.append(save,action('결정 보류',()=>d.close()),action('저장 취소',async()=>{try{await api('/memory/candidates/'+candidate.candidate_id+'/reject','POST',{});d.close();}catch(e){fail(e);}}));
  }
  async function show(id) {
    const item=await api('/memory/'+id), d=dialog('저장된 기억');
    const epistemic={user_reported:'사용자 진술 · 객관적 검증 전',ai_proposed:'AI 제안 · 실행 사실 아님',unverified:'원본 기록 · 검증 전'};
    d.append(node('p',types[item.memory_type]+' · '+(epistemic[item.epistemic_status] || '검증 전')),node('pre',item.content),node('p',item.lifecycle_status==='archived'?'보관됨':(statuses[item.index_status] || item.index_status)));
    d.append(action('상태 새로고침',async()=>{d.close(); await show(id);}),action('수정 이력',async()=>{
      try {const h=await api('/memory/'+id+'/history'); for(const version of h.items) d.append(node('p','버전 '+version.record_version+' · '+version.lifecycle_status),node('pre',version.content));}catch(e){fail(e);}
    }));
    if(item.lifecycle_status==='archived') d.append(action('보관 해제',async()=>{try{await api('/memory/'+id+'/unarchive','POST',{expected_version:item.record_version});d.close();await show(id);}catch(e){fail(e);}}));
    if(item.lifecycle_status==='active') {
      d.append(action('기억 보관',async()=>{try{await api('/memory/'+id+'/archive','POST',{expected_version:item.record_version});d.close();await show(id);}catch(e){fail(e);}}));
      const text=node('textarea'); text.value=item.content; text.maxLength=3500;
      const label=node('label','정정할 내용'); label.append(text); d.append(label);
      d.append(action('정정 미리보기',async()=>{try {const c=await api('/memory/'+id+'/corrections','POST',{content:text.value,expected_version:item.record_version}); d.close(); preview(c);}catch(e){fail(e);}}));
      if(item.index_status==='index_failed') d.append(action('검색 처리 재시도',async()=>{try {await api('/memory/'+id+'/retry','POST',{}); d.close(); await show(id);}catch(e){fail(e);}}));
      d.append(action('기억 삭제',()=>{const confirmation=dialog('기억 삭제 확인');confirmation.append(node('p','이 기억을 휴지통으로 옮깁니다. 30일 동안 복구할 수 있습니다.'),action('휴지통으로 이동',async()=>{try{await api('/memory/'+id+'?expected_version='+item.record_version,'DELETE');confirmation.close();d.close();notice('기억을 삭제했습니다.');}catch(e){fail(e);}}));}));
    }
  }
  async function capture(ids, source, selectedText=null) {
    try {preview(await api('/memory/candidates','POST',{session_id:sessionId,message_ids:ids,source_type:source,selected_text:selectedText}));}catch(e){fail(e);}
  }
  function attach(parent, message, source, controls=parent) {
    controls.append(action('기억에 저장',()=>capture([message.id],source)), action('선택 문장 저장',()=>{
      const selection=window.getSelection();
      if(!selection?.toString() || !parent.contains(selection.anchorNode) || !parent.contains(selection.focusNode)) {notice('이 메시지 안의 문장을 먼저 선택해 주세요.',true);return;}
      capture([message.id],source,selection.toString());
    }));
    {
      const key=source+':'+message.id;
      const label=node('label','함께 저장 선택'), box=node('input');box.type='checkbox'; box.checked=selected.has(key);
      box.addEventListener('change',()=>box.checked?selected.add(key):selected.delete(key)); label.prepend(box);controls.append(label);
    }
  }
  const toolbar=node('div',undefined,'actions');
  toolbar.append(action('선택한 메시지 저장',async()=>{
    try {const candidates=[];
    for(const source of ['user_message','assistant_message']) {
      const ids=[...selected].filter(k=>k.startsWith(source+':')).map(k=>k.slice(source.length+1));
      if(ids.length)candidates.push(await api('/memory/candidates','POST',{session_id:sessionId,message_ids:ids,source_type:source}));
    }
    if(!candidates.length){notice('저장할 메시지를 먼저 선택해 주세요.',true);return;}
    chooseCandidates(candidates);}catch(e){fail(e);}
  }),action('대화에서 저장 후보 선택',async()=>{
    try{const result=await api('/memory/extract','POST',{session_id:sessionId});const d=dialog('대화의 결정·계획·선호 후보');
    if(!result.items.length)d.append(node('p','발견한 후보가 없습니다. 메시지에서 직접 선택할 수 있습니다.'));
    for(const c of result.items)d.append(action(c.content.slice(0,140),()=>{d.close();preview(c);}));}catch(e){fail(e);}
  }),action('기억 관리',async()=>{
    try {const result=await api('/memory?include_inactive=true'),d=dialog('기억 관리');
      const policy=node('select');policy.setAttribute('aria-label','저장 정책 · 자동 저장은 꺼져 있습니다');for(const [value,title] of [['MANUAL','직접 요청한 내용만 후보로 만들기'],['SUGGEST','대화에서 저장 후보 제안받기']]){const opt=node('option',title);opt.value=value;policy.append(opt);}policy.value=result.policy;const label=node('label','저장 정책 · 자동 저장은 꺼져 있습니다');label.append(policy);d.append(label);policy.addEventListener('change',async()=>{try{await api('/memory/policy','PUT',{policy:policy.value});}catch(e){fail(e);}}); for(const item of result.items) d.append(action(item.content.slice(0,100)+' · '+(item.lifecycle_status==='archived'?'보관됨':(statuses[item.index_status] || item.index_status)),()=>{d.close();show(item.memory_id).catch(fail);}));if(!result.items.length)d.append(node('p','저장한 기억이 없습니다.'));const pending=await api('/memory/candidates'); if(pending.items.length)d.append(node('h3','보류 중인 후보'));for(const c of pending.items)d.append(action(c.content.slice(0,100),()=>{d.close();preview(c);}));}catch(e){fail(e);}
  }));
  document.getElementById('memory-toolbar').append(toolbar);
  function chooseCandidates(items) {
    items=items?.filter(c=>c.lifecycle_status==='pending');
    if(!items?.length)return;
    if(items.length===1){preview(items[0]);return;}
    const d=dialog('저장 후보 선택');
    d.append(node('p','저장할 내용을 선택해 미리보기와 승인을 진행해 주세요.'));
    for(const c of items)d.append(action((c.source_type==='assistant_message'?'AI 제안: ':'사용자 진술: ')+c.content.slice(0,140),()=>{d.close();preview(c);}));
  }
  return {attach,preview,session(id){if(sessionId!==id)selected.clear();sessionId=id;},candidates:chooseCandidates};
}
