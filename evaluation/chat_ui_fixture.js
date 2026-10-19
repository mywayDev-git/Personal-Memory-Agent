import {setupChat} from '/static/chat.js';
const $=id=>document.getElementById(id);
const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
const notice=(text)=>{$('notice').hidden=!text;$('notice').textContent=text;};
const action=(text,fn,cls='secondary')=>{const b=node('button',text,cls);b.type='button';b.onclick=async()=>{try{await fn();}catch(e){notice(e.message);}};return b;};
const sessions=new Map();
const scenarios=[
 ['partial','부분 근거','민수와 부산에 언제, 왜 갔어?',['2025년 7월 20일 민수와 부산에 다녀왔습니다.','여행 이유는 기록에서 확인되지 않습니다.']],
 ['conflict','충돌 기록','프로젝트 마감일이 언제야?',['초기 계획에는 11월 15일로 예정되어 있습니다.','변경 메모는 11월 20일을 검토했지만, 확정 여부는 확인되지 않습니다.']],
 ['same_event','동일 사건','민수랑 부산에 간 적 있어?',['네, 2025년 7월 민수와 부산에 다녀온 기록이 두 곳에 있습니다.']],
 ['events','여러 사건','민수랑 언제 만났어?',['2025년 5월 15일 점심을 먹었습니다.','2025년 7월 8일 저녁을 먹었습니다.']],
 ['clarification','확인 질문','민수 만난 날 무슨 이야기 했지?',['2025.05.15 · 점심 식사','2025.07.08 · 저녁 식사']],
];
function message(kind,question,texts,id=crypto.randomUUID()) {
 const evidence=texts.map((text,i)=>({id:'e'+i,record_id:'r'+i,revision_id:'v'+i,version:1,source_text:text,title:'기록 '+(i+1),recorded_at:'2026-10-14T10:00:00Z'}));
 if(kind==='same_event')evidence.push({...evidence[0],id:'e1',record_id:'r1',revision_id:'v1'});
 const items=texts.map((text,i)=>({text,citations:kind==='same_event'?['e0','e1']:['e'+i]}));
 const display={kind,verified:true,items:texts.map((_,i)=>({index:i,state:kind==='partial'&&i===1?'unknown':'confirmed',event:kind==='events'?'event'+i:kind==='same_event'?'trip':'',event_date:kind==='events'?['2025-05-15','2025-07-08'][i]:''}))};
 const presentation=kind==='events'?texts.map((_,i)=>({type:'event_timeline',item_indices:[i],event_date:display.items[i].event_date})):[{type:{partial:'claim_coverage',conflict:'evidence_comparison',same_event:'evidence_group'}[kind]||'text',item_indices:items.map((_,i)=>i)}];
 return {id,question,state:'completed',request_id:id,evidence,response:{status:kind==='clarification'?'needs_clarification':'answered',clarification:kind==='clarification'?'어느 날의 대화를 말씀하시나요?':undefined,items,display:kind==='clarification'?undefined:display,presentation,citation_details:items.flatMap((item,i)=>item.citations.map(cid=>{const e=evidence.find(e=>e.id===cid);return {item_index:i,memory_id:cid,record_id:e.record_id,revision_id:e.revision_id,start:0,end:Array.from(e.source_text).length,quote:e.source_text};}))}};
}
for(const [kind,title,q,texts] of scenarios)sessions.set(kind,{id:kind,title,mode:'auto',messages:[message(kind,q,texts)]});
const sample=sessions.get('partial').messages[0];
sample.evidence[0].search_explanation={query:'민수 부산 여행',methods:['keyword','semantic'],conditions:[{condition:'person',status:'matched',value:['민수']}],keyword_matches:[{term:'민수',kind:'exact',field:'source_text',start:12,end:14,quote:'민수'}],ranks:{keyword:1,semantic:2,combined:1},selection:{status:'selected',reason:'model_selected'}};
const matchStart=Array.from(sample.evidence[0].source_text).join('').indexOf('민수');sample.evidence[0].search_explanation.keyword_matches[0].start=matchStart;sample.evidence[0].search_explanation.keyword_matches[0].end=matchStart+2;
sample.snapshot={searches:[{question:'민수 부산 여행',query_source:'context_or_followup',keywords:['민수','부산'],audit:{candidates:[{id:'e0',record_id:'r0',version:1,status:'selected',reason:'model_selected',methods:['keyword','semantic']},{id:'excluded',record_id:'r2',version:1,status:'excluded',reason:'unknown_filtered_date'}]}}]};
const auditSample=structuredClone(sample);
auditSample.id='audit-message';
auditSample.snapshot.answer_audit={version:1,status:'rejected',attempts:[
 {status:'rejected',reasons:['answer_incomplete'],draft_citations:['e0'],reviewed_citations:[]},
 {status:'rejected',reasons:['claim_unsupported'],draft_citations:['e0'],reviewed_citations:[]}
],usage:[{id:'e0',status:'unused',reason:'answer_rejected'}]};
auditSample.response={status:'insufficient_evidence',items:[],validation:'rejected'};
auditSample.snapshot.searches[0].audit.candidates[0].stages={conditions:{status:'passed'},selection:{status:'selected',reason:'combined_rank',limit:8},answer:{status:'not_run'}};
Object.assign(auditSample.snapshot.searches[0].audit.candidates[1],{
 conditions:[{condition:'time',status:'failed',expected:{start:'2026-01-01',end:'2026-12-31'},reason:'unknown_filtered_date'}],
 stages:{conditions:{status:'failed',reason:'unknown_filtered_date'},selection:{status:'not_run'},answer:{status:'not_run'}}
});
sessions.set('audit',{id:'audit',title:'검색 사유',mode:'auto',messages:[auditSample]});
sessions.set('long',{id:'long',title:'긴 대화',mode:'auto',messages:Array.from({length:24},(_,i)=>message('plain','질문 '+i,['답변 '+i+' · 이전 메시지를 읽을 때 스크롤 위치가 유지됩니다.']))});
sessions.set('running',{id:'running',title:'진행 중인 대화',mode:'auto',messages:[{id:'running1',request_id:'running1',question:'진행 중인 요청',state:'running'}]});
let polls=0;
async function api(path,method='GET',data){
 const parts=path.split('/'); const sid=parts[3]; const session=sessions.get(sid);
 if(path.startsWith('/chat/sessions?')||path==='/chat/sessions') {
  if(method==='POST'){const id=crypto.randomUUID();const s={id,title:'새 대화',mode:'auto',messages:[]};sessions.set(id,s);return structuredClone(s);}
  const q=new URLSearchParams(path.split('?')[1]).get('q')||'';
  return {items:[...sessions.values()].filter(s=>s.title.includes(q))};
 }
 if(parts[4]==='requests') {
  const m=session.messages.find(m=>m.request_id===parts[5]);
  if(method==='POST'){m.state='failed';m.error_code='CANCELLED';}
  else if(sid==='running'&&++polls>=2&&m.state==='running')Object.assign(m,message('plain',m.question,['자동으로 완료된 답변입니다.'],m.id));
  return {state:m.state,phase:'generating'};
 }
 if(parts[4]==='messages') {
  const existing=session.messages.find(m=>m.request_id===data.request_id);
  const m=existing||{id:crypto.randomUUID(),request_id:data.request_id,question:data.question};
  m.state='running';delete m.error_code;if(!existing)session.messages.push(m);
  await new Promise(resolve=>setTimeout(resolve,1800));
  if(m.state==='failed')throw Error('중단되었습니다.');
  if(data.question==='실패'&&!existing){m.state='failed';throw Error('연결 실패 테스트');}
  Object.assign(m,message('plain',data.question,['후속 답변입니다.'],m.id));m.request_id=data.request_id;
  return {message_id:m.id};
 }
 if(session)return structuredClone(session);
 if(path==='/memory')return {items:[]};
 throw Error('Fixture does not support '+path);
}
setupChat({api,node,action,notice,today:()=> '2026-10-18'});
for(const el of document.querySelectorAll('.tab'))el.hidden=el.id!=='chat';
document.querySelector('[data-tab="chat"]').click();
