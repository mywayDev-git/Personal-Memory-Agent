'use strict';
// Runs the production chat API with the existing authenticated LOCAL model.
// The test conversation lives in memory; it never saves threads or archive records.
const fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const root=path.resolve(__dirname,'..'),fixture=require('../tests/fixtures/latest-turn-11.json');
const {createChatApi,existingRuntime}=require('../ui/chat-api.cjs'),state=require('../ui/plant-thought/chat-state.js'),maps=require('../ui/plant-thought/dialogue-map.js');
const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function verify(outcomes,thread){
 const experience=fixture.inputs.slice(1,5),checks=[];
 for(let i=0;i<fixture.inputs.length;i++){
  const row=outcomes[i],r=row?.value,issues=[];
  if(!row||row.input!==fixture.inputs[i]||row.status!==200)issues.push(row?.value?.error||'요청 미실행 또는 원문 불일치');
  if(r&&row.status===200){
   if(r.stored!==false)issues.push('실제 쓰기 없이 저장 성공 표시');
   if(r.dialogue_trace?.original!==fixture.inputs[i])issues.push('최신 입력 누락');
   if(!r.context?.directives.some(d=>d.type==='record'&&d.value==='enabled'))issues.push('지속 기록 지시 유실');
   const input=JSON.parse(r.inspection?.request_body.messages[1]?.content||'{}');
   if(input.question!==fixture.inputs[i])issues.push('생성 요청의 최신 질문 누락');
   if(i===0&&r.dialogue_trace?.operation!=='directive')issues.push('설정 변경 처리 실패');
   if(i>=1&&i<=4){
    if(r.recording?.statements.at(-1)!==fixture.inputs[i])issues.push('경험·이유·정정 누락');
    if(r.recording?.sources?.at(-1)?.text!==fixture.inputs[i])issues.push('사용자 원문 출처 누락');
   }
   if(i===2||i===3){if(!r.map_context?.corrections?.some(c=>c.turn_id==='u-'+r.request_id))issues.push('정정 상태 누락');}
   if(i===5||i===6){if(r.intent!=='general'||r.action!=='answer'||!/초안/.test(r.answer)||!/저장/.test(r.answer))issues.push('기록 상태 안내 실패');}
   if(i===7||i===8){
    if(r.intent!=='experience'||r.action!=='draft')issues.push('기록 요청 의도 불일치');
    if(JSON.stringify(r.recording?.statements)!==JSON.stringify(experience))issues.push('기록 내용 누락 또는 질문·명령 혼입');
    if(r.recording?.sources?.some(s=>!s.turn_id.startsWith('u-')||!experience.includes(s.text)))issues.push('비사용자 출처 혼입');
   }
   if(i===9){if(r.action!=='clarify'||!['general','memory_query'].includes(r.intent)||!/민수/.test(r.answer)||/똥|슬픔/.test(r.answer))issues.push('새 인물 질문 분리 실패');}
   if(i===10){
    if(r.intent!=='general'||r.action!=='answer'||!/(?<!\d)2(?!\d)/.test(r.answer)||/똥|슬픔|민수/.test(r.answer))issues.push('계산 요청 미처리');
    if(input.conversation_context?.corrections.length)issues.push('관련 없는 감정 정정 문맥 혼입');
    if(r.inspection?.checks.latest_grounding!=='passed')issues.push('독립 답변 검증 미통과');
   }
  }
  checks.push({turn:i+1,input:fixture.inputs[i],passed:issues.length===0,issues});
 }
 for(const p of thread.mapContext?.flow?.pending||[])for(const s of p.recording?.statements||[])if(!experience.includes(s))checks.push({turn:0,passed:false,issues:['확인 대기 초안에 질문·명령 혼입: '+s]});
 return {passed:checks.length===11&&checks.every(c=>c.passed),passed_turns:checks.filter(c=>c.passed).length,total_turns:11,checks};
}
function report(dir,outcomes,thread,calls){
 const result=verify(outcomes,thread),phases={};for(const c of calls)phases[c.phase]=(phases[c.phase]||0)+1;
 const summary={...result,model:'Qwen3.5 4B Q4_K_M',endpoint:'127.0.0.1:18491',model_calls:calls.length,phases,archive_writes:0,conversation_persistence:'memory only'};
 fs.writeFileSync(path.join(dir,'verification.json'),JSON.stringify(summary,null,2));
 const rows=result.checks.map(c=>{const r=outcomes[c.turn-1]?.value;return '<tr><td>'+c.turn+'</td><td>'+escape(c.input)+'</td><td>'+escape(r?.intent+' / '+r?.action)+'</td><td><pre>'+escape(r?.answer||r?.error)+'</pre></td><td>'+escape(c.passed?'통과':c.issues.join('; '))+'</td></tr>';}).join('');
 fs.writeFileSync(path.join(dir,'report.html'),'<!doctype html><html lang="ko"><meta charset="utf-8"><title>11턴 로컬 모델 재현 결과</title><style>body{font:15px/1.65 system-ui;margin:40px;color:#193d32;background:#fafaf7}table{border-collapse:collapse;width:100%;background:white}td,th{border:1px solid #dce2da;padding:12px;text-align:left;vertical-align:top}pre{white-space:pre-wrap;font:inherit;margin:0}h1{font-size:26px}</style><h1>11턴 로컬 모델 재현: '+result.passed_turns+'/11 통과</h1><p>Qwen3.5 4B · 로컬 모델 호출 '+calls.length+'회 · 외부 모델 호출 없음 · 기존 대화 및 보관소 쓰기 없음</p><p>요청 분석과 대화 지도는 로컬 모델로 처리합니다. 정정·기록 상태·초안은 검증된 앱 규칙으로 처리하며 자유 생성 답변에는 별도 검증을 적용합니다.</p><table><thead><tr><th>턴</th><th>사용자 입력</th><th>분류 / 행동</th><th>실제 답변</th><th>판정</th></tr></thead><tbody>'+rows+'</tbody></table>');
 return summary;
}
async function run(dir){
 fs.mkdirSync(dir,{recursive:true});const real=await existingRuntime(root),calls=[];
 const runtime={chat:async(...args)=>{const input=JSON.parse(args[0][1].content),phase=input.phase||'answer',start=Date.now();const r=await real.chat(...args);calls.push({phase,input,output:r.parsed,elapsed_ms:Date.now()-start});fs.writeFileSync(path.join(dir,'calls.json'),JSON.stringify(calls,null,2));return r;}};
 const thread={id:'regression-'+Date.now(),draft:'',inputVersion:0,messages:[]},outcomes=[];
 const api=createChatApi(root,{runtime:async()=>runtime,conversation:d=>maps.turns(thread,d.collection_id)}),server=http.createServer((req,res)=>api.handle(req,res,new URL(req.url,'http://127.0.0.1')));
 await new Promise(r=>server.listen(0,'127.0.0.1',r));const base='http://127.0.0.1:'+server.address().port,{token}=await(await fetch(base+'/api/chat/bootstrap')).json();
 try{for(const [i,text]of fixture.inputs.entries()){
  thread.draft=text;thread.inputVersion++;const submission=state.submission(thread,{profile:'personal',collectionId:'personal'},{version:'v2',inspect:true});thread.contextRequest=submission.request_id;
  const m={kind:'assistant',status:'pending',submission,createdAt:new Date().toISOString()};thread.messages.push({kind:'user',text,requestId:submission.request_id,createdAt:m.createdAt},m);
  const response=await fetch(base+'/api/chat/respond',{method:'POST',headers:{'Content-Type':'application/json','X-Plant-Token':token},body:JSON.stringify(submission)}),value=await response.json();
  if(response.ok){m.status='success';m.result=value;state.applyContext(thread,submission,value.context,value.map_context);}else{m.status='error';m.error=value.error;}
  outcomes.push({turn:i+1,input:text,status:response.status,value});fs.writeFileSync(path.join(dir,'outcomes.json'),JSON.stringify(outcomes,null,2));fs.writeFileSync(path.join(dir,'thread.json'),JSON.stringify(thread,null,2));console.log(JSON.stringify({turn:i+1,input:text,status:response.status,intent:value.intent,action:value.action,answer:value.answer,error:value.error}));
  if(!response.ok)break;
 }}finally{await new Promise(r=>server.close(r));}
 return report(dir,outcomes,thread,calls);
}
if(require.main===module){const at=process.argv.indexOf('--verify-log'),dir=path.resolve(at>=0?process.argv[at+1]:(process.argv[2]||path.join(root,'.test-output','latest-turn-local-'+Date.now())));(async()=>{const result=at>=0?report(dir,JSON.parse(fs.readFileSync(path.join(dir,'outcomes.json'))),JSON.parse(fs.readFileSync(path.join(dir,'thread.json'))),JSON.parse(fs.readFileSync(path.join(dir,'calls.json')))):await run(dir);console.log(JSON.stringify(result,null,2));if(!result.passed)process.exitCode=1;})().catch(e=>{console.error(e.message);process.exitCode=1;});}
module.exports={verify,report};
