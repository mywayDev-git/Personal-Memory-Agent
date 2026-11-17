const pages=[
  'home','chat','emotion','archive','memorylab','settings'
];
const today=seoulDate();
const now=new Date(today+'T12:00:00+09:00');
const pad=n=>String(n).padStart(2,'0');
const key=(y,m,d)=>`${y}-${pad(m+1)}-${pad(d)}`;
let [year,month]=today.split('-').slice(0,2).map(Number);
month-=1;
let selected=today;

let searchFilter='all';
let archiveSearchActive=false;
let archiveView='calendar';
let calendarExpanded=false;
let emotionReturnPage='home';

function safe(v){
  return String(v??'').replace(/[&<>"']/g,c=>({
    '&':'&amp;',
    '<':'&lt;',
    '>':'&gt;',
    '"':'&quot;',
    "'":'&#39;'
  }[c]));
}

function go(id){
  const target=document.getElementById(id);
  if(!target)return;
  if(id==='emotion'){
    const previous=document.querySelector('.page.active');
    if(previous&&previous.id!=='emotion')emotionReturnPage=previous.id;
  }

  document.querySelectorAll('.page')
    .forEach(p=>p.classList.remove('active'));

  target.classList.add('active');
  document.body.classList.toggle('chat-mode',id==='chat');
  closeChatSidebar();

  document.querySelectorAll('#nav button')
    .forEach((b,i)=>{
      b.classList.toggle('active',pages[i]===id);
    });

  const select=document.getElementById('mobileSelect');
  if([...select.options].some(o=>o.value===id)){
    select.value=id;
  }

  window.scrollTo(0,0);

  if(id==='archive'){
    renderCalendar();
    renderTimeline();
    syncArchiveView();
    runSearch();
  }
  if(id==='home')renderRecent();
  if(id==='chat'){
    requestAnimationFrame(scrollChatToBottom);
  }
}

/* UI preview: no saved records are loaded. */
const records=[];

function recordIndex(r){
  return records.indexOf(r);
}

function openRecord(index){
  const r=records[index];
  if(!r)return;

  document.getElementById('detailTitle')
    .textContent=r.title;
  document.getElementById('detailDate')
    .textContent=r.date+' · '+r.type;
  document.getElementById('detailBody')
    .textContent=r.body;

  go('recordDetail');
}

function previewRecordDate(index){
  const record=records[index];
  if(!record)return;
  const [y,m]=record.date.split('-').map(Number);
  year=y;
  month=m-1;
  selected=record.date;
  renderCalendar();
  document.querySelectorAll('#searchResults [data-record-index]').forEach(card=>{
    const active=Number(card.dataset.recordIndex)===index;
    card.classList.toggle('date-preview',active);
    card.setAttribute('aria-pressed',String(active));
  });
}

function renderRecent(){
  document.getElementById('homeRecent').innerHTML=
    [...records]
      .sort((a,b)=>b.date.localeCompare(a.date))
      .slice(0,3)
      .map(r=>`
        <li><button class="recent-row"
          onclick="openRecord(${recordIndex(r)})">
          <span class="recent-record-date">
            ${safe(r.date)} · ${safe(r.type)}
          </span>
          <span class="recent-record-content">
            <span class="recent-record-title">${safe(r.title)}</span>
            <span class="recent-record-preview">${safe(r.body)}</span>
          </span>
          <span class="recent-record-link"><span class="recent-record-link-label">기록 읽기 </span>↗</span>
        </button></li>
      `).join('');
}

