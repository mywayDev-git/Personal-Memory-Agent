'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { seoulDate, dateForDiary, dateForDiaryQuestion, dateForStoredMemory, isDiaryDate, dateForSchedule, timeForSchedule, scheduleForText } = require('../local/diary-dates.js');
const { buildConstellation } = require('../demo-frontend/constellation.js');

test('the diary date changes at midnight in Seoul, including year rollover', () => {
  const before = new Date('2026-12-31T14:59:59Z');
  const after = new Date('2026-12-31T15:00:00Z');
  assert.equal(seoulDate(before), '2026-12-31');
  assert.equal(seoulDate(after), '2027-01-01');
  assert.equal(dateForDiary('어제는 도서관에 갔다.', '', after), '2026-12-31');
  assert.equal(dateForDiary('조용히 책을 읽었다.', '', after), '2027-01-01');
  assert.equal(dateForDiary('어제 도서관에 갔다.', '2026-12-29', after), '2026-12-29');
  assert.equal(dateForDiary('2024년 2월 29일 도서관에 갔다.', '', after), '2024-02-29');
  assert.throws(() => dateForDiary('2026-02-29 도서관에 갔다.', '', after), /날짜/);
  assert.equal(dateForStoredMemory('이전 방식으로 저장한 메모', after.toISOString()), '2027-01-01');
});

test('only single-day relative questions scope the search', () => {
  const now = new Date('2026-11-09T15:00:00Z');
  assert.equal(dateForDiaryQuestion('내가 어제 어디 갔었지', now), '2026-11-09');
  assert.equal(dateForDiaryQuestion('오늘은 무슨 일이 있었어?', now), '2026-11-10');
  assert.equal(dateForDiaryQuestion('어제 몇 시까지 도서관에 있었어?', now), '2026-11-09');
  assert.equal(dateForDiaryQuestion('어제와 오늘 기록 비교해 줘', now), null);
  assert.equal(dateForDiaryQuestion('오늘이랑 어제 기록 비교해 줘', now), null);
  assert.equal(dateForDiaryQuestion('어제부터 있던 회의 기록 보여 줘', now), null);
  assert.equal(dateForDiaryQuestion('오늘과 11월 8일 기록 비교해 줘', now), null);
});

test('calendar questions recognize an exact numeric day without using the closest record', () => {
  const now = new Date('2026-11-09T15:00:00Z');
  assert.equal(dateForDiaryQuestion('8일에 뭐 했냐고', now), '2026-11-08');
  assert.equal(dateForDiary('8일에 도서관에 갔다.', '', now), '2026-11-08');
  assert.equal(dateForDiaryQuestion('11월 8일 기록 찾아줘', now), '2026-11-08');
  assert.equal(dateForDiaryQuestion('2025년 11월 8일에 뭐 했어?', now), '2025-11-08');
  assert.equal(dateForDiaryQuestion('2026-11-08에 뭐 했어?', now), '2026-11-08');
  assert.equal(dateForDiaryQuestion('지난달 8일에 뭐 했어?', now), '2026-10-08');
  assert.equal(dateForDiaryQuestion('8일 동안 뭐 했어?', now), null);
  assert.throws(() => dateForDiaryQuestion('11월 31일에 뭐 했어?', now), /날짜/);
});

test('two-digit Korean years preserve the explicit year for diaries, schedules and questions', () => {
  const now = new Date('2026-11-12T03:00:00Z');
  assert.equal(dateForSchedule('27년 1월 17일에는 입대하는 친구와 만날 예정이다', '', now), '2027-01-17');
  assert.equal(dateForDiary('27년 1월 17일 친구를 만났다', '', now), '2027-01-17');
  assert.equal(dateForDiaryQuestion('27년 1월 17일 일정 알려줘', now), '2027-01-17');
  assert.equal(dateForSchedule('2027년 1월 17일 친구와 만난다', '', now), '2027-01-17');
  assert.throws(() => dateForSchedule('27년 2월 29일 회의', '', now), /날짜/);
});

