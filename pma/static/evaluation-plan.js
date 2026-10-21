// Static plan viewing; execution lives in the explicit-action module.
const host = document.getElementById('main-test-plan');
const node = (tag, text) => { const n = document.createElement(tag); n.textContent = text; return n; };
try {
  const response = await fetch('/api/eval/plan', {credentials: 'same-origin'});
  if (!response.ok) throw new Error('메인 테스트 계획을 불러오지 못했습니다.');
  const plan = await response.json();
  host.replaceChildren(node('h2', plan.title), node('p', plan.policy),
    node('p', `${plan.threshold_status} · 기준 시각 ${plan.reference_time}`),
    node('p', `변수 ${plan.variables.length}개 · 사례 ${plan.scenario_count}개 · 자동 실행 ${plan.automated_scenario_count}개 · 답변 외 조건 미검증 ${plan.partial_coverage_scenario_count||0}개`),
    node('p', `등록된 동작 조건 검사: 변수 ${plan.fully_covered_variable_count||0}개 · 답변만 연결: 변수 ${plan.answer_only_variable_count||0}개. 자동 실행 수는 전체 기능 검증 완료 수가 아닙니다.`),
    node('p', `추가 실제 동작 검사 ${plan.behavior_contract_variable_count||0}개 변수 · 지원 밖 기능의 거절 검사 ${plan.unsupported_behavior_variable_count||0}개 변수. 실행 결과와 제품 지원 여부는 별도입니다.`),
    node('p', `동일 질문·동일 실행 조건의 중복 ${plan.consolidated_duplicate_count||0}개를 통합했습니다. 같은 질문이어도 검사 조건이 다르면 별도 사례입니다.`),
    node('p', plan.coverage_note));
  const profiles = node('ul', '');
  for (const [name, spec] of Object.entries(plan.profiles)) profiles.append(node('li', `${name}: ${spec.label} · ${spec.repeats}회 · ${spec.split === 'final' ? '최종 검증용' : '개발용'}`));
  host.append(profiles, node('p', '“메인 테스트 실행”은 현재 조합의 핵심 평가입니다. 모델 비교·확장·최종 검증은 별도 요청합니다. 아래 표는 전체 카탈로그이며, 실행 전 상태는 미실행입니다.'));
  const details = document.createElement('details');
  details.append(node('summary', '전체 변수·지원 현황 보기'));
  const category = document.createElement('select'); category.setAttribute('aria-label', '테스트 영역');
  category.append(new Option('모든 영역', ''));
  for (const name of plan.categories) category.append(new Option(name, name));
  const priority = document.createElement('select'); priority.setAttribute('aria-label', '우선순위');
  for (const name of ['', 'P0', 'P1', 'P2']) priority.append(new Option(name || '모든 우선순위', name));
  const table = document.createElement('table');
  const head = document.createElement('thead'); const row = document.createElement('tr');
  for (const title of ['변수', '검증 내용', '우선순위', '구현 현황', '판정 방식', '등록 시 상태']) row.append(node('th', title));
  head.append(row); const body = document.createElement('tbody'); table.append(head, body);
  const statuses = {IMPLEMENTED:'구현됨',PARTIAL:'일부 구현·검증 필요',MISSING:'미구현',BROKEN:'고장',UNKNOWN:'미확인'};
  function render() {
    body.replaceChildren();
    for (const item of plan.variables.filter(v => (!category.value || v.category === category.value) && (!priority.value || v.priority === priority.value))) {
      const tr = document.createElement('tr');
      tr.title=item.automation_note||'';
      for (const text of [item.variable_id, item.description, item.priority, statuses[item.implementation_status], ({executable_behavior_contract:'실제 제품 동작 검사',automatic_answer_comparison:'실제 답변 자동 비교',source_and_behavior_review:'원문·동작 검토'})[item.oracle_type]||item.oracle_type, '미실행']) tr.append(node('td', text));
      const preview=document.createElement('details');preview.className='plan-case-preview';
      preview.append(node('summary','질문·예상 답변 보기'));
      let loading=false,loaded=false;
      preview.ontoggle=async()=>{
        if(!preview.open||loading||loaded)return;
        loading=true;const content=node('div','불러오는 중입니다.');preview.append(content);
        try{
          const response=await fetch('/api/eval/plan/cases/'+encodeURIComponent(item.variable_id),{credentials:'same-origin'});
          if(!response.ok)throw new Error('등록된 사례를 불러오지 못했습니다.');
          const data=await response.json();content.replaceChildren(node('p','합성 테스트 사례입니다. 실제 답변은 테스트 실행 후 결과 목록에서 확인할 수 있습니다.'));
          for(const group of data.question_groups){const box=node('section','');
            box.append(node('h3','질문'),node('pre',group.question));
            const answers=group.expected_answers.filter(Boolean);if(answers.length===1)box.append(node('h3','예상 답변·동작'),node('pre',answers[0]));
            const conditions=document.createElement('details');conditions.append(node('summary',`검사 조건 ${group.conditions.length}개 보기`));
            for(const example of group.conditions){const entry=node('section','');
              const variants=(example.variable_variants?.[item.variable_id]||[example.variant]).map(v=>({normal:'정상',boundary:'경계'})[v]||v).join('·');
              entry.append(node('strong',`${example.id} · ${variants} · ${example.split==='final'?'최종 검증용':'개발용'}`));
              if(answers.length!==1)entry.append(node('pre',example.expected_answer));
              for(const gap of example.coverage_gaps||[])entry.append(node('p',gap));
              conditions.append(entry);
            }
            box.append(conditions);content.append(box);
          }
          loaded=true;
        }catch(error){content.textContent=error.message;}finally{loading=false;}
      };
      tr.children[1].append(preview);
      body.append(tr);
    }
  }
  category.onchange = priority.onchange = render; render();
  const wrap = document.createElement('div'); wrap.className='table-wrap'; wrap.append(table);
  details.append(category, priority, wrap); host.append(details);
} catch (error) { host.textContent = error.message; }

const select = document.getElementById('comparison-mode');
if (select) select.onchange = () => document.getElementById('comparison-data').replaceChildren();
