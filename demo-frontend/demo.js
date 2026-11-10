'use strict';

const demoApi = '/api/baseline';
const modelPicker = document.getElementById('demoModel');
const chatStatus = document.getElementById('demoStatus');
const saveStatus = document.getElementById('demoSaveStatus');
const saveButton = document.getElementById('demoSave');
const sendButton = document.querySelector('.chat-send-btn');
const homeInput = document.getElementById('homeSearch');
const homeSubmit = document.getElementById('homeSubmit');
const homeStatus = document.getElementById('homeStatus');
const archiveStatus = document.getElementById('archiveStatus');
const chatInput = document.getElementById('chatInput');
let demoBusy = false;
let pendingRecord = null;

function updateDemoControls() {
  const disabled = demoBusy || !modelPicker.value;
  modelPicker.disabled = disabled;
  saveButton.disabled = disabled;
  sendButton.disabled = disabled;
  homeSubmit.disabled = disabled;
  for (const button of pendingRecord?.actions.children || []) button.disabled = disabled;
}

async function demoJson(path, options) {
  const response = await fetch(demoApi + path, options);
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || '요청에 실패했습니다.');
  return value;
}

async function demoRequest(path, payload) {
  const boot = await demoJson('/bootstrap');
  if (boot.busy || boot.setup?.status === 'RUNNING') {
    throw new Error('모델 테스트 또는 준비가 진행 중입니다. 끝난 뒤 다시 시도해 주세요.');
  }
  return demoJson('/summary-memory/' + path, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Memory-Lab-Token': boot.token,
    },
    body: JSON.stringify({
      ...payload,
      config: { model: modelPicker.value, route: 'M1', top_k: 3 },
    }),
  });
}

async function loadDemoModels() {
  updateDemoControls();
  try {
    const { runtime } = await demoJson('/bootstrap');
    const models = runtime.models.filter(model => model.role === 'generation' && model.present);
    if (!models.length) {
      throw new Error('모델 준비 화면에서 다운로드를 완료한 뒤 이 페이지를 새로고침해 주세요.');
    }
    for (const model of models) modelPicker.add(new Option(model.name, model.id));
    const activeId = runtime.states.generation.model_id;
    if (runtime.states.generation.status === 'ready' && models.some(model => model.id === activeId)) {
      modelPicker.value = activeId;
    } else if (models.some(model => model.id === 'qwen35-2b-q4')) {
      modelPicker.value = 'qwen35-2b-q4';
    }
    chatStatus.textContent = '일기나 일정을 남기거나 저장한 기록을 질문해 보세요.';
    homeStatus.textContent = '시작하기를 누르면 사색 대화에서 이어집니다. 새 일기나 일정은 확인한 뒤 저장합니다.';
  } catch (error) {
    chatStatus.textContent = error.message;
    saveStatus.textContent = error.message;
    homeStatus.textContent = error.message;
  } finally {
    updateDemoControls();
  }
}

async function withDemoRequest(action) {
  if (demoBusy || !modelPicker.value) return;
  demoBusy = true;
  updateDemoControls();
  try {
    await action();
  } finally {
    demoBusy = false;
    updateDemoControls();
  }
}

function addArchiveRecord(record, memory) {
  const item = {
    ...record,
    memoryKey: memory.memory_key,
    summary: memory.summary,
    mood: memory.mood || record.mood,
    schedule: memory.schedule,
    entities: (memory.structured_index?.cards || []).flatMap(card => card.entities || []),
  };
  const index = records.findIndex(existing => existing.memoryKey === item.memoryKey);
  if (index === -1) records.push(item);
  else records[index] = item;
  return item;
}

function refreshRecords() {
  renderCalendar();
  renderRecent();
  runSearch();
}

async function persistDemoRecord({ date, title, body, mood, tags, type, schedule }) {
  const fields = ['제목: ' + title, '기록일: ' + date, '감정: ' + mood];
  if (schedule) fields.push('일정 시각: ' + (schedule.time || '미정'));
  if (tags) fields.push('태그: ' + tags);
  const { memory } = await demoRequest('save', { text: fields.join('\n') + '\n\n' + body });
  if (!memory?.memory_key) throw new Error('저장한 기록을 확인하지 못했습니다.');
  addArchiveRecord({ date, title, body, mood, tags, type }, memory);
  refreshRecords();
}

