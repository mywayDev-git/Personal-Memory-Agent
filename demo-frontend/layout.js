

/* ========== COMMON ========== */

const pages = [
  'home','chat','emotion','map','archive','settings'
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
  document.querySelectorAll('.page').forEach(p=>{
    p.classList.remove('active');
  });

  document.getElementById(id).classList.add('active');

  document.querySelectorAll('#nav button').forEach((b,i)=>{
    b.classList.toggle('active',pages[i]===id);
  });

  document.getElementById('mobileSelect').value=id;

  window.scrollTo(0,0);

  if(id==='archive') {
    renderCalendar();
    runSearch();
  }

  if(id==='home') renderRecent();

  if(id==='map') renderConstellation();

  if(id==='chat') {
    requestAnimationFrame(scrollChatToBottom);
  }
}

/* ========== RECORDS ========== */

const records = [];

function recordDetail(record) {
  return record.schedule ? record.schedule.time || '시각 미정' : '감정 · ' + record.mood;
}

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
    b.classList.remove('on');
  });
  el.classList.add('on');
}



/* ========== CHAT SCENARIOS ========== */

const scenarios = [

  [
    '민수와 부산에 간 적 있어?',
    '예시 기록에서는 2025년 7월에 민수와 부산에 다녀온 내용이 확인됩니다.',
    [
      '2025.07.20 · 민수와 부산으로 여행을 다녀왔다.',
      '2025.07.21 · 부산에서 민수와 함께 식사했다.'
    ]
  ],

  [
    '그때 무슨 일이 있었지?',
    '어느 시점인지 명확하지 않습니다. 부산 여행이나 팀 회의 중 무엇을 말씀하시나요?',
    [
      '후보 A · 부산 여행',
      '후보 B · 팀 프로젝트 회의'
    ]
  ],

  [
    '민수와 부산도 가고 제주에도 갔어?',
    '부산 여행 기록은 있지만 제주에도 함께 갔다는 정보는 확인되지 않습니다.',
    [
      '확인된 기록 · 부산 여행',
      '미확인 정보 · 제주 동행'
    ]
  ],

  [
    '회의는 금요일이었어?',
    '회의 날짜에 관한 기록이 충돌하여 확정하기 어렵습니다.',
    [
      '기록 A · 금요일에 회의하기로 계획했다.',
      '기록 B · 토요일로 일정이 변경되었다.'
    ]
  ],

  [
    '부산 여행을 다녀왔어?',
    '여러 기록에서 같은 내용이 확인됩니다. 다만 반복 기록과 독립적인 사실 검증은 구분합니다.',
    [
      '여행 일기 · 민수와 부산에 다녀왔다.',
      '여행 회고 · 민수와 부산을 여행했다.'
    ]
  ],

  [
    '민수를 만났던 날은?',
    '민수와 만난 날짜가 여러 번 기록되어 있습니다.',
    [
      '2025.05.14 · 카페에서 만남',
      '2025.07.20 · 부산 여행',
      '2025.09.03 · 학교에서 대화'
    ]
  ],

  [
    '기분이 안 좋았던 날을 찾아줘.',
    '화가 났거나 속상했던 날이 의미상 관련된 기록 후보로 표시됩니다.',
    [
      '팀원과 말다툼이 생겨 화가 났다.',
      '기대했던 일이 취소되어 속상했다.'
    ]
  ]
];

/* 채팅 내부 자동 스크롤 */
function scrollChatToBottom() {
  const chat=document.getElementById('chatScroll');
  if(!chat)return;

  chat.scrollTop=chat.scrollHeight;
}

/* 시나리오 변경 */
function scenario(n) {

  document.querySelectorAll('#scenarioTabs button')
    .forEach((b,i)=>{
      b.classList.toggle('active',i===n);
    });

  const s=scenarios[n];

  document.getElementById('conversation').innerHTML=`
    <div class="bubble user">
      ${safe(s[0])}
    </div>

    <div class="bubble bot">
      <span class="tag">AI 답변 예시</span>
      <p>${safe(s[1])}</p>
    </div>
  `;

  document.getElementById('evidences').innerHTML=
    s[2].map(t=>`
      <div class="evidence">${safe(t)}</div>
    `).join('');

  const details=document.getElementById('evidenceDetails');
  details.open=false;

  requestAnimationFrame(scrollChatToBottom);
}

