'use strict';
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const repo='D:/development/personal-memory-agent';
const {Library}=require(repo+'/ui/library.cjs'),{ActionService}=require(repo+'/ui/action-service.cjs');
const {respond}=require(repo+'/ui/action-agent.cjs'),{existingRuntime,retrieve}=require(repo+'/ui/chat-api.cjs');
const dir=path.join(__dirname,'runs',new Date().toISOString().replaceAll(':','-'));fs.mkdirSync(dir,{recursive:true});
let store=new Library(dir),service=new ActionService(store),turns=[],threadId=crypto.randomUUID();
store.save(0,s=>({...s,threads:[{id:threadId,messages:[],draft:'새 초안 B',inputVersion:2}]}));
const scope=async()=>({id:'personal',now:new Date().toISOString(),sources:store.read().records.filter(r=>!r.deleted_at&&r.search_enabled).map(r=>({id:r.id,revision:r.revision,text:r.body,metadata:{title:r.title,created_at:r.created_at}}))});
const outcomes=[];let server;
async function main(){
 const actual=await existingRuntime(repo);let callIndex=0;const runtime={chat:async(...args)=>{const result=await actual.chat(...args);fs.writeFileSync(path.join(dir,'call-'+(++callIndex)+'.json'),JSON.stringify({messages:args[0],schema:args[1],result},null,2));return result;}};
 const api=require(repo+'/ui/chat-api.cjs').createChatApi(repo,{get actions(){return service;},runtime:async()=>runtime,conversation:async()=>turns,scope});server=require('node:http').createServer((req,res)=>api.handle(req,res,new URL(req.url,'http://'+req.headers.host)));await new Promise(r=>server.listen(0,'127.0.0.1',r));const base='http://127.0.0.1:'+server.address().port,token=(await(await fetch(base+'/api/chat/bootstrap')).json()).token;
 async function post(route,data){const response=await fetch(base+'/api/chat/'+route,{method:'POST',headers:{'Content-Type':'application/json','X-Plant-Token':token},body:JSON.stringify(data)}),body=await response.json();if(!response.ok)throw Error(JSON.stringify(body));return body;}
 async function ask(text){const data={request_id:crypto.randomUUID(),thread_id:threadId,text,input_version:1,collection_id:'personal',profile:'personal',example_id:'',history:[],analysis_version:'v2',conversation_ids:turns.map(t=>t.id)};
  const result=await post('respond',data);
  turns.push({id:'u-'+data.request_id,role:'user',text},{id:'a-'+data.request_id,role:'assistant',text:result.answer});
  const row={text,data,result};outcomes.push(row);fs.writeFileSync(path.join(dir,'trace.json'),JSON.stringify(outcomes,null,2));console.log(JSON.stringify({text,action:result.action_trace.plan.steps.map(s=>s.tool).join(','),answer:result.answer,proposals:result.proposals?.map(p=>p.operation)}));return row;
 }
 async function approve(row){const p=row.result.proposals[0];assert.ok(p,'expected proposal');const input={thread_id:threadId,proposal_id:p.id,version:p.version,operation_id:p.operation_id,decision:'confirm'},receipt=await post('operation',input);row.receipt=receipt;row.result.answer=receipt.message;turns.find(t=>t.id==='a-'+row.data.request_id).text=receipt.message;assert.equal(receipt.status,'succeeded');assert.deepEqual(await post('operation',input),receipt);assert.equal(store.read().threads[0].draft,'새 초안 B');return receipt;}
 const create=await ask('오늘 학교에서 민수와 도서관에 갔어. 이 경험을 내 기록으로 남겨 줘.');assert.equal(create.result.proposals[0]?.operation,'create');assert.equal(store.read().records.length,0);const saved=await approve(create);assert.match(store.read().records[0].body,/도서관/);
 const updated=await ask('방금 남긴 내용의 장소가 잘못됐어. 도서관이 아니라 과학관에 갔어. 그 기록을 고쳐 줘.');assert.equal(updated.result.proposals[0]?.operation,'update');assert.equal(updated.result.proposals[0].target_id,saved.record_id);await approve(updated);assert.match(store.read().records[0].body,/과학관/);assert.doesNotMatch(store.read().records[0].body,/도서관/);
 const math=await ask('1 더하기 1은?');assert.equal(math.result.proposals.length,0);assert.match(math.result.answer,/2/);assert.equal(store.read().records[0].revision,2);
 const deleted=await ask('학교 민수랑 과학관에 간 방금 그 기록은 이제 보관하지 않을래. 서재에서 없애 줘.');assert.equal(deleted.result.proposals[0]?.operation,'delete');await approve(deleted);assert.equal((await scope()).sources.length,0);assert.ok(store.read().records[0].deleted_at);
 // Lost response/restart: exact approval is recovered, with no second mutation.
 const p=deleted.result.proposals[0],input={thread_id:threadId,proposal_id:p.id,version:p.version,operation_id:p.operation_id,decision:'confirm'};store.close();store=new Library(dir);service=new ActionService(store);assert.deepEqual(service.execute(input),deleted.receipt);assert.equal(store.read().records[0].revision,3);
 const restored=await ask('아까 없앤 학교 민수와 과학관 간 기록을 다시 볼 수 있게 되돌려 줘.');assert.equal(restored.result.proposals[0]?.operation,'restore');await approve(restored);assert.equal((await scope()).sources.length,1);
 const query=await ask('학교 민수랑 어디 갔었지? 내 기록으로 확인해 줘.');assert.match(query.result.answer,/과학관/);assert.ok(query.result.citations.length);assert.equal(store.read().records[0].revision,4);
 const transcript=await ask('방금 내가 한 질문과 네 답변을 둘 다 대화 원문으로 보관해 줘.');assert.equal(transcript.result.proposals[0]?.after.kind,'transcript');assert.ok(transcript.result.proposals[0].sources.some(s=>s.role==='assistant'));assert.ok(transcript.result.proposals[0].sources.some(s=>s.role==='user'));await approve(transcript);assert.equal(store.read().records.length,2);
 fs.writeFileSync(path.join(dir,'trace.json'),JSON.stringify(outcomes,null,2));fs.writeFileSync(path.join(dir,'summary.json'),JSON.stringify({passed:true,model:'local Qwen3.5 4B Q4',steps:outcomes.length,records:store.read().records,checks:['create','update','delete','restore','query','transcript','idempotency','restart-recovery','draft-preservation']},null,2));console.log('PASS '+dir);
}
main().catch(error=>{fs.writeFileSync(path.join(dir,'failure.txt'),error.stack);console.error(error.stack);process.exitCode=1;}).finally(()=>{server?.close();store.close();});
