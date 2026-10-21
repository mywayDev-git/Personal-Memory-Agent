// Compact case summaries; full content is fetched only for the selected case.
const node=(tag,text,cls)=>{const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(cls)el.className=cls;return el;};
const valueText=value=>typeof value==='string'?value:JSON.stringify(value,null,2);
const actions={contract_tests:'제품 동작 검사',chat:'대화 질문',search:'기록 검색',delete:'기록 삭제',update:'기록 수정',restore:'기록 복원',new_session:'새 대화',capture:'기억 저장',assert_no_capture:'비저장 검사',owner_probe:'사용자 범위 검사',import_probe:'문서 가져오기'};
export function shorten(value,limit=88){const text=String(value??'').replace(/\s+/g,' ').trim();return [...text].length>limit?[...text].slice(0,limit).join('')+'…':text;}
export function answerText(value){if(value==null)return null;if(typeof value!=='string')return valueText(value);try{const parsed=JSON.parse(value);if(Array.isArray(parsed))return parsed.length?parsed.map(valueText).join('\n'):null;}catch{}return value;}
export function answerState(data){
  const scenario=data.metadata?.scenario,evaluation=data.evaluation||{};
  if(scenario?.adapter==='review')return {
    notice:'이전 버전의 수동 검토 결과입니다. 새 테스트를 실행하면 등록된 질문·예상 답변으로 실제 응답을 수집합니다. 기존 결과는 보존됩니다.',
    expected:scenario.review_checklist?.length?scenario.review_checklist.join('\n'):'검토 기준이 등록되지 않았습니다.',
    actual:'자동 실행 대상이 아니므로 모델 답변이 생성되지 않았습니다. 예상·실제 동작 탭에서 검토 항목을 확인하세요.',
    manual:true,
  };
  const steps=scenario?.steps||[],nonAnswer=steps.length&&!steps.some(step=>step.action==='chat');
  const verdict=String(data.suite_verdict||data.verdict||'').toUpperCase();
  let actual='응답 기록이 없습니다. 처리 과정 탭에서 수집 상태를 확인하세요.';
  if(nonAnswer)actual='답변 생성 대신 동작을 검사하는 사례입니다. 예상·실제 동작 탭에서 처리 결과를 확인하세요.';
  if(['NOT_RUN','NOT_APPLICABLE','SKIP','UNSUPPORTED'].includes(verdict))actual='실행되지 않았거나 실행 대상에서 제외되었습니다. 판정·실패 사유를 확인하세요.';
  if(verdict==='ERROR')actual='실행 중 오류가 기록되었습니다. 예상·실제 동작 탭에서 실패 사유를 확인하세요.';
  return {notice:'',manual:false,expected:answerText(data.expected_answer)||answerText(scenario?.required_facts)||
    (nonAnswer?'문장 정답 대신 동작과 상태를 검증합니다. 예상·실제 동작 탭에서 기준을 확인하세요.':
      data.expected_behavior==='clarify'?'필요한 정보를 되물어야 합니다. 고정된 답변 문장은 없습니다.':
      data.expected_behavior==='abstain'?'근거 부족으로 답변을 보류해야 합니다. 고정된 답변 문장은 없습니다.':
      '필수 사실 정답이 등록되지 않았습니다. 이 상태로 답변 정확도를 확정할 수 없습니다.'),actual};
}

