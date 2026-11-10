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
let pendingClarification = null;
let activeChatProgress = null;

const searchStages = {
  preparing: '검색에 필요한 모델을 준비하는 중…',
  indexing: '기억 색인을 확인하는 중…',
  retrieving: '과거 기억을 탐색하는 중…',
  answering: '답변을 작성하는 중…',
};

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
    chatStatus.textContent = '일기나 일정을 남기거나, 기억과 지금 기분을 이야기해 보세요.';
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
  return memory.memory_key;
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
  const mood = document.querySelector('.mood.on')?.dataset.mood || '평온함';
  const tags = tagsInput.value.trim();
  const calendar = document.getElementById('emotionCalendar');
  await withDemoRequest(async () => {
    calendar.hidden = true;
    saveStatus.textContent = '기록을 요약하고 검색을 준비하는 중입니다…';
    try {
      const date = dateForDiary(body, chosenDate);
      await persistDemoRecord({ date, title, body, mood, tags, type: '감정' });
      if (bodyInput.value.trim() === body) bodyInput.value = '';
      if ((titleInput.value.trim() || '새로운 기록') === title) titleInput.value = '';
      if (tagsInput.value.trim() === tags) tagsInput.value = '';
      if (dateInput.value === chosenDate) dateInput.value = '';
      saveStatus.textContent = date + ' 감정 기록을 저장했어요. 사색 대화에서 이 기록을 물어볼 수 있어요.';
      calendar.onclick = () => showRecordInCalendar(date);
      calendar.hidden = false;
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

function startChatProgress(reply, initialStage) {
  activeChatProgress?.stop();
  const time = document.createElement('small');
  time.className = 'chat-progress-time';
  time.setAttribute('aria-hidden', 'true');
  const stage = document.createElement('small');
  stage.className = 'chat-progress-stage';
  stage.setAttribute('role', 'status');
  stage.textContent = initialStage;
  reply.before(time);
  reply.after(stage);
  reply.hidden = true;
  const startedAt = performance.now();
  const updateTime = () => {
    time.textContent = Math.floor((performance.now() - startedAt) / 1000) + '초째 생각 중';
  };
  updateTime();
  const timer = setInterval(updateTime, 250);
  const controller = new AbortController();
  let pollTimer;
  const progress = {
    setStage(label) {
      if (stage.textContent !== label) stage.textContent = label;
    },
    watch(id) {
      const poll = async () => {
        try {
          const update = await demoJson('/summary-memory/progress?id=' + id, { signal: controller.signal });
          if (!controller.signal.aborted && searchStages[update.stage]) progress.setStage(searchStages[update.stage]);
        } catch {
          // A missed poll does not interrupt the answer request.
        }
        if (!controller.signal.aborted) pollTimer = setTimeout(poll, 350);
      };
      void poll();
    },
    stop() {
      if (controller.signal.aborted) return;
      controller.abort();
      clearInterval(timer);
      clearTimeout(pollTimer);
      time.remove();
      stage.remove();
      reply.hidden = false;
      if (activeChatProgress === progress) activeChatProgress = null;
    },
  };
  activeChatProgress = progress;
  return progress;
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
  return withDemoRequest(async () => {
    let savedKey;
    if (approved) {
      const reply = addBubble('bot', '기록을 요약하고 검색을 준비하는 중입니다…');
      chatStatus.textContent = '기록 저장 중…';
      try {
        savedKey = await persistDemoRecord(draft.record);
      } catch (error) {
        if (!reply.isConnected) return;
        reply.textContent = '저장 실패: ' + error.message + ' 기록하기를 눌러 다시 시도할 수 있어요.';
        chatStatus.textContent = '저장 실패';
        return;
      }
      if (!reply.isConnected) return;
      reply.textContent = '저장했어요. ' + recordDescription(draft.record) + ' 기록은 달력에서 볼 수 있어요.';
      offerCalendarLink(reply, draft.record.date);
      chatStatus.textContent = '저장 완료';
    } else {
      addBubble('bot', '기록을 취소했어요.');
      chatStatus.textContent = '저장 취소';
    }
    if (pendingRecord === draft) pendingRecord = null;
    draft.actions.remove();
    if (draft.emotion) await answerEmotionInChat(draft.record.body, savedKey);
    chatInput.focus();
    scrollChatToBottom();
  });
}

function normalizeRecordBody(text) {
  return text.normalize('NFC').replace(/\s+/g, ' ').trim();
}

async function offerRecord(reply, record, emotion = false) {
  activeChatProgress?.setStage('같은 날짜에 저장한 기록을 확인하는 중…');
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
    if (emotion) await answerEmotionInChat(record.body, existing.memoryKey);
    return;
  }
  const [, month, day] = record.date.split('-').map(Number);
  const dateLabel = month + '월 ' + day + '일';
  const recordAs = record.type === '일정' ? '일정으로' : '일기로';
  const previous = sameDay.length
    ? dateLabel + ' 기록에 같은 내용은 없어요.'
    : dateLabel + '에 저장된 기록을 찾지 못했어요.';
  reply.textContent = emotion ? '이 이야기를 일기로 기록할까요? 선택하시면 이어서 답해드릴게요.'
    : previous + ' 이 내용을 ' + recordAs + ' 기록할까요?' + (record.schedule ? ' (' + description + ')' : '');
  const actions = document.createElement('div');
  actions.className = 'chat-record-actions';
  reply.after(actions);
  const draft = { record, actions, emotion };
  pendingRecord = draft;
  addChatAction(actions, '기록하기', 'primary', () => confirmRecord(draft, true, '네, 기록해 주세요.'));
  addChatAction(actions, emotion ? '기록 없이 답변' : '취소', 'ghost', () => confirmRecord(draft, false, '아니요, 기록하지 않을게요.'));
  updateDemoControls();
  chatStatus.textContent = '저장 여부를 확인해 주세요.';
}

function askForClarification(reply, question, state) {
  reply.textContent = question;
  pendingClarification = state;
  chatStatus.textContent = '추가 답변을 기다리고 있어요.';
}

async function offerSchedule(reply, draft, followUp, answer) {
  try {
    draft.date ||= dateForSchedule(followUp === 'date' ? answer : draft.body, '', draft.submittedAt);
  } catch {
    askForClarification(reply, '어느 날짜로 일정을 잡을까요? “내일”이나 “11월 12일”처럼 하루를 알려주세요.', { kind: 'date', draft });
    return;
  }
  let time;
  try {
    const unspecified = followUp === 'time' && /^(?:미정|시각 미정|시간 미정)[.!]?$/u.test(answer);
    time = unspecified ? null : timeForSchedule(answer || draft.body);
    if (followUp === 'date' && !time) time = timeForSchedule(draft.body);
    if (followUp === 'time' && !unspecified && !time) throw new Error('시각이 필요해요.');
  } catch {
    askForClarification(reply, '일정은 몇 시에 시작하나요? “오후 3시”처럼 알려주시거나 “시각 미정”이라고 답해 주세요.', { kind: 'time', draft });
    return;
  }
  const body = [draft.body, draft.dateReply, followUp === 'time' ? answer : null].filter(Boolean).join('\n');
  await offerRecord(reply, { date: draft.date, title: draft.title, body, mood: '미지정', type: '일정', schedule: { date: draft.date, time } });
}

function handleChatInput(body, knownIntent) {
  if (demoBusy || !modelPicker.value) return;
  if (pendingRecord) {
    const choice = body.replace(/[.!。！]+$/u, '').trim();
    if (/^(?:네|예|응|그래|좋아|기록하기|(?:기록|저장)해\s*(?:줘|주세요|줘요)|네,?\s*(?:기록|저장)해\s*(?:줘|주세요|줘요))$/.test(choice)) {
      return confirmRecord(pendingRecord, true, body);
    }
    if (/^(?:아니|아니오|아니요|취소|취소해\s*줘|기록 없이 답변|(?:기록|저장)하지\s*마)$/.test(choice)) {
      return confirmRecord(pendingRecord, false, body);
    }
    addBubble('user', body);
    addBubble('bot', '새 기록을 저장할지 먼저 선택해 주세요. 기록하기나 취소를 누르거나, 채팅에 “네” 또는 “아니요”라고 답할 수 있어요.');
    return;
  }

  const clarification = pendingClarification;
  pendingClarification = null;
  const submittedAt = new Date();
  return withDemoRequest(async () => {
    addBubble('user', body);
    const reply = addBubble('bot', '');
    const progress = startChatProgress(reply, '입력 내용을 확인하는 중…');
    chatStatus.textContent = '입력 목적을 확인하고 있어요.';
    try {
      if (clarification && /^취소[.!]?$/u.test(body)) {
        reply.textContent = '확인 중이던 입력을 취소했어요.';
        chatStatus.textContent = '입력 취소';
        return;
      }
      if (clarification?.draft) {
        if (clarification.kind === 'date') clarification.draft.dateReply = body;
        await offerSchedule(reply, clarification.draft, clarification.kind, body);
        return;
      }
      const text = clarification ? clarification.text + '\n추가 설명: ' + body : body;
      const intent = clarification?.kind === 'question' ? 'question' : knownIntent;
      const classified = intent ? { intent } : await demoRequest('intent', clarification ? { text: clarification.text, follow_up: body } : { text });
      if (!reply.isConnected) return;
      if (classified.intent === 'question') {
        await answerInChat(text, reply, progress);
      } else if (classified.intent === 'schedule') {
        await offerSchedule(reply, { body: text, title: classified.title || '일정', submittedAt });
      } else if (classified.intent === 'diary' || classified.intent === 'emotion') {
        const date = dateForDiary(text, '', submittedAt);
        await offerRecord(reply, { date, title: '일기', body: text, mood: '미지정', type: '일기' }, classified.intent === 'emotion');
      } else {
        const kind = classified.clarification_kind === 'question' ? 'question' : 'intent';
        const question = classified.clarification || (kind === 'question' ? '어떤 날짜나 사건을 말씀하시는지 알려주실래요?' : '기록을 남길까요, 아니면 저장된 기억에서 무엇을 찾아볼까요?');
        askForClarification(reply, question, { kind, text });
      }
    } catch (error) {
      if (!reply.isConnected) return;
      pendingClarification ||= clarification;
      reply.textContent = '처리 실패: ' + error.message;
      chatStatus.textContent = '입력을 확인해 주세요.';
      if (!chatInput.value) chatInput.value = body;
    } finally {
      progress.stop();
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

async function answerEmotionInChat(query, excludeMemoryKey) {
  const reply = addBubble('bot', '');
  const progress = startChatProgress(reply, '이야기에 답할 준비를 하는 중…');
  try {
    await answerInChat(query, reply, progress, true, excludeMemoryKey);
  } catch (error) {
    if (!reply.isConnected) return;
    reply.textContent = '답변을 불러오지 못했어요. ' + error.message;
    chatStatus.textContent = '답변 생성 실패';
  } finally {
    progress.stop();
  }
}

async function answerInChat(query, reply, progress, emotion = false, excludeMemoryKey) {
  const progressId = crypto.randomUUID();
  progress.setStage('기억 검색을 요청하는 중…');
  progress.watch(progressId);
  document.getElementById('evidenceDetails').hidden = true;
  const { answer, diary_date } = await demoRequest('search', {
    query, answer: true, use_diary_dates: true, emotion_support: emotion, exclude_memory_key: excludeMemoryKey, progress_id: progressId,
  }).finally(() => progress.stop());
  if (!reply.isConnected) return;
  reply.textContent = answer?.answer || '저장된 기록에서 질문에 답할 만한 내용을 찾지 못했어요.';
  if (answer?.action === 'clarify') {
    askForClarification(reply, answer.answer || '어떤 날짜나 사건을 말씀하시는지 조금 더 알려주실래요?', { kind: 'question', text: query });
    return;
  }
  const citations = answer?.citations || [];
  const citationErrors = answer?.citation_errors || [];
  const snippets = [...new Set(citations.map(({ quote, diary_date: date }) => {
    const compact = quote.replace(/\s+/g, ' ').trim();
    const excerpt = compact.length > 90 ? compact.slice(0, 89) + '…' : compact;
    return (date ? date + ' ' : '') + '“' + excerpt + '”';
  }))].slice(0, 2);
  if (snippets.length || emotion) {
    const note = document.createElement('small');
    note.className = 'chat-source';
    note.textContent = snippets.length ? '참고한 기록 · ' + snippets.join(' / ') : '현재 이야기 바탕 · 참고 기록 없음';
    reply.after(note);
  }
  chatStatus.textContent = citationErrors.length
    ? '인용 검사를 통과하지 못했습니다. 요약 근거를 확인해 주세요.'
    : diary_date ? diary_date + ' 기록 기준 · 답변 완료' : '답변 완료';
}

const homeForm = document.getElementById('homeMemoryForm');
document.addEventListener('pma-chat-reset', () => {
  activeChatProgress?.stop();
  pendingRecord = null;
  pendingClarification = null;
  chatStatus.textContent = '일기나 일정을 남기거나, 기억과 지금 기분을 이야기해 보세요.';
});
homeForm.addEventListener('submit', submitHome);
homeInput.addEventListener('keydown', event => {
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing) return;
  event.preventDefault();
  homeForm.requestSubmit();
});
loadDemoModels();
restoreArchive();
