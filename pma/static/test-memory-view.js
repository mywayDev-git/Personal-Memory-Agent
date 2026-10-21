const node=(tag,text)=>{const el=document.createElement(tag);if(text!==undefined)el.textContent=text;return el;};

export function inputSourceView(records){
  const host=node('section');host.className='test-source-texts';host.append(node('h3','테스트 기억 원문 · 합성 입력'));
  if(!records.length)host.append(node('p','사전에 입력하는 기록이 없습니다. 저장 요청 대화가 있다면 수행 단계에서 확인할 수 있습니다.'));
  for(const record of records){const box=node('article');box.append(node('h4',`${record.id} · 버전 ${record.version||1} · ${record.owner||'user-a'}`),node('pre',record.text));
    if(record.initial_text&&record.initial_text!==record.text){const previous=node('details');previous.append(node('summary','수정 전 원문'),node('pre',record.initial_text));box.append(previous);}host.append(box);
  }
  return host;
}

export function setupTestMemories(host){
  let loaded=false,loading=null,offset=0,request=0,selection=0;
  const title=node('h2','테스트 원문 데이터'),notice=node('p','검색 검사에 사용하던 합성 문장들을 원문 데이터로 등록했습니다. 테스트는 이 원문을 참조합니다. 개인 기록과 분리된 읽기 전용 보기입니다.');
  const download=node('a','원문 데이터 전체 내려받기');download.href='/api/eval/plan/memories/export';download.setAttribute('download','main-test-source-records.json');
  const form=node('form'),query=node('input'),label=node('label','원문 검색'),search=node('button','찾기'),status=node('p'),list=node('div'),detail=node('section');
  query.type='search';query.placeholder='원문·질문·변수 검색';label.append(query);search.type='submit';form.append(label,search);form.className='dataset-filters';
  list.className='dataset-list';detail.className='dataset-detail';detail.hidden=true;status.setAttribute('role','status');
  const pager=node('div'),previous=node('button','이전'),next=node('button','다음'),count=node('span');previous.type=next.type='button';pager.className='dataset-pagination';pager.append(previous,count,next);
  host.replaceChildren(title,notice,download,form,status,list,pager,detail);
  async function get(path){const response=await fetch('/api/eval/plan/memories'+path,{credentials:'same-origin',cache:'no-store'});if(!response.ok)throw Error('테스트 기억을 불러오지 못했습니다.');return response.json();}
  async function open(id){const ticket=++selection;detail.hidden=false;detail.replaceChildren(node('p','원문을 불러오는 중입니다.'));
    try{const {source:s}=await get('/'+encodeURIComponent(id));if(ticket!==selection)return;const close=node('button','원문 닫기');close.type='button';close.onclick=()=>{selection++;detail.hidden=true;};
      detail.replaceChildren(node('h3',`원문 · 버전 ${s.version}`),close,node('p',`${s.kinds.join(' · ')} · ${s.owner}`),node('pre',s.text));
      const cases=node('details');cases.append(node('summary',`사용하는 검사 조건 ${s.cases.length}개`));
      for(const c of s.cases){const link=node('a',`${c.case_id} · ${c.kind} · ${c.question}`);link.href='/evaluation/datasets?case_id='+encodeURIComponent(c.case_id);const p=node('p');p.append(link);cases.append(p);}detail.append(cases);
      detail.tabIndex=-1;detail.focus({preventScroll:true});detail.scrollIntoView({behavior:'smooth',block:'nearest'});
    }catch(error){if(ticket===selection)detail.replaceChildren(node('p',error.message));}
  }
  async function load(){const ticket=++request;selection++;detail.hidden=true;status.textContent='테스트 원문을 불러오는 중입니다.';
    try{const data=await get('?'+new URLSearchParams({q:query.value,offset:String(offset),limit:'20'}));if(ticket!==request)return;loaded=true;status.textContent=`합성 원문 ${data.inventory_total}개 · 검색 결과 ${data.total}개`;list.replaceChildren();
      for(const source of data.items){const row=node('article'),button=node('button',source.preview);button.type='button';button.className='test-source-open';button.onclick=()=>open(source.id);row.className='dataset-row';row.append(button,node('small',`버전 ${source.version} · ${source.kinds.join(' · ')} · 검사 조건 ${source.case_count}개`));list.append(row);}
      if(!data.items.length)list.append(node('p','해당하는 테스트 원문이 없습니다.'));count.textContent=`${data.total?offset+1:0}–${offset+data.items.length} / ${data.total}`;previous.disabled=offset===0;next.disabled=offset+data.items.length>=data.total;
    }catch(error){if(ticket===request)status.textContent=error.message;}
  }
  form.onsubmit=event=>{event.preventDefault();offset=0;return load();};previous.onclick=()=>{offset=Math.max(0,offset-20);return load();};next.onclick=()=>{offset+=20;return load();};
  return {ensureLoaded(){if(loaded)return Promise.resolve();if(!loading)loading=load().finally(()=>{loading=null;});return loading;}};
}
