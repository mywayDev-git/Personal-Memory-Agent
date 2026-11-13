'use strict';

const demoApi = '/api/baseline';
const modelPicker = document.createElement('select');
const chatStatus = document.querySelector('.chat-disclaimer');
const saveStatus = document.querySelector('#emotion .notice');
const saveButton = document.querySelector('#emotion .primary');
const sendButton = document.getElementById('chatSend');
const homeInput = document.getElementById('homeSearch');
const homeSubmit = document.querySelector('#home .chat-send-btn');
const homeStatus = {set textContent(value){homeInput.title=value;homeSubmit.title=value;}};
const archiveStatus = {set textContent(value){archiveError=value;}};
const chatInput = document.getElementById('chatInput');
const conversation = document.getElementById('conversation');
const historyList = document.getElementById('chatHistory');
const newChatButtons = [...document.querySelectorAll('[onclick="newChat()"]')];
let archiveError='';
let searchVersion=0;
let archiveMatches=[];
let connectionError='';
const messageActions = new WeakMap();
const chatHistoryState = { threads: [], activeId: null };
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
  modelPicker.disabled=demoBusy;
  saveButton.disabled=demoBusy;
  sendButton.disabled=demoBusy||!chatInput.value.trim();
  homeSubmit.disabled=demoBusy;
  for(const button of newChatButtons)button.disabled=demoBusy;
  for(const button of historyList.querySelectorAll('button'))button.disabled=demoBusy;
  for(const button of document.querySelectorAll('.chat-followups button'))button.disabled=demoBusy;
}

async function demoJson(path, options) {
  let response;
  try {response=await fetch(demoApi+path,options);}
  catch(error){if(error.name==='AbortError')throw error;throw Error('로컬 기억 서버에 연결하지 못했어요. 실행 안내를 확인해 주세요.');}
  let value;try{value=await response.json();}catch{throw Error('기억 서버의 응답을 확인하지 못했어요. 실행 안내를 확인해 주세요.');}
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
      ...(['intent', 'search'].includes(path) ? { conversation: currentConversation() } : {}),
      ...payload,
      config: { model: modelPicker.value, route: 'M1', top_k: 3 },
    }),
  });
}

async function loadDemoModels() {
  try {
    const {runtime}=await demoJson('/bootstrap');
    const models=runtime.models.filter(model=>model.role==='generation'&&model.present);
    if(!models.length)throw Error('모델 준비 화면(127.0.0.1:4321/baseline)에서 생성 모델과 임베딩 모델을 준비해 주세요.');
    modelPicker.replaceChildren();
    for(const model of models)modelPicker.add(new Option(model.name,model.id));
    const preferred=models.find(model=>model.default);
    const active=models.find(model=>model.id===runtime.states.generation.model_id);
    modelPicker.value=(preferred||active||models[0]).id;
    connectionError='';showChatPrompt();
    homeStatus.textContent='생각이나 기억을 입력하면 사색 대화에서 이어집니다.';
    return true;
  }catch(error){
    connectionError=error.message;
    chatStatus.textContent=connectionError;saveStatus.textContent=connectionError;
    homeStatus.textContent=connectionError;return false;
  }finally{updateDemoControls();}
}
async function requireModel(){
  if(modelPicker.value||await loadDemoModels())return true;
  return false;
}

async function withDemoRequest(action) {
  if(demoBusy)throw Error('진행 중인 처리가 끝난 뒤 다시 시도해 주세요.');
  demoBusy = true;
  updateDemoControls();
  try {
    if(!await requireModel())throw Error(connectionError);
    return await action();
  } finally {
    demoBusy = false;
    formatReplies();
    updateDemoControls();
  }
}