test('calendar scheduling resolves one day and a supplied time without defaulting to today', () => {
  const now = new Date('2026-11-09T15:00:00Z');
  assert.deepEqual(scheduleForText('내일 모레에 일정이 있어서 내일 모레에 일정 기록해 줘', '', now),
    { date: '2026-11-12', time: null });
  assert.deepEqual(scheduleForText('내일모레 오후 3시 반에 캡스톤 회의 일정 기록해 줘', '', now),
    { date: '2026-11-12', time: '15:30' });
  assert.deepEqual(scheduleForText('다음 주 수요일 16:05 회의', '', now), { date: '2026-11-18', time: '16:05' });
  assert.deepEqual(scheduleForText('다음 달 8일 저녁 일곱 시에 회의', '', now), { date: '2026-12-08', time: '19:00' });
  assert.deepEqual(scheduleForText('내일 오전 9시 20분 회의', '2026-11-20', now), { date: '2026-11-20', time: '09:20' });
  assert.throws(() => scheduleForText('회의 일정 잡아 줘', '', now), /날짜/);
  assert.throws(() => scheduleForText('내일과 모레 회의', '', now), /날짜/);
  assert.throws(() => scheduleForText('모레 3시 회의', '', now), /오전·오후/);
  assert.throws(() => scheduleForText('내일 18:60 회의', '', now), /시각/);
});

async function demoFixture(handler, { status = () => ({ stage: null }), timing = {}, archive = [] } = {}) {
  const elements = new Map();
  function element() {
    return {
      value: '', isConnected: true, children: [], dataset: {},
      addEventListener(event, listener) { this['on' + event] = listener; }, focus() {}, remove() {}, setAttribute() {},
      append(...children) { this.children.push(...children); },
      replaceChildren(...children) { this.children = children; },
      before(node) { this.previous = node; node.remove = () => { if (this.previous === node) delete this.previous; }; },
      after(node) { this.next = node; node.remove = () => { if (this.next === node) delete this.next; }; },
    };
  }
  const get = id => {
    if (!elements.has(id)) elements.set(id, element());
    return elements.get(id);
  };
  get('demoModel').add = () => { get('demoModel').value = 'qwen35-4b-q4'; };
  const saved = [];
  const navigation = [];
  const context = {
    document: {
      getElementById: get, querySelector: get, createElement: element, addEventListener() {},
      querySelectorAll: () => get('conversation').children.flatMap(bubble =>
        (bubble.children[0]?.next?.children || []).filter(button => button.className?.includes('chat-save-memory'))),
    },
    Option: class {},
    crypto: require('node:crypto').webcrypto,
    AbortController, performance, setInterval, clearInterval, setTimeout, clearTimeout, ...timing,
    go: page => navigation.push(page),
    dateForDiary, dateForSchedule, timeForSchedule, dateForStoredMemory, isDiaryDate, records: [], year: 2026, month: 10, selected: '2026-11-10',
    renderCalendar() {}, renderRecent() {}, runSearch() {}, scrollChatToBottom() {},
    fetch: async (url, options) => ({ ok: true, json: async () => {
      if (url.endsWith('/bootstrap')) return {
        token: 'test-token', runtime: { models: [{ role: 'generation', present: true, id: 'qwen35-4b-q4' }], states: { generation: {} } },
      };
      if (url.endsWith('/save')) {
        saved.push(JSON.parse(options.body).text);
        return { memory: { memory_key: 'memory-' + saved.length } };
      }
      if (url.includes('/summary-memory/progress?id=')) return status(url);
      if (options) return handler(url, JSON.parse(options.body));
      if (url.includes('/summary-memory/original?key=')) {
        const key = decodeURIComponent(url.split('key=')[1]);
        return { source: { text: archive.find(memory => memory.memory_key === key).text } };
      }
      return { memories: archive };
    } }),
  };
  vm.runInNewContext(fs.readFileSync(require.resolve('../demo-frontend/demo.js'), 'utf8'), context);
  await new Promise(resolve => setImmediate(resolve));
  return { context, get, saved, navigation, last: () => get('conversation').children.at(-1).children[0] };
}

test('home records go through chat confirmation before saving', async () => {
  const { context, get, saved, navigation, last } = await demoFixture(() => ({ intent: 'diary' }));
  get('homeSearch').value = '2026-11-08 도서관에서 책을 읽었다.';
  await context.submitHome({ preventDefault() {} });
  assert.deepEqual(navigation, ['chat']);
  assert.match(last().textContent, /일기로 기록할까요/);
  assert.equal(saved.length, 0);
  await context.handleChatInput('네');
  assert.match(saved[0], /기록일: 2026-11-08/);
});

