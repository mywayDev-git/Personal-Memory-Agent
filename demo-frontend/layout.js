

/* ========== COMMON ========== */

const pages = [
  'home','chat','emotion','archive','settings'
];

const pad = n => String(n).padStart(2,'0');

const key = (y,m,d) =>
  `${y}-${pad(m+1)}-${pad(d)}`;

let selected = seoulDate();
const [initialYear, initialMonth] = selected.split('-').map(Number);
let year = initialYear;
let month = initialMonth - 1;
let searchFilter = 'all';

function safe(v) {
  return String(v).replace(/[&<>"']/g,c=>({
    '&':'&amp;',
    '<':'&lt;',
    '>':'&gt;',
    '"':'&quot;',
    "'":'&#39;'
  }[c]));
}

function go(id) {
  const page = document.getElementById(id);
  if (!page?.classList.contains('page')) return;
  const menuPage = id === 'recordDetail' ? 'archive' : id;

  document.querySelectorAll('.page').forEach(p=>{
    p.classList.remove('active');
  });

  page.classList.add('active');

  document.querySelectorAll('#nav button').forEach((b,i)=>{
    b.classList.toggle('active',pages[i]===menuPage);
  });

  document.getElementById('mobileSelect').value=menuPage;

  window.scrollTo(0,0);

  if(id==='archive') {
    renderCalendar();
    runSearch();
  }

  if(id==='home') renderRecent();


  if(id==='chat') {
    requestAnimationFrame(scrollChatToBottom);
  }
}

/* ========== RECORDS ========== */

const records = [];

function recordDetail(record) {
  return record.schedule ? record.schedule.time || '시각 미정' : '감정 · ' + record.mood;
}

function recordDetailsButton(record) {
  return `<button class="ghost small record-more" type="button"
    data-open-record="${safe(record.memoryKey)}">기록 자세히 보기</button>`;
}

function openRecord(memoryKey) {
  const record = records.find(item => item.memoryKey === memoryKey);
  if (!record) return;

  document.getElementById('detailTitle').textContent = record.title;
  document.getElementById('detailDate').textContent =
    [record.date, record.type, recordDetail(record), record.tags].filter(Boolean).join(' · ');
  document.getElementById('detailBody').textContent = record.body;
  go('recordDetail');
}

document.addEventListener('click', event => {
  const button = event.target.closest('[data-open-record]');
  if (button) openRecord(button.dataset.openRecord);
});

function renderRecent() {
  if(!records.length) {
    document.getElementById('homeRecent').textContent = '아직 저장한 기록이 없습니다.';
    return;
  }
  document.getElementById('homeRecent').innerHTML =
    [...records]
      .sort((a,b)=>b.date.localeCompare(a.date))
      .slice(0,3)
      .map(r=>`
        <div class="record">
          <small>${safe(r.date)} · ${safe(r.type)}${r.schedule ? ' · ' + safe(recordDetail(r)) : ''}</small>
          <p><b>${safe(r.title)}</b></p>
          <p>${safe(r.body)}</p>
          ${recordDetailsButton(r)}
        </div>
      `).join('');
}

/* ========== CALENDAR ========== */

function renderCalendar() {
  const grid=document.getElementById('calendarDays');
  grid.innerHTML='';

  document.getElementById('monthTitle').textContent =
    `${year}년 ${month+1}월`;

  const today=seoulDate();
  const offset=new Date(Date.UTC(year,month,1)).getUTCDay();
  const days=new Date(Date.UTC(year,month+1,0)).getUTCDate();

  for(let i=0;i<offset;i++) {
    const gap=document.createElement('div');
    gap.className='day empty';
    grid.appendChild(gap);
  }

  for(let d=1;d<=days;d++) {
    const date=key(year,month,d);
    const count=records.filter(r=>r.date===date).length;

    const btn=document.createElement('button');
    btn.className='day'
      +(selected===date?' selected':'')
      +(date===today?' today':'');

    btn.innerHTML =
      `<span class="number">${d}</span>`+
      (count?
        `<span class="dot"></span>
         <span class="count">${count}개 기록</span>`:
        '');

    btn.setAttribute(
      'aria-label',
      `${month+1}월 ${d}일, 기록 ${count}개`
    );

    btn.onclick=()=>{
      selected=date;
      renderCalendar();
    };

    grid.appendChild(btn);
  }

  renderSelected();
}

