'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),path=require('node:path'),http=require('node:http');
const root=process.env.PMA_APP_ROOT||path.resolve(__dirname,'..');
const {classifyRequest,responseIssues,constrainSchema}=require(path.join(root,'ui/request-intent.cjs'));
const {createChatApi,schema}=require(path.join(root,'ui/chat-api.cjs'));
const {createInspection,normalizeInspection}=require(path.join(root,'ui/chat-inspection.cjs'));
const {chatRequest}=require(path.join(root,'local/token-budget.cjs'));
test('direct recording, future capture, edit and delete commands establish independent contracts',()=>{
 const cases=[
  ['앞으로 내가 하는 말 기록해줘','automatic_capture_request','experience'],
  ['이제부터 내 대화를 자동으로 저장해 주세요.','automatic_capture_request','experience'],
  ['오늘 지연과 도예 수업을 들었어. 이걸 기록해 줘.','record_content','experience'],
  ['“오늘 지연과 도예 수업을 들었어”를 기억해 주세요.','record_content','experience'],
  ['오늘 일을 메모해 줄래?','record_content','experience'],
  ['이번 주 계획을 저장해둬','record_content','experience'],
  ['앞으로 병원에 갈 계획이야. 이 내용을 기록해줘','record_content','experience'],
  ['그 기록의 시간을 오후 3시로 고쳐 줘','edit_request','edit'],
  ['어제 메모를 수정해 주세요','edit_request','edit'],
  ['지난주 영화 감상 기록을 지워 줘','delete_request','delete'],
  ['그 기억을 삭제해줄래?','delete_request','delete'],
  ['그 일은 잊어줘','delete_request','delete'],
 ];
 for(const [text,kind,intent]of cases){const c=classifyRequest(text);assert.equal(c?.kind,kind,text);assert.deepEqual(c.expected_intents,[intent]);}
 assert.deepEqual(classifyRequest(cases[0][0]).allowed_actions,['clarify']);
});
test('quoted commands, past-tense questions, negations and wording advice are not storage commands',()=>{
 const queries=['내가 기록해 달라고 했던 책은 뭐였지?','그 기록을 언제 수정했어?','삭제한 기록의 날짜 알려줘','"기록해줘"는 무슨 뜻이야?','`삭제해줘`를 영어로 번역해줘','문장을 고쳐줘','기억을 저장하는 방법 알려줘','기록을 삭제해 달라고 한 사람이 누구야?','내가 저장하지 말라고 했던 값은 뭐였지?','> 이 기록 삭제해줘\n누가 그렇게 말했어?','```text\n저장해줘\n```\n이 문장의 뜻을 알려줘'];
 for(const text of queries){const c=classifyRequest(text);assert(!c||c.expected_intents.every(v=>!['experience','edit','delete'].includes(v)),text);}
 for(const text of ['이 내용은 기록하지 마','저장해 주지 마','이건 기억하지 말아줘']){const c=classifyRequest(text);assert.equal(c.kind,'do_not_store');assert(!c.allowed_actions.includes('draft'));}
 const query=classifyRequest('새로 저장하지 말고 내 기록에서 위치를 찾아줘');assert.equal(query.kind,'query_without_storage');assert.equal(query.retrieval,'allow');
 assert.equal(classifyRequest('내가 저장하지 말라고 했던 값은 뭐였지?'),null);
 assert.equal(classifyRequest('기억을 삭제하는 방법 알려줘'),null);
});
test('parallel requests clarify instead of silently handling only a subset',()=>{
 for(const text of ['이 기록 삭제해줘. 그리고 오늘 일은 기록해줘.','내 기록에서 금액을 알려주고 오늘 일은 저장해줘','이 기록은 수정해 주고 저 기록은 삭제해줘']){const c=classifyRequest(text);assert.equal(c?.kind,'mixed_request',text);assert.deepEqual(c.allowed_actions,['clarify']);}
});
test('all intent/action combinations obey the response contract, even without a recognized command',()=>{
 assert.deepEqual(responseIssues(null,{intent:'emotion',action:'answer'}),['intent_action']);
 assert.deepEqual(responseIssues(null,{intent:'advice',action:'empathy'}),['intent_action']);
 const c=classifyRequest('앞으로 내가 하는 말 기록해줘');
 assert(responseIssues(c,{intent:'memory_query',action:'answer'}).includes('request_intent'));
 assert(responseIssues(c,{intent:'experience',action:'draft'}).includes('request_intent'));
 assert.deepEqual(responseIssues(c,{intent:'experience',action:'clarify',answer:c.clarification}),[]);
 assert(responseIssues(c,{intent:'experience',action:'clarify',answer:'앞으로 모든 대화를 자동으로 저장하겠습니다.'}).includes('request_intent'));
 assert.deepEqual(constrainSchema(schema,c).properties.intent.enum,['experience']);assert.deepEqual(schema.properties.intent.enum,['memory_query','emotion','advice','experience','edit','delete','general']);
});
async function client(t,run){
 const api=createChatApi(root,{runtime:async()=>({chat:run}),scope:async()=>({id:'personal',now:'2026-11-17',sources:[{id:'record-a',revision:1,text:'공방을 비우는 일이 더 급했다.',metadata:{title:'공방',created_at:'2026-11-17'}}]})});
 const server=http.createServer((req,res)=>api.handle(req,res,new URL(req.url,'http://127.0.0.1')));await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));t.after(()=>new Promise(resolve=>server.close(resolve)));
 const url='http://127.0.0.1:'+server.address().port,{token}=await(await fetch(url+'/api/chat/bootstrap')).json();
 return async text=>{const r=await fetch(url+'/api/chat/respond',{method:'POST',headers:{'Content-Type':'application/json','X-Plant-Token':token},body:JSON.stringify({request_id:'intent-a',thread_id:'thread-a',text,input_version:1,collection_id:'personal',profile:'personal',example_id:'',history:['공방은 어디였지?'],inspect:true})});return {status:r.status,value:await r.json()};};
}
test('the reported regression fails intent validation; retry keeps the same request and can recover',async t=>{
 let calls=0;
 const post=await client(t,async(messages,outputSchema)=>{
  calls++;const input=JSON.parse(messages[1].content);assert.equal(input.question,'앞으로 내가 하는 말 기록해줘');assert.equal(input.request_contract.kind,'automatic_capture_request');assert.deepEqual(input.evidence,[]);assert.equal(input.scope.retrieval,'not-requested');assert.deepEqual(outputSchema.properties.intent.enum,['experience']);
  return {parsed:calls===1?{intent:'memory_query',action:'answer',answer:'공방을 비우는 일이 급했다고 합니다.',citations:[]}:{intent:'experience',action:'clarify',answer:input.request_contract.clarification,citations:[]}};
 });
 const a=await post('앞으로 내가 하는 말 기록해줘');assert.equal(a.status,502);assert.equal(a.value.stage,'validation');assert.equal(a.value.answer,undefined);assert.equal(a.value.inspection.checks.request_intent,'failed');assert.equal(a.value.inspection.checks.citation_references,'not_run');assert.equal(a.value.inspection.output.intent,'memory_query');
 const b=await post('앞으로 내가 하는 말 기록해줘');assert.equal(b.status,200);assert.equal(b.value.action,'clarify');assert.equal(b.value.stored,false);assert.equal(b.value.scope.retrieved_count,0);assert.equal(b.value.inspection.checks.request_intent,'passed');assert.equal(calls,2);
 const c=await post('앞으로 내가 하는 말 기록해줘');assert.deepEqual(c.value,b.value);assert.equal(calls,2);
});
test('wrong response actions fail separately from absent memory and ordinary queries still search',async t=>{
 const post=await client(t,async messages=>{assert.equal(JSON.parse(messages[1].content).evidence.length,1);return {parsed:{intent:'emotion',action:'answer',answer:'기록에 없습니다.',citations:[]}};});
 const r=await post('공방 위치가 어디였지?');assert.equal(r.status,502);assert.equal(r.value.inspection.checks.intent_action,'failed');assert.equal(r.value.answer,undefined);
});
test('an automatic-recording promise is rejected even if the model labels it as clarification',async t=>{
 const post=await client(t,async(messages,outputSchema)=>{
  const c=JSON.parse(messages[1].content).request_contract;assert.deepEqual(outputSchema.properties.answer.enum,[c.clarification]);
  return {parsed:{intent:'experience',action:'clarify',answer:'앞으로 모든 말을 자동 기록해 드릴까요?',citations:[]}};
 });
 const r=await post('앞으로 내가 하는 말 기록해줘');assert.equal(r.status,502);assert.equal(r.value.inspection.checks.request_intent,'failed');assert.equal(r.value.answer,undefined);
});
test('old inspection snapshots remain readable and do not invent new completed checks',()=>{
 const old=createInspection(chatRequest([{role:'system',content:'지침'}],schema,{seed:42,output_tokens:1536}),8192);delete old.checks.intent_action;delete old.checks.request_intent;
 const restored=normalizeInspection(old);assert.equal(restored.checks.intent_action,'not_run');assert.equal(restored.checks.request_intent,'not_run');
});
