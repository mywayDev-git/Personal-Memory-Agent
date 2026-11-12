'use strict';

const DIARY_TIME_ZONE = 'Asia/Seoul';
const seoulCalendar = new Intl.DateTimeFormat('en-CA', {
  timeZone: DIARY_TIME_ZONE, year: 'numeric', month: '2-digit', day: '2-digit',
});
const relativeOffsets = { 그저께: -2, 엊그제: -2, 어제: -1, 오늘: 0, 내일: 1, 모레: 2, 내일모레: 2, 글피: 3 };
const leadingRelativeDay = /^(그저께|엊그제|어제|오늘)(?:에는|에도|은|는|에|도|엔|의)?(?=$|[\s,.!?。:：])/;

function seoulDate(now = new Date()) {
  const parts = Object.fromEntries(seoulCalendar.formatToParts(now).map(p => [p.type, p.value]));
  return `${parts.year}-${parts.month}-${parts.day}`;
}

function calendarDate(year, month, day) {
  if (!Number.isInteger(year) || year < 1000 || year > 9999) return null;
  const date = new Date(Date.UTC(year, month - 1, day));
  return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day
    ? date.toISOString().slice(0, 10) : null;
}

function isDiaryDate(value) {
  return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)
    && calendarDate(...value.split('-').map(Number)) === value;
}