test('emotion support answers first and saves the user message only when clicked', async () => {
  const body = '오늘은 과제가 많아서 힘들었다';
  let answers = 0;
  const { context, get, saved, last } = await demoFixture((url, data) => {
    if (url.endsWith('/intent')) return { intent: 'emotion' };
    answers++;
    assert.equal(data.query, body);
    assert.equal(data.emotion_support, true);
    assert.equal(saved.length, 0);
    return { answer: { answer: '과제가 많아서 힘들었겠어요. 잠깐 쉬어가는 건 어때요?', citations: [] } };
  });
  await context.handleChatInput(body);
  assert.equal(answers, 1);
  assert.equal(saved.length, 0);
  assert.match(last().textContent, /힘들었겠어요/);
  assert.equal(last().next.textContent, '현재 이야기 바탕 · 참고 기록 없음');
  const userMessage = get('conversation').children[0].children[0];
  assert.equal(userMessage.textContent, body);
  const [save] = userMessage.next.children;
  assert.equal(save.textContent, '이 내용 저장');
  await save.onclick();
  assert.equal(answers, 1);
  assert.equal(saved.length, 1);
  assert.ok(saved[0].endsWith(body));
  assert.deepEqual(userMessage.next.children.map(node => node.textContent), ['일기로 저장했어요.', '달력에서 보기']);
});

test('emotion support shows a reference without offering to save', async () => {
  const { context, get, saved, last } = await demoFixture(url => url.endsWith('/intent')
    ? { intent: 'emotion' }
    : { answer: { answer: '잠깐 걸어보는 건 어때요?', citations: [{ quote: '운동장을 산책했다.' }] } });
  await context.handleChatInput('오늘 힘든데 어떡하지?');
  assert.match(last().next.textContent, /참고한 기록/);
  assert.equal(get('conversation').children[0].children[0].next, undefined);
  assert.equal(saved.length, 0);
});

test('emotion support answers an already saved message without offering a duplicate', async () => {
  const body = '2026-11-08 과제가 많아서 힘들었다.';
  const archive = [{ memory_key: 'existing', text: '제목: 일기\n기록일: 2026-11-08\n감정: 미지정\n\n' + body }];
  const { context, get, saved, last } = await demoFixture((url, data) => {
    if (url.endsWith('/intent')) return { intent: 'emotion' };
    assert.equal(data.exclude_memory_key, 'existing');
    return { answer: { answer: '힘들었겠어요.', citations: [] } };
  }, { archive });
  await context.handleChatInput(body);
  assert.match(last().textContent, /힘들었겠어요/);
  assert.equal(get('conversation').children[0].children[0].next, undefined);
  assert.equal(saved.length, 0);
});

test('a clarification asks again without searching until the user names the event', async () => {
  let searches = 0;
  const { context, last } = await demoFixture((url, data) => {
    if (url.endsWith('/intent')) {
      if (!data.follow_up) {
        assert.equal(data.text, '그거 언제였지?');
        return { intent: 'unclear', clarification_kind: 'question', clarification: '어떤 일을 말씀하시는지 알려주실래요?' };
      }
      assert.equal(data.clarification_kind, 'question');
      if (data.follow_up === '그거 있잖아') {
        return { intent: 'unclear', clarification_kind: 'question', clarification: '기억을 찾으려면 사건 이름이나 날짜를 알려주실래요?' };
      }
      assert.equal(data.follow_up, '팀 회의');
      return { intent: 'question' };
    }
    searches++;
    assert.equal(data.query, '그거 언제였지?\n추가 설명: 그거 있잖아\n추가 설명: 팀 회의');
    return { answer: { answer: '11월 12일이에요.', citations: [{ diary_date: '2026-11-12', quote: '팀 회의는 11월 12일이다.' }] } };
  });
  await context.handleChatInput('그거 언제였지?');
  assert.equal(last().textContent, '어떤 일을 말씀하시는지 알려주실래요?');
  await context.handleChatInput('그거 있잖아');
  assert.equal(last().textContent, '기억을 찾으려면 사건 이름이나 날짜를 알려주실래요?');
  assert.equal(searches, 0);
  await context.handleChatInput('팀 회의');
  assert.equal(searches, 1);
  assert.equal(last().next.textContent, '참고한 기록 · 2026-11-12 “팀 회의는 11월 12일이다.”');
});

