// Persistent fixed-evidence conversations. All record content is rendered as text.
export function setupChat({api, node, action, notice, today}) {
  const $ = id => document.getElementById(id);
  let search = null, current = null, pending = null;
  async function list() {
    const result = await api('/chat/sessions');
    if (current && !result.items.some(s => s.id === current.id)) {
      current = null; pending = null;
      $('chat-conversation').hidden = true;
      $('chat-messages').replaceChildren(); $('chat-evidence').replaceChildren();
    }
    $('chat-list').replaceChildren();
    if (!result.items.length) $('chat-list').append(node('p', '저장된 대화가 없습니다.', 'muted'));
    for (const session of result.items) {
      $('chat-list').append(action(session.title + (session.state === 'read_only' ? ' · 읽기 전용' : ''), () => open(session.id)));
    }
  }
  function source(row, refs = row.evidence) {
    const details = node('details');
    const stamp = row.reference_time || row.recorded_at;
    const dateLabel = stamp ? new Date(stamp).toLocaleString('ko-KR') : '날짜 미상';
    details.append(node('summary', `원문 확인 · 버전 ${row.version} · ${dateLabel}`));
    details.append(node('p', '기록 기준/저장 날짜이며 사건 날짜와 다를 수 있습니다.', 'muted'));
    const text = node('pre', row.source_text, 'chat-source');
    details.append(text);
    for (const ref of refs) details.append(node('blockquote', ref.quote));
    return details;
  }
  function render(session) {
    current = session;
    $('chat-conversation').hidden = false;
    $('chat-title').textContent = session.title;
    $('chat-state').textContent = session.state === 'read_only'
      ? '원본이 수정되어 읽기 전용입니다. 새 검색으로 대화를 시작하세요.'
      : '선택한 근거만 사용합니다. 새 기록은 새 대화에서 선택하세요.';
    $('chat-question').disabled = session.state !== 'active';
    $('chat-send').disabled = session.state !== 'active' || session.messages.some(m => m.state === 'running');
    $('chat-evidence').replaceChildren(...session.evidence.map(row => source(row)));
    $('chat-messages').replaceChildren();
    for (const message of session.messages) {
      const turn = node('article', undefined, 'chat-turn');
      turn.append(node('h3', '나'), node('p', message.question));
      if (message.state === 'failed') {
        turn.append(node('p', '답변을 완료하지 못했습니다. 다시 시도할 수 있습니다.', 'muted'));
        if (session.state === 'active') turn.append(action('다시 시도', () => send(message.question, message.request_id)));
      } else if (message.state === 'running') {
        turn.append(node('p', '답변을 작성 중입니다. 잠시 후 대화 새로고침을 누르세요.'));
      } else {
        const response = message.response;
        turn.append(node('h3', 'AI'));
        if (response.status === 'needs_clarification') turn.append(node('p', response.clarification));
        if (response.status === 'insufficient_evidence') turn.append(node('p', '선택된 기록에서 답변을 뒷받침할 근거를 확인하지 못했습니다. 새 검색으로 다른 기록을 선택해 주세요.'));
        for (const [index, item] of response.items.entries()) {
          turn.append(node('p', item.text));
          for (const id of item.citations) {
            const row = session.evidence.find(r => r.id === id);
            const refs = (response.citation_details || []).filter(ref => ref.item_index === index && ref.memory_id === id);
            if (row) turn.append(source(row, refs.length ? refs : row.evidence));
          }
        }
      }
      $('chat-messages').append(turn);
    }
  }
  async function open(id) {
    const session = await api('/chat/sessions/' + encodeURIComponent(id));
    if (current?.id !== id) pending = null;
    render(session);
  }
  async function send(question, requestId) {
    if (!current || current.state !== 'active') return;
    const sid = current.id;
    pending = {sid, question, requestId: requestId || (pending?.sid === sid && pending.question === question ? pending.requestId : crypto.randomUUID())};
    $('chat-send').disabled = true;
    notice('선택한 기록을 바탕으로 답변을 검증하고 있습니다.');
    try {
      await api('/chat/sessions/' + sid + '/messages', 'POST', {question, request_id: pending.requestId, today: today()});
      if (current?.id === sid) { pending = null; $('chat-question').value = ''; await open(sid); }
      await list();
      notice('');
    } catch (error) {
      notice(error.message, true);
      if (current?.id === sid) {
        try { await open(sid); } catch { $('chat-conversation').hidden = true; current = null; }
      }
    } finally { $('chat-send').disabled = !current || current.state !== 'active'; }
  }
  $('chat-search-form').addEventListener('submit', async event => {
    event.preventDefault();
    $('chat-search-button').disabled = true;
    $('chat-start').disabled = true;
    search = null;
    $('chat-results').replaceChildren();
    try {
      const filters = {date_from: $('chat-date-from').value || null, date_to: $('chat-date-to').value || null};
      search = await api('/chat/searches', 'POST', {question: $('chat-search-question').value, filters, today: today()});
      if (!search.results.length) $('chat-results').append(node('p', '검색된 근거가 없습니다. 질문이나 기간을 바꿔 보세요.'));
      if (search.facts_pending) $('chat-results').append(node('p', '일부 기록의 검색 정보를 정리 중입니다. 결과가 완전하지 않을 수 있습니다.'));
      for (const row of search.results) {
        const card = node('article', undefined, 'chat-turn');
        const label = node('label');
        const check = node('input'); check.type = 'checkbox'; check.value = row.id;
        label.append(check, document.createTextNode(' ' + row.content));
        card.append(label, source(row)); $('chat-results').append(card);
      }
      $('chat-start').disabled = !search.results.length;
    } catch (error) { notice(error.message, true); }
    finally { $('chat-search-button').disabled = false; }
  });
  $('chat-start').addEventListener('click', async () => {
    const selected_ids = [...$('chat-results').querySelectorAll('input:checked')].map(el => el.value);
    if (!selected_ids.length) { notice('대화에 사용할 기억을 선택하세요.', true); return; }
    $('chat-start').disabled = true;
    try {
      const session = await api('/chat/sessions', 'POST', {search_id: search.search_id, selected_ids});
      pending = null; render(session); await list(); $('chat-question').focus();
    } catch (error) { notice(error.message, true); }
    finally { $('chat-start').disabled = !search; }
  });
  $('chat-form').addEventListener('submit', event => { event.preventDefault(); send($('chat-question').value); });
  $('chat-refresh').addEventListener('click', () => list().then(() => current && open(current.id)).catch(e => notice(e.message, true)));
  $('chat-delete').addEventListener('click', async () => {
    if (!current || !confirm('이 대화와 저장된 근거를 삭제할까요?')) return;
    try { await api('/chat/sessions/' + current.id, 'DELETE'); current = null; pending = null; $('chat-conversation').hidden = true; await list(); }
    catch (error) { notice(error.message, true); }
  });
  document.querySelector('[data-tab="chat"]').addEventListener('click', () => list().then(() => current && open(current.id)).catch(e => notice(e.message, true)));
}