function renderSelected() {
  const list=records.filter(r=>r.date===selected).sort((a,b)=>(a.schedule?.time||'').localeCompare(b.schedule?.time||''));
  const parts=selected.split('-').map(Number);

  document.getElementById('selectedDate').textContent =
    `${parts[1]}월 ${parts[2]}일`;

  document.getElementById('selectedCount').textContent =
    list.length?
      `${list.length}개의 기록이 남아 있어요`:
      '이날 기록이 없습니다.';

  document.getElementById('selectedList').innerHTML =
    list.length?
      list.map(r=>`
        <div class="record">
          <span class="tag">${safe(r.type)}</span>
          <h3 style="font-size:17px;margin-top:12px">
            ${safe(r.title)}
          </h3>
          <p>${safe(r.body)}</p>
          <small>${safe(recordDetail(r))}</small>
          <div>${recordDetailsButton(r)}</div>
        </div>
      `).join(''):
      '<p class="muted small">그날의 이야기를 새로 남겨보세요.</p>';
}

function moveMonth(n) {
  const d=new Date(year,month+n,1);
  year=d.getFullYear();
  month=d.getMonth();
  selected=key(year,month,1);
  renderCalendar();
}

function todayMonth() {
  selected=seoulDate();
  const [todayYear,todayMonthNumber]=selected.split('-').map(Number);
  year=todayYear;
  month=todayMonthNumber-1;
  renderCalendar();
}

function writeSelected() {
  go('emotion');
  document.getElementById('recordDate').value=selected;
}

/* ========== EMOTION ========== */

function chooseMood(el) {
  document.querySelectorAll('.mood').forEach(b=>{
    b.classList.toggle('on', b===el);
    b.setAttribute('aria-pressed', String(b===el));
  });
}



/* ========== CHAT ========== */

/* 채팅 내부 자동 스크롤 */
function scrollChatToBottom() {
  const chat=document.getElementById('chatScroll');
  if(!chat)return;

  chat.scrollTop=chat.scrollHeight;
}

/* 새 메시지나 근거 변경 시 스크롤 */
const chatObserver=new MutationObserver(()=>{
  requestAnimationFrame(scrollChatToBottom);
});

chatObserver.observe(
  document.getElementById('conversation'),
  {
    childList:true
  }
);

/* ========== SEARCH ========== */

function setFilter(el,type) {
  document.querySelectorAll('#filters .chip').forEach(b=>{
    b.classList.remove('on');
  });

  el.classList.add('on');
  searchFilter=type;
  runSearch();
}

function runSearch(scrollToResults = false) {
  const q=
    document.getElementById('archiveInput')
      .value.trim().toLowerCase();

  const direct=[];
  const semantic=[];

  records.forEach(r=>{
    const content=(r.title+' '+r.body).toLowerCase();

    const exact=!q||content.includes(q);

    const similar=q
      && /기분|화남|짜증|속상|우울|스트레스/.test(q)
      && ['화남','불안함','슬픔'].includes(r.mood);

    if(exact) direct.push(r);
    else if(similar) semantic.push(r);
  });

  let list=[];

  if(searchFilter!=='semantic') {
    list.push(...direct.map(r=>({
      ...r,match:'원문 일치'
    })));
  }

  if(searchFilter!=='exact') {
    list.push(...semantic.map(r=>({
      ...r,match:'의미 유사 · 예시'
    })));
  }

  document.getElementById('resultCount').textContent=
    `${list.length}건`;

  document.getElementById('searchResults').innerHTML=
    list.length?
      list.map(r=>`
        <div class="card">
          <span class="tag ${r.match.startsWith('의미')?'brown':''}">
            ${r.match}
          </span>

          <h3 style="margin-top:15px;font-size:18px">
            ${safe(r.title)}
          </h3>

          <p class="muted small">
            ${safe(r.body)}
          </p>

          <div class="line"></div>

          <span class="muted small">
            ${safe(r.date)} · ${safe(recordDetail(r))}
          </span>
          <div>${recordDetailsButton(r)}</div>
        </div>
      `).join(''):
      '<p class="muted small">해당 조건의 저장된 기록이 없습니다.</p>';

  document.getElementById('searchNotice').innerHTML=`
    <b>달력과 보관소</b>
    <p>달력에서 저장한 기록을 날짜별로 확인할 수 있습니다. 모델로 기억을 검색하려면 서재 홈이나 사색 대화에서 질문하세요.</p>
  `;
  if (scrollToResults) {
    document.getElementById('searchResultsHeading').scrollIntoView({ block: 'start' });
  }
}

/* ========== AUTH ========== */

function authDemo(e,mode) {
  e.preventDefault();

  if(mode==='signup') {
    const p1=document.getElementById('password1').value;
    const p2=document.getElementById('password2').value;

    if(p1!==p2) {
      alert('비밀번호 확인이 일치하지 않습니다.');
      return;
    }
  }

  alert(
    mode==='login'?
      '로그인 UI 시연용입니다.':
      '회원가입 UI 시연용입니다. 실제 계정은 생성되지 않습니다.'
  );
}