function addArchiveRecord(record, memory) {
  const item = {
    ...record,
    memoryKey: memory.memory_key,
    version: memory.summary_artifact_id,
    sourceId: memory.source_id,
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
  archiveMatches=[];
  renderCalendar();renderTimeline();renderRecent();applyPreferences();
  if(archiveSearchActive)void runSearch(false);
}

async function persistDemoRecord(record, status) {
  const { date, title, body, mood, tags, type, schedule }=record;
  const fields = ['제목: '+title,'기록일: '+date,'감정: '+(mood||'미지정')];

  if (schedule) fields.push('일정 시각: ' + (schedule.time || '미정'));
  if (tags) fields.push('태그: ' + tags);
  const elapsed = document.createElement('span');
  elapsed.setAttribute('aria-hidden', 'true');
  status.textContent = '기록을 요약하고 검색을 준비하는 중입니다…';
  status.append(elapsed);
  const stopTimer = startElapsedTimer(seconds => {
    elapsed.textContent = ' (' + seconds + '초 경과)';
  });
  try {
    const text=fields.join('\n')+'\n\n'+body;
    const { memory } = typeof uxPersist==='function'?await uxPersist(record,text):await demoRequest('save',{text});
    if (!memory?.memory_key) throw new Error('저장한 기록을 확인하지 못했습니다.');
    addArchiveRecord({ date, title, body, mood, tags, type }, memory);
    refreshRecords();
    return memory;
  } finally {
    stopTimer();
    elapsed.remove();
  }
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
      const type = memory.schedule ? '일정' : '일기';
      restored.push(addArchiveRecord({title,date,mood,tags,body,type},memory));
    }
    const keys=new Set(restored.map(record=>record.memoryKey));
    for(let i=records.length-1;i>=0;i--)if(!keys.has(records[i].memoryKey))records.splice(i,1);
    archiveStatus.textContent = '';
  } catch (error) {
    archiveStatus.textContent='저장된 기록 목록을 불러오지 못했습니다. '+error.message;
    document.getElementById('selectedCount').textContent=archiveError;
    return null;
  }
  refreshRecords();
  if(typeof uxScrubHistory==='function')uxScrubHistory();
  return restored;
}

async function askFromHome(query){go('chat');return handleChatInput(query,'question');}
async function startChatFromHome(){
  const body=homeInput.value.trim();if(!body||demoBusy)return;
  rememberChat();openChat();homeInput.value='';go('chat');
  await handleChatInput(body);updateChatInput();
}
function newChat(){
  if(demoBusy)return;
  rememberChat();openChat();go('home');homeInput.focus();
}
async function addRecord(){
  if(demoBusy)return;
  const bodyInput=document.getElementById('recordBody');
  const titleInput=document.getElementById('recordTitle');
  const dateInput=document.getElementById('recordDate');
  const body=bodyInput.value.trim(),title=titleInput.value.trim()||'새로운 기록';
  if(!body){saveStatus.textContent='기록할 내용을 입력해 주세요.';bodyInput.focus();return;}
  try{
    const date=dateForDiary(body,dateInput.value);
    await withDemoRequest(async()=>{
      await persistDemoRecord({date,title,body,mood:'미지정',type:'일기'},saveStatus);
      if(bodyInput.value.trim()===body)bodyInput.value='';
      if((titleInput.value.trim()||'새로운 기록')===title)titleInput.value='';
      saveStatus.textContent=date+' 기록을 저장했어요.';
      document.getElementById('archiveInput').value='';archiveSearchActive=false;
      selectArchiveDate(date,false);go('archive');
    });
  }catch(error){saveStatus.textContent='저장 실패: '+error.message;}
}

function renderChatHistory() {
  historyList.replaceChildren();
  if (!chatHistoryState.threads.length) {
    const empty = document.createElement('p');
    empty.className = 'sidebar-label';
    empty.textContent = '아직 나눈 대화가 없어요.';
    historyList.append(empty);
    return;
  }
  for (const thread of chatHistoryState.threads) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'chat-session' + (thread.id === chatHistoryState.activeId ? ' active' : '');
    button.textContent = thread.title;
    button.title = thread.title;
    button.disabled = demoBusy;
    if (thread.id === chatHistoryState.activeId) button.setAttribute('aria-current', 'true');
    button.addEventListener('click', () => {
      if (!demoBusy && thread.id !== chatHistoryState.activeId) {
        rememberChat();
        openChat(thread);
        chatInput.focus();
      }
    });
    historyList.append(button);
  }
}

function rememberChat() {
  const thread = chatHistoryState.threads.find(item => item.id === chatHistoryState.activeId);
  if (thread) {
    thread.messages = [...conversation.children].flatMap(bubble => {
      const paragraph=bubble.querySelector('.bot-content')||bubble.querySelector('p');
      if (!paragraph.textContent) return [];
      return [{
        kind: bubble.classList.contains('user') ? 'user' : 'bot',
        text: paragraph.dataset.messageText??paragraph.textContent,
        notes: [...bubble.querySelectorAll('.evidence')].map(note => note.textContent),
        sourceCount:Number(bubble.querySelector('.message-sources')?.dataset.sourceCount||0),
        action: messageActions.get(paragraph),
        refs:JSON.parse(paragraph.dataset.uxRefs||'[]'),
      }];
    });
    thread.clarification = pendingClarification;
    thread.input = chatInput.value;
  }
}