export function caseRow(result,{runId,selectedId,select,labels,failureNames}){
  const row=node('tr',undefined,'case-row');row.dataset.caseId=result.case_id;
  if(result.case_id===selectedId)row.classList.add('is-selected');
  const first=node('td');
  const link=node('a',result.case_id,'case-select');
  link.href=`/evaluation/cases?run_id=${encodeURIComponent(runId)}&case_id=${encodeURIComponent(result.case_id)}`;
  link.setAttribute('aria-label',`${result.case_id} 상세 보기`);
  if(result.case_id===selectedId)link.setAttribute('aria-current','true');
  link.onclick=event=>{if(event.button&&event.button!==0||event.ctrlKey||event.metaKey||event.shiftKey||event.altKey)return;event.preventDefault();select(result.case_id);};
  first.append(link,node('span',shorten(result.question_preview??result.question??'질문 원문 숨김'),'case-question'));
  const badge=node('td');badge.append(node('span',labels[result.suite_verdict||result.verdict]||result.verdict,'badge '+result.verdict));
  const expected=node('td');expected.append(node('span',labels[result.expected_behavior]||result.expected_behavior||'미정','case-behavior'));
  expected.append(node('span',shorten(result.expected_preview??answerText(result.expected_answer)??'예상 답변 미정',56),'case-preview'));
  const actual=node('td');actual.append(node('span',result.measurement_type==='functional'?'제품 동작 검사':labels[result.response_behavior]||'미관측','case-behavior'));
  actual.append(node('span',shorten(result.actual_preview??result.actual_answer??'답변 미수집',56),'case-preview'));
  if(result.error_type)actual.append(node('span',shorten(failureNames[result.error_type]||result.error_type,42),'case-error'));
  const time=node('td',result.latency_ms==null?'—':`${Math.round(result.latency_ms)} ms`,'case-time');
  row.append(first,badge,expected,actual,time);
  row.onclick=event=>{if(event.target.closest?.('a,button,input,select'))return;select(result.case_id);};
  return row;
}

