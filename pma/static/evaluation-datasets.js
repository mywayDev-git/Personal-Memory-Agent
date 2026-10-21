import {inputSourceView} from './test-memory-view.js';
// Synthetic plan viewing only. No evaluation execution endpoints or polling.
const host=document.getElementById('evaluation-dataset-browser');
const node=(tag,text)=>{const el=document.createElement(tag);if(text!==undefined)el.textContent=text;return el;};
const short=text=>[...String(text??'')].slice(0,90).join('')+([...String(text??'')].length>90?'…':'');
if(host){
  const preview=host.dataset.mode==='preview',params=new URLSearchParams(location.search);
  let offset=preview?0:Math.max(0,Number(params.get('offset'))||0),request=0,detailRequest=0;
  const title=node('h2','전체 테스트 데이터셋'),message=node('p','데이터셋을 불러오는 중입니다.');message.setAttribute('role','status');
  const form=node('form'),query=node('input'),category=node('select'),split=node('select'),profile=node('select');form.className='dataset-filters';
  query.type='search';query.placeholder='질문·예상 답변·기록·변수 검색';query.value=preview?'':params.get('q')||'';
  function field(label,input){const box=node('label',label);box.append(input);form.append(box);}
  function choices(select,items,value){for(const [id,label] of items){const option=node('option',label);option.value=id;select.append(option);}select.value=value||'';}
  choices(category,[['','모든 영역'],...['IN','EX','ST','QI','QU','RT','RR','EV','CV','AG','MW','UI','SEC','PF','LC'].map(c=>[c,c])],params.get('category'));
  choices(split,[['','개발·최종 전체'],['development','개발용'],['final','최종 검증용']],params.get('split'));
  choices(profile,[['','모든 프로필'],['core','핵심 평가'],['compare','모델 비교'],['extended','확장 평가'],['final','최종 검증']],params.get('profile'));
  field('검색',query);field('영역',category);field('데이터 구분',split);field('실행 범위',profile);
  const search=node('button','찾기');search.type='submit';form.append(search);
  const list=node('div'),detail=node('section'),pagination=node('div'),previous=node('button','이전'),next=node('button','다음'),count=node('span');
  list.className='dataset-list';detail.className='dataset-detail';detail.hidden=true;pagination.className='dataset-pagination';
  previous.type=next.type='button';pagination.append(previous,count,next);
  host.replaceChildren(title,message);if(!preview){host.append(form,list,pagination,detail);}else{const toggle=node('details');toggle.append(node('summary','질문·예상 답변 미리보기'),list);host.append(toggle);}
  const all=node('a','전체 데이터셋 보기 →');all.href='/evaluation/datasets';if(preview)host.append(all);
  async function get(path){const response=await fetch('/api/eval/plan/dataset'+path,{credentials:'same-origin',cache:'no-store'});if(!response.ok)throw Error(response.status===401?'메인 화면에서 다시 접속해 주세요.':'데이터셋을 불러오지 못했습니다.');return response.json();}
  function save(caseId){if(preview)return;const p=new URLSearchParams();for(const [key,value] of Object.entries({q:query.value,category:category.value,split:split.value,profile:profile.value,offset:String(offset),case_id:caseId||''}))if(value)p.set(key,value);history.replaceState(null,'','/evaluation/datasets?'+p);}
  async function open(id,focus=true){const ticket=++detailRequest;detail.hidden=false;detail.replaceChildren(node('p','사례를 불러오는 중입니다.'));save(id);
    try{const data=await get('/'+encodeURIComponent(id));if(ticket!==detailRequest)return;const conditions=data.conditions||[data.case];detail.replaceChildren();
      const close=node('button','상세 닫기');close.type='button';close.onclick=()=>{detailRequest++;detail.hidden=true;save();};
      detail.append(node('h2',data.case.question),close,node('p',`같은 질문의 전체 검사 조건 ${conditions.length}개입니다. 조건을 선택하면 해당 입력과 예상 결과를 확인할 수 있습니다.`));
      const choice=node('select'),label=node('label','검사 조건');
      for(const c of conditions){const option=node('option',`${c.id} · ${{normal:'정상',boundary:'경계'}[c.variant]||c.variant} · ${c.split==='final'?'최종 검증':'개발용'}`);option.value=c.id;choice.append(option);}
      choice.value=data.case.id;label.append(choice);detail.append(label);const body=node('div');detail.append(body);
      function showCondition(){const c=conditions.find(c=>c.id===choice.value)||data.case;save(c.id);body.replaceChildren(inputSourceView(c.records));if(c.behavior_contract)body.append(node('p',c.behavior_contract.unsupported?'지원 밖 기능입니다. 실제 거절 동작을 검사하며 기능 구현 통과로 계산하지 않습니다.':'실제 제품 동작 검사입니다. 대체 모델을 사용하는 기능 검사 결과는 모델 정확도에 포함하지 않습니다.'));if(c.behavior_case_ids?.length)body.append(node('p','답변 외 동작 검사: '+c.behavior_case_ids.join(', ')));const archive=node('a','나의 기록에서 테스트 기억 원문 보기 →');archive.href='/?view=test-memories';body.append(archive);
        for(const [label,value] of [['예상 답변·동작',c.expected_answer],['필수 사실',c.required_facts],['금지 사실',c.forbidden_facts],['연결 변수',c.variables],['수행 단계',c.steps],['정답 원문 위치',c.gold_groups],['추가 검증이 필요한 조건',c.coverage_gaps||[]]]){const block=node('section');block.append(node('h3',label),node('pre',typeof value==='string'?value:JSON.stringify(value,null,2)));body.append(block);}
      }
      choice.onchange=showCondition;showCondition();
      detail.append(node('p','실제 답변은 실행 결과에서 확인합니다. 이 화면을 여는 것만으로 테스트가 실행되지 않습니다.'));
      if(focus){detail.tabIndex=-1;detail.focus({preventScroll:true});detail.scrollIntoView({behavior:'smooth',block:'nearest'});}
    }catch(error){if(ticket===detailRequest)detail.replaceChildren(node('p',error.message));}
  }
  async function load(){const ticket=++request;detailRequest++;detail.hidden=true;const p=new URLSearchParams({limit:preview?'5':'20',offset:String(offset),view:'questions'});if(!preview)for(const [key,input] of [['q',query],['category',category],['split',split],['profile',profile]])if(input.value)p.set(key,input.value);
    try{const data=await get('?'+p);if(ticket!==request)return;host.hidden=false;message.textContent=`전체 질문 ${data.inventory_question_total}개 · 검사 조건 ${data.inventory_total}개 · ${preview?'질문 미리보기':`검색 결과 ${data.total}개 질문`}`;list.replaceChildren();
      for(const c of data.items){const row=node('article'),link=node('a',short(c.question));row.className='dataset-row';link.href='/evaluation/datasets?case_id='+encodeURIComponent(c.id);if(!preview)link.onclick=event=>{if(event.ctrlKey||event.metaKey||event.shiftKey||event.altKey)return;event.preventDefault();open(c.id);};row.append(link,node('small',`${c.priority} · ${c.splits.map(s=>s==='final'?'최종 검증':'개발용').join('·')} · 검사 조건 ${c.condition_count}개 · 변수 ${c.variables.length}개`),node('p',c.expected_answers.length===1?'예상: '+short(c.expected_answers[0]):`조건별 예상 답변 ${c.expected_answers.length}종 · 상세에서 확인`));list.append(row);}
      if(!data.items.length)list.append(node('p','조건에 맞는 사례가 없습니다.'));count.textContent=`${data.total?offset+1:0}–${offset+data.items.length} / ${data.total}`;previous.disabled=offset===0;next.disabled=offset+data.items.length>=data.total;
    }catch(error){if(ticket===request){if(preview)host.hidden=true;else message.textContent=error.message;}}
  }
  form.onsubmit=async event=>{event.preventDefault();offset=0;save();await load();};
  previous.onclick=async()=>{offset=Math.max(0,offset-20);save();await load();};next.onclick=async()=>{offset+=20;save();await load();};
  if(preview)window.addEventListener('evaluation-ready',()=>load());
  await load();if(!preview&&request===1&&params.get('case_id'))await open(params.get('case_id'),false);
}
