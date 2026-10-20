// Navigation and source panels use native focus behavior and text-only content.
export function setupConversationUI({api,node,action,notice,memory}) {
  const $=id=>document.getElementById(id), shell=document.querySelector('.shell');
  const header=document.querySelector('.site-header');
  document.body.dataset.tab='chat';
  if(header && $('chat-sidebar')) header.querySelector('.header-inner').append($('chat-sidebar'));
  if(header)header.querySelector('.header-inner').prepend(action('메뉴 닫기',()=>{sidebar(false);$('app-menu-toggle')?.focus();},'sidebar-close secondary'));
  let panel=null,returnFocus=null;
  function closePanel(){if(panel){panel.close();panel=null;}}
  function showPanel(title,content){
    closePanel();returnFocus=document.activeElement;
    const d=node('dialog',undefined,'chat-evidence-panel card'),h=node('h2',title);h.id='evidence-heading';
    d.setAttribute('aria-labelledby',h.id);d.append(h,action('닫기',()=>d.close()),content);
    d.addEventListener('close',()=>{d.remove();$('chat-layout').classList.remove('with-evidence');if(panel===d)panel=null;returnFocus?.focus();});
    document.body.append(d);panel=d;
    if(matchMedia('(min-width:1440px)').matches){$('chat-layout').classList.add('with-evidence');d.show();}
    else d.showModal();
    d.querySelector('button').focus();
  }
  function sidebar(open){
    if(!header)return;
    shell.classList.toggle('sidebar-collapsed',!open);
    $('chat-sidebar').hidden=false;
    $('chat-sidebar-toggle').setAttribute('aria-expanded',String(open));
    $('chat-sidebar-toggle').textContent=open?'대화 목록 접기':'대화 목록 열기';
    $('app-menu-toggle')?.setAttribute('aria-expanded',String(open));
    const modal=open&&matchMedia('(max-width:760px)').matches;
    if($('sidebar-scrim'))$('sidebar-scrim').hidden=!modal;
    if($('main-content'))$('main-content').inert=modal;
    if(modal){header.setAttribute('role','dialog');header.setAttribute('aria-modal','true');header.setAttribute('aria-label','메뉴와 대화 목록');header.querySelector('button')?.focus();}
    else{header.removeAttribute('role');header.removeAttribute('aria-modal');}
  }
  $('app-menu-toggle')?.addEventListener('click',()=>sidebar(shell.classList.contains('sidebar-collapsed')));
  $('sidebar-scrim')?.addEventListener('click',()=>sidebar(false));
  document.addEventListener('keydown',e=>{
    if(e.key==='Escape'&&!panel){sidebar(false);$('app-menu-toggle')?.focus();}
    if(e.key==='Tab'&&header&&!shell.classList.contains('sidebar-collapsed')&&matchMedia('(max-width:760px)').matches&&!panel){
      const els=[...header.querySelectorAll('button,input,a,summary')].filter(el=>el.getClientRects().length&&!el.disabled);
      if(e.shiftKey&&document.activeElement===els[0]){e.preventDefault();els.at(-1)?.focus();}
      else if(!e.shiftKey&&document.activeElement===els.at(-1)){e.preventDefault();els[0]?.focus();}
    }
  });
  sidebar(!matchMedia('(max-width:760px)').matches);
  matchMedia('(max-width:760px)').addEventListener('change',e=>{closePanel();sidebar(!e.matches);});
  async function resultPanel(result,message) {
    if(result.effect==='save_preview'){
      if(result.candidates?.some(c=>c.lifecycle_status==='pending'))memory.candidates(result.candidates);
      else notice('이미 처리한 저장 후보입니다. 기억 관리에서 결과를 확인할 수 있습니다.');
      return;
    }
    const content=node('section');
    const ids=result.record_ids || [...new Set((message.evidence || []).map(r=>r.record_id))];
    for(const rid of ids){
      const record=await api('/records/'+encodeURIComponent(rid));
      if(record.state!=='active' || (result.source_versions?.[rid] && result.source_versions[rid]!==record.version))throw Error('기록이 변경되었습니다. 현재 기록으로 다시 질문해 주세요.');
      const article=node('article',undefined,'chat-evidence-card');
      article.append(node('h3','기록 · 버전 '+record.version));
      if(record.source_location){const s=record.source_location;article.append(node('p',`${s.filename} · 가져온 원문 ${s.start+1}~${s.end}자 · 버전 ${s.record_version}`,'muted'));}
      if(result.effect==='history') {
        const observations=message.response?.interpretation?.observations || [];
        const dates=observations.filter(o=>o.record_id===rid&&o.event_time).map(o=>o.event_time);
        article.append(node('p','사건 시각: '+(dates.join(', ') || '기록에서 확인되지 않음'),'muted'));
        const versions=await api('/records/'+encodeURIComponent(rid)+'/revisions');
        for(const item of versions.items){const detail=node('details');detail.append(node('summary',`수정 버전 ${item.version} · 저장 ${new Date(item.created_at).toLocaleString('ko-KR')}`),node('pre',item.text));article.append(detail);}
      } else {
        article.append(node('pre',record.text,'chat-source'));
        if(result.effect==='compare')article.append(node('p','같은 대상·사건·시점·조건인지 원문을 비교하세요. 값이 다르다는 이유만으로 충돌이나 향상을 확정하지 않습니다.','muted'));
      }
      const recordSources=(message.response?.evidence_refs || []).filter(r=>r.record_id===rid);
      for(const ref of recordSources)for(const span of ref.spans || [])article.append(node('blockquote',span.quote));
      if(result.effect==='record_preview') {
        const managed=await api('/memory');
        const captured=managed.items?.find(m=>m.record_id===rid);
        article.append(action('내용 확인·수정',()=>{
          closePanel();if(captured)memory.show(captured.memory_id);else document.dispatchEvent(new CustomEvent('pma-edit-record',{detail:{record_id:rid}}));
        }));
      }
      article.append(action('기록 열기',()=>{closePanel();document.dispatchEvent(new CustomEvent('pma-open-record',{detail:{record_id:rid}}));},'link'));
      if(message.response?.primary_response_type==='DELETE_CONFIRM')article.append(action('이 기록을 휴지통으로 이동',async()=>{
        if(!confirm('이 원문을 휴지통으로 옮길까요? 관련 답변과 인용은 제거됩니다. 기록은 30일 동안 복원할 수 있습니다.'))return;
        await api('/records/'+encodeURIComponent(rid)+'?expected_version='+record.version,'DELETE');closePanel();notice('휴지통으로 옮겼습니다.');document.dispatchEvent(new Event('pma-chat-refresh'));
      },'danger'));
      content.append(article);
    }
    showPanel({evidence:'답변의 근거',history:'진행·변경 이력',compare:'근거 비교',record_preview:'진도·기록 확인'}[result.effect] || '참고 기록',content);
  }
  return {sidebar,closePanel,showPanel,resultPanel};
}
