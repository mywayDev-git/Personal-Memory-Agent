'use strict';
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const spec=require('./대화기억_UX_테스트사례.json');
const base='http://127.0.0.1:4321/api/baseline';
const output=path.join(__dirname,'all-test-records-load-report.json');
const report={started_at:new Date().toISOString(),status:'running',mode:'combined-browsable-synthetic-records',notes:[
 '사용자 요청으로 모든 가상 원문을 한 보관소에 함께 저장합니다. 사례별 독립 평가 실행과는 다릅니다.',
 '삭제·권한 회수 원문도 가상 자료로 열람 가능하게 저장합니다. 실제 삭제·권한·오류·시각 조건은 재현하지 않습니다.',
 '사용자 질문, 앞 대화, 예상 답변은 저장 원문에 섞지 않습니다. 같은 날짜·본문은 한 번만 저장합니다.'
],records:[]};
const unique=new Map();
function add(date,body,caseId,title,access='allowed'){
 const signature=JSON.stringify([date,body]);
 let record=unique.get(signature);
 if(!record){record={date,body,case_ids:[],titles:[],fixture_access:[]};unique.set(signature,record);}
 if(!record.case_ids.includes(caseId))record.case_ids.push(caseId);
 if(!record.titles.includes(title))record.titles.push(title);
 if(!record.fixture_access.includes(access))record.fixture_access.push(access);
}
for(const c of spec.cases)for(const r of c.records)add(r.date,r.text,c.id,c.title,r.access);
add('2026-11-11','회사 동료 민수와 강남 카페에 갔다.','EX01','동명이인 예시 · 회사 동료 민수');
add('2026-11-12','대학 친구 민수와 부산에 갔다.','EX02','동명이인 예시 · 대학 친구 민수');
const save=()=>fs.writeFileSync(output,JSON.stringify(report,null,2));
async function get(route){
 const r=await fetch(base+route,{signal:AbortSignal.timeout(20000)}),v=await r.json();
 if(!r.ok)throw Error(v.error||'조회 실패 '+r.status);return v;
}
async function originals(){
 const list=(await get('/summary-memory')).memories,result=[];
 for(const row of list){const {source}=await get('/summary-memory/original?key='+row.memory_key);result.push({row,text:source.text});}
 return result;
}
function parse(text){
 const title=text.match(/^제목: ([^\r\n]+)/)?.[1];
 const date=text.match(/^기록일: (\d{4}-\d{2}-\d{2})$/m)?.[1];
 const split=text.indexOf('\n\n');return {title,date,body:split>=0?text.slice(split+2):text};
}
function signatureOf(text){const {date,body}=parse(text);return JSON.stringify([date,body]);}
async function main(){
 let boot=await get('/bootstrap');
 if(boot.busy||boot.setup?.status==='RUNNING')throw Error('진행 중인 처리가 있어 데이터 추가를 시작하지 않았습니다.');
 const present=boot.runtime.models.filter(m=>m.role==='generation'&&m.present);
 const model=(present.find(m=>m.default)||present[0])?.id;if(!model)throw Error('설치된 생성 모델 없음');
 const before=await originals();
 report.existing_count=before.length;report.unique_fixture_count=unique.size;
 report.original_records=before.map(({row})=>({key:row.memory_key,version:row.summary_artifact_id}));
 const existing=new Map(before.map(item=>[signatureOf(item.text),item.row]));
 save();
 let index=0;
 for(const [signature,record]of unique){
  index++;
  const started=Date.now();let row=existing.get(signature),reused=Boolean(row);
  const title='[테스트 UX '+record.case_ids.join(',')+'] '+record.titles[0];
  if(!row){
   console.log(index+'/'+unique.size+' 저장 중: '+title);
   const digest=crypto.createHash('sha256').update('plant-all-test-fixtures-v1:'+signature).digest('hex').slice(0,32);
   const request_id=[digest.slice(0,8),digest.slice(8,12),digest.slice(12,16),digest.slice(16,20),digest.slice(20)].join('-');
   const text='제목: '+title+'\n기록일: '+record.date+'\n감정: 미지정\n\n'+record.body;
   boot=await get('/bootstrap');
   const response=await fetch(base+'/summary-memory/ux/save',{method:'POST',headers:{Origin:'http://127.0.0.1:4321','Content-Type':'application/json','X-Memory-Lab-Token':boot.token},
    body:JSON.stringify({session_id:'all-test-fixtures-v1',request_id,text,config:{model,route:'M1',top_k:3}})});
   const value=await response.json();if(!response.ok||value.state!=='committed')throw Error(value.error||'저장 미완료: '+title);
   row=value.memory;existing.set(signature,row);
  }
  report.records.push({...record,title:reused?parse(before.find(i=>i.row.memory_key===row.memory_key)?.text||'').title||'기존 원문 재사용':title,key:row.memory_key,version:row.summary_artifact_id,reused,elapsed_ms:Date.now()-started});save();
  console.log(index+'/'+unique.size+' '+(reused?'기존 원문 확인':'저장 완료'));
 }
 const after=await originals(),signatures=new Set(after.map(i=>signatureOf(i.text)));
 const missing=[...unique.keys()].filter(key=>!signatures.has(key));
 report.original_records_unchanged=report.original_records.every(old=>after.some(i=>i.row.memory_key===old.key&&i.row.summary_artifact_id===old.version));
 report.active_count=after.length;report.added_count=report.records.filter(r=>!r.reused).length;report.reused_count=report.records.filter(r=>r.reused).length;
 if(missing.length||!report.original_records_unchanged)throw Error('최종 원문 검증 실패: 누락 '+missing.length);
 report.status='complete';report.finished_at=new Date().toISOString();save();
 console.log(JSON.stringify({status:report.status,unique:unique.size,added:report.added_count,reused:report.reused_count,total:after.length,original_records_unchanged:true}));
}
main().catch(error=>{report.status='error';report.error=error.message;save();console.error(error.message);process.exitCode=1;});
