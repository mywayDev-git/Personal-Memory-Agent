// Text-only rendering: model output never becomes HTML or executable content.
import {setupMemory} from './memory.js';
import {explanation, auditView, answerAuditView, correctionView, expansionView} from './search-explanation.js';
export function setupChat({api, node, action, notice, today}) {
  const memory = setupMemory({api,node,action,notice});
  const $ = id => document.getElementById(id);
  let current = null, pending = null, sending = false, openVersion = 0, listVersion = 0;
  let contextId = null, searchTimer = null, resumeTimer = null, resumeVersion = 0;
  const drafts = new Map(), positions = new Map();
  function saveDraft() {
    if (!current) return;
    const value = $('chat-question').value;
    drafts.set(current.id, value);
    try { sessionStorage.setItem('pma-chat-draft:' + current.id, value); } catch { /* Private mode may disable storage. */ }
  }
  function restoreDraft(id) {
    let value = drafts.get(id);
    if (value === undefined) { try { value = sessionStorage.getItem('pma-chat-draft:' + id); } catch {} }
    $('chat-question').value = value || ''; resizeInput();
  }
  function resizeInput() { const input = $('chat-question'); input.style.height='auto'; input.style.height=Math.min(input.scrollHeight,180)+'px'; }
  const nearBottom = () => { const el=$('chat-messages'); return el.scrollHeight-el.clientHeight-el.scrollTop < 64; };
  const states = {resolving_context:'대화 맥락을 살펴보고 있어요', searching:'관련 기록을 찾고 있어요', generating:'답변을 작성하고 있어요', validating:'답변과 근거를 확인하고 있어요'};
  const phaseNames = {resolving_context:'맥락 확인',searching:'검색',generating:'답변 생성',validating:'근거 확인'};
  function timingText(state, completed=false) {
    const parts = Object.entries(state.phase_timings || {}).map(([key,seconds]) => `${phaseNames[key] || key} ${Number(seconds).toFixed(1)}초${!completed && key !== state.phase ? ' 완료' : ''}`);
    return [...parts, Number.isFinite(state.elapsed_seconds) ? `전체 ${state.elapsed_seconds.toFixed(1)}초` : '', completed ? '완료' : (states[state.phase] || '요청 준비 중')].filter(Boolean).join(' · ');
  }
  function searchInfo(message) {
    const searches=message.snapshot?.searches || [];
    if(!searches.length) return null;
    const wrap=node('details',undefined,'chat-search-info');
    wrap.open=true;
    wrap.append(node('summary',`검색 완료 · 검색어와 조건 ${searches.length}건`));
    wrap.append(node('p','내 질문: '+message.question));
    const answerAudit=message.snapshot?.answer_audit;
    const answerInfo=answerAuditView(node,answerAudit);if(answerInfo)wrap.append(answerInfo);
    const citedIds=new Set((message.response?.items || []).flatMap(item=>item.citations || []));
    for(const search of searches) {
      wrap.append(node('p','검색 질문: '+search.question));
      const expansion=expansionView(node,search.query_expansion);if(expansion)wrap.append(expansion);
      wrap.append(node('small',search.query_source==='current_question'?'현재 질문 그대로':'검색용 재구성 · 대화 해석 또는 추가 검색','muted'));
      const audit=auditView({node,action,api},search.audit,citedIds,message.evidence || [],answerAudit);if(audit)wrap.append(audit);
      const tags=node('div',undefined,'search-tags');
      for(const term of search.keywords || []) tags.append(node('span',term,'search-tag'));
      wrap.append(tags);
      const filters=search.filters || {};
      if(filters.date_from || filters.date_to) wrap.append(node('p',`기간: ${filters.date_from || '제한 없음'} ~ ${filters.date_to || '제한 없음'}`,'muted'));
    }
    wrap.append(node('p','검색어와 의미 유사도로 찾은 기록 중, 답변에 사용된 원문은 아래 근거에서 확인할 수 있습니다.','muted'));
    return wrap;
  }
  const validTurn = m => m.state === 'completed' && m.response && !m.error_code;
  function closeEvidence() {
    // Evidence now stays with its answer; there is no detached panel.
  }
  function context() {
    const target = current?.messages.find(m => m.id === contextId && validTurn(m));
    if (!target) contextId = null;
    $('chat-context').hidden = !target || target.id === current?.messages.filter(validTurn).at(-1)?.id;
    $('chat-context').replaceChildren(node('span', target ? '이어서 이야기할 주제: ' + target.question : '최근 대화 흐름을 따라 이야기합니다.'));
    if (target) $('chat-context').append(action('선택 해제', () => { contextId = null; context(); }));
    $('chat-context').append(action('대상·조건 정정', () => {
      if (!$('chat-question').value.trim()) $('chat-question').value = '정정할게. ';
      saveDraft(); resizeInput(); $('chat-question').focus();
    }, 'link'));
  }
  function chooseTopic(message) {
    contextId = message.id; context(); $('chat-topics').open = false; $('chat-menu').open = false; $('chat-question').focus();
  }
  function collapseSidebar() {
    $('chat-sidebar').hidden = true; $('chat-layout').classList.add('sidebar-collapsed');
    $('chat-sidebar-toggle').setAttribute('aria-expanded','false'); $('chat-sidebar-toggle').textContent='대화 목록 열기';
  }
  const fail = e => notice(e.message, true);
  const bottom = () => { $('chat-messages').scrollTop = $('chat-messages').scrollHeight; $('chat-jump').hidden = true; };
  function clear() {
    saveDraft(); clearTimeout(resumeTimer); ++resumeVersion;
    current = null; pending = null; contextId = null; closeEvidence(); $('chat-conversation').hidden = true;
    $('chat-empty').hidden = false; $('chat-messages').replaceChildren();
  }
  async function list() {
    const version = ++listVersion;
    const query = $('chat-search').value?.trim() || '';
    const result = await api('/chat/sessions' + (query ? '?q=' + encodeURIComponent(query) : ''));
    if (version !== listVersion) return;
    if (!query && current && !result.items.some(s => s.id === current.id)) clear();
    $('chat-list').replaceChildren();
    for (const s of result.items) {
      const button = action(s.title, () => open(s.id).catch(fail));
      button.dataset.sessionId=s.id;
      button.classList.add('chat-list-item');
      button.setAttribute('aria-current', String(current?.id === s.id));
      $('chat-list').append(button);
    }
    if (!result.items.length) $('chat-list').append(node('p',query ? '일치하는 대화가 없습니다.' : '새 대화를 시작해 보세요.', 'muted'));
  }
  function source(row, refs) {
    const details = node('details', undefined, 'chat-citation');
    details.append(node('summary', '기록 확인 · 버전 ' + row.version));
    for (const [label, stamp] of [['기록 작성 시각',row.recorded_at], ['기록 기준 시각',row.reference_time]]) {
      if (stamp) { const d = new Date(stamp); details.append(node('p',label + ': ' + (Number.isNaN(d.getTime()) ? stamp : d.toLocaleString('ko-KR')), 'muted')); }
    }
    const eventTime = typeof row.time === 'string' ? row.time : row.time?.raw || [row.time?.start,row.time?.end].filter(Boolean).join(' ~ ');
    details.append(node('p','사건 시각: ' + (eventTime || '기록에서 확인되지 않음'), 'muted'));
    const original = node('pre', undefined, 'chat-source');
    // Server offsets count Unicode code points, not JavaScript UTF-16 units.
    const chars = Array.from(row.source_text);
    const slice = (start, end) => chars.slice(start, end).join('');
    let cursor = 0;
    for (const ref of [...refs].sort((a,b) => a.start-b.start)) {
      if (ref.start < cursor || slice(ref.start, ref.end) !== ref.quote) continue;
      original.append(document.createTextNode(slice(cursor, ref.start)), node('mark', ref.quote,'evidence-highlight'));
      cursor = ref.end;
    }
    original.append(document.createTextNode(slice(cursor)));
    details.append(original); return details;
  }
  function validRefs(response, evidence, i) {
    const groups = new Map();
    for (const cid of response.items[i].citations || []) {
      const row = evidence.find(r => r.id === cid); if (!row || typeof row.source_text !== 'string' || !row.record_id || !row.revision_id) continue;
      const chars = Array.from(row.source_text);
      const refs = (response.citation_details || []).filter(r => r.item_index === i && r.memory_id === cid &&
        r.record_id === row.record_id && r.revision_id === row.revision_id && Number.isInteger(r.start) && Number.isInteger(r.end) &&
        r.start >= 0 && r.end > r.start && r.end <= chars.length && chars.slice(r.start,r.end).join('') === r.quote);
      if (!refs.length) continue;
      const key = row.record_id + ':' + row.version;
      if (!groups.has(key)) groups.set(key, {row,refs:[]});
      groups.get(key).refs.push(...refs);
    }
    return [...groups.values()];
  }
  function citationButton(groups, outdated=false) {
    const details = node('details', undefined, 'chat-evidence');
    details.append(node('summary', '근거 ' + groups.length + '건'));
    const body = node('section', undefined, 'chat-evidence-content');
    body.append(node('h3','사용된 원문 근거'));
    if (outdated) body.append(node('p','이전 기록 기준입니다. 답변을 만들 당시의 원문입니다.', 'chat-warning'));
    for (const {row, refs} of groups) {
      const card = node('article', undefined, 'chat-evidence-card');
      card.append(node('strong', row.title || '참고 기록'));
      const why=explanation(node,row);if(why)card.append(why);
      card.append(node('small','답변 근거 문장 · 초록색','muted'));
      if (row.recorded_at) { const d=new Date(row.recorded_at); card.append(node('small','기록 작성: ' + (Number.isNaN(d.getTime()) ? row.recorded_at : d.toLocaleDateString('ko-KR')),'muted')); }
      for (const quote of new Set(refs.map(r=>r.quote))) { const excerpt=node('blockquote'); excerpt.append(node('mark',quote,'evidence-highlight')); card.append(excerpt); };
      const full=source(row,refs); full.querySelector('summary').textContent='전체 원문 · 버전 ' + row.version;
      let checking = false;
      full.addEventListener('toggle', async () => {
        if (!full.open || checking) return;
        const citationId = refs.find(ref => ref.citation_id)?.citation_id;
        if (!citationId) return;
        checking = true;
        try {
          await api('/chat/citations/' + encodeURIComponent(citationId));
        } catch (error) {
          full.replaceChildren(node('summary','원본을 확인할 수 없습니다'),
            node('p',error.message,'chat-warning'));
        } finally { checking = false; }
      });
      card.append(full); body.append(card);
    }
    details.append(body); return details;
  }
  function answerEvidence(response, evidence, outdated) {
    const groups = new Map();
    response.items.forEach((_,i)=>{
      for (const group of validRefs(response,evidence,i)) {
        const key=group.row.record_id+':'+group.row.version;
        if(!groups.has(key)) groups.set(key,{row:group.row,refs:[]});
        const refs=groups.get(key).refs;
        for(const ref of group.refs) if(!refs.some(r=>r.start===ref.start && r.end===ref.end)) refs.push(ref);
      }
    });
    return groups.size ? citationButton([...groups.values()],outdated) : null;
  }
  function richText(text) {
    // A small allowlist, not an HTML parser. Links and raw HTML stay literal text.
    if (text.includes('```')) {
      const wrap = node('div');
      text.split('```').forEach((part, index) => {
        if (index % 2) { const pre = node('pre'); pre.append(node('code', part.replace(/^[^\n]*\n/, ''))); wrap.append(pre); }
        else if (part) wrap.append(richText(part));
      });
      return wrap;
    }
    const lines = text.trim().split('\n');
    const divider = lines.findIndex(line => /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line));
    if (divider > 0) {
      const wrap = node('div'), table = node('table');
      if (divider > 1) wrap.append(richText(lines.slice(0,divider-1).join('\n')));
      const rows = [lines[divider-1], ...lines.slice(divider+1)];
      for (const [index,line] of rows.entries()) {
        if (!line.includes('|')) { if (line) wrap.append(richText(line)); continue; }
        const row = node('tr');
        for (const value of line.replace(/^\s*\||\|\s*$/g,'').split('|')) row.append(node(index === 0 ? 'th' : 'td', value.trim()));
        table.append(row);
      }
      wrap.append(table); return wrap;
    }
    if (!/`|\*\*|^#{1,6}\s|^[-*]\s|^\d+\.\s/m.test(text)) return node('p',text);
    const wrap=node('div');
    for (const line of text.split('\n')) {
      const heading=line.match(/^#{1,6}\s+(.+)$/);
      const entry=node(heading?'h3':'p');
      const value=heading?heading[1]:line;
      const parts=value.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
      for(const part of parts) entry.append(part.startsWith('**')&&part.endsWith('**')?node('strong',part.slice(2,-2)):part.startsWith('`')&&part.endsWith('`')?node('code',part.slice(1,-1)):document.createTextNode(part));
      wrap.append(entry);
    }
    return wrap;
  }
  function content(parent, response, evidence, outdated=false) {
    const shown = new Set();
    // Append unrepresented items so an incomplete layout cannot hide verified text.
    const types = {text:'paragraph',evidence_group:'list',event_timeline:'timeline',evidence_comparison:'paragraph',claim_coverage:'list',clarification_choices:'list'};
    const presentation = response.display?.verified && Array.isArray(response.presentation) ? response.presentation.map(b => b && ({...b,semanticType:b.type,type:types[b.type] || 'paragraph'})) : [];
    const blocks = [...(Array.isArray(presentation) ? presentation : []),
      {type:'paragraph', item_indices:response.items.map((_,i)=>i)}];
    for (const block of blocks) {
      if (!block || !Array.isArray(block.item_indices)) continue;
      const allowed = ['paragraph','list','timeline','entity','table'];
      const style = allowed.includes(block.type) ? block.type : 'paragraph';
      const wrap = node(style === 'list' ? 'ul' : style === 'timeline' ? 'ol' : style === 'table' ? 'table' : 'div', undefined, 'chat-block chat-block-' + style);
      if (block.semanticType === 'claim_coverage') parent.append(node('h3','확인된 내용과 기록의 한계'));
      if (block.semanticType === 'evidence_comparison') parent.append(node('p','서로 다른 기록이 있습니다. 최신 기록만으로 최종 상태를 확정하지 않습니다.','chat-conflict'));
      if (block.semanticType === 'event_timeline') wrap.append(node('li',block.event_date || '사건 날짜 미확인','chat-event-date'));
      if (block.semanticType === 'evidence_comparison') wrap.append(node('caption','기록에서 확인한 내용 · 각 근거를 비교해 보세요'));
      for (const i of block.item_indices) {
        if (!Number.isInteger(i) || i < 0 || i >= response.items.length) continue;
        const item = response.items[i]; if (!item || shown.has(i)) continue; shown.add(i);
        const entry = node(style === 'list' || style === 'timeline' ? 'li' : style === 'table' ? 'tr' : 'div');
        const cell = style === 'table' ? node('td') : entry;
        if (item.source_type === 'inference') cell.append(node('small','제안 · 추론','muted'));
        const meta=response.display?.verified && response.display.items.find(row=>row.index===i);
        if (meta && response.display.kind === 'partial') cell.append(node('small',meta.state === 'unknown' ? '기록에서 확인되지 않음' : '기록에서 확인됨', 'chat-coverage ' + meta.state));
        cell.append(richText(item.text));
        if (cell !== entry) entry.append(cell); wrap.append(entry);
      }
      parent.append(wrap);
    }
  }
  function render(session) {
    memory.session(session.id);
    const switched = current?.id !== session.id;
    const oldScroll=$('chat-messages').scrollTop, follow=nearBottom();
    const signature = messages => messages.map(m=>m.id+':'+m.state+':'+(m.error_code || '')).join('|');
    const changed = signature(current?.messages || []) !== signature(session.messages);
    const expanded = [...$('chat-messages').querySelectorAll('details')].map((d,i)=>d.open ? i : -1).filter(i=>i>=0);
    if(switched) { saveDraft(); if(current) positions.set(current.id,oldScroll); }
    if (switched) contextId = session.messages.filter(validTurn).at(-1)?.id || null;
    if (switched && globalThis.matchMedia?.('(max-width:760px)').matches) collapseSidebar();
    closeEvidence();
    if (switched) { $('chat-mode').value = session.mode || 'auto'; $('chat-mode').dispatchEvent(new Event('change')); }
    current = session; $('chat-empty').hidden = true; $('chat-conversation').hidden = false;
    for(const button of $('chat-list').children) if(button.dataset.sessionId) button.setAttribute('aria-current',String(button.dataset.sessionId===session.id));
    $('chat-cancel').hidden=!sending || pending?.sid!==session.id;
    if(!session.messages.some(m=>m.state==='running')) $('chat-state').textContent='';
    if(switched) restoreDraft(session.id);
    $('chat-title').textContent = session.title; $('chat-messages').replaceChildren();
    context(); $('chat-topic-list').replaceChildren();
    for (const m of session.messages.filter(validTurn)) {
      if(m.response.status==='needs_clarification' && session.messages.at(-1)?.id!==m.id) continue;
      $('chat-topic-list').append(action(m.question, () => chooseTopic(m), 'chat-topic link'));
    }
    for (const message of session.messages) {
      const user = node('article', undefined, 'chat-bubble chat-user');
      user.append(node('small','나'), node('p', message.question)); $('chat-messages').append(user);
      if(validTurn(message)) { const utilities=node('details',undefined,'chat-user-actions'); utilities.append(node('summary','메시지 작업')); const actions=node('div',undefined,'chat-message-actions'); utilities.append(actions); user.append(utilities); memory.attach(user,message,'user_message',actions); }
      const ai = node('article', undefined, 'chat-bubble chat-ai'); ai.append(node('small','AI'));
      if (message.error_code === 'SOURCE_DELETED') ai.append(node('p','참고한 기록이 삭제되어 이 답변을 지웠습니다.', 'muted'));
      else if (message.state === 'failed') {
        ai.append(node('p',message.error_code === 'CANCELLED' ? '중단한 요청입니다. 검증되지 않은 답변은 보관하지 않습니다.' : '답변을 완료하지 못했습니다. 기록이 없다는 뜻은 아닙니다.', 'muted'), action('다시 시도', () => send(message.question, message.request_id, message.request_today, message.context_message_id, message.mode || 'auto')));
      } else if (message.state === 'running') { ai.dataset.requestId=message.request_id; ai.append(node('p','답변을 준비하고 있습니다.', 'chat-progress'), action('요청 중단',async()=>{
        await api('/chat/sessions/'+session.id+'/requests/'+message.request_id+'/cancel','POST',{}); await open(session.id);
      })); }
      else if (message.response) {
        if (['SOURCE_MODIFIED','SOURCE_REPROCESSED'].includes(message.error_code)) ai.append(node('p',message.error_code==='SOURCE_REPROCESSED'?'이전 추출 기준 · 기억을 재처리했습니다. 현재 기록으로 다시 질문해 주세요.':'이전 기록 기준 · 원본이 변경되었습니다.', 'chat-warning'));
        const r = message.response;
        if(Number.isFinite(r.elapsed_seconds)) ai.append(node("p",timingText(r,true),"chat-timing"));
        const correctionSearches=message.snapshot?.searches || (r.query_corrections || []).map(c=>({question:c.original_query,query_correction:c}));
        for(const search of correctionSearches){
          const view=correctionView(node,search.query_correction,{originalQuery:search.question,
            evidence:message.evidence || [],retry:message.error_code?null:action('원문으로만 다시 검색',()=>send(message.question,undefined,message.request_today,message.context_message_id,message.mode || 'auto',false))});
          if(view)ai.append(view);
        }
        const searchView=searchInfo(message); if(searchView) ai.append(searchView);
        if(r.memory_save_notice) ai.append(node('p',r.memory_save_notice,'chat-warning'));
        if (r.status === 'needs_clarification') ai.append(node('p',r.clarification));
        if (r.status === 'insufficient_evidence') ai.append(node('p',r.notice || '관련 기록에서 답변을 뒷받침할 근거를 확인하지 못했습니다.'));
        if (r.status !== 'needs_clarification') content(ai, r, message.evidence || [],['SOURCE_MODIFIED','SOURCE_REPROCESSED'].includes(message.error_code));
        if (r.status === 'needs_clarification') {
          const card = node('div',undefined,'chat-clarification');
          const expired = !!message.error_code || session.messages.at(-1)?.id !== message.id;
          if (expired) { card.append(node('p','이 선택은 만료되었습니다. 현재 기록으로 다시 질문해 주세요.', 'muted')); content(card,r,message.evidence || [],['SOURCE_MODIFIED','SOURCE_REPROCESSED'].includes(message.error_code)); }
          else {
            for (let i=0;i<r.items.length;i++) {
              const groups=validRefs(r,message.evidence || [],i);
              if (!groups.length) continue;
              const option=node('div',undefined,'chat-choice');
              option.append(action(r.items[i].text, () => send(r.items[i].text, undefined, undefined, message.id)));
              card.append(option);
            }
            card.append(action('직접 설명하기', () => chooseTopic(message)),action('선택 취소 · 주제 바꾸기', () => { contextId=null; context(); card.replaceChildren(node('p','새로운 질문을 입력해 주세요.')); $('chat-question').focus(); }));
          }
          card.append(action('현재 기록으로 다시 검색', () => send(message.question,undefined,undefined,null)));
          ai.append(card);
        }
        if (r.validation === 'rejected') ai.append(node('p','근거 검증을 통과하지 못한 답변은 표시하지 않았습니다.', 'chat-warning'));
        const evidenceView=answerEvidence(r,message.evidence || [],['SOURCE_MODIFIED','SOURCE_REPROCESSED'].includes(message.error_code));
        if(evidenceView) ai.append(evidenceView);
        const utilities=node('div',undefined,'chat-message-actions'); ai.append(utilities);
        utilities.append(action('답변 복사', async () => {
          await navigator.clipboard.writeText([r.clarification,r.notice,...r.items.map(i=>i.text)].filter(Boolean).join('\n\n')); notice('답변을 복사했습니다.');
        }, 'link'));
        if (r.index_notice) ai.append(node('p',r.index_notice,'muted'));
      }
      $('chat-messages').append(ai);
      if(validTurn(message)) { const utilities=ai.querySelector('.chat-message-actions') || ai; memory.attach(ai,message,'assistant_message',utilities); }
    }
    if (!session.messages.length) $('chat-messages').append(node('p','편하게 말을 걸어 보세요. 궁금한 기억도 함께 찾을 수 있어요.', 'chat-welcome'));
    $('chat-send').disabled = sending || session.messages.some(m => m.state === 'running');
    if(!switched) expanded.forEach(i=>{ const d=$('chat-messages').querySelectorAll('details')[i]; if(d)d.open=true; });
    if(switched && positions.has(session.id)) $('chat-messages').scrollTop=positions.get(session.id);
    else if(switched || follow) bottom();
    else { $('chat-messages').scrollTop=oldScroll; if(changed) $('chat-jump').hidden=false; }
    watchRunning(session);
    $('chat-diagnostics').hidden = !session.diagnostics_enabled;
    $('chat-metrics').replaceChildren();
    if (session.diagnostics_enabled) {
      const completed = session.messages.filter(validTurn);
      const counts = Object.fromEntries(['answered','needs_clarification','insufficient_evidence'].map(s=>[s,completed.filter(m=>m.response.status===s).length]));
      const timed=completed.map(m=>m.response.elapsed_seconds).filter(Number.isFinite);
      $('chat-metrics').append(node('p',`완료 ${completed.length}턴 · 답변 ${counts.answered} · 확인 질문 ${counts.needs_clarification} · 근거 부족 ${counts.insufficient_evidence} · 실패 ${session.messages.filter(m=>m.state==='failed').length}`),node('p',`평균 응답 ${timed.length?(timed.reduce((a,b)=>a+b,0)/timed.length).toFixed(1):'—'}초 · 의미 정확도는 별도 원문 대조 평가가 필요합니다.`));
      for (const m of completed) {
        const d = node('details'); d.append(node('summary', `${m.response.status} · ${m.response.elapsed_seconds ?? '?'}초`),node('pre',JSON.stringify({validation:m.response.validation,model:m.response.model,searches:m.snapshot?.searches,performance:m.snapshot?.performance},null,2))); $('chat-metrics').append(d);
      }
    }
  }
  function watchRunning(session) {
    clearTimeout(resumeTimer); const version=++resumeVersion;
    const running=session.messages.find(m=>m.state==='running');
    if(!running) return;
    const poll=async()=>{
      if(version!==resumeVersion || current?.id!==session.id) return;
      try {
        const state=await api('/chat/sessions/'+session.id+'/requests/'+running.request_id);
        if(version!==resumeVersion || current?.id!==session.id) return;
        if(state.state==='completed' || state.state==='failed') { await open(session.id); await list(); return; }
        const bubble=[...$('chat-messages').children].find(el=>el.dataset.requestId===running.request_id);
        const label=timingText(state);
        if(bubble?.querySelector('.chat-progress')) bubble.querySelector('.chat-progress').textContent=label;
      } catch { if(current?.id===session.id) $('chat-state').textContent='연결 확인 중 · 자동으로 다시 시도합니다.'; }
      if(version===resumeVersion) resumeTimer=setTimeout(poll,1200);
    };
    resumeTimer=setTimeout(poll,1200);
  }
  async function open(id) {
    const version = ++openVersion;
    const session = await api('/chat/sessions/' + encodeURIComponent(id));
    if (version !== openVersion) return;
    if (current?.id !== id && !sending) pending = null;
    render(session);
  }
  async function send(question, requestId, requestToday, requestedContext, requestedMode, correctionEnabled) {
    if (!current || sending || current.messages.some(m=>m.state==='running') || !question.trim()) return;
    const sid = current.id;
    const req = requestId || (pending?.sid === sid && pending.question === question ? pending.requestId : crypto.randomUUID());
    const requestDate = requestToday !== undefined ? requestToday : pending?.requestId === req ? pending.today : today();
    const anchor = requestedContext !== undefined ? requestedContext : pending?.requestId === req ? pending.contextId : contextId;
    const mode = requestedMode ?? (pending?.requestId === req ? pending.mode : $('chat-mode').value || 'auto');
    correctionEnabled = correctionEnabled ?? (pending?.requestId === req ? pending.correctionEnabled : true);
    pending = {sid, question, requestId:req, today:requestDate, contextId:anchor, mode, correctionEnabled}; sending = true; $('chat-send').disabled = true; $('chat-cancel').hidden = false;
    const user = node('article',question,'chat-bubble chat-user');
    const progress = node('article','맥락을 살펴보고 필요한 기억과 답변을 확인하고 있어요…','chat-bubble chat-ai chat-progress');
    $('chat-messages').append(user,progress); bottom();
    let polling = false;
    const poll = setInterval(async () => {
      if (polling) return; polling = true;
      try { const state = await api('/chat/sessions/' + sid + '/requests/' + req);
        if (current?.id === sid) { const label = state.error_code === 'CANCELLED' ? '중단 요청을 마무리하고 있어요' : timingText(state); progress.textContent = label; $('chat-state').textContent = label; }
      } catch { /* The final request reports connection failures. */ } finally { polling = false; }
    }, 1200);
    try {
      const clarifying = current?.messages.some(m => m.id === anchor && m.response?.status === 'needs_clarification');
      const result = await api('/chat/sessions/' + sid + (clarifying ? '/clarifications' : '/messages'),'POST',{question,correction_enabled:correctionEnabled,request_id:req,today:requestDate,context_message_id:anchor || null,mode});
      if (current?.id === sid) { pending = null; contextId = result.message_id || null; await open(sid); }
      await list(); notice('');
      if(current?.id === sid) memory.candidates(result.memory_candidates);
      if(result.memory_capture_error) notice('답변은 보존되었습니다. 저장 후보를 만들지 못했으니 메시지의 기억에 저장 버튼으로 다시 시도해 주세요.',true);
    } catch (error) {
      if(current?.id===sid && !$('chat-question').value) { $('chat-question').value=question; saveDraft(); resizeInput(); }
      fail(error); if (current?.id === sid) { try { await open(sid); } catch { clear(); } }
    } finally { clearInterval(poll); sending = false; $('chat-cancel').hidden = true; $('chat-state').textContent = ''; $('chat-send').disabled = !current || current.messages.some(m => m.state === 'running'); }
  }
  $('chat-new').addEventListener('click', async () => {
    if (sending) return;
    $('chat-new').disabled = true;
    try { const session = await api('/chat/sessions','POST',{}); ++openVersion; pending = null; render(session); await list(); $('chat-question').focus(); }
    catch (e) { fail(e); } finally { $('chat-new').disabled = false; }
  });
  $('chat-form').addEventListener('submit', e => {
    e.preventDefault(); if(!current || sending || current.messages.some(m=>m.state==='running')) return;
    const question=$('chat-question').value; if(!question.trim())return;
    $('chat-question').value=''; saveDraft(); resizeInput(); send(question);
  });
  $('chat-question').addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing && e.keyCode !== 229) { e.preventDefault(); $('chat-form').requestSubmit(); }
  });
  $('chat-question').addEventListener('input', () => { resizeInput(); saveDraft(); });
  window.addEventListener('pagehide',saveDraft);
  $('chat-jump').addEventListener('click',bottom);
  $('chat-messages').addEventListener('scroll',()=>{ if(nearBottom()) $('chat-jump').hidden=true; });
  $('chat-search').addEventListener('input', () => { clearTimeout(searchTimer); searchTimer=setTimeout(()=>list().catch(fail),250); });
  $('chat-sidebar-toggle').addEventListener('click', () => {
    const hidden = !$('chat-sidebar').hidden; $('chat-sidebar').hidden=hidden;
    $('chat-layout').classList.toggle('sidebar-collapsed',hidden);
    $('chat-sidebar-toggle').setAttribute('aria-expanded',String(!hidden)); $('chat-sidebar-toggle').textContent=hidden?'대화 목록 열기':'대화 목록 접기';
  });
  $('chat-menu').addEventListener('keydown',e=>{if(e.key==='Escape'){ $('chat-menu').open=false; $('chat-menu').querySelector('summary').focus(); }});
  $('chat-cancel').addEventListener('click', async () => {
    if (!pending || !sending) return;
    try { const result=await api('/chat/sessions/'+pending.sid+'/requests/'+pending.requestId+'/cancel','POST',{}); $('chat-state').textContent=result.state==='completed'?'이미 답변을 완료했습니다.':'중단 요청됨 · 실행 중인 모델 호출이 끝나면 초안을 폐기합니다.'; } catch(e) { fail(e); }
  });
  const refresh = () => list().then(() => current && open(current.id)).catch(fail);
  $('chat-refresh').addEventListener('click', refresh);
  document.querySelector('[data-tab="chat"]').addEventListener('click', refresh);
  $('chat-delete').addEventListener('click', async () => {
    if (!current || sending || !confirm('이 대화와 저장된 근거를 삭제할까요?')) return;
    try { await api('/chat/sessions/' + current.id,'DELETE'); ++openVersion; clear(); await list(); } catch (e) { fail(e); }
  });
  if(globalThis.matchMedia?.('(max-width:760px)').matches) collapseSidebar();
  const modeHelp=()=>{ $('chat-mode-help').textContent={auto:'필요할 때 기억을 찾아 답합니다.',general:'개인 기록을 검색하지 않고 최근 대화 맥락으로 답합니다.',memory:'개인 기록에서 확인한 내용으로 답합니다.',hybrid:'일반 지식과 개인 기록을 구분해 답합니다.'}[$('chat-mode').value]; };
  $('chat-mode').addEventListener('change',modeHelp); modeHelp();
}