async function restoreArchive() {
  const restored = [];
  try {
    const { memories } = await demoJson('/summary-memory');
    for (const memory of memories) {
      const { source } = await demoJson('/summary-memory/original?key=' + encodeURIComponent(memory.memory_key));
      const fields = source?.text.match(/^제목: ([^\r\n]+)\r?\n기록일: (\d{4}-\d{2}-\d{2})\r?\n감정: ([^\r\n]*)(?:\r?\n일정 시각: [^\r\n]*)?(?:\r?\n태그: ([^\r\n]*))?\r?\n\r?\n([\s\S]+)$/);
      if (!fields) {
        if (typeof source?.text !== 'string') continue;
        const date = dateForStoredMemory(source.text, memory.source_timestamp || memory.created_at);
        if (date) restored.push(addArchiveRecord({ date, title: '기록', body: source.text, mood: '미지정', type: '기록' }, memory));
        continue;
      }
      const [, title, date, mood, tags, body] = fields;
      if (!isDiaryDate(date)) continue;
      const type = memory.schedule ? '일정' : title === '일기' ? '일기' : '감정';
      restored.push(addArchiveRecord({ title, date, mood, tags, body, type }, memory));
    }
    archiveStatus.textContent = '';
  } catch (error) {
    archiveStatus.textContent = '저장된 기록 목록을 불러오지 못했습니다. ' + error.message;
    return null;
  }
  refreshRecords();
  return restored;
}

function askFromHome(query) {
  if (demoBusy || !modelPicker.value) return;
  go('chat');
  return handleChatInput(query, 'question');
}

function submitHome(event) {
  event.preventDefault();
  const body = homeInput.value.trim();
  if (!body || demoBusy || !modelPicker.value) return;
  homeInput.value = '';
  go('chat');
  return handleChatInput(body);
}

async function addRecord() {
  const bodyInput = document.getElementById('recordBody');
  const titleInput = document.getElementById('recordTitle');
  const tagsInput = document.getElementById('recordTags');
  const body = bodyInput.value.trim();
  if (!body) {
    saveStatus.textContent = '기록할 내용을 입력해 주세요.';
    bodyInput.focus();
    return;
  }
  const title = titleInput.value.trim() || '새로운 기록';
  const dateInput = document.getElementById('recordDate');
  const chosenDate = dateInput.value;
  const mood = document.querySelector('.mood.on')?.lastChild?.textContent.trim() || '평온함';
  const tags = tagsInput.value.trim();
  await withDemoRequest(async () => {
    saveStatus.textContent = '기록을 요약하고 검색을 준비하는 중입니다…';
    try {
      const date = dateForDiary(body, chosenDate);
      await persistDemoRecord({ date, title, body, mood, tags, type: '감정' });
      if (bodyInput.value.trim() === body) bodyInput.value = '';
      if ((titleInput.value.trim() || '새로운 기록') === title) titleInput.value = '';
      if (tagsInput.value.trim() === tags) tagsInput.value = '';
      if (dateInput.value === chosenDate) dateInput.value = '';
      saveStatus.textContent = '저장 완료. 사색 대화에서 이 기록에 대해 물어보세요.';
    } catch (error) {
      saveStatus.textContent = '저장 실패: ' + error.message;
    }
  });
}

function addBubble(kind, text) {
  const bubble = document.createElement('div');
  bubble.className = 'bubble ' + kind;
  const paragraph = document.createElement('p');
  paragraph.textContent = text;
  bubble.append(paragraph);
  document.getElementById('conversation').append(bubble);
  return paragraph;
}

function addChatAction(actions, label, style, onClick) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = style;
  button.textContent = label;
  button.addEventListener('click', onClick);
  actions.append(button);
}

function showRecordInCalendar(date) {
  const [recordYear, recordMonth] = date.split('-').map(Number);
  year = recordYear;
  month = recordMonth - 1;
  selected = date;
  document.getElementById('archiveInput').value = '';
  go('archive');
}

function offerCalendarLink(reply, date) {
  const actions = document.createElement('div');
  actions.className = 'chat-record-actions';
  reply.after(actions);
  addChatAction(actions, '달력에서 보기', 'ghost', () => showRecordInCalendar(date));
}