test('chat progress shows elapsed seconds and the live phase until the answer replaces it', async () => {
  let elapsed = 0, tick, poll, timerStopped = false, requestedId;
  let resolveAnswer;
  const waiting = new Promise(resolve => { resolveAnswer = resolve; });
  const { context, last } = await demoFixture((url, data) => {
    assert.ok(url.endsWith('/search'));
    requestedId = data.progress_id;
    return waiting;
  }, {
    status: url => ({ stage: url.endsWith(requestedId) ? 'retrieving' : null }),
    timing: {
      performance: { now: () => elapsed },
      setInterval(callback) { tick = callback; return 1; },
      clearInterval() { timerStopped = true; },
      setTimeout(callback) { poll = callback; return 2; },
      clearTimeout() {},
    },
  });
  const response = context.handleChatInput('어제 뭐 했어?', 'question');
  await new Promise(resolve => setImmediate(resolve));
  await poll();
  const reply = last();
  assert.equal(reply.hidden, true);
  assert.equal(reply.next.textContent, '과거 기억을 탐색하는 중…');
  elapsed = 2300;
  tick();
  assert.equal(reply.previous.textContent, '2초째 생각 중');
  resolveAnswer({ answer: { answer: '산책했어요.', citations: [{ quote: '운동장을 산책했다.' }] } });
  await response;
  assert.equal(reply.hidden, false);
  assert.equal(reply.previous, undefined);
  assert.equal(reply.next.textContent, '참고한 기록 · “운동장을 산책했다.”');
  assert.equal(timerStopped, true);
});

test('an ambiguous record waits for the user to explain what to save', async () => {
  const { context, last, saved } = await demoFixture((url, data) => {
    if (!data.follow_up) return { intent: 'unclear', clarification: '민수에 대한 기억을 찾을까요, 기록을 남길까요?' };
    assert.equal(data.text, '민수');
    assert.equal(data.follow_up, '민수와 점심을 먹었다는 일기를 남겨 줘');
    return { intent: 'diary' };
  });
  await context.handleChatInput('민수');
  assert.match(last().textContent, /기억을 찾을까요/);
  await context.handleChatInput('민수와 점심을 먹었다는 일기를 남겨 줘');
  assert.match(last().textContent, /일기로 기록할까요/);
  assert.equal(saved.length, 0);
});

test('a schedule asks for missing date and ambiguous time before confirmation', async () => {
  const { context, saved, last } = await demoFixture(() => ({ intent: 'schedule', title: '팀 회의' }));
  await context.handleChatInput('3시에 팀 회의 일정 잡아줘');
  assert.match(last().textContent, /어느 날짜/);
  await context.handleChatInput('2026-11-12');
  assert.match(last().textContent, /몇 시에/);
  await context.handleChatInput('오후 3시');
  assert.match(last().textContent, /2026-11-12 15:00/);
  assert.equal(saved.length, 0);
  await context.handleChatInput('네');
  assert.match(saved[0], /일정 시각: 15:00/);
});

test('emotion harvest saves the selected date and mood and opens that calendar day', async () => {
  const { context, get, saved, navigation } = await demoFixture();
  get('recordBody').value = '운동장을 산책하니 마음이 편해졌다.';
  get('recordTitle').value = '운동장 산책';
  get('recordTags').value = '산책';
  get('recordDate').value = '2026-11-08';
  get('.mood.on').dataset.mood = '슬픔';
  await context.addRecord();
  assert.match(saved[0], /기록일: 2026-11-08\n감정: 슬픔\n태그: 산책/);
  assert.equal(context.records[0].type, '감정');
  assert.equal(get('emotionCalendar').hidden, false);
  get('emotionCalendar').onclick();
  assert.equal(context.selected, '2026-11-08');
  assert.deepEqual(navigation, ['archive']);
});

test('constellation links stored records and only source-grounded labels', () => {
  const records = [
    { memoryKey: 'a', date: '2026-11-09', title: '일기', body: '민수와 도서관에 갔다.', mood: '미지정',
      entities: [{ name: '민수', type: 'person' }, { name: '도서관', type: 'place' }, { name: '없는 인물', type: 'person' }] },
    { memoryKey: 'b', date: '2026-11-10', title: '캡스톤 발표', body: '민수를 만났다.', mood: '😊 평온함', tags: '시연, 시연',
      entities: [{ name: '민수', type: 'person' }, { name: '캡스톤 발표', type: 'event' }] },
    { memoryKey: 'c', date: '2026-11-10', title: '일기', body: '집에 있었다.', mood: '단서 없음' },
  ];
  const { memories, linked } = buildConstellation(records);
  assert.deepEqual(memories.map(({ record }) => record.memoryKey), ['b', 'c', 'a']);
  assert.equal(memories.filter(item => item.links.includes('person:민수')).length, 2);
  assert.deepEqual([...linked.keys()].sort(), ['event:캡스톤 발표', 'mood:평온함', 'person:민수', 'place:도서관', 'tag:시연']);
  assert.equal(buildConstellation(records, 'person').memories.length, 2);
  assert.equal(buildConstellation(records, 'mood').memories[0].record.memoryKey, 'b');
  assert.equal(buildConstellation([], 'all').linked.size, 0);
});
