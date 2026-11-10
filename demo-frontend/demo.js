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
const homeDate = document.getElementById('homeDate');
const archiveStatus = document.getElementById('archiveStatus');
const homeSaved = document.getElementById('homeSaved');
let demoBusy = false;

function updateDemoControls() {
  const disabled = demoBusy || !modelPicker.value;
  modelPicker.disabled = disabled;
  saveButton.disabled = disabled;
  sendButton.disabled = disabled;
  homeSubmit.disabled = disabled;
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
    chatStatus.textContent = '저장한 기록을 질문해 보세요.';
    homeStatus.textContent = '로컬 AI가 일기, 일정, 기억 질문을 구분합니다. 날짜는 한국 시간 기준입니다.';
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
}

function refreshRecords() {
  renderCalendar();
  renderRecent();
  runSearch();
  renderConstellation();
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
  try {
    const { memories } = await demoJson('/summary-memory');
    for (const memory of memories) {
      const { source } = await demoJson('/summary-memory/original?key=' + encodeURIComponent(memory.memory_key));
      const fields = source?.text.match(/^제목: ([^\r\n]+)\r?\n기록일: (\d{4}-\d{2}-\d{2})\r?\n감정: ([^\r\n]*)(?:\r?\n일정 시각: [^\r\n]*)?(?:\r?\n태그: ([^\r\n]*))?\r?\n\r?\n([\s\S]+)$/);
      if (!fields) {
        if (typeof source?.text !== 'string') continue;
        const date = dateForStoredMemory(source.text, memory.source_timestamp || memory.created_at);
        if (date) addArchiveRecord({ date, title: '기록', body: source.text, mood: '미지정', type: '기록' }, memory);
        continue;
      }
      const [, title, date, mood, tags, body] = fields;
      if (!isDiaryDate(date)) continue;
      const type = memory.schedule ? '일정' : title === '일기' ? '일기' : '감정';
      addArchiveRecord({ title, date, mood, tags, body, type }, memory);
    }
  } catch (error) {
    archiveStatus.textContent = '저장된 기록 목록을 불러오지 못했습니다. ' + error.message;
  }
  refreshRecords();
}

function openHomeChat() {
  go('chat');
  newChat();
}

function askFromHome(query) {
  return withDemoRequest(async () => {
    openHomeChat();
    await answerInChat(query);
  });
}

async function submitHome(event) {
  event.preventDefault();
  const body = homeInput.value.trim();
  if (!body || demoBusy || !modelPicker.value) return;
  const modePicker = document.getElementById('homeMode');
  const mode = modePicker.value;
  const chosenDate = homeDate.value;
  const submittedAt = new Date();
  await withDemoRequest(async () => {
    let intent = mode;
    let scheduleTitle;
    if (mode === 'auto') {
      homeStatus.textContent = '로컬 AI가 일기, 일정, 기억 질문을 확인하는 중입니다…';
      try {
        ({ intent, title: scheduleTitle } = await demoRequest('intent', { text: body }));
      } catch (error) {
        homeStatus.textContent = '자동 판단 실패: ' + error.message + ' 입력 방식을 직접 선택해 주세요.';
        return;
      }
    }
    if (intent === 'question') {
      if (homeInput.value.trim() === body) homeInput.value = '';
      homeStatus.textContent = '기억 질문으로 보냈습니다.';
      openHomeChat();
      await answerInChat(body);
      return;
    }
    if (intent !== 'diary' && intent !== 'schedule') {
      homeStatus.textContent = '입력 목적이 확실하지 않습니다. 일기, 일정, 질문 중에서 직접 선택해 주세요.';
      modePicker.focus();
      return;
    }
    try {
      const schedule = intent === 'schedule' ? scheduleForText(body, chosenDate, submittedAt) : null;
      const date = schedule?.date || dateForDiary(body, chosenDate, submittedAt);
      const type = schedule ? '일정' : '일기';
      const title = schedule ? scheduleTitle || '일정' : '일기';
      homeStatus.textContent = date + (schedule ? ' 일정을' : ' 일기를') + ' 저장하는 중입니다…';
      await persistDemoRecord({ date, title, body, mood: '미지정', type, schedule });
      if (homeInput.value.trim() === body) homeInput.value = '';
      if (homeDate.value === chosenDate) homeDate.value = '';
      const [, month, day] = date.split('-').map(Number);
      const when = month + '월 ' + day + '일' + (schedule?.time ? ' ' + schedule.time : '');
      const message = when + (schedule ? ' 일정이' : ' 일기가') + ' 저장되었습니다.';
      homeStatus.textContent = message;
      document.getElementById('homeSavedMessage').textContent = message;
      homeSaved.showModal();
    } catch (error) {
      homeStatus.textContent = '저장 실패: ' + error.message;
    }
  });
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

async function sendChat() {
  const input = document.getElementById('chatInput');
  const query = input.value.trim();
  if (!query) return;

  await withDemoRequest(() => {
    input.value = '';
    return answerInChat(query);
  });
}

async function answerInChat(query) {
    const input = document.getElementById('chatInput');
    addBubble('user', query);
    const reply = addBubble('bot', '저장된 기억을 검색하고 있습니다…');
    const details = document.getElementById('evidenceDetails');
    const evidence = document.getElementById('evidences');
    evidence.replaceChildren();
    details.open = false;
    chatStatus.textContent = '답변 생성 중…';
    try {
      const { answer, diary_date } = await demoRequest('search', { query, answer: true, use_diary_dates: true });
      if (!reply.isConnected) {
        chatStatus.textContent = '질문을 입력해 주세요.';
        return;
      }
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
    } catch (error) {
      reply.textContent = '질문 처리 실패: ' + error.message;
      chatStatus.textContent = '질문 처리 실패';
      if (!input.value) input.value = query;
    }
    input.focus();
    scrollChatToBottom();
}

const homeForm = document.getElementById('homeMemoryForm');
homeForm.addEventListener('submit', submitHome);
homeInput.addEventListener('keydown', event => {
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing) return;
  event.preventDefault();
  homeForm.requestSubmit();
});
loadDemoModels();
restoreArchive();