/* ========== KEYBOARD ========== */

document.getElementById('archiveInput')
  .addEventListener('keydown',e=>{
    if(e.key==='Enter' && !e.isComposing) runSearch(true);
  });

document.getElementById('chatInput')
  .addEventListener('keydown',e=>{
    if(e.key==='Enter' && !e.isComposing)sendChat();
  });

/* ========== INITIALIZE ========== */

renderCalendar();
renderRecent();
runSearch();


document.querySelector('[data-layout-event="0"]').addEventListener('click', function(event) { go('home') });
document.querySelector('[data-layout-event="1"]').addEventListener('click', function(event) { go('home') });
document.querySelector('[data-layout-event="2"]').addEventListener('click', function(event) { go('chat') });
document.querySelector('[data-layout-event="3"]').addEventListener('click', function(event) { go('emotion') });
document.querySelector('[data-layout-event="5"]').addEventListener('click', function(event) { go('archive') });
document.querySelector('[data-layout-event="6"]').addEventListener('click', function(event) { go('settings') });
document.querySelector('[data-layout-event="7"]').addEventListener('click', function(event) { go('login') });
document.querySelector('[data-layout-event="8"]').addEventListener('change', function(event) { go(this.value) });
document.querySelector('[data-layout-event="10"]').addEventListener('click', function(event) { go('emotion') });
document.querySelector('[data-layout-event="11"]').addEventListener('click', function(event) { askFromHome('기분이 안 좋았던 날의 기록을 찾아줘.') });
document.querySelector('[data-layout-event="12"]').addEventListener('click', function(event) { go('chat') });
document.querySelector('[data-layout-event="13"]').addEventListener('click', function(event) { go('emotion') });
document.querySelector('[data-layout-event="14"]').addEventListener('click', function(event) { go('archive') });
document.querySelector('[data-layout-event="15"]').addEventListener('click', function(event) { go('chat') });
document.querySelector('[data-layout-event="27"]').addEventListener('click', function(event) { alert('파일 첨부는 현재 UI 시연용입니다.') });
document.querySelector('[data-layout-event="28"]').addEventListener('click', function(event) { sendChat() });
document.querySelector('[data-layout-event="29"]').addEventListener('click', function(event) { chooseMood(this) });
document.querySelector('[data-layout-event="30"]').addEventListener('click', function(event) { chooseMood(this) });
document.querySelector('[data-layout-event="31"]').addEventListener('click', function(event) { chooseMood(this) });
document.querySelector('[data-layout-event="32"]').addEventListener('click', function(event) { chooseMood(this) });
document.querySelector('[data-layout-event="33"]').addEventListener('click', function(event) { chooseMood(this) });
document.querySelector('[data-layout-event="34"]').addEventListener('click', function(event) { addRecord() });
document.querySelector('[data-layout-event="39"]').addEventListener('click', function(event) { runSearch(true) });
document.querySelector('[data-layout-event="40"]').addEventListener('click', function(event) { setFilter(this,'all') });
document.querySelector('[data-layout-event="41"]').addEventListener('click', function(event) { setFilter(this,'exact') });
document.querySelector('[data-layout-event="42"]').addEventListener('click', function(event) { setFilter(this,'semantic') });
document.querySelector('[data-layout-event="43"]').addEventListener('click', function(event) { moveMonth(-1) });
document.querySelector('[data-layout-event="44"]').addEventListener('click', function(event) { todayMonth() });
document.querySelector('[data-layout-event="45"]').addEventListener('click', function(event) { moveMonth(1) });
document.querySelector('[data-layout-event="46"]').addEventListener('click', function(event) { writeSelected() });
document.querySelector('[data-layout-event="47"]').addEventListener('submit', function(event) { authDemo(event,'login') });
document.querySelector('[data-layout-event="48"]').addEventListener('click', function(event) { go('signup') });
document.querySelector('[data-layout-event="49"]').addEventListener('submit', function(event) { authDemo(event,'signup') });
document.querySelector('[data-layout-event="50"]').addEventListener('click', function(event) { go('login') });
document.querySelector('[data-layout-event="51"]').addEventListener('click', function(event) { alert('서비스 안내 UI 준비 중') });
document.querySelector('[data-layout-event="52"]').addEventListener('click', function(event) { alert('개인정보 보호 UI 준비 중') });
document.querySelector('[data-layout-event="53"]').addEventListener('click', function(event) { alert('도움말 UI 준비 중') });
document.querySelector('[data-layout-event="54"]').addEventListener('click', () => go('archive'));