/* 새 대화 화면 */
function newChat() {
  document.querySelectorAll('#scenarioTabs button')
    .forEach(b=>b.classList.remove('active'));

  document.getElementById('conversation').innerHTML=`
    <div class="bubble bot">
      안녕하세요. 지난 기록에 대해 무엇이 궁금하신가요?
    </div>
  `;

  document.getElementById('evidences').innerHTML='';
  document.getElementById('evidenceDetails').open=false;
  document.getElementById('chatInput').value='';

  requestAnimationFrame(scrollChatToBottom);
}

/* 메시지 보내기 */


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

/* 근거 패널을 열었을 때 */
document.getElementById('evidenceDetails')
  .addEventListener('toggle',()=>{
    requestAnimationFrame(scrollChatToBottom);
  });

/* ========== SEARCH ========== */

function setFilter(el,type) {
  document.querySelectorAll('#filters .chip').forEach(b=>{
    b.classList.remove('on');
  });

  el.classList.add('on');
  searchFilter=type;
  runSearch();
}

function runSearch() {
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
        </div>
      `).join(''):
      '<p class="muted small">해당 조건의 저장된 기록이 없습니다.</p>';

  document.getElementById('searchNotice').innerHTML=`
    <b>달력과 보관소 미리보기</b>
    <p>달력에서 저장한 기록을 날짜별로 확인할 수 있습니다. 모델로 기억을 검색하려면 서재 홈이나 사색 대화에서 질문하세요.</p>
  `;
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
    if(e.key==='Enter')runSearch();
  });

document.getElementById('chatInput')
  .addEventListener('keydown',e=>{
    if(e.key==='Enter' && !e.isComposing)sendChat();
  });

/* ========== INITIALIZE ========== */

newChat();
renderCalendar();
renderRecent();
runSearch();


document.querySelector('[data-layout-event="0"]').addEventListener('click', function(event) { go('home') });
document.querySelector('[data-layout-event="1"]').addEventListener('click', function(event) { go('home') });
document.querySelector('[data-layout-event="2"]').addEventListener('click', function(event) { go('chat') });
document.querySelector('[data-layout-event="3"]').addEventListener('click', function(event) { go('emotion') });
document.querySelector('[data-layout-event="4"]').addEventListener('click', function(event) { go('map') });
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
document.querySelector('[data-layout-event="16"]').addEventListener('click', function(event) { newChat() });
document.querySelector('[data-layout-event="17"]').addEventListener('click', function(event) { scenario(0) });
document.querySelector('[data-layout-event="18"]').addEventListener('click', function(event) { scenario(6) });
document.querySelector('[data-layout-event="19"]').addEventListener('click', function(event) { scenario(4) });
document.querySelector('[data-layout-event="20"]').addEventListener('click', function(event) { scenario(0) });
document.querySelector('[data-layout-event="21"]').addEventListener('click', function(event) { scenario(1) });
document.querySelector('[data-layout-event="22"]').addEventListener('click', function(event) { scenario(2) });
document.querySelector('[data-layout-event="23"]').addEventListener('click', function(event) { scenario(3) });
document.querySelector('[data-layout-event="24"]').addEventListener('click', function(event) { scenario(4) });
document.querySelector('[data-layout-event="25"]').addEventListener('click', function(event) { scenario(5) });
document.querySelector('[data-layout-event="26"]').addEventListener('click', function(event) { scenario(6) });
document.querySelector('[data-layout-event="27"]').addEventListener('click', function(event) { alert('파일 첨부는 현재 UI 시연용입니다.') });
document.querySelector('[data-layout-event="28"]').addEventListener('click', function(event) { sendChat() });
document.querySelector('[data-layout-event="29"]').addEventListener('click', function(event) { chooseMood(this) });
document.querySelector('[data-layout-event="30"]').addEventListener('click', function(event) { chooseMood(this) });
document.querySelector('[data-layout-event="31"]').addEventListener('click', function(event) { chooseMood(this) });
document.querySelector('[data-layout-event="32"]').addEventListener('click', function(event) { chooseMood(this) });
document.querySelector('[data-layout-event="33"]').addEventListener('click', function(event) { chooseMood(this) });
document.querySelector('[data-layout-event="34"]').addEventListener('click', function(event) { addRecord() });
document.querySelector('[data-layout-event="39"]').addEventListener('click', function(event) { runSearch() });
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