function shiftedDay(now, offset) {
  const date = new Date(`${seoulDate(now)}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + offset);
  return date.toISOString().slice(0, 10);
}

function dateForDiary(text, chosenDate, now = new Date()) {
  if (chosenDate) {
    if (isDiaryDate(chosenDate)) return chosenDate;
    throw new Error('기록 날짜를 확인해 주세요.');
  }
  const leading = text.trimStart().replace(/^일기\s*[:：]\s*/, '').replace(/^(?:나는|난|저는|전)\s+/, '');
  const full = leading.match(/^(\d{4})[-./](\d{1,2})[-./](\d{1,2})(?!\d)/)
    || leading.match(/^(\d{4}|\d{2})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일/);
  const short = leading.match(/^(\d{1,2})\s*월\s*(\d{1,2})\s*일/);
  if (full || short) {
    const parts = full ? full.slice(1).map(Number) : [Number(seoulDate(now).slice(0, 4)), ...short.slice(1).map(Number)];
    if (full && full[1].length === 2) parts[0] += 2000;
    const date = calendarDate(...parts);
    if (date) return date;
    throw new Error('기록 날짜를 확인해 주세요.');
  }
  if (/^\d{1,2}\s*일(?!\s*(?:전|후|간|동안|째|차))/.test(leading)) {
    const [year, month] = seoulDate(now).split('-').map(Number);
    const date = calendarDate(year, month, Number(leading.match(/^\d+/)[0]));
    if (date) return date;
    throw new Error('기록 날짜를 확인해 주세요.');
  }
  const relative = leading.match(leadingRelativeDay)?.[1];
  return relative ? shiftedDay(now, relativeOffsets[relative]) : seoulDate(now);
}

function singleCalendarDay(text, now, forSchedule = false) {
  const today = seoulDate(now);
  const [year, month] = today.split('-').map(Number);
  const dates = new Set();
  const days = /(?<![\d./-])(?:(\d{4})[-./](\d{1,2})[-./](\d{1,2})(?![\d./-])|(?:(?:(\d{4}|\d{2})\s*년\s*)?(\d{1,2})\s*월\s*|(지난|이번|다음)\s*달\s*)?(\d{1,2})\s*일(?!\s*(?:전|후|간|동안|째)))/gu;
  for (const [, isoYear, isoMonth, isoDay, namedYear, namedMonth, relativeMonth, namedDay] of text.matchAll(days)) {
    const reference = new Date(Date.UTC(year, month - 1 + ({ 지난: -1, 다음: 1 }[relativeMonth] || 0), 1));
    const explicitYear = namedYear?.length === 2 ? 2000 + Number(namedYear) : namedYear;
    const date = calendarDate(Number(isoYear || explicitYear || reference.getUTCFullYear()),
      Number(isoMonth || namedMonth || reference.getUTCMonth() + 1), Number(isoDay || namedDay));
    if (!date) throw new Error('입력한 날짜가 달력에 없습니다. 날짜를 확인해 주세요.');
    dates.add(date);
  }
  const relativeDays = /(?<![\p{L}\p{N}])(내일\s*모레|그저께|엊그제|어제|오늘|내일|모레|글피)(?:이랑|하고|에는|에도|보다|은|는|에|도|엔|의|만|과|와|랑)?(?![\p{L}\p{N}])/gu;
  for (const [, relative] of text.matchAll(relativeDays)) {
    dates.add(shiftedDay(now, relativeOffsets[relative.replace(/\s/g, '')]));
  }
  const weekdays = /(?:(지난|이번|다음)\s*주\s*)?([월화수목금토일])요일/gu;
  const weekday = (new Date(today + 'T00:00:00Z').getUTCDay() + 6) % 7;
  const inferWeekday = forSchedule && dates.size === 0;
  for (const [, week, day] of text.matchAll(weekdays)) {
    if (!week && !inferWeekday) continue;
    const difference = '월화수목금토일'.indexOf(day) - weekday;
    const offset = week ? difference + { 지난: -7, 이번: 0, 다음: 7 }[week] : (difference + 7) % 7;
    dates.add(shiftedDay(now, offset));
  }
  const range = /(?:그저께|엊그제|어제|오늘|내일|모레|글피|\d\s*일|\d{4}[-./]\d{1,2}[-./]\d{1,2}|요일)\s*(?:부터|까지|이전|이후|[~～〜])/u;
  return !range.test(text) && dates.size === 1 ? dates.values().next().value : null;
}

function dateForDiaryQuestion(text, now = new Date()) {
  return singleCalendarDay(text, now);
}

function timeForSchedule(text) {
  const matches = [...text.matchAll(/(?:(오전|오후|새벽|아침|저녁|밤)\s*)?(?:(?<!\d)(\d{1,2})\s*:\s*(\d{2})(?!\d)|(?<!\d)(\d{1,2}|열\s*[한두]|다섯|여섯|일곱|여덟|아홉|열|한|두|세|네)\s*시(?!간)(?:\s*(?:(\d{1,2})\s*분|(반)))?)/gu)];
  if (!matches.length) return null;
  if (matches.length > 1) throw new Error('일정의 시작 시각을 한 가지로 적어 주세요.');
  const [, period, clockHour, colonMinutes, spokenHour, namedMinutes, half] = matches[0];
  const hour = clockHour || spokenHour.replace(/\s/g, '');
  const names = ['한', '두', '세', '네', '다섯', '여섯', '일곱', '여덟', '아홉', '열', '열한', '열두'];
  let hours = names.includes(hour) ? names.indexOf(hour) + 1 : Number(hour);
  const minutes = half ? 30 : Number(colonMinutes || namedMinutes || 0);
  if (hours > 23 || minutes > 59 || (period && (hours < 1 || hours > 12))) {
    throw new Error('일정 시각을 확인해 주세요.');
  }
  if (period) hours = hours % 12 + (['오후', '저녁', '밤'].includes(period) ? 12 : 0);
  else if (!colonMinutes && hours >= 1 && hours <= 12) {
    throw new Error('일정 시각에 오전·오후를 붙이거나 15:00처럼 적어 주세요.');
  }
  return [hours, minutes].map(value => String(value).padStart(2, '0')).join(':');
}

function dateForSchedule(text, chosenDate, now = new Date()) {
  const date = chosenDate || singleCalendarDay(text, now, true);
  if (!isDiaryDate(date)) throw new Error('일정 날짜를 하루로 적거나 날짜를 직접 선택해 주세요.');
  return date;
}

function scheduleForText(text, chosenDate, now = new Date()) {
  return { date: dateForSchedule(text, chosenDate, now), time: timeForSchedule(text) };
}

function storedDiaryDate(text) {
  const date = text.match(/^제목: [^\r\n]+\r?\n기록일: (\d{4}-\d{2}-\d{2})(?=\r?\n)/)?.[1];
  return isDiaryDate(date) ? date : null;
}

function storedSchedule(text) {
  const fields = text.match(/^제목: ([^\r\n]+)\r?\n기록일: \d{4}-\d{2}-\d{2}\r?\n감정: [^\r\n]*\r?\n일정 시각: ([^\r\n]+)(?=\r?\n)/);
  if (!fields) return null;
  const [, title, time] = fields;
  if (time !== '미정' && !/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(time)) throw new Error('일정 시각을 확인해 주세요.');
  return { title, time: time === '미정' ? null : time };
}

function dateForStoredMemory(text, savedAt) {
  const header = storedDiaryDate(text);
  if (header || isDiaryDate(savedAt)) return header || savedAt;
  if (typeof savedAt !== 'string') return null;
  const timestamp = new Date(savedAt);
  return Number.isFinite(timestamp.getTime()) ? seoulDate(timestamp) : null;
}

if (typeof module === 'object' && module.exports) {
  module.exports = { DIARY_TIME_ZONE, seoulDate, isDiaryDate, dateForDiary, dateForDiaryQuestion, dateForSchedule, timeForSchedule, scheduleForText, storedDiaryDate, storedSchedule, dateForStoredMemory };
}