function currentConversation() {
  const thread = chatHistoryState.threads.find(item => item.id === chatHistoryState.activeId);
  const messages = (thread?.context || []).map(message => ({ ...message }));
  if (thread?.unansweredQuestion) messages.push({ role: 'user', text: thread.unansweredQuestion });
  return messages.slice(-6);
}

function rememberCompletedTurn(question, answer) {
  const thread = chatHistoryState.threads.find(item => item.id === chatHistoryState.activeId);
  if (!thread || !question?.trim() || !answer?.trim()) return;
  delete thread.unansweredQuestion;
  // Keep only completed turns in the active, in-memory chat. Refresh clears them.
  // Omit a long turn rather than silently changing its meaning by truncation.
  if (question.length > 1200 || answer.length > 1200) {
    thread.context = [];
    return;
  }
  thread.context = [...(thread.context || []),
    { role: 'user', text: question }, { role: 'assistant', text: answer },
  ].slice(-6);
}

function openChat(thread) {
  chatHistoryState.activeId = thread?.id ?? null;
  pendingRecord = null;
  pendingClarification = thread?.clarification ?? null;
  conversation.replaceChildren();
  for (const message of thread?.messages ?? []) {
    const paragraph = renderChatBubble(message.kind === 'user' ? 'user' : 'bot', message.text);
    if(message.refs?.length)paragraph.dataset.uxRefs=JSON.stringify(message.refs);
    renderChatSources(paragraph, message.notes ?? [],message.sourceCount??message.refs?.length??0);
    const action = message.action;
    if (action?.type === 'confirm') addRecordConfirmation(paragraph, action.record, true);
    if (action?.type === 'emotion') offerEmotionSave(paragraph, action.record);
    if (action?.type === 'calendar') offerCalendarLink(paragraph, action.date, action.notice);
    if(typeof uxRestoreAction==='function')uxRestoreAction(paragraph,action);
  }
  chatInput.value = thread?.input ?? '';
  showChatPrompt();
  formatReplies();
  renderChatHistory();
  updateDemoControls();
  requestAnimationFrame(scrollChatToBottom);
}

function showChatPrompt() {
  chatStatus.textContent = pendingRecord ? '저장 여부를 확인해 주세요.'
    : pendingClarification ? '추가 답변을 기다리고 있어요.'
    : '일기나 일정을 남기거나, 기억과 지금 기분을 이야기해 보세요.';
}

function addBubble(kind, text) {
  if (kind === 'user') {
    const index = chatHistoryState.threads.findIndex(thread => thread.id === chatHistoryState.activeId);
    const thread = index === -1
      ? { id: crypto.randomUUID(), title: text.replace(/\s+/g, ' ').trim(), messages: [], context: [] }
      : chatHistoryState.threads.splice(index, 1)[0];
    chatHistoryState.threads.unshift(thread);
    chatHistoryState.activeId = thread.id;
    renderChatHistory();
  }
  return renderChatBubble(kind, text);
}

function renderChatBubble(kind,text){
  const bubble=document.createElement('div');bubble.className='bubble '+kind;
  let paragraph;
  if(kind==='user'){
    paragraph=document.createElement('p');paragraph.textContent=text;bubble.append(paragraph);
  }else{
    const label=document.createElement('span');label.className='bot-label';label.textContent='Plant Thought';
    paragraph=document.createElement('div');paragraph.className='bot-content';paragraph.textContent=text;
    bubble.append(label,paragraph);
  }
  conversation.append(bubble);return paragraph;
}
function formatReplies(){
  for(const content of conversation.querySelectorAll('.bot-content')){
    if(content.dataset.formatted==='yes'&&content.dataset.renderedText===content.textContent)continue;
    const text=content.textContent;content.dataset.messageText=text;
    content.replaceChildren(...renderBotText(text).childNodes);content.dataset.formatted='yes';content.dataset.renderedText=content.textContent;
  }
}

function startElapsedTimer(render) {
  const startedAt = performance.now();
  let lastSecond = -1;
  const updateTime = () => {
    const seconds = Math.floor((performance.now() - startedAt) / 1000);
    if (seconds === lastSecond) return;
    lastSecond = seconds;
    render(seconds);
  };
  updateTime();
  const timer = setInterval(updateTime, 250);
  return () => clearInterval(timer);
}

