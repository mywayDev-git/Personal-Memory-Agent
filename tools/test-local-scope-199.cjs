'use strict';
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),assert=require('node:assert/strict'),http=require('node:http');
const root=path.resolve(__dirname,'..'),{Library}=require(root+'/ui/library.cjs'),{ActionService}=require(root+'/ui/action-service.cjs'),{createChatApi,existingRuntime}=require(root+'/ui/chat-api.cjs');
const dir=path.join(root,'.local','scope-199-tests',new Date().toISOString().replaceAll(':','-'));fs.mkdirSync(dir,{recursive:true});const library=new Library(dir),service=new ActionService(library),threads=new Map(),outcomes=[];let server;
const sha=()=>crypto.createHash('sha256').update(fs.readFileSync(root+'/datasets/pma-generalization-v1.0.0/sources.json')).digest('hex'),beforeHash=sha();
async function main(){const actual=await existingRuntime(root);let call=0;const runtime={chat:async(...args)=>{const r=await actual.chat(...args);fs.writeFileSync(path.join(dir,'model-'+(++call)+'.json'),JSON.stringify({messages:args[0],schema:args[1],result:r},null,2));return r;}};
 // Deliberately retain an unrelated personal record: sample lookups must never use it.
 library.save(0,s=>({...s,records:[{id:'private-backup',body:'PRIVATE_SENTINEL 백업 검증용 기록',title:'PRIVATE_SENTINEL 백업 검증용 기록',search_enabled:true}]}));
 const api=createChatApi(root,{runtime:async()=>runtime,actions:service,conversation:data=>threads.get(data.thread_id)||[]});server=http.createServer((req,res)=>api.handle(req,res,new URL(req.url,'http://'+req.headers.host)));await new Promise(r=>server.listen(0,'127.0.0.1',r));const base='http://127.0.0.1:'+server.address().port,token=(await(await fetch(base+'/api/chat/bootstrap')).json()).token;
 async function ask(label,text,options={},check=()=>{}){if(process.env.PMA_CROSS_ONLY&&!label.includes('선택→'))return;const threadId=options.thread||crypto.randomUUID(),turns=threads.get(threadId)||[];threads.set(threadId,turns);const data={request_id:crypto.randomUUID(),thread_id:threadId,text,input_version:1,collection_id:'samples',profile:options.profile||'development',example_id:options.example||'',history:[],analysis_version:'v2',conversation_ids:turns.map(t=>t.id),inspect:true};let result,error;
  try{const response=await fetch(base+'/api/chat/respond',{method:'POST',headers:{'Content-Type':'application/json','X-Plant-Token':token},body:JSON.stringify(data)});result=await response.json();assert.equal(response.status,200,JSON.stringify(result));assert.equal(result.scope.accessible_count,199);assert.ok(result.action_trace.observations.some(o=>o.tool==='search'&&o.accessible_count===199));assert.doesNotMatch(JSON.stringify(result.action_trace.model_calls),/PRIVATE_SENTINEL|"gold"/);for(const c of result.citations){const originals=JSON.parse(fs.readFileSync(root+'/datasets/pma-generalization-v1.0.0/sources.json','utf8')).records,source=originals.find(s=>s.id===c.source_id);assert.ok(source);assert.equal(source.text.slice(c.start,c.end),c.quote);}turns.push({id:'u-'+data.request_id,role:'user',text},{id:'a-'+data.request_id,role:'assistant',text:result.answer});check(result);}catch(e){error=e.stack;}
  const row={label,data,result,passed:!error,error};outcomes.push(row);fs.writeFileSync(path.join(dir,'results.json'),JSON.stringify(outcomes,null,2));console.log(JSON.stringify({label,passed:!error,count:result?.scope?.accessible_count,answer:result?.answer,citations:result?.citations?.map(c=>c.source_id),error:error?.split('\n')[0]}));return row;
 }
 const reportThread='report-followup';
 if(!process.env.PMA_STALE_ONLY){
 await ask('보고서 회귀','보고서 표 두 개의 단위 검토를 마친 사람은?',{thread:reportThread},r=>{assert.ok(r.citations.some(c=>c.source_id==='D-M3S-b68af7ce13b8399a'||c.source_id==='D-identity-EDIT'));assert.match(r.answer,/하린/);assert.match(r.answer,/수진/);});
 await ask('보고서 후속','기록을 통해 알려줘',{thread:reportThread},r=>{assert.ok(r.citations.length);assert.match(r.answer,/하린/);assert.match(r.answer,/수진/);});
 await ask('개발용 선택→확인용 원문','탐색 알고리즘 강의에서 BFS 큐 코드를 고친 사람은?',{example:'D-identity-BASE'},r=>{assert.ok(r.citations.some(c=>c.source_id.startsWith('CBG-')));assert.match(r.answer,/소율/);});
 await ask('확인용 선택→개발용 원문','10월 28일 주간 보고서의 표 두 개 검토를 부탁받은 회사 하린은 어느 팀에서 일해?',{profile:'confirmation',example:'C-identity-BASE'},r=>{assert.ok(r.citations.some(c=>c.source_id.startsWith('D-')));assert.match(r.answer,/회계팀/);});
 await ask('199개 중 끝부분 원문','탐색 알고리즘 실습 표에 BFS와 DFS 시간이 각각 얼마라고 적혀 있어?',{profile:'confirmation'},r=>{assert.match(r.answer,/18/);assert.match(r.answer,/15/);assert.ok(r.citations.some(c=>c.source_id==='CBG-M3S-b7775282176a06db'));});
 await ask('원문 없는 질문','내 여권 번호를 기록에서 확인해 줘.',{},r=>{assert.ok(['abstain','clarify'].includes(r.action));assert.notEqual(r.answer,'abstain');assert.doesNotMatch(r.answer,/[A-Z]\d{8}/);});
 await ask('주제 전환 계산','1 더하기 1은?',{thread:reportThread},r=>{assert.match(r.answer,/2/);assert.equal(r.action,'answer');assert.equal(r.citations.length,0);assert.equal(r.proposal,undefined);});
 }
 if(process.env.PMA_STALE_ONLY){
 threads.set('stale-history',[{id:'u-old',role:'user',text:'보고서 표 두 개의 단위 검토를 마친 사람은?'},{id:'a-old',role:'assistant',text:'현재 보관소에는 백업 검증용 기록만 있어 보고서 관련 기록을 찾을 수 없습니다.'}]);
 await ask('이전 잘못된 답변에서 회복','보고서 표 두 개의 단위 검토를 마친 사람은? 기록을 통해 알려줘',{thread:'stale-history'},r=>{assert.ok(r.citations.some(c=>c.source_id==='D-identity-EDIT'));assert.ok(r.citations.some(c=>c.source_id==='D-M3S-b68af7ce13b8399a'));assert.match(r.answer,/하린/);assert.match(r.answer,/수진/);assert.doesNotMatch(r.answer,/백업 검증용 기록만/);});
 }
 assert.equal(library.read().records.length,1);assert.equal(service.db.prepare('SELECT count(*) n FROM action_receipts').get().n,0);assert.equal(sha(),beforeHash);
 const summary={passed:outcomes.every(r=>r.passed),passed_count:outcomes.filter(r=>r.passed).length,total:outcomes.length,model:'local Qwen3.5 4B Q4',source_count:199,original_sha256:beforeHash,source_unchanged:true,dir};fs.writeFileSync(path.join(dir,'summary.json'),JSON.stringify(summary,null,2));console.log(JSON.stringify(summary));if(!summary.passed)process.exitCode=1;
}
main().catch(e=>{console.error(e.stack);process.exitCode=1;}).finally(()=>{server?.close();library.close();});
