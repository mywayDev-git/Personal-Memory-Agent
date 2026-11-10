'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { seoulDate, dateForDiary, dateForDiaryQuestion, dateForStoredMemory, scheduleForText } = require('../local/diary-dates.js');
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

test('saving from home opens a dated confirmation and keeps the current page', async () => {
  const elements = new Map();
  let modalShown = 0;
  const get = id => {
    if (!elements.has(id)) elements.set(id, { value: '', addEventListener() {} });
    return elements.get(id);
  };
  get('demoModel').add = () => { get('demoModel').value = 'qwen35-4b-q4'; };
  get('homeSaved').showModal = () => { modalShown++; };
  const saved = [];
  const navigation = [];
  const context = {
    document: { getElementById: get, querySelector: get },
    Option: class {},
    go: page => navigation.push(page),
    dateForDiary, scheduleForText, records: [],
    renderCalendar() {}, renderRecent() {}, runSearch() {}, renderConstellation() {},
    fetch: async (url, options) => ({ ok: true, json: async () => {
      if (url.endsWith('/bootstrap')) return {
        token: 'test-token', runtime: { models: [{ role: 'generation', present: true, id: 'qwen35-4b-q4' }], states: { generation: {} } },
      };
      if (url.endsWith('/save')) {
        saved.push(JSON.parse(options.body).text);
        return { memory: { memory_key: 'memory-' + saved.length, mood: '기쁨' } };
      }
      return { memories: [] };
    } }),
  };
  vm.runInNewContext(fs.readFileSync(require.resolve('../demo-frontend/demo.js'), 'utf8'), context);
  await new Promise(resolve => setImmediate(resolve));
  get('homeMode').value = 'diary';
  get('homeDate').value = '2026-11-08';
  get('homeSearch').value = '도서관에서 책을 읽었다.';
  await context.submitHome({ preventDefault() {} });
  assert.equal(get('homeSavedMessage').textContent, '11월 8일 일기가 저장되었습니다.');
  assert.equal(modalShown, 1);
  assert.deepEqual(navigation, []);
  assert.match(saved[0], /기록일: 2026-11-08/);
  assert.equal(context.records[0].mood, '기쁨');
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
