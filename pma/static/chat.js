// Text-only rendering: model output never becomes HTML or executable content.
export function setupChat({api, node, action, notice, today}) {
  const $ = id => document.getElementById(id);
  let current = null, pending = null, sending = false, openVersion = 0, listVersion = 0;
  let contextId = null, evidenceTrigger = null, searchTimer = null;
  const states = {resolving_context:'대화 맥락을 살펴보고 있어요', searching:'관련 기록을 찾고 있어요', generating:'답변을 작성하고 있어요', validating:'답변과 근거를 확인하고 있어요'};
  const validTurn = m => m.state === 'completed' && m.response && !m.error_code;
  function closeEvidence() {
    $('chat-evidence-panel').hidden = true;
    $('chat-layout').classList.remove('with-evidence');
    evidenceTrigger?.focus(); evidenceTrigger = null;
  }
  function context() {
    const target = current?.messages.find(m => m.id === contextId && validTurn(m));
    if (!target) contextId = null;
    $('chat-context').replaceChildren(node('span', target ? '이어서 이야기할 주제: ' + target.question : '최근 대화 흐름을 따라 이야기합니다.'));
    if (target) $('chat-context').append(action('선택 해제', () => { contextId = null; context(); }));
    $('chat-context').append(action('대상·조건 정정', () => {
      $('chat-question').value = '정정할게. '; $('chat-question').focus();
    }, 'link'));
  }
  function chooseTopic(message) {
    contextId = message.id; context(); $('chat-topics').open = false; $('chat-question').focus();
  }
  function collapseSidebar() {
    $('chat-sidebar').hidden = true; $('chat-layout').classList.add('sidebar-collapsed');
    $('chat-sidebar-toggle').setAttribute('aria-expanded','false'); $('chat-sidebar-toggle').textContent='대화 목록 열기';
  }
  const fail = e => notice(e.message, true);
  const bottom = () => { $('chat-messages').scrollTop = $('chat-messages').scrollHeight; };
  function clear() {
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
      original.append(document.createTextNode(slice(cursor, ref.start)), node('mark', ref.quote));
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
    const button = action('근거 ' + groups.length + '건', () => {
      evidenceTrigger = button; $('chat-evidence-content').replaceChildren();
      if (outdated) $('chat-evidence-content').append(node('p','이전 기록 기준입니다. 아래 원문은 이 답변을 만들 당시 버전입니다.', 'chat-warning'));
      for (const {row,refs} of groups) { const detail = source(row,refs); detail.open = true; $('chat-evidence-content').append(detail); }
      $('chat-evidence-panel').hidden = false; $('chat-layout').classList.add('with-evidence'); $('chat-evidence-panel').focus();
    }, 'citation');
    button.setAttribute('aria-controls','chat-evidence-panel'); return button;
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
    const types = {text:'paragraph',evidence_group:'list',event_timeline:'timeline',evidence_comparison:'table',claim_coverage:'list',clarification_choices:'list'};
    const presentation = Array.isArray(response.presentation) ? response.presentation.map(b => b && ({...b,semanticType:b.type,type:types[b.type] || 'paragraph'})) : response.blocks;
    const blocks = [...(Array.isArray(presentation) ? presentation : []),
      {type:'paragraph', item_indices:response.items.map((_,i)=>i)}];
    for (const block of blocks) {
      if (!block || !Array.isArray(block.item_indices)) continue;
      const allowed = ['paragraph','list','timeline','entity','table'];
      const style = allowed.includes(block.type) ? block.type : 'paragraph';
      const wrap = node(style === 'list' ? 'ul' : style === 'timeline' ? 'ol' : style === 'table' ? 'table' : 'div', undefined, 'chat-block chat-block-' + style);
      if (block.semanticType === 'claim_coverage') parent.append(node('h3','답변과 기록의 한계'));
      if (block.semanticType === 'evidence_comparison') wrap.append(node('caption','기록에서 확인한 내용 · 각 근거를 비교해 보세요'));
      for (const i of block.item_indices) {
        if (!Number.isInteger(i) || i < 0 || i >= response.items.length) continue;
        const item = response.items[i]; if (!item || shown.has(i)) continue; shown.add(i);
        const entry = node(style === 'list' || style === 'timeline' ? 'li' : style === 'table' ? 'tr' : 'div');
        const cell = style === 'table' ? node('td') : entry;
        if (item.source_type === 'inference') cell.append(node('small','제안 · 추론','muted'));
        cell.append(richText(item.text));
        const groups = validRefs(response,evidence,i);
        if (groups.length) cell.append(citationButton(groups,outdated));
        if (cell !== entry) entry.append(cell); wrap.append(entry);
      }
      parent.append(wrap);
    }
  }
  function render(session) {
    const switched = current?.id !== session.id;
    if (switched) contextId = session.messages.filter(validTurn).at(-1)?.id || null;
    if (switched && globalThis.matchMedia?.('(max-width:900px)').matches) collapseSidebar();
    closeEvidence();
    if (switched) $('chat-mode').value = session.mode === 'hybrid' ? 'memory' : session.mode || 'auto';
    current = session; $('chat-empty').hidden = true; $('chat-conversation').hidden = false;
    $('chat-title').textContent = session.title; $('chat-messages').replaceChildren();
    context(); $('chat-topic-list').replaceChildren();
    for (const m of session.messages.filter(validTurn)) {
      if(m.response.status==='needs_clarification' && session.messages.at(-1)?.id!==m.id) continue;
      $('chat-topic-list').append(action(m.question, () => chooseTopic(m), 'chat-topic link'));
    }
    for (const message of session.messages) {
      const user = node('article', undefined, 'chat-bubble chat-user');
      user.append(node('small','나'), node('p', message.question)); $('chat-messages').append(user);
      const ai = node('article', undefined, 'chat-bubble chat-ai'); ai.append(node('small','AI'));
      if (message.error_code === 'SOURCE_DELETED') ai.append(node('p','참고한 기록이 삭제되어 이 답변을 지웠습니다.', 'muted'));
      else if (message.state === 'failed') {
        ai.append(node('p',message.error_code === 'CANCELLED' ? '중단한 요청입니다. 검증되지 않은 답변은 보관하지 않습니다.' : '답변을 완료하지 못했습니다. 기록이 없다는 뜻은 아닙니다.', 'muted'), action('다시 시도', () => send(message.question, message.request_id, message.request_today, message.context_message_id, message.mode || 'auto')));
      } else if (message.state === 'running') ai.append(node('p','답변을 준비하고 있습니다. 잠시 후 새로고침해 주세요.', 'muted'), action('요청 중단',async()=>{
        await api('/chat/sessions/'+session.id+'/requests/'+message.request_id+'/cancel','POST',{}); await open(session.id);
      }));
      else if (message.response) {
        if (message.error_code === 'SOURCE_MODIFIED') ai.append(node('p','이전 기록 기준 · 원본이 변경되었습니다.', 'chat-warning'));
        const r = message.response;
        if (r.status === 'needs_clarification') ai.append(node('p',r.clarification));
        if (r.status === 'insufficient_evidence') ai.append(node('p',r.notice || '관련 기록에서 답변을 뒷받침할 근거를 확인하지 못했습니다.'));
        if (r.status !== 'needs_clarification') content(ai, r, message.evidence || [],message.error_code==='SOURCE_MODIFIED');
        if (r.status === 'needs_clarification') {
          const card = node('div',undefined,'chat-clarification');
          const expired = !!message.error_code || session.messages.at(-1)?.id !== message.id;
          if (expired) { card.append(node('p','이 선택은 만료되었습니다. 현재 기록으로 다시 질문해 주세요.', 'muted')); content(card,r,message.evidence || [],message.error_code==='SOURCE_MODIFIED'); }
          else {
            for (let i=0;i<r.items.length;i++) {
              const groups=validRefs(r,message.evidence || [],i);
              if (!groups.length) continue;
              const option=node('div',undefined,'chat-choice');
              option.append(action(r.items[i].text, () => send(r.items[i].text, undefined, undefined, message.id)),citationButton(groups));
              card.append(option);
            }
            card.append(action('직접 설명하기', () => chooseTopic(message)),action('선택 취소 · 주제 바꾸기', () => { contextId=null; context(); card.replaceChildren(node('p','새로운 질문을 입력해 주세요.')); $('chat-question').focus(); }));
          }
          card.append(action('현재 기록으로 다시 검색', () => send(message.question,undefined,undefined,null)));
          ai.append(card);
        }
        if (r.validation === 'rejected') ai.append(node('p','근거 검증을 통과하지 못한 답변은 표시하지 않았습니다.', 'chat-warning'));
        ai.append(action('답변 복사', async () => {
          await navigator.clipboard.writeText([r.clarification,r.notice,...r.items.map(i=>i.text)].filter(Boolean).join('\n\n')); notice('답변을 복사했습니다.');
        }, 'link'));
        if (r.index_notice) ai.append(node('p',r.index_notice,'muted'));
      }
      $('chat-messages').append(ai);
    }
    if (!session.messages.length) $('chat-messages').append(node('p','편하게 말을 걸어 보세요. 궁금한 기억도 함께 찾을 수 있어요.', 'chat-welcome'));
    $('chat-send').disabled = sending || session.messages.some(m => m.state === 'running'); bottom();
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
  async function open(id) {
    const version = ++openVersion;
    const session = await api('/chat/sessions/' + encodeURIComponent(id));
    if (version !== openVersion) return;
    if (current?.id !== id) pending = null;
    render(session);
  }
  async function send(question, requestId, requestToday, requestedContext, requestedMode) {
    if (!current || sending || !question.trim()) return;
    const sid = current.id;
    const req = requestId || (pending?.sid === sid && pending.question === question ? pending.requestId : crypto.randomUUID());
    const requestDate = requestToday !== undefined ? requestToday : pending?.requestId === req ? pending.today : today();
    const anchor = requestedContext !== undefined ? requestedContext : pending?.requestId === req ? pending.contextId : contextId;
    const mode = requestedMode ?? (pending?.requestId === req ? pending.mode : $('chat-mode').value || 'auto');
    pending = {sid, question, requestId:req, today:requestDate, contextId:anchor, mode}; sending = true; $('chat-send').disabled = true; $('chat-cancel').hidden = false;
    const user = node('article',question,'chat-bubble chat-user');
    const progress = node('article','맥락을 살펴보고 필요한 기억과 답변을 확인하고 있어요…','chat-bubble chat-ai chat-progress');
    $('chat-messages').append(user,progress); bottom();
    let polling = false;
    const poll = setInterval(async () => {
      if (polling) return; polling = true;
      try { const state = await api('/chat/sessions/' + sid + '/requests/' + req);
        if (current?.id === sid) { const label = state.error_code === 'CANCELLED' ? '중단 요청을 마무리하고 있어요' : states[state.phase] || '요청을 준비하고 있어요'; progress.textContent = label; $('chat-state').textContent = label; }
      } catch { /* The final request reports connection failures. */ } finally { polling = false; }
    }, 1200);
    try {
      const result = await api('/chat/sessions/' + sid + '/messages','POST',{question,request_id:req,today:requestDate,context_message_id:anchor || null,mode});
      if (current?.id === sid) { pending = null; contextId = result.message_id || null; if ($('chat-question').value === question) $('chat-question').value = ''; await open(sid); }
      await list(); notice('');
    } catch (error) {
      fail(error); if (current?.id === sid) { try { await open(sid); } catch { clear(); } }
    } finally { clearInterval(poll); sending = false; $('chat-cancel').hidden = true; $('chat-state').textContent = '입력 대기 · 필요한 기억은 기록에서 다시 확인합니다.'; $('chat-send').disabled = !current || current.messages.some(m => m.state === 'running'); }
  }
  $('chat-new').addEventListener('click', async () => {
    if (sending) return;
    $('chat-new').disabled = true;
    try { const session = await api('/chat/sessions','POST',{}); ++openVersion; pending = null; $('chat-question').value = ''; render(session); await list(); $('chat-question').focus(); }
    catch (e) { fail(e); } finally { $('chat-new').disabled = false; }
  });
  $('chat-form').addEventListener('submit', e => { e.preventDefault(); send($('chat-question').value); });
  $('chat-question').addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing && e.keyCode !== 229) { e.preventDefault(); $('chat-form').requestSubmit(); }
  });
  $('chat-question').addEventListener('input', () => { $('chat-question').style.height='auto'; $('chat-question').style.height=Math.min($('chat-question').scrollHeight,220)+'px'; });
  $('chat-search').addEventListener('input', () => { clearTimeout(searchTimer); searchTimer=setTimeout(()=>list().catch(fail),250); });
  $('chat-sidebar-toggle').addEventListener('click', () => {
    const hidden = !$('chat-sidebar').hidden; $('chat-sidebar').hidden=hidden;
    $('chat-layout').classList.toggle('sidebar-collapsed',hidden);
    $('chat-sidebar-toggle').setAttribute('aria-expanded',String(!hidden)); $('chat-sidebar-toggle').textContent=hidden?'대화 목록 열기':'대화 목록 접기';
  });
  $('chat-evidence-close').addEventListener('click', closeEvidence);
  $('chat-evidence-panel').addEventListener('keydown', e => { if(e.key==='Escape') closeEvidence(); });
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
}