function startChatProgress(reply,initialStage){
  activeChatProgress?.stop();
  let label=initialStage,pollTimer;
  const controller=new AbortController();
  const stopTimer=startElapsedTimer(seconds=>{reply.textContent=label+' ('+seconds+'초)';});
  const progress={
    setStage(value){label=value;},
    watch(id){
      const poll=async()=>{
        try{const update=await demoJson('/summary-memory/progress?id='+encodeURIComponent(id),{signal:controller.signal});
          if(!controller.signal.aborted&&searchStages[update.stage])label=searchStages[update.stage];
        }catch{}
        if(!controller.signal.aborted)pollTimer=setTimeout(poll,500);
      };void poll();
    },
    stop(){if(controller.signal.aborted)return;controller.abort();stopTimer();clearTimeout(pollTimer);if(activeChatProgress===progress)activeChatProgress=null;}
  };
  activeChatProgress=progress;return progress;
}

function addChatAction(actions, label, style, onClick) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = style;
  button.textContent = label;
  button.addEventListener('click', onClick);
  actions.append(button);
  return button;
}

function showRecordInCalendar(date) {
  const [recordYear, recordMonth] = date.split('-').map(Number);
  year = recordYear;
  month = recordMonth - 1;
  selected = date;
  document.getElementById('archiveInput').value = '';
  go('archive');
}

function offerCalendarLink(reply, date, notice) {
  const actions = document.createElement('div');
  actions.className='chat-followups';
  if (notice) {
    const status = document.createElement('small');
    status.textContent = notice;
    actions.append(status);
  }
  reply.after(actions);
  messageActions.set(reply, { type: 'calendar', date, notice });
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
    if (approved) {
      const reply = addBubble('bot', draft.restored ? '기존 기록을 확인하는 중…' : '');
      chatStatus.textContent = '기록 저장 중…';
      let alreadySaved = false;
      let savedMemory;
      try {
        if (draft.restored) {
          const latest = await restoreArchive();
          if (!latest) throw new Error('기존 기록을 확인하지 못했어요.');
          alreadySaved = Boolean(findSameRecord(latest, draft.record));
        }
        if (!alreadySaved) savedMemory = await persistDemoRecord(draft.record, reply);
      } catch (error) {
        if (!reply.isConnected) return;
        reply.textContent = '저장 실패: ' + error.message + ' 기록하기를 눌러 다시 시도할 수 있어요.';
        chatStatus.textContent = '저장 실패';
        return;
      }
      if (!reply.isConnected) return;
      reply.textContent = alreadySaved
        ? '같은 내용이 이미 저장돼 있어요. 달력에서 볼 수 있어요.'
        : '저장했어요. ' + recordDescription(draft.record) + ' 기록은 달력에서 볼 수 있어요.';
      offerCalendarLink(reply, draft.record.date);
      if (savedMemory?.summary_review?.status === 'SOURCE_PRESERVED') {
        renderChatSources(reply, ['내용이 바뀌지 않도록 일부 구간은 원문 그대로 보관했어요.']);
      }
      rememberCompletedTurn(userReply, reply.textContent);
      chatStatus.textContent = '저장 완료';
    } else {
      addBubble('bot', '기록을 취소했어요.');
      rememberCompletedTurn(userReply, '기록을 취소했어요.');
      chatStatus.textContent = '저장 취소';
    }
    if (pendingRecord === draft) pendingRecord = null;
    draft.actions.remove();
    messageActions.delete(draft.reply);
    chatInput.focus();
    scrollChatToBottom();
  });
}

function normalizeRecordBody(text) {
  return text.normalize('NFC').replace(/\s+/g, ' ').trim();
}

function findSameRecord(items, record) {
  const body = normalizeRecordBody(record.body);
  return items.find(item => item.date === record.date && normalizeRecordBody(item.body) === body);
}

async function offerRecord(reply, record) {
  activeChatProgress?.setStage('같은 날짜에 저장한 기록을 확인하는 중…');
  const restored = await restoreArchive();
  if (!reply.isConnected) return;
  if (!restored) throw new Error('기존 기록을 확인하지 못했어요. 잠시 뒤 다시 보내 주세요.');
  const sameDay = restored.filter(item => item.date === record.date);
  const existing = findSameRecord(sameDay, record);
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
  reply.textContent = previous + ' 이 내용을 ' + recordAs + ' 기록할까요?' + (record.schedule ? ' (' + description + ')' : '');
  addRecordConfirmation(reply, record);
  chatStatus.textContent = '저장 여부를 확인해 주세요.';
}