function recordDescription({ date, type, title, schedule }) {
  const when = date + (schedule?.time ? ' ' + schedule.time : '');
  return schedule && title !== '일정' ? when + ' 일정 ‘' + title + '’' : when + ' ' + type;
}

function confirmRecord(draft, approved, userReply) {
  if (draft !== pendingRecord || demoBusy || !modelPicker.value) return;
  addBubble('user', userReply);
  if (!approved) {
    pendingRecord = null;
    draft.actions.remove();
    addBubble('bot', '기록을 취소했어요.');
    chatStatus.textContent = '저장 취소';
    chatInput.focus();
    return;
  }
  return withDemoRequest(async () => {
    const reply = addBubble('bot', '기록을 요약하고 검색을 준비하는 중입니다…');
    chatStatus.textContent = '기록 저장 중…';
    try {
      await persistDemoRecord(draft.record);
      if (pendingRecord === draft) pendingRecord = null;
      draft.actions.remove();
      if (!reply.isConnected) return;
      reply.textContent = '저장했어요. ' + recordDescription(draft.record) + ' 기록은 달력에서 볼 수 있어요. 이어서 질문해도 됩니다.';
      offerCalendarLink(reply, draft.record.date);
      chatStatus.textContent = '저장 완료';
    } catch (error) {
      if (!reply.isConnected) return;
      reply.textContent = '저장 실패: ' + error.message + ' 기록하기를 눌러 다시 시도할 수 있어요.';
      chatStatus.textContent = '저장 실패';
    }
    chatInput.focus();
    scrollChatToBottom();
  });
}

function normalizeRecordBody(text) {
  return text.normalize('NFC').replace(/\s+/g, ' ').trim();
}

function isClearDiary(text) {
  if (/^일기\s*[:：]/.test(text)) return true;
  if (/[?？]|내일|모레|다음\s*(?:주|달)|예정|하기로|할\s*계획/.test(text)) return false;
  const statement = text.match(/^(.*?)(?:습니다|다)[.!。！\s]*$/su);
  // Past-tense ㅆ before “다” or “습니다”, as in “정리했다” and “정리했습니다”.
  return Boolean(statement?.[1].normalize('NFD').endsWith('\u11bb'));
}

async function offerRecord(reply, record) {
  const restored = await restoreArchive();
  if (!reply.isConnected) return;
  if (!restored) throw new Error('기존 기록을 확인하지 못했어요. 잠시 뒤 다시 보내 주세요.');
  const body = normalizeRecordBody(record.body);
  const sameDay = restored.filter(item => item.date === record.date);
  const existing = sameDay.find(item => normalizeRecordBody(item.body) === body);
  const description = recordDescription(record);
  if (existing) {
    reply.textContent = description + ' 기록에 같은 내용이 이미 있어요.';
    offerCalendarLink(reply, existing.date);
    chatStatus.textContent = '기존 기록 확인';
    return;
  }
  const [, month, day] = record.date.split('-').map(Number);
  const dateLabel = month + '월 ' + day + '일';
  const recordAs = record.type === '일정' ? '일정으로' : '일기로';
  const previous = sameDay.length
    ? dateLabel + ' 기록에 같은 내용은 없어요.'
    : dateLabel + '에 저장된 기록을 찾지 못했어요.';
  reply.textContent = previous + ' 이 내용을 ' + recordAs + ' 기록할까요?'
    + (record.schedule ? ' (' + description + ')' : '');
  const actions = document.createElement('div');
  actions.className = 'chat-record-actions';
  reply.after(actions);
  const draft = { record, actions };
  pendingRecord = draft;
  addChatAction(actions, '기록하기', 'primary', () => confirmRecord(draft, true, '네, 기록해 주세요.'));
  addChatAction(actions, '취소', 'ghost', () => confirmRecord(draft, false, '아니요, 기록하지 않을게요.'));
  updateDemoControls();
  chatStatus.textContent = '저장 여부를 확인해 주세요.';
}