export class CaseInspector {
  constructor({api,labels,failureNames,stageNames,gradeNames}){
    Object.assign(this,{api,labels,failureNames,stageNames,gradeNames});
    this.tab='answer';this.key='';this.data=null;this.request=0;this.traceRequest=0;
    this.tabs=[...document.querySelectorAll('[data-case-tab]')];
    for(const tab of this.tabs){
      tab.onclick=()=>this.setTab(tab.dataset.caseTab);
      tab.onkeydown=event=>{const index=this.tabs.indexOf(tab);let next;
        if(event.key==='ArrowRight')next=(index+1)%this.tabs.length;
        if(event.key==='ArrowLeft')next=(index+this.tabs.length-1)%this.tabs.length;
        if(event.key==='Home')next=0;if(event.key==='End')next=this.tabs.length-1;
        if(next!==undefined){event.preventDefault();this.tabs[next].focus();this.setTab(this.tabs[next].dataset.caseTab);}
      };
    }
  }
  get(id){return document.getElementById(id);}
  clear(){
    this.key='';this.data=null;this.request++;this.traceRequest++;this.traceKey='';
    this.get('inspector').hidden=true;
    for(const id of ['answer-detail','behavior-detail','evidence','trace','case-summary','case-detail-notice'])this.get(id).replaceChildren();
  }
  setTab(name){
    this.tab=name;
    for(const tab of this.tabs){const selected=tab.dataset.caseTab===name;tab.setAttribute('aria-selected',String(selected));tab.tabIndex=selected?0:-1;this.get(tab.getAttribute('aria-controls')).hidden=!selected;}
    if(name==='trace'&&this.data)this.loadTrace();
  }
  async open(runId,caseId,{refresh=false,focus=false}={}){
    const key=JSON.stringify([runId,caseId]);
    if(this.key===key&&this.data&&!refresh){this.get('inspector').hidden=false;if(focus)this.focus();return;}
    if(this.key!==key){this.clear();this.key=key;this.get('answer-detail').append(node('p','상세 정보를 불러오는 중입니다.'));}
    this.get('inspector').hidden=false;
    this.get('inspector-title').textContent=`사례 상세 · ${caseId}`;
    this.setTab(this.tab);
    const ticket=++this.request;
    try{
      const data=await this.api(`/runs/${encodeURIComponent(runId)}/cases/${encodeURIComponent(caseId)}`);
      if(ticket!==this.request||key!==this.key)return;
      this.data=data;this.traceKey='';this.traceRequest++;this.render(data);this.setTab(this.tab);
      if(focus)this.focus();
    }catch(error){if(ticket===this.request&&key===this.key){this.get('case-detail-notice').textContent=error.message;this.get('answer-detail').replaceChildren(node('p','이 사례의 상세 정보를 불러오지 못했습니다.'));}}
  }
  focus(){this.get('inspector-title').focus({preventScroll:true});this.get('inspector').scrollIntoView({behavior:'smooth',block:'nearest'});}
  field(host,label,value,empty='기록되지 않음'){
    const section=node('section',undefined,'case-field');section.append(node('h3',label),node('pre',value==null||value===''?empty:valueText(value),'case-full-text'));host.append(section);
  }
  render(data){
    const {labels,failureNames}=this;
    const summary=this.get('case-summary');summary.replaceChildren(node('span',labels[data.suite_verdict||data.verdict]||data.verdict,'badge '+data.verdict),
      node('span',data.evaluation?.probe?'기대 조건 → 실제 제품 동작 검사':`예상 ${labels[data.expected_behavior]||data.expected_behavior||'미정'} → 실제 ${labels[data.response_behavior]||'미관측'}`),
      node('span',data.latency_ms==null?'응답 시간 미수집':`${Math.round(data.latency_ms)} ms`));
    const state=answerState(data);
    const notice=this.get('case-detail-notice');notice.textContent=data.text_masked?'원문 상세 조회가 꺼져 있습니다. 목록 위의 ‘질문·답변 원문 표시’를 선택하면 원문을 확인할 수 있습니다.':state.notice;
    const answer=this.get('answer-detail');answer.replaceChildren();
    const hidden=data.text_masked?'상세 조회 허용 시 표시됩니다.':undefined;
    this.field(answer,'질문 원문',data.question,hidden||'질문이 기록되지 않았습니다.');
    this.field(answer,state.manual?'예상 동작·수동 검토 기준':'예상 답변·필수 사실',data.text_masked?null:state.expected,hidden);
    this.field(answer,'실제 답변',data.actual_answer||(!data.text_masked&&data.evaluation?.observation?.response?.notice),hidden||state.actual);
    const scenario=data.metadata?.scenario,evaluation=data.evaluation||{},observation=evaluation.observation;
    if(scenario?.variables?.length>1){const shared=node('details');shared.append(node('summary',`함께 검사하는 변수 ${scenario.variables.length}개`),node('p',scenario.variables.join(', ')));answer.append(shared);}
    const comparison=evaluation.answer_comparison;
    if(!data.text_masked){
      const gaps=comparison?.coverage_gaps||scenario?.coverage_gaps||[];
      if(gaps.length){answer.append(node('h3',scenario?.behavior_case_ids?.length?'이 답변 사례의 범위 · 추가 동작은 별도 검사':'자동 검증 범위'));for(const gap of gaps)answer.append(node('p',scenario?.behavior_case_ids?.length?gap.replace('원본 변수 전체 조건의 자동 검증은 미완료: ','별도 동작 검사 대상: '):gap,'case-scope-note'));}
      if(scenario?.behavior_case_ids?.length)this.field(answer,'연결된 실제 동작 검사',scenario.behavior_case_ids.join('\n'));
      if(comparison){
        this.field(answer,'자동 비교 결과',({EXACT_MATCH:comparison.method==='product_contract'?'기대 동작과 일치':'예상 답변과 일치',MISMATCH:'기대 동작과 불일치',NO_ANSWER:'답변 없음',EXECUTION_ERROR:'실행 오류 · 답변 비교 불가',REVIEW_REQUIRED:'표현 또는 의미 차이 · 추가 검토 필요'})[comparison.status]||comparison.status);
        for(const item of comparison.required_facts||[])answer.append(node('p',`${item.status==='MATCH'?'일치':'누락'} · 필수 사실: ${item.fact}`));
        for(const item of comparison.forbidden_facts||[])answer.append(node('p',`${item.status==='MENTIONED'?'언급됨 · 문맥 확인 필요':'미언급'} · 금지 사실: ${item.fact}`));
        answer.append(node('small',comparison.note));
      }else if(scenario?.expected_answer)answer.append(node('p','이전 실행에는 자동 비교 결과가 없습니다. 새로 실행하면 수집됩니다.'));
    }
    const behavior=this.get('behavior-detail');behavior.replaceChildren();
    this.field(behavior,'예상 동작',labels[data.expected_behavior]||data.expected_behavior);
    this.field(behavior,'실제 동작',labels[data.response_behavior]||data.response_behavior,'실제 동작이 관측되지 않았습니다.');
    this.field(behavior,'판정·실패 사유',data.error_type?failureNames[data.error_type]||data.error_type:
      evaluation.review_reason||((data.verdict==='pending_review')?'추가 검토가 필요합니다.':'별도 실패 사유가 기록되지 않았습니다.'));
    if(evaluation.failure)this.field(behavior,'오류 발생 단계와 진단',evaluation.failure);
    if(evaluation.probe?.checks){
      const probe=evaluation.probe;
      this.field(behavior,'검사 방식','합성 DB·실제 제품 코드·대체 모델을 사용하는 기능 검사입니다. 모델 정확도에서는 제외합니다.');
      if(probe.unsupported)this.field(behavior,'제품 지원 범위','지원 밖 기능입니다. 거절 동작을 검사했으며 기능 구현 완료로 계산하지 않습니다.');
      this.field(behavior,'기대 동작',probe.expected_checks?.join('\n'));
      this.field(behavior,'실제 검사 결과',`통과 ${probe.checks.filter(c=>c===true||c?.outcome==='passed').length} / ${probe.checks.length}개`);
      const checks=node('details');checks.append(node('summary','검사별 실행 기록'));
      for(const [index,check] of probe.checks.entries())checks.append(node('p',`${check===true||check?.outcome==='passed'?'통과':check?.outcome==='skipped'?'미실행':'실패'} · ${check?.id||`내부 범위 검사 ${index+1}`}`));
      behavior.append(checks);
    }
    if(evaluation.behavior_review_required)behavior.append(node('p','응답 상태만으로 답변 보류·되물음을 판정할 수 없어 문장 검토가 필요합니다.'));
    for(const turn of data.text_masked?[]:evaluation.turn_contracts||[]){
      const box=node('details');box.append(node('summary',`${turn.step+1}번째 단계: ${turn.passed?'기대 조건 충족':'기대 조건 미충족'}`));
      this.field(box,'예상 조건',turn.expected);this.field(box,'실제 답변',turn.actual_answer);
      if(turn.missing_facts?.length)this.field(box,'누락 사실',turn.missing_facts.join(', '));
      if(turn.forbidden_mentions?.length)this.field(box,'금지 결과',turn.forbidden_mentions.join(', '));behavior.append(box);
    }
    for(const [key,label] of Object.entries(this.gradeNames))behavior.append(node('p',`${label}: ${evaluation[key]===true?'충족':evaluation[key]===false?'미충족':'미관측 / 검토 대기'}`));
    if(scenario?.steps?.length){behavior.append(node('h3','예상 수행 단계'));for(const [index,step] of scenario.steps.entries()){
      const box=node('section',undefined,'case-step');box.append(node('strong',`${index+1}. ${actions[step.action]||step.action}`));
      if(step.question)this.field(box,'질문',step.question);if(step.text)this.field(box,'입력',step.text);if(step.record)this.field(box,'대상 기록',step.record);if(step.filters)this.field(box,'검색 조건',step.filters);behavior.append(box);
    }}
    if(observation?.steps?.length){behavior.append(node('h3','실제로 기록된 단계'));for(const [index,step] of observation.steps.entries()){
      const box=node('section',undefined,'case-step');box.append(node('strong',`${index+1}. ${actions[step.action]||step.action}`));
      if(step.latency_ms!=null)box.append(node('small',`${Math.round(step.latency_ms)} ms`));
      if(['chat','search'].includes(step.action)){
        const response=step.response||{};const text=[response.clarification,response.items?.map(item=>item.text).join('\n')||response.answer||response.notice].filter(Boolean).join('\n');
        this.field(box,'처리 상태',labels[response.status]||({answered:'답변',needs_clarification:'되물음',insufficient_evidence:'근거 부족'}[response.status])||response.status);
        if(step.action==='search'&&Array.isArray(response.results))this.field(box,'검색 결과',response.results.map((item,index)=>`${index+1}. ${item.content||item.text||item.id}`).join('\n'),'검색 결과가 없습니다.');
        else this.field(box,'응답',text);
      }else box.append(node('p','동작 완료 단계가 기록되었습니다.'));
      behavior.append(box);
    }}else behavior.append(node('p',data.text_masked?'상세 조회 허용 시 단계 기록을 확인할 수 있습니다.':'단계별 동작은 수집되지 않았습니다.'));
    if(evaluation.review_checklist?.length){behavior.append(node('h3','검토 항목'));for(const item of evaluation.review_checklist)behavior.append(node('p',item));}
    const evidence=this.get('evidence');evidence.replaceChildren();
    const groups=scenario?.gold_groups||data.gold_groups||{};
    if(!Object.keys(groups).length)evidence.append(node('p',data.text_masked?'상세 조회 허용 시 근거를 확인할 수 있습니다.':'필수 근거가 정의되지 않았습니다.'));
    for(const [group,refs] of Object.entries(groups)){
      evidence.append(node('h3',group));for(const ref of refs){
        if(typeof ref==='string')evidence.append(node('p',ref));
        else evidence.append(node('p',`${ref.record_id} · 버전 ${ref.version} · 문자 ${ref.start}–${ref.end}`),node('blockquote',ref.quote));
      }
    }
    for(const [id,source] of Object.entries(observation?.sources||{})){
      const box=node('details');box.id='source-'+id;box.append(node('summary',`원문 ${source.logical_id} · 버전 ${source.version} · ${{active:'사용 중',trash:'휴지통'}[source.state]||'상태 미기록'}`),node('pre',source.text));evidence.append(box);
    }
    for(const ref of observation?.response?.citation_details||[]){const link=node('a',`인용 원문 · 문자 ${ref.start}–${ref.end}`);link.href='#source-'+ref.record_id;
      link.onclick=()=>{const target=document.getElementById('source-'+ref.record_id);if(target)target.open=true;};evidence.append(link,node('blockquote',ref.quote));}
    if(data.claims?.length){evidence.append(node('h3','주장별 근거'));for(const claim of data.claims)evidence.append(node('p',`${claim.claim_text} · ${{supported:'근거 확인',unsupported:'근거 부족',uncertain:'검토 대기'}[claim.support_status]||'미확인'}`));}
    const diagnostic=node('details',undefined,'case-diagnostic');diagnostic.append(node('summary','재현 정보'));
    if(evaluation.reproduce)this.field(diagnostic,'재현 명령',evaluation.reproduce);
    if(evaluation.observation_hash)this.field(diagnostic,'검토 대상 해시',evaluation.observation_hash);
    if(evaluation.reproduce||evaluation.observation_hash)behavior.append(diagnostic);
  }
  async loadTrace(){
    const key=this.key;if(this.traceKey===key)return;
    this.traceKey=key;const ticket=++this.traceRequest;
    const host=this.get('trace');host.replaceChildren(node('p','처리 과정을 불러오는 중입니다.'));
    if(this.data.text_masked){host.replaceChildren(node('p','상세 조회 허용 시 처리 과정을 확인할 수 있습니다.'));return;}
    const [runId,caseId]=JSON.parse(key);
    try{
      const trace=await this.api(`/runs/${encodeURIComponent(runId)}/cases/${encodeURIComponent(caseId)}/trace`);
      if(ticket!==this.traceRequest||key!==this.key)return;
      host.replaceChildren(node('p',`수집 상태: ${{partial:'일부 수집',complete:'완료',truncated:'수집 상한 도달',not_instrumented:'수집되지 않음'}[trace.trace_status]||trace.trace_status}`));
      if(trace.diagnosis?.error_type&&trace.diagnosis.error_type!=='unknown')host.append(node('p',this.failureNames[trace.diagnosis.error_type]||trace.diagnosis.error_type));
      if(!trace.stages?.length)host.append(node('p','수집된 처리 단계가 없습니다.'));
      for(const event of trace.stages||[]){const box=node('details',undefined,'stage');box.append(node('summary',this.stageNames[event.stage]||event.stage));
        if(event.candidates)for(const candidate of event.candidates)box.append(node('p',`${candidate.rank??'—'}위 · ${candidate.id}${typeof candidate.score==='number'&&Number.isFinite(candidate.score)?' · 점수 '+candidate.score.toFixed(4):''}`));
        if(event.ids||event.selected_ids)box.append(node('p',(event.ids||event.selected_ids).join(', ')||'선택 근거 없음'));
        if(event.supported!==undefined)box.append(node('p',event.supported?'근거 검증 통과':'근거 검증 실패'));
        this.field(box,'수집한 상세 정보',event);host.append(box);
      }
      host.append(node('small','수집되지 않은 단계와 실패 원인은 추정하지 않습니다.'));
    }catch(error){if(ticket===this.traceRequest&&key===this.key){this.traceKey='';host.replaceChildren(node('p',error.message));}}
  }
}