function addRecordConfirmation(reply, record, restored = false) {
  const actions = document.createElement('div');
  actions.className='chat-followups';
  reply.after(actions);
  messageActions.set(reply, { type: 'confirm', record });
  const draft = { record, actions, reply, restored };
  pendingRecord = draft;
  addChatAction(actions, '기록하기', 'primary', () => confirmRecord(draft, true, '네, 기록해 주세요.'));
  addChatAction(actions, '취소', 'ghost', () => confirmRecord(draft, false, '아니요, 기록하지 않을게요.'));
  updateDemoControls();
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
  const record={ date: draft.date, title: draft.title, body, mood: '미지정', type: '일정', schedule: { date: draft.date, time } };
  if(draft.explicit&&typeof uxSaveExplicit==='function')await uxSaveExplicit(record,reply);
  else await offerRecord(reply,record);
}

function scheduleDetailOnly(body) {
  const remainder = body.trim().replace(/\d{4}[-./]\d{1,2}[-./]\d{1,2}|(?:\d{4}\s*년\s*)?(?:\d{1,2}\s*월\s*)?\d{1,2}\s*일(?:에는|은|에)?|(?:지난|이번|다음)\s*(?:주|달)|[월화수목금토일]요일|내일모레|내일|모레|오늘/gu, '')
    .replace(/(?:오전|오후|아침|저녁|밤|새벽)?\s*(?:\d{1,2}:\d{2}|(?:\d{1,2}|열한|열두|열|한|두|세|네|다섯|여섯|일곱|여덟|아홉)\s*시(?:\s*\d{1,2}\s*분|\s*반)?)/gu, '')
    .replace(/[\s,.!。！]/gu, '');
  return /^(?:이야|야|요|입니다|이에요|예요|에요|로|에|쯤|정도|미정|시간미정|시각미정)*$/u.test(remainder);
}

function handleChatInput(body, knownIntent, fromRetry=false) {
  if(demoBusy)return;
  if(!modelPicker.value)return loadDemoModels().then(ready=>{
    if(ready)return handleChatInput(body,knownIntent,fromRetry);
    addBubble('user',body);addBubble('bot',connectionError);formatReplies();chatInput.value=body;updateChatInput();
  });
  if (pendingRecord) {
    const choice = body.replace(/[.!。！]+$/u, '').trim();
    if (/^(?:네|예|응|그래|좋아|기록하기|(?:기록|저장)해\s*(?:줘|주세요|줘요)|네,?\s*(?:기록|저장)해\s*(?:줘|주세요|줘요))$/.test(choice)) {
      return confirmRecord(pendingRecord, true, body);
    }
    if (/^(?:아니|아니오|아니요|취소|취소해\s*줘|(?:기록|저장)하지\s*마)$/.test(choice)) {
      return confirmRecord(pendingRecord, false, body);
    }
    pendingRecord.actions.remove();
    messageActions.delete(pendingRecord.reply);
    pendingRecord=null;
  }

  let clarification = pendingClarification;
  const submittedAt = new Date();
  return withDemoRequest(async () => {
    const userMessage = addBubble('user', body);
    pendingClarification = null;
    const reply = addBubble('bot', '');
    const progress = startChatProgress(reply, '입력 내용을 확인하는 중…');
    let failed = false;
    chatStatus.textContent = '입력 목적을 확인하고 있어요.';
    try {
      if (clarification && /^취소[.!]?$/u.test(body)) {
        reply.textContent = '확인 중이던 입력을 취소했어요.';
        chatStatus.textContent = '입력 취소';
        return;
      }
      if (clarification?.draft && scheduleDetailOnly(body)) {
        if (clarification.kind === 'date') clarification.draft.dateReply = body;
        await offerSchedule(reply, clarification.draft, clarification.kind, body);
        return;
      }
      // A full new statement is a new request, not the missing date of an old draft.
      if (clarification?.draft) clarification = null;
      const text = clarification&&clarification.kind!=='ux' ? clarification.text + '\n추가 설명: ' + body : body;
      const classified = typeof uxPlan==='function'?await uxPlan(body,clarification,knownIntent):knownIntent && !clarification ? { intent: knownIntent } : await demoRequest('intent', clarification
        ? { text: clarification.text, follow_up: body, clarification_kind: clarification.kind }
        : { text });
      if (!reply.isConnected) return;
      if(typeof uxHandlePlan==='function'&&await uxHandlePlan(classified,reply,text))return;
      if (classified.intent === 'question') {
        await answerInChat(classified.query || text, reply, progress);
      } else if (classified.intent === 'schedule') {
        await offerSchedule(reply, { body: text, title: classified.title || '일정', submittedAt,explicit:classified.explicit_save });
      } else if (classified.intent === 'diary') {
        const date = dateForDiary(text, '', submittedAt);
        const record={date,title:'일기',body:text,mood:'미지정',type:'일기'};
        if(classified.explicit_save&&typeof uxSaveExplicit==='function')await uxSaveExplicit(record,reply);
        else await offerRecord(reply,record);
      } else if (classified.intent === 'emotion') {
        await replyToEmotion(text, submittedAt, userMessage, reply, progress);
      } else if (classified.intent === 'assistant') {
        if (!classified.reply?.trim()) throw new Error('로컬 모델의 답변을 받지 못했어요.');
        reply.textContent = classified.reply;
        chatStatus.textContent = '답변 완료';
      } else {
        const kind = classified.clarification_kind === 'question' ? 'question' : 'intent';
        if (!classified.clarification) throw new Error('로컬 모델의 확인 질문을 받지 못했어요.');
        askForClarification(reply, classified.clarification, { kind, text });
      }
    } catch (error) {
      failed = true;
      if (!reply.isConnected) return;
      const thread = chatHistoryState.threads.find(item => item.id === chatHistoryState.activeId);
      // A failed answer is not evidence. Keep only the user's question as a topic.
      if (thread && body.length <= 1200) thread.unansweredQuestion = body;
      pendingClarification ||= clarification;
      reply.textContent = '처리 실패: ' + error.message;
      chatStatus.textContent = '입력을 확인해 주세요.';
      if (!chatInput.value) chatInput.value = body;
      if(typeof uxRetry==='function')uxRetry(reply,body,error);
    } finally {
      progress.stop();
      if (!failed && reply.isConnected) rememberCompletedTurn(body, reply.textContent);
      if(!failed&&fromRetry&&chatInput.value===body){chatInput.value='';updateChatInput();}
      formatReplies();
      if (reply.isConnected) chatInput.focus();
      scrollChatToBottom();
    }
  });
}