function handleChatInput(body, knownIntent) {
  if (demoBusy || !modelPicker.value) return;
  if (pendingRecord) {
    const choice = body.replace(/[.!。！]+$/u, '').trim();
    if (/^(?:네|예|응|그래|좋아|기록하기|(?:기록|저장)해\s*(?:줘|주세요|줘요)|네,?\s*(?:기록|저장)해\s*(?:줘|주세요|줘요))$/.test(choice)) {
      return confirmRecord(pendingRecord, true, body);
    }
    if (/^(?:아니|아니오|아니요|취소|취소해\s*줘|(?:기록|저장)하지\s*마)$/.test(choice)) {
      return confirmRecord(pendingRecord, false, body);
    }
    addBubble('user', body);
    addBubble('bot', '새 기록을 저장할지 먼저 선택해 주세요. 기록하기나 취소를 누르거나, 채팅에 “네” 또는 “아니요”라고 답할 수 있어요.');
    return;
  }

  const submittedAt = new Date();
  const intent = knownIntent || (isClearDiary(body) ? 'diary' : null);
  return withDemoRequest(async () => {
    addBubble('user', body);
    const reply = addBubble('bot', '입력하신 내용을 확인하고 있습니다…');
    chatStatus.textContent = intent === 'diary' ? '기존 기록 확인 중…' : '일기·일정·질문 확인 중…';
    try {
      const classified = intent ? { intent } : await demoRequest('intent', { text: body });
      if (!reply.isConnected) return;
      if (classified.intent === 'question') {
        await answerInChat(body, reply);
      } else if (classified.intent === 'diary' || classified.intent === 'schedule') {
        const schedule = classified.intent === 'schedule' ? scheduleForText(body, '', submittedAt) : null;
        const date = schedule?.date || dateForDiary(body, '', submittedAt);
        const type = schedule ? '일정' : '일기';
        await offerRecord(reply, { date, title: schedule ? classified.title || type : type, body, mood: '미지정', type, schedule });
      } else {
        reply.textContent = '일기나 일정이면 “일기로 기록해 줘” 또는 “내일 오후 3시 회의 일정을 기록해 줘”처럼 말해 주세요. 기억을 찾으려면 질문으로 입력해 주세요.';
        chatStatus.textContent = '입력 목적을 확인해 주세요.';
      }
    } catch (error) {
      if (!reply.isConnected) return;
      reply.textContent = error.message === '일정 날짜를 하루로 적거나 날짜를 직접 선택해 주세요.'
        ? '일정이 있는 날짜를 문장에 적어 다시 보내 주세요. 예를 들어 “내일 오후 3시에 회의 일정 기록해 줘”라고 입력할 수 있어요.'
        : '처리 실패: ' + error.message;
      chatStatus.textContent = '입력을 확인해 주세요.';
      if (!chatInput.value) chatInput.value = body;
    } finally {
      if (reply.isConnected) chatInput.focus();
      scrollChatToBottom();
    }
  });
}

function sendChat() {
  const body = chatInput.value.trim();
  if (!body || demoBusy || !modelPicker.value) return;
  chatInput.value = '';
  return handleChatInput(body);
}

async function answerInChat(query, reply) {
  reply.textContent = '저장된 기억을 검색하고 있습니다…';
  const evidence = document.getElementById('evidences');
  evidence.replaceChildren();
  document.getElementById('evidenceDetails').open = false;
  chatStatus.textContent = '답변 생성 중…';
  const { answer, diary_date } = await demoRequest('search', { query, answer: true, use_diary_dates: true });
  if (!reply.isConnected) return;
  reply.textContent = answer?.answer || '저장된 기록에서 질문에 답할 만한 내용을 찾지 못했어요.';
  const citations = answer?.citations || [];
  const citationErrors = answer?.citation_errors || [];
  for (const citation of citations) {
    const item = document.createElement('div');
    item.className = 'evidence';
    item.textContent = citation.quote;
    evidence.append(item);
  }
  if (citations.length === 0) evidence.textContent = '표시할 요약 인용이 없습니다.';
  chatStatus.textContent = citationErrors.length
    ? '인용 검사를 통과하지 못했습니다. 요약 근거를 확인해 주세요.'
    : diary_date ? diary_date + ' 기록 기준 · 답변 완료' : '답변 완료';
}

const homeForm = document.getElementById('homeMemoryForm');
document.addEventListener('pma-chat-reset', () => {
  pendingRecord = null;
  chatStatus.textContent = '일기나 일정을 남기거나 저장한 기록을 질문해 보세요.';
});
homeForm.addEventListener('submit', submitHome);
homeInput.addEventListener('keydown', event => {
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing) return;
  event.preventDefault();
  homeForm.requestSubmit();
});
loadDemoModels();
restoreArchive();
