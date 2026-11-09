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
    homeStatus.textContent = '일기 첫머리에 날짜나 “어제”를 적을 수 있어요. 날짜가 없으면 오늘로 저장합니다.';
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

function validDiaryDate(year, month, day) {
  const date = new Date(year, month - 1, day, 12);
  if (date.getFullYear() !== year || date.getMonth() + 1 !== month || date.getDate() !== day) {
    throw new Error('기록 날짜를 확인해 주세요.');
  }
  return key(year, month - 1, day);
}

function diaryDate(text, chosenDate, now = new Date()) {
  const dateText = chosenDate || text.replace(/^일기\s*[:：]\s*/, '');
  const full = dateText.match(/^(\d{4})[-./](\d{1,2})[-./](\d{1,2})(?!\d)/)
    || dateText.match(/^(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일/);
  if (full) return validDiaryDate(...full.slice(1).map(Number));
  const monthDay = dateText.match(/^(\d{1,2})\s*월\s*(\d{1,2})\s*일/);
  if (monthDay) return validDiaryDate(now.getFullYear(), ...monthDay.slice(1).map(Number));
  const relative = dateText.match(/^(그저께|엊그제|어제|오늘)(?:는|에)?(?=\s|[,.!:：]|$)/)?.[1];
  const daysBack = { 그저께: 2, 엊그제: 2, 어제: 1, 오늘: 0 }[relative] || 0;
  const date = new Date(now.getFullYear(), now.getMonth(), now.getDate() - daysBack, 12);
  return key(date.getFullYear(), date.getMonth(), date.getDate());
}

function homeIntent(text) {
  if (/^일기\s*[:：]/.test(text)) return 'diary';
  if (/[?？]\s*$|(?:알려\s*줘|찾아\s*줘|보여\s*줘|뭐지|뭐였지|했지|였지|인가요|나요|까요|맞아)\s*[.!。]*$/.test(text)) return 'question';
  if (/(?:^|\s)(?:누가|누구|뭐|무엇|언제|어디|왜|어떻게)/.test(text)
      && /(?:었어|았어|했어|였어|이야|야)\s*[.!。]*$/.test(text)) return 'question';
  // A final ㅆ before “다” catches past forms such as “마셨다” and “갔다”.
  const pastStatement = /\u11bb\u1103\u1161\s*[.!。]*$/.test(text.normalize('NFD'));
  if (/^(?:오늘|어제|그저께|엊그제)(?:는|에)?(?:\s|[,.!:：])/.test(text)
      || pastStatement
      || /(?:한다|된다|있다|없다|이다|같다|했어|갔어|봤어|었어|았어|였어|어요|아요|습니다)\s*[.!。]*$/.test(text)) {
    return 'diary';
  }
  return 'question';
}

function addArchiveRecord(record) {
  if (!records.some(item => item.memoryKey === record.memoryKey)) records.push(record);
}

async function persistDemoRecord({ date, title, body, mood, tags, type }) {
  const fields = ['제목: ' + title, '기록일: ' + date, '감정: ' + mood];
  if (tags) fields.push('태그: ' + tags);
  const { memory } = await demoRequest('save', { text: fields.join('\n') + '\n\n' + body });
  if (!memory?.memory_key) throw new Error('저장한 기록을 확인하지 못했습니다.');
  addArchiveRecord({ date, title, body, mood, type, memoryKey: memory.memory_key });
}

async function restoreArchive() {
  try {
    const { memories } = await demoJson('/summary-memory');
    for (const memory of memories) {
      const { source } = await demoJson('/summary-memory/original?key=' + encodeURIComponent(memory.memory_key));
      const fields = source?.text.match(/^제목: ([^\r\n]+)\r?\n기록일: (\d{4}-\d{2}-\d{2})\r?\n감정: ([^\r\n]+)(?:\r?\n태그: [^\r\n]*)?\r?\n\r?\n([\s\S]+)$/);
      if (!fields) continue;
      const [, title, date, mood, body] = fields;
      addArchiveRecord({ title, date, mood, body, type: title === '일기' ? '일기' : '감정', memoryKey: memory.memory_key });
    }
  } catch (error) {
    archiveStatus.textContent = '저장된 기록 목록을 불러오지 못했습니다. ' + error.message;
  }
  renderCalendar();
  renderRecent();
  runSearch();
}

function askFromHome(query) {
  if (demoBusy || !modelPicker.value) return;
  go('chat');
  newChat();
  document.getElementById('chatInput').value = query;
  return sendChat();
}

async function submitHome(event) {
  event.preventDefault();
  const body = homeInput.value.trim();
  if (!body || demoBusy || !modelPicker.value) return;
  const mode = document.getElementById('homeMode').value;
  if ((mode === 'auto' ? homeIntent(body) : mode) === 'question') {
    homeInput.value = '';
    await askFromHome(body);
    return;
  }

  const chosenDate = homeDate.value;
  await withDemoRequest(async () => {
    try {
      const date = diaryDate(body, chosenDate);
      homeStatus.textContent = date + ' 일기를 요약해 저장하는 중입니다…';
      await persistDemoRecord({ date, title: '일기', body, mood: '미지정', type: '일기' });
      if (homeInput.value.trim() === body) homeInput.value = '';
      if (homeDate.value === chosenDate) homeDate.value = '';
      const [recordYear, recordMonth] = date.split('-').map(Number);
      year = recordYear;
      month = recordMonth - 1;
      selected = date;
      document.getElementById('archiveInput').value = '';
      archiveStatus.textContent = date + ' 일기 저장 완료';
      homeStatus.textContent = date + ' 일기를 저장했습니다.';
      go('archive');
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
  const date = document.getElementById('recordDate').value || today;
  const mood = document.querySelector('.mood.on')?.textContent.trim() || '평온함';
  const tags = tagsInput.value.trim();
  await withDemoRequest(async () => {
    saveStatus.textContent = '기록을 요약하고 검색을 준비하는 중입니다…';
    try {
      await persistDemoRecord({ date, title, body, mood, tags, type: '감정' });
      if (bodyInput.value.trim() === body) bodyInput.value = '';
      if ((titleInput.value.trim() || '새로운 기록') === title) titleInput.value = '';
      if (tagsInput.value.trim() === tags) tagsInput.value = '';
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

  await withDemoRequest(async () => {
    input.value = '';
    addBubble('user', query);
    const reply = addBubble('bot', '저장된 기억을 검색하고 있습니다…');
    const details = document.getElementById('evidenceDetails');
    const evidence = document.getElementById('evidences');
    evidence.replaceChildren();
    details.open = false;
    chatStatus.textContent = '답변 생성 중…';
    try {
      const { answer } = await demoRequest('search', { query, answer: true });
      if (!reply.isConnected) {
        chatStatus.textContent = '질문을 입력해 주세요.';
        return;
      }
      reply.textContent = answer?.answer || '이 질문에 답할 수 있는 기억을 찾지 못했습니다.';
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
        : '답변 완료';
    } catch (error) {
      reply.textContent = '질문 처리 실패: ' + error.message;
      chatStatus.textContent = '질문 처리 실패';
      if (!input.value) input.value = query;
    }
    input.focus();
    scrollChatToBottom();
  });
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