function sendChat() {
  const body = chatInput.value.trim();
  if(!body||demoBusy)return;
  chatInput.value = '';
  const pending=handleChatInput(body);updateChatInput();return pending;
}

function offerEmotionSave(userMessage, record) {
  const actions = document.createElement('div');
  actions.className='chat-followups';
  userMessage.after(actions);
  messageActions.set(userMessage, { type: 'emotion', record });
  const save = addChatAction(actions, '이 내용 저장', 'ghost chat-save-memory', () => {
    if (!save.isConnected || demoBusy || !modelPicker.value) return;
    return withDemoRequest(async () => {
      chatStatus.textContent = '기록 저장 중…';
      try {
        const restored = await restoreArchive();
        if (!restored) throw new Error('기존 기록을 확인하지 못했어요. 다시 시도해 주세요.');
        const existing = findSameRecord(restored, record);
        if (!existing) await persistDemoRecord(record, chatStatus);
        if (!userMessage.isConnected) return;
        actions.remove();
        const notice = existing ? '이미 저장된 기록이에요.' : '일기로 저장했어요.';
        offerCalendarLink(userMessage, record.date, notice);
        chatStatus.textContent = notice;
      } catch (error) {
        if (userMessage.isConnected) chatStatus.textContent = '저장 실패: ' + error.message;
      }
    });
  });
}

async function replyToEmotion(body, submittedAt, userMessage, reply, progress) {
  let date;
  try {
    date = dateForDiary(body, '', submittedAt);
  } catch {
    // An invalid date can prevent saving, but should not prevent an answer.
  }
  const record = date ? { date, title: '일기', body, mood: '미지정', type: '일기' } : null;
  const existing = record && findSameRecord(records, record);
  const answer = await answerInChat(body, reply, progress, true, existing?.memoryKey);
  if (!answer || answer.citations?.length || !record || !userMessage.isConnected) return;

  const restored = await restoreArchive();
  if (userMessage.isConnected && restored && !findSameRecord(restored, record)) {
    offerEmotionSave(userMessage, record);
  }
}

