'use strict';
// Keep the existing Lab markup for inspection, without loading any API clients.
const labPreviewText='지금은 화면 미리보기입니다. 데이터 조회와 실제 실행은 연결하지 않았어요.';
const banner=document.createElement('div');banner.className='ui-preview-banner';banner.setAttribute('role','note');
const message=document.createElement('div');const title=document.createElement('strong');title.textContent='화면 미리보기';message.append(title,document.createTextNode(labPreviewText));
const back=document.createElement('a');back.href='/#memorylab';back.textContent='← 서재의 Memory Lab으로';banner.append(message,back);
const main=document.querySelector('main .page')||document.querySelector('main');main.prepend(banner);
const sidebarNote=document.querySelector('.side-bottom p');if(sidebarNote)sidebarNote.textContent='화면 구성만 미리 확인합니다. 모델·데이터·실험 실행은 연결 전입니다.';
const footer=document.querySelector('main footer');if(footer)footer.textContent='UI 미리보기 · 모델 실행과 기록 저장 없음';
for(const button of document.querySelectorAll('button:not([data-page]):not([data-view])')){button.disabled=true;button.title='UI 미리보기 · 기능 연결 전';}
for(const form of document.querySelectorAll('form'))form.addEventListener('submit',event=>event.preventDefault());
for(const id of ['dataset','local-model','model','family','frozen-run','compare-a','compare-b','compare-question']){
  const el=document.getElementById(id);if(el?.tagName==='SELECT'&&!el.options.length){const option=document.createElement('option');option.textContent=id.includes('model')?'모델 연결 전':'자료 연결 전';el.add(option);}
}
for(const id of ['runtime-state','runtime-description','process-status','snapshot-state','notice']){const el=document.getElementById(id);if(el)el.textContent='화면 미리보기 · 기능 연결 전';}
for(const el of document.querySelectorAll('.badge.actual,.local-tag,.local'))if(!el.closest('.ui-preview-banner'))el.textContent='UI 미리보기';
for(const id of ['question-count','nav-runs','count']){const el=document.getElementById(id);if(el)el.textContent='—';}
function syncPreviewControls(){
  const route=document.getElementById('route')?.value;
  if(route){
    const summaryRoute=['M0','M1','G1','G2'].includes(route),chunkRoute=['K1','A1'].includes(route);
    for(const [id,visible]of [['summary-mode-control',summaryRoute],['event-graph-mode-control',route==='G1'],['chunk-search-mode-control',chunkRoute],['answer-pipeline-control',true],['all-candidates-control',route!=='R0-Full']]){const el=document.getElementById(id);if(el)el.hidden=!visible;}
    const mode=document.getElementById('summary-mode');if(mode&&['G1','G2'].includes(route))mode.value='extractive-v1';
    const label=document.getElementById('top-k-label');if(label)label.textContent=summaryRoute?'Top-K 출처':chunkRoute?'Top-K 구간':'Top-K 원문';
    const hint=document.getElementById('stage-help');if(hint)hint.textContent='선택한 설정의 화면 미리보기입니다. 검색·답변은 실행하지 않습니다.';
  }
  const searchRoute=document.getElementById('search-route');
  if(searchRoute)for(const id of ['summary-mode-control','answer-pipeline-control']){const el=document.getElementById(id);if(el)el.hidden=searchRoute.value!=='M1';}
}
document.getElementById('route')?.addEventListener('change',syncPreviewControls);
document.getElementById('search-route')?.addEventListener('change',syncPreviewControls);
syncPreviewControls();
const empty=(heading,text)=>{const box=document.createElement('div');box.className='ui-preview-empty';const strong=document.createElement('strong');strong.textContent=heading;const p=document.createElement('div');p.textContent=text;box.append(strong,p);return box;};
for(const [id,heading]of [['question-list','질문 목록'],['result-panel','실행 결과가 놓일 자리'],['selected-question','테스트 질문'],['trace-panel','처리 과정'],['gold-panel','검토 기준'],['history-list','실행 기록'],['memories','요약 기억'],['results','검색 결과']]){
  const el=document.getElementById(id);if(el)el.replaceChildren(empty(heading,'실제 자료를 불러오거나 테스트를 실행하지 않았습니다.'));
}
for(const nav of document.querySelectorAll('[data-page]'))nav.addEventListener('click',()=>{
  for(const page of document.querySelectorAll('section[id$="-page"]'))page.hidden=page.id!==nav.dataset.page+'-page';
  for(const item of document.querySelectorAll('[data-page]'))item.classList.toggle('active',item===nav);
  const page=document.getElementById(nav.dataset.page+'-page');
  if(page&&!page.querySelector('.ui-preview-empty')&&nav.dataset.page!=='workspace')page.appendChild(empty(nav.textContent.trim(),'화면 구성만 확인할 수 있어요. 실제 자료는 기능 연결 후 표시됩니다.'));
  const breadcrumb=document.getElementById('breadcrumb');if(breadcrumb)breadcrumb.textContent=nav.textContent.trim();window.scrollTo(0,0);
});
for(const nav of document.querySelectorAll('[data-view]'))nav.addEventListener('click',()=>{
  for(const view of document.querySelectorAll('section[id$="-view"]'))view.hidden=view.id!==nav.dataset.view+'-view';
  for(const item of document.querySelectorAll('[data-view]'))item.classList.toggle('active',item===nav);
  const view=document.getElementById(nav.dataset.view+'-view');if(view&&!view.querySelector('.ui-preview-empty'))view.appendChild(empty(nav.textContent.trim(),'기존 UI의 배치 미리보기입니다. 실제 실행은 연결되지 않았습니다.'));
});