/* CALENDAR */
function syncArchiveView(){
  const timeline=archiveView==='timeline';
  document.getElementById('archiveCalendar').hidden=timeline;
  document.getElementById('archiveTimeline').hidden=!timeline;
  document.getElementById('calendarViewButton').setAttribute('aria-pressed',String(!timeline));
  document.getElementById('timelineViewButton').setAttribute('aria-pressed',String(timeline));
  document.getElementById('calendarZoomButton').hidden=timeline;
  document.getElementById('timelineSortControl').hidden=!timeline;
  document.getElementById('archiveWorkspace').classList.toggle('calendar-expanded',!timeline&&calendarExpanded);
  document.getElementById('calendarZoomButton').setAttribute('aria-pressed',String(calendarExpanded));
  document.getElementById('calendarZoomButton').textContent=calendarExpanded?'↙ 기본 크기':'↗ 달력 확대';
  document.getElementById('calendarDetailsHint').hidden=timeline||!calendarExpanded;
  document.getElementById('calendarGridScroll').tabIndex=calendarExpanded?0:-1;
}
function setArchiveView(view){
  archiveView=view==='timeline'?'timeline':'calendar';
  if(archiveView==='timeline')renderTimeline();
  syncArchiveView();
  renderSelected();
}
function toggleCalendarSize(){
  calendarExpanded=!calendarExpanded;
  syncArchiveView();
}
function selectArchiveDate(date,revealPanel=true){
  if(!/^\d{4}-\d{2}-\d{2}$/.test(date))return;
  const [y,m]=date.split('-').map(Number);
  const sameMonth=year===y&&month===m-1;
  selected=date;year=y;month=m-1;archiveSearchActive=false;
  if(sameMonth){updateCalendarSelection();renderSelected();updateTimelineSelection();}
  else renderCalendar();
  if(revealPanel&&window.matchMedia('(max-width:900px)').matches){
    requestAnimationFrame(()=>document.getElementById('archiveSidePanel').scrollIntoView({behavior:'smooth',block:'start'}));
  }
}
function updateCalendarSelection(){
  document.querySelectorAll('#calendarDays .day[data-date]').forEach(day=>{
    const active=day.dataset.date===selected;
    day.classList.toggle('selected',active);
    day.querySelector('.day-date-control').setAttribute('aria-pressed',String(active));
  });
}
function selectArchiveRecordDate(index){
  const record=records[index];if(record)selectArchiveDate(record.date);
}
function updateTimelineSelection(){
  document.querySelectorAll('.timeline-group').forEach(group=>{
    const active=group.dataset.date===selected;
    group.classList.toggle('is-selected',active);
    group.querySelector('.timeline-date').setAttribute('aria-pressed',String(active));
  });
}
function renderTimeline(){
  const newest=document.getElementById('timelineSort').value==='newest';
  const sorted=[...records].sort((a,b)=>(newest?-1:1)*(a.date.localeCompare(b.date)||recordIndex(a)-recordIndex(b)));
  const groups=new Map();
  sorted.forEach(record=>{if(!groups.has(record.date))groups.set(record.date,[]);groups.get(record.date).push(record);});
  document.getElementById('timelineCount').textContent=`${groups.size}일 · ${records.length}개 기록`;
  document.getElementById('timelineGroups').innerHTML=[...groups].map(([date,items])=>{
    const [y,m,d]=date.split('-').map(Number);
    return `<div class="timeline-group" data-date="${safe(date)}">
      <button class="timeline-date" data-date="${safe(date)}" onclick="selectArchiveDate(this.dataset.date)">${y}년 ${m}월 ${d}일 · ${items.length}개 기록</button>
      <ul class="timeline-record-list">${items.map(record=>`<li class="timeline-entry">
        <button class="timeline-record" data-record-id="${safe(record.sampleId||'')}" data-source-profile="${safe(record.profile||'')}" onclick="selectArchiveRecordDate(${recordIndex(record)})" ondblclick="openRecord(${recordIndex(record)})" onkeydown="if(event.key==='Enter'){event.preventDefault();openRecord(${recordIndex(record)})}" title="한 번 클릭하면 날짜 선택, 더블클릭하면 기록 열기">
          <strong>${safe(record.title)}</strong><span>${record.profileLabel?safe(record.profileLabel)+' · ':''}${safe(record.body)}</span>
        </button>
        <button class="timeline-open" onclick="openRecord(${recordIndex(record)})" aria-label="${safe(record.title)} 기록 열기">↗</button>
      </li>`).join('')}</ul>
    </div>`;
  }).join('')||'<p class="muted small">아직 기록이 없습니다.</p>';
  updateTimelineSelection();
}
function renderCalendar(){
  const grid=document.getElementById('calendarDays');
  grid.innerHTML='';

  document.getElementById('monthTitle').textContent=
    `${year}년 ${month+1}월`;

  const offset=new Date(year,month,1).getDay();
  const days=new Date(year,month+1,0).getDate();

  for(let i=0;i<offset;i++){
    const gap=document.createElement('div');
    gap.className='day empty';
    grid.appendChild(gap);
  }

  for(let d=1;d<=days;d++){
    const date=key(year,month,d);
    const dayRecords=records.filter(r=>r.date===date);
    const count=dayRecords.length;

    const cell=document.createElement('div');
    cell.className='day'
      +(selected===date?' selected':'')
      +(date===today?' today':'');
    cell.dataset.date=date;
    const btn=document.createElement('button');
    btn.className='day-date-control';

    btn.innerHTML=
      `<span class="number">${d}</span>`+
      (count
        ? `<span class="dot"></span>
           <span class="count">${count}개 기록</span>`
        : '');

    btn.setAttribute(
      'aria-label',
      `${month+1}월 ${d}일, 기록 ${count}개`
    );
    btn.setAttribute('aria-pressed',String(selected===date));

    btn.onclick=event=>{
      event.stopPropagation();
      selectArchiveDate(date);
    };
    cell.appendChild(btn);
    cell.onclick=()=>selectArchiveDate(date);
    if(count){
      const previews=document.createElement('div');
      previews.className='day-record-previews';
      dayRecords.slice(0,2).forEach(record=>{
        const preview=document.createElement('button');
        preview.className='calendar-record';preview.dataset.recordId=record.sampleId||'';preview.dataset.sourceProfile=record.profile||'';
        preview.title=record.title+'\n'+record.body;
        preview.setAttribute('aria-label',record.title+' · '+record.date+' · 날짜 확인, 더블클릭으로 기록 열기');
        const title=document.createElement('span');title.className='calendar-record-title';title.textContent=record.title;
        const excerpt=document.createElement('span');excerpt.className='calendar-record-preview';excerpt.textContent=record.body;
        preview.append(title,excerpt);
        preview.onclick=event=>{event.stopPropagation();selectArchiveDate(date,false);};
        preview.ondblclick=event=>{event.stopPropagation();openRecord(recordIndex(record));};
        preview.onkeydown=event=>{if(event.key==='Enter'){event.preventDefault();openRecord(recordIndex(record));}};
        previews.appendChild(preview);
      });
      if(count>2){
        const more=document.createElement('button');more.className='calendar-more-records';more.textContent='+'+(count-2)+'개 더 보기';
        more.onclick=event=>{event.stopPropagation();selectArchiveDate(date);};previews.appendChild(more);
      }
      cell.appendChild(previews);
    }
    grid.appendChild(cell);
  }

  renderSelected();
  updateTimelineSelection();
}