async function answerInChat(query, reply, progress, emotion = false, excludeMemoryKey) {
  const progressId = crypto.randomUUID();
  progress.setStage('기억 검색을 요청하는 중…');
  progress.watch(progressId);
  const request={
    query, answer: true, use_diary_dates: true, emotion_support: emotion, exclude_memory_key: excludeMemoryKey, progress_id: progressId,
  };
  const result=await (typeof uxSearch==='function'?uxSearch(request):demoRequest('search',request)).finally(()=>progress.stop());
  const {answer,diary_date}=result;
  if (!reply.isConnected) return;
  reply.textContent = answer?.answer || '저장된 기록에서 질문에 답할 만한 내용을 찾지 못했어요.';
  if (answer?.action === 'clarify') {
    if (!answer.answer?.trim()) throw new Error('로컬 모델의 확인 질문을 받지 못했어요.');
    askForClarification(reply, answer.answer, { kind: 'question', text: query });
    return;
  }
  const citations = answer?.citations || [];
  const citationErrors = answer?.citation_errors || [];
  const snippet = ({ quote, diary_date: date }) => {
    const compact = quote.replace(/\s+/g, ' ').trim();
    return (date ? date + ' ' : '') + '“' + compact + '”';
  };
  const snippets = [...new Set(citations.map(snippet))];
  const notes = [];
  if (snippets.length || emotion) {
    if(snippets.length)notes.push(...snippets);
    else notes.push('현재 이야기 바탕 · 참고 기록 없음');
  }
  if (answer?.examined_record) {
    notes.push('함께 검토한 기록 · ' + snippet(answer.examined_record));
  }
  const sourceIds=new Set([...citations,answer?.examined_record].filter(Boolean).map(c=>c.memory_key||c.source_id).filter(Boolean));
  renderChatSources(reply, notes,sourceIds.size);
  if(typeof uxAfterAnswer==='function')uxAfterAnswer(query,reply,result);
  chatStatus.textContent = citationErrors.length
    ? '인용 검사를 통과하지 못했습니다. 요약 근거를 확인해 주세요.'
    : diary_date ? diary_date + ' 기록 기준 · 답변 완료' : '답변 완료';
  return answer;
}

function renderChatSources(reply,notes,sourceCount=0){
  if(!notes.length)return;
  const details=document.createElement('details');details.className='message-sources';
  details.open=!preferences.collapseDetails;details.hidden=!preferences.showSources;
  details.dataset.sourceCount=String(sourceCount);
  const summary=document.createElement('summary');summary.textContent=sourceCount?'참고한 기록 '+sourceCount+'개':notes.some(n=>n.includes('참고 기록 없음'))?'현재 이야기 바탕 · 참고 기록 없음':'처리 안내';details.append(summary);
  for(const text of notes){const item=document.createElement('div');item.className='evidence';item.textContent=text;details.append(item);}
  reply.after(details);
}

