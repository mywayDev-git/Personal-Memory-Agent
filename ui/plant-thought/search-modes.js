'use strict';
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.PlantSearchModes=api;})(typeof window==='object'?window:globalThis,()=>{
 const modes=[
  {id:'legacy',label:'기존 · 간단한 키워드',description:'현재 대화의 단어 일치 검색과 비교합니다.'},
  {id:'R0',label:'R0 · 원문 청크',route:'R0',description:'원문 청크의 키워드·벡터 검색 결과를 결합합니다.'},
  {id:'R0-Full',label:'R0-Full · 원문 전체',route:'R0-Full',description:'검색 없이 전체 원문을 제공합니다. 입력 한도를 넘으면 중단합니다.'},
  {id:'S0',label:'S0 · 구조화',route:'S0',description:'사실·관계를 구조화한 단위로 검색합니다.'},
  {id:'H1',label:'H1 · 원문 + 구조화',route:'H1',description:'원문과 구조화 단위를 함께 검색합니다.'},
  {id:'M0',label:'M0 · 요약 검색',route:'M0',description:'요약으로 기록을 찾습니다. 사색 대화의 답변 근거는 선택된 원문에서 확인합니다.'},
  {id:'M1',label:'M1 · 구조화 요약',route:'M1',description:'요약의 검색어·개체·관계로 기록을 찾고 원문을 확인합니다.'},
  {id:'M1-extractive',label:'M1 · 원문 발췌·키워드',route:'M1',summary_mode:'extractive-v1',description:'원문 발췌와 키워드·개체·관계로 검색합니다.'},
  {id:'G1',label:'G1 · 사건 그래프',route:'G1',description:'원문별 사건 그래프로 검색합니다.'},
  {id:'G1-linked',label:'G1 · 사건 연결·근거 확인',route:'G1',event_graph_mode:'linked-v2',description:'원문 간 사건 연결을 근거로 확인한 그래프에서 검색합니다.'},
  {id:'G1-claim',label:'G1 · 사건 → Claim → 근거',route:'G1',event_graph_mode:'claim-v1',description:'사건과 주장·계획·실행의 근거를 검색합니다.'},
  {id:'G2',label:'G2 · 다중 대상·사실',route:'G2',description:'여러 대상과 독립적인 사실을 함께 검색합니다.'},
  {id:'K1',label:'K1 · 원문 키워드·조건',route:'K1',description:'원문 구간에 키워드 증강과 조건 필터를 적용합니다.'},
  {id:'A1',label:'A1 · 질문별 근거 선택',route:'A1',description:'LLM이 질문과 후보 원문을 읽고 근거의 관련성과 역할을 판단합니다.'}
 ].map(Object.freeze);
 const get=id=>modes.find(mode=>mode.id===id);
 function normalize(id){if(id==null)return 'legacy';if(typeof id!=='string'||!get(id))throw Error('지원하지 않는 검색 방식입니다.');return id;}
 function describe(submission={},result,status='success'){
  const traces=(result?.parts?result.parts.map(p=>p.result?.retrieval_trace):[result?.retrieval_trace]).filter(Boolean);
  if(traces.length&&traces.every(t=>t.status==='skipped'))return {label:'기록 검색 없음',title:'이 응답에서는 기록 검색을 실행하지 않았습니다.'};
  const used=traces.filter(t=>t.status!=='skipped'),ids=[...new Set(used.map(t=>t.mode).filter(Boolean))];
  if(ids.length){const labels=ids.map(id=>get(id)?.label||'알 수 없는 검색 방식'),failed=used.some(t=>t.status==='failed');return {label:labels.join(' / ')+(failed?' · 검색 실패':''),title:failed?'기록 검색 과정에서 실패한 단계가 있습니다.':'이 답변에 사용한 기록 검색 방식입니다.'};}
  const selected=get(submission.search_mode);
  if(selected)return {label:selected.label+(status==='pending'?' · 선택':status==='error'||status==='cancelled'?' · 미완료':' · 선택값'),title:'질문을 보낼 때 선택한 방식입니다. 실제 검색 실행 정보는 아직 없거나 저장되지 않았습니다.'};
  return {label:status==='pending'?'기록 검색 확인 중':'검색 방식 미기록',title:'이 답변에 저장된 검색 방식 정보가 없습니다.'};
 }
 return Object.freeze({modes:Object.freeze(modes),get,normalize,describe});
});