function renderSelected(){
  syncArchivePanel();
  const list=records.filter(r=>r.date===selected);
  const parts=selected.split('-').map(Number);

  document.getElementById('selectedDate').textContent=
    archiveView==='timeline'?`${parts[0]}년 ${parts[1]}월 ${parts[2]}일`:`${parts[1]}월 ${parts[2]}일`;

  document.getElementById('selectedCount').textContent=
    list.length
      ? `${list.length}개의 기록이 남아 있어요`
      : '이날 기록이 없습니다.';

  document.getElementById('selectedList').innerHTML=
    list.length
      ? list.map(r=>`
          <div class="record"
            style="cursor:pointer"
            onclick="openRecord(${recordIndex(r)})">
            <span class="tag">${safe(r.type)}</span>
            <h3 style="font-size:17px;margin-top:12px">
              ${safe(r.title)}
            </h3>
            <p>${safe(r.body)}</p>
            <small>${safe(r.date)}</small>
          </div>
        `).join('')
      : '<p class="muted small">그날의 이야기를 새로 남겨보세요.</p>';
}

function moveMonth(n){
  archiveSearchActive=false;
  const d=new Date(year,month+n,1);
  year=d.getFullYear();
  month=d.getMonth();
  selected=key(year,month,1);
  renderCalendar();
}

function todayMonth(){
  archiveSearchActive=false;
  year=now.getFullYear();
  month=now.getMonth();
  selected=today;
  renderCalendar();
}

function writeSelected(){
  go('emotion');
  document.getElementById('recordDate').value=selected;
}

function appendInlineText(target,text){
  text.split(/(\*\*[^*]+\*\*)/g).forEach(part=>{
    if(part.startsWith('**')&&part.endsWith('**')){
      const strong=document.createElement('strong');strong.textContent=part.slice(2,-2);target.appendChild(strong);
    }else target.appendChild(document.createTextNode(part));
  });
}
function renderBotText(text){
  const content=document.createElement('div');content.className='bot-content';
  text.split('\n\n').forEach(block=>{
    const lines=block.split('\n');
    if(lines.every(line=>line.startsWith('- '))){
      const list=document.createElement('ul');
      lines.forEach(line=>{const item=document.createElement('li');appendInlineText(item,line.slice(2));list.appendChild(item);});
      content.appendChild(list);
    }else{
      const paragraph=document.createElement('p');
      lines.forEach((line,i)=>{if(i)paragraph.appendChild(document.createElement('br'));appendInlineText(paragraph,line);});
      content.appendChild(paragraph);
    }
  });
  return content;
}

