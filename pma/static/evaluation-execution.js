// The only mutation paths are the user's submit and cancel button handlers.
const byId = id => document.getElementById(id);
const active = new Set(['running', 'cancelling', 'detached']);
const form = byId('execution-form');
const profile = byId('execution-profile');
const start = byId('execution-start');
const cancel = byId('execution-cancel');
const feedback = byId('execution-feedback');
let followStartedJob=false;
let options = null, current = {status:'idle'}, busy = false, known = false, selectedRun = '', checking = false, revision = 0;
const labels = {idle:'실행 중인 테스트가 없습니다.',running:'테스트 진행 중입니다. 아래에서 진행률과 결과를 확인하세요.',cancelling:'중단을 요청했습니다. 현재 모델 처리가 끝나면 평가용 서버를 정리합니다.',detached:'평가 실행 상태를 확인하고 있습니다.',completed:'평가 실행을 마쳤습니다. 검토 대기 항목은 별도 확인이 필요합니다.',cancelled:'평가를 중단했습니다. 완료한 결과는 보존됩니다.',failed:'평가 실행에 실패했습니다. 생성된 결과가 있으면 아래에서 확인할 수 있습니다.',interrupted:'이전 평가가 예기치 않게 종료되었습니다. 완료한 결과는 보존됩니다.',unavailable:'이전 평가 실행 정보를 확인할 수 없습니다.'};

async function api(path, body) {
  const request = {credentials:'same-origin',cache:'no-store'};
  if (body !== undefined) {
    const session = await fetch('/api/v1/session', {credentials:'same-origin',cache:'no-store'});
    if (!session.ok) throw new Error('접속 인증이 필요합니다. 앱 실행기가 연 화면으로 다시 접속해 주세요.');
    const value = await session.json();
    request.method='POST'; request.headers={'Content-Type':'application/json','X-CSRF-Token':value.csrf};
    request.body=JSON.stringify(body);
  }
  const response = await fetch('/api/eval'+path, request);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error?.message || data.detail?.message || '평가 요청을 처리하지 못했습니다.');
  return data;
}

function names(role) {
  if (['core','extended'].includes(profile.value)) return ['baseline'];
  return [...byId('execution-'+role).querySelectorAll('input:checked')].map(input=>input.value);
}

function render() {
  const running=active.has(current.status), locked=running||busy;
  profile.disabled=locked;
  for (const role of ['generation','embedding']) byId('execution-'+role).disabled=locked||['core','extended'].includes(profile.value);
  cancel.disabled=!running||current.status==='cancelling'||busy;
  if (!options) {start.disabled=true; return;}
  const spec=options.profiles[profile.value];
  byId('execution-scope').textContent=`각 조합 기준: 자동 실행 ${spec.automated}개 · 답변 외 조건 미검증 ${spec.partial_coverage||0}개 · ${spec.repeats}회 반복. ${profile.value==='extended'?'최대 10,000건을 실제 처리하므로 오래 걸릴 수 있습니다.':''}`;
  let ready=options.server_available;
  for (const role of ['generation','embedding']) {
    const selected=names(role);
    ready=ready&&selected.length>0&&selected.every(id=>options[role].some(m=>m.id===id&&m.available));
    if(profile.value==='compare') ready=ready&&selected.includes('baseline');
  }
  if(profile.value==='compare')ready=ready&&names('generation').length+names('embedding').length>=3;
  byId('execution-ready').textContent=ready?'평가용 로컬 모델을 별도로 불러옵니다. 앱의 기본 모델 설정은 바뀌지 않습니다.':'모델 파일과 평가 실행 프로그램이 준비되어야 합니다. 모델 비교에는 기준 모델과 다른 후보를 함께 선택하세요.';
  start.disabled=!ready||locked||!known;
  start.textContent=busy?'요청 처리 중…':'테스트 실행';
}

function show(value) {
  if(known&&!followStartedJob&&JSON.stringify(current)===JSON.stringify(value))return;
  current=value; known=true;
  feedback.textContent=labels[value.status]||'평가 상태를 확인해 주세요.';
  const run=value.run_ids?.at(-1);
  if(followStartedJob&&run&&run!==selectedRun){selectedRun=run;followStartedJob=false;window.dispatchEvent(new CustomEvent('evaluation-run-selected',{detail:{runId:run}}));}
  render();
}

async function refresh() {
  if(checking)return;
  checking=true;const version=revision;
  try {const value=await api('/execution');if(version===revision)show(value);}
  catch(error){if(version===revision){known=false;feedback.textContent=error.message;render();}}
  finally {checking=false;}
}

profile.onchange=()=>{
  if(['core','extended'].includes(profile.value))for(const role of ['generation','embedding']){
    for(const input of byId('execution-'+role).querySelectorAll('input'))input.checked=input.value==='baseline';
  }
  render();
};
form.onsubmit=async event=>{
  event.preventDefault();
  if(start.disabled||busy) return;
  const request={request_id:crypto.randomUUID(),profile:profile.value,generation:names('generation'),embedding:names('embedding')};
  revision++;busy=true;render();
  try {const result=await api('/execution',request);followStartedJob=true;selectedRun='';show(result);}
  catch(error){feedback.textContent=error.message;}
  finally {busy=false;render();}
};
cancel.onclick=async()=>{
  if(cancel.disabled||busy||!current.id)return;
  revision++;busy=true;render();
  try {show(await api(`/execution/${encodeURIComponent(current.id)}/cancel`,{}));}
  catch(error){feedback.textContent=error.message;}
  finally {busy=false;render();}
};

try {
  options=await api('/execution/options');
  for (const role of ['generation','embedding']) {
    const host=byId('execution-'+role);
    for (const model of options[role]) {
      const label=document.createElement('label');label.className='execution-choice';
      const input=document.createElement('input');input.type='checkbox';input.value=model.id;
      input.checked=model.id==='baseline';input.disabled=!model.available;input.onchange=render;
      label.append(input,document.createTextNode(`${model.label}${model.id==='baseline'?' (기준)':''}${model.available?'':' · 파일 없음'}`));
      host.append(label);
    }
  }
  await refresh();
} catch(error) {feedback.textContent=error.message;render();}
setInterval(async()=>{if(!document.hidden&&!busy)await refresh();},2000);
