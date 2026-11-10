'use strict';

const constellationKinds = {
  mood: { label: '감정', fill: '#f0e3d9', ink: '#684838' },
  person: { label: '인물', fill: '#dceade', ink: '#193c2e' },
  event: { label: '사건', fill: '#e5e5f2', ink: '#3e4060' },
  place: { label: '장소', fill: '#e5e5f2', ink: '#3e4060' },
  tag: { label: '태그', fill: '#e5e5f2', ink: '#3e4060' },
};

function buildConstellation(records, filter = 'all') {
  const linked = new Map();
  const memories = [];
  const normalize = text => text.normalize('NFKC').trim().replace(/\s+/g, ' ');
  for (const record of [...records].sort((a, b) => b.date.localeCompare(a.date))) {
    const keys = new Map();
    function add(kind, value) {
      const label = normalize(value || '');
      if (label) keys.set(kind + ':' + label, { kind, label });
    }
    const mood = normalize(record.mood || '').replace(/^[^\p{L}\p{N}]+/u, '');
    if (mood !== '미지정' && mood !== '단서 없음') add('mood', mood);
    for (const tag of (record.tags || '').split(/[,，]/)) add('tag', tag);
    const original = normalize(record.title + ' ' + record.body);
    for (const entity of record.entities || []) {
      const label = normalize(entity.name || '');
      if (!label || !original.includes(label) || ['나', '사용자', '저'].includes(label)) continue;
      if (entity.type === 'person') add('person', label);
      if (entity.type === 'event' || entity.type === 'project') add('event', label);
      if (entity.type === 'place') add('place', label);
    }
    const chosen = [...keys].filter(([, item]) => filter === 'all' || filter === item.kind
      || (filter === 'event' && ['place', 'tag'].includes(item.kind)));
    if (filter !== 'all' && !chosen.length) continue;
    for (const [key, item] of chosen) linked.set(key, item);
    memories.push({ record, links: chosen.map(([key]) => key) });
  }
  return { memories, linked };
}

let constellationFilter = 'all';
let constellationSelectedKey = null;

function renderConstellation() {
  const area = document.getElementById('constellationGraph');
  const detail = document.getElementById('constellationDetail');
  const status = document.getElementById('constellationStatus');
  const { memories, linked } = buildConstellation(records, constellationFilter);
  area.replaceChildren();
  status.textContent = records.length
    ? '표시된 기록 ' + memories.length + '개 · 연결 항목 ' + linked.size + '개'
    : '저장한 일기나 감정 기록이 여기에 나타납니다.';
  if (!memories.length) {
    const empty = document.createElement('p');
    empty.className = 'constellation-empty muted';
    empty.textContent = records.length ? '이 범주와 연결된 기록이 없습니다.' : '아직 저장한 기록이 없습니다.';
    area.append(empty);
    detail.textContent = '';
    return;
  }

  const svgElement = (name, attributes, text) => {
    const element = document.createElementNS('http://www.w3.org/2000/svg', name);
    for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, value);
    if (text !== undefined) element.textContent = text;
    return element;
  };
  const trimLabel = (text, length) => {
    const chars = [...text];
    return chars.length <= length ? text : chars.slice(0, length - 1).join('') + '…';
  };
  const height = Math.max(240, Math.max(memories.length, linked.size) * 48 + 50);
  const svg = svgElement('svg', { viewBox: '0 0 900 ' + height, width: 900, height, role: 'group', 'aria-label': '저장 기록의 연결망' });
  const positions = new Map([...linked.keys()].map((key, index) => [key, 49 + index * 48]));
  for (const [index, memory] of memories.entries()) {
    for (const key of memory.links) {
      const y = 49 + index * 48, target = positions.get(key);
      svg.append(svgElement('path', { d: 'M 339 ' + y + ' C 450 ' + y + ' 464 ' + target + ' 573 ' + target, fill: 'none', stroke: '#a9c1ae', 'stroke-width': 1.5, 'aria-hidden': true }));
    }
  }
  const choose = record => {
    constellationSelectedKey = record.memoryKey;
    const title = document.createElement('strong');
    title.textContent = record.date + ' · ' + record.title;
    const body = document.createElement('p');
    body.textContent = record.summary || record.body;
    detail.replaceChildren(title, body);
  };
  for (const [index, { record }] of memories.entries()) {
    const y = 49 + index * 48;
    const label = record.title === '일기' ? record.body.split('\n')[0] : record.title;
    const group = svgElement('g', { class: 'constellation-record', role: 'button', tabindex: 0, 'aria-label': record.date + ' ' + label });
    group.append(
      svgElement('rect', { x: 28, y: y - 18, width: 311, height: 36, rx: 12, fill: '#fff', stroke: '#afc7b3' }),
      svgElement('text', { x: 42, y: y + 5, fill: '#193c2e' }, record.date + ' · ' + trimLabel(label, 17))
    );
    group.addEventListener('click', () => choose(record));
    group.addEventListener('keydown', event => {
      if (!['Enter', ' '].includes(event.key)) return;
      event.preventDefault();
      choose(record);
    });
    svg.append(group);
  }
  for (const [key, item] of linked) {
    const y = positions.get(key);
    const theme = constellationKinds[item.kind];
    const label = theme.label + ' · ' + item.label;
    const group = svgElement('g', {});
    group.append(
      svgElement('title', {}, label),
      svgElement('rect', { x: 573, y: y - 17, width: 287, height: 34, rx: 12, fill: theme.fill }),
      svgElement('text', { x: 588, y: y + 5, fill: theme.ink }, trimLabel(label, 24))
    );
    svg.append(group);
  }
  area.append(svg);
  choose(memories.find(({ record }) => record.memoryKey === constellationSelectedKey)?.record || memories[0].record);
}

if (typeof module === 'object' && module.exports) {
  module.exports = { buildConstellation };
} else {
  document.getElementById('constellationFilters').addEventListener('click', event => {
    const selected = event.target.closest('button[data-constellation-filter]');
    if (!selected) return;
    constellationFilter = selected.dataset.constellationFilter;
    for (const button of event.currentTarget.querySelectorAll('button')) {
      button.classList.toggle('on', button === selected);
      button.setAttribute('aria-pressed', String(button === selected));
    }
    renderConstellation();
  });
}