function scrollChatToBottom(){
  const element=document.getElementById('chatScroll');
  if(element)element.scrollTop=element.scrollHeight;
}
function updateChatInput(){
  const input=document.getElementById('chatInput');
  input.style.height='40px';
  input.style.height=Math.min(Math.max(input.scrollHeight,40),180)+'px';
  if(typeof updateDemoControls==='function')updateDemoControls();
}

function syncSidebarAccessibility(){
  const layout=document.getElementById('chatLayout');
  const mobile=window.matchMedia('(max-width:1000px)').matches;
  document.getElementById('sidebarToggle').setAttribute('aria-expanded',String(mobile?layout.classList.contains('sidebar-open'):!layout.classList.contains('sidebar-collapsed')));
}
function toggleChatSidebar(){
  const layout=document.getElementById('chatLayout');
  layout.classList.toggle(window.matchMedia('(max-width:1000px)').matches?'sidebar-open':'sidebar-collapsed');
  syncSidebarAccessibility();
}
function closeChatSidebar(){
  document.getElementById('chatLayout').classList.remove('sidebar-open');
  syncSidebarAccessibility();
}
document.getElementById('chatInput').addEventListener('input',updateChatInput);
document.addEventListener('keydown',e=>{
  if(e.key==='Escape'){
    const wasOpen=document.getElementById('chatLayout').classList.contains('sidebar-open');
    closeChatSidebar();
    if(wasOpen)document.getElementById('sidebarToggle').focus();
  }
});
window.addEventListener('resize',closeChatSidebar);
const headerObserver=new ResizeObserver(entries=>{
  document.documentElement.style.setProperty('--header-height',entries[0].target.getBoundingClientRect().height+'px');
});
headerObserver.observe(document.querySelector('header'));


const chatObserver=new MutationObserver(()=>{
  requestAnimationFrame(scrollChatToBottom);
});

chatObserver.observe(
  document.getElementById('conversation'),
  {childList:true}
);

/* SEARCH */
function syncArchivePanel(){
  const timeline=archiveView==='timeline';
  document.getElementById('dayRecordsView').hidden=archiveSearchActive||timeline;
  document.getElementById('archiveTimelinePreview').hidden=archiveSearchActive||!timeline;
  document.getElementById('archiveSearchView').hidden=!archiveSearchActive;
  document.getElementById('archiveSidePanel').setAttribute('aria-label',archiveSearchActive?'검색 결과':timeline?'선택한 원문 미리보기':'선택 날짜의 기록');
  document.querySelector('#archiveSearchView>button').textContent=timeline?'← 선택한 원문 미리보기로 돌아가기':'← 날짜 기록으로 돌아가기';
}
function showDayRecords(){
  archiveSearchActive=false;
  syncArchivePanel();
}
function setFilter(el,type){
  document.querySelectorAll('#filters .chip')
    .forEach(b=>b.classList.remove('on'));

  el.classList.add('on');
  searchFilter=type;
  runSearch(archiveSearchActive);
}

/* 검색 결과로 스크롤하는 함수 */
function scrollToSearchResults(){
  requestAnimationFrame(()=>{
    const heading=document.getElementById(
      'searchResultsHeading'
    );
    if(heading){
      heading.scrollIntoView({
        behavior:'smooth',
        block:'start'
      });
    }
  });
}

/* Preview-only input handling is supplied by preview.js. */

function searchHome(value){
  const q=value||
    document.getElementById('homeSearch').value.trim();

  document.getElementById('archiveInput').value=q;
  archiveSearchActive=false;
  go('archive');
  runSearch(true);
}

/* AUTH */
function authDemo(e,mode){
  e.preventDefault();

  if(mode==='signup'){
    const p1=document.getElementById('password1').value;
    const p2=document.getElementById('password2').value;

    if(p1!==p2){
      alert('비밀번호 확인이 일치하지 않습니다.');
      return;
    }
  }

  alert(
    mode==='login'
      ? '로그인 UI 시연용입니다.'
      : '회원가입 UI 시연용입니다. 실제 계정은 생성되지 않습니다.'
  );
}

/* KEYBOARD */
document.getElementById('homeSearch')
  .addEventListener('keydown',e=>{
    if(e.key==='Enter'&&!e.isComposing){
      e.preventDefault();
      startChatFromHome();
    }
  });

document.getElementById('archiveInput')
  .addEventListener('keydown',e=>{
    if(e.key==='Enter'){
      runSearch(true);
    }
  });

document.getElementById('chatInput')
  .addEventListener('keydown',e=>{
    if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){
      e.preventDefault();
      sendChat();
    }
  });

/* INITIALIZE */
document.getElementById('recordDate').value=today;

renderCalendar();
renderRecent();
// The preview controller restores the active screen after loading.