// Wire existing settings without adding screen sections or styles.
const preferenceDefaults={semanticSearch:true,showSources:true,showCalendar:true,collapseDetails:true};
let preferences={...preferenceDefaults};
try{
  const saved=JSON.parse(localStorage.getItem('plant-thought-preferences-v1')||'{}');
  for(const name of Object.keys(preferenceDefaults))if(typeof saved[name]==='boolean')preferences[name]=saved[name];
}catch{}
function applyPreferences(){
  for(const name of Object.keys(preferences))document.getElementById(name).checked=preferences[name];
  for(const details of document.querySelectorAll('.message-sources'))details.hidden=!preferences.showSources;
  for(const indicator of document.querySelectorAll('#calendarDays .dot,#calendarDays .count'))indicator.hidden=!preferences.showCalendar;
  for(const previews of document.querySelectorAll('.day-record-previews')){
    if(preferences.showCalendar)previews.style.removeProperty('display');
    else previews.style.display='none';
  }
}
for(const name of Object.keys(preferences)){
  document.getElementById(name).addEventListener('change',event=>{
    preferences[name]=event.target.checked;
    try{localStorage.setItem('plant-thought-preferences-v1',JSON.stringify(preferences));document.querySelector('#settings .notice').textContent='설정은 현재 브라우저에 저장됩니다.';}
    catch{document.querySelector('#settings .notice').textContent='이 브라우저에서는 설정을 저장하지 못했어요. 현재 화면에만 적용합니다.';}
    applyPreferences();
    if(name==='collapseDetails')for(const details of document.querySelectorAll('.message-sources'))details.open=!preferences.collapseDetails;
    if(name==='semanticSearch'){archiveMatches=[];if(archiveSearchActive)void runSearch(false);}
  });
}
const originalRenderCalendar=renderCalendar;
renderCalendar=function(){originalRenderCalendar();applyPreferences();};
const originalRenderSelected=renderSelected;
renderSelected=function(){originalRenderSelected();if(archiveError)document.getElementById('selectedCount').textContent=archiveError;};
const originalRenderRecent=renderRecent;
renderRecent=function(){
  originalRenderRecent();
  if(!records.length){
    const item=document.createElement('li');item.className='recent-row';
    item.textContent='아직 저장한 기록이 없어요. 오늘의 이야기를 남겨보세요.';
    document.getElementById('homeRecent').append(item);
  }
};
function renderArchiveResults(list,query,notice=''){
  const loading=notice==='관련 기억을 찾는 중입니다…';
  document.getElementById('resultCount').textContent=loading?'검색 중':list.length+'건';
  document.getElementById('searchQueryCaption').textContent=query?'전체 날짜 · “'+query+'”':'전체 날짜의 기록';
  document.getElementById('searchResults').innerHTML=list.length?list.map(({record:r,match})=>`
    <div class="card" role="button" tabindex="0" data-record-index="${recordIndex(r)}" aria-pressed="false"
      title="한 번 클릭하면 날짜 확인, 더블클릭하면 기록 열기"
      onclick="previewRecordDate(${recordIndex(r)})" ondblclick="openRecord(${recordIndex(r)})"
      onkeydown="if(event.key==='Enter'){event.preventDefault();openRecord(${recordIndex(r)})}else if(event.key===' '){event.preventDefault();previewRecordDate(${recordIndex(r)})}">
      <span class="tag ${match==='의미 유사'?'brown':''}">${match}</span>
      <h3 style="margin-top:15px;font-size:18px">${safe(r.title)}</h3>
      <p class="muted small">${safe(r.body)}</p><div class="line"></div>
      <span class="muted small">${safe(r.date)}</span>
    </div>`).join(''):loading?'':'<p class="muted small">해당 조건의 기록이 없습니다.</p>';
  if(notice){const item=document.createElement('p');item.className='muted small';item.textContent=notice;document.getElementById('searchResults').prepend(item);}
  syncArchivePanel();
}
async function runSearch(scrollToResults=false){
  if(scrollToResults)archiveSearchActive=true;
  const version=++searchVersion;
  const query=document.getElementById('archiveInput').value.trim();
  const needle=query.toLocaleLowerCase();
  const direct=records.filter(record=>!needle||(record.title+' '+record.body).toLocaleLowerCase().includes(needle));
  const exact=direct.map(record=>({record,match:'원문 일치'}));
  const base=searchFilter==='semantic'?[]:exact;
  renderArchiveResults(base,query);
  if(scrollToResults)scrollToSearchResults();
  if(!query||!archiveSearchActive||searchFilter==='exact'||!preferences.semanticSearch)return;
  if(demoBusy){renderArchiveResults(base,query,'진행 중인 처리가 끝난 뒤 검색해 주세요.');return;}
  const keys=records.map(record=>record.memoryKey).join(',');
  const cached=archiveMatches.find(item=>item.query===query&&item.keys===keys);
  if(cached){renderArchiveResults([...base,...cached.records.filter(record=>!direct.includes(record)).map(record=>({record,match:'의미 유사'}))],query);return;}
  renderArchiveResults(base,query,'관련 기억을 찾는 중입니다…');
  try{
    await withDemoRequest(async()=>{
      const result=await demoRequest('search',{query,answer:false,use_diary_dates:false,conversation:[]});
      const sourceIds=new Set((result.retrieval?.selected_sources||result.retrieval?.ranked_sources||[]).map(item=>item.source_id));
      for(const evidence of result.retrieval?.evidence||[])sourceIds.add(evidence.source_id);
      const related=records.filter(record=>sourceIds.has(record.sourceId));
      archiveMatches=[{query,keys,records:related}];
      if(version!==searchVersion)return;
      renderArchiveResults([...base,...related.filter(record=>!direct.includes(record)).map(record=>({record,match:'의미 유사'}))],query);
    });
  }catch(error){if(version===searchVersion)renderArchiveResults(base,query,'의미 유사 검색 실패: '+error.message);}
}
// No example records or artificial conversation history in the connected app.
openChat();applyPreferences();renderRecent();
const memoryReady=Promise.allSettled([loadDemoModels(),restoreArchive()]);
if(location.protocol==='file:'){
  connectionError='기능을 사용하려면 start-local.ps1로 실행한 뒤 http://127.0.0.1:4180 에 접속해 주세요.';
  chatStatus.textContent=connectionError;saveStatus.textContent=connectionError;
}
