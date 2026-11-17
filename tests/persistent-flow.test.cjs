'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),path=require('node:path'),http=require('node:http');
const root=process.env.PMA_APP_ROOT||path.resolve(__dirname,'..');
const context=require(path.join(root,'ui/plant-thought/conversation-context.js')),dialogue=require(path.join(root,'ui/dialogue-context.cjs'));
const {makeBackup,readBackup,merge}=require(path.join(root,'ui/library.cjs')),{createChatApi}=require(path.join(root,'ui/chat-api.cjs'));
const clock='2026-11-17T08:35:11.089Z',scope={id:'all-originals',now:'2026-12-01T12:00:00+09:00',sources:[]};
function session(thread='flow'){
 let ctx=context.empty(thread),seq=0;
 return {get context(){return ctx;},turn(text,override){const data={thread_id:thread,request_id:thread+'-'+(++seq),text,context:ctx,collection_id:'samples',profile:'development',example_id:'',history:[],input_version:seq,inspect:true};const plan=dialogue.resolve(data,scope,clock),result=dialogue.policy(plan)||override||{intent:plan.expected?.expected_intents[0]||'general',action:'answer',answer:'단발성 답변',citations:[]};ctx=dialogue.update(plan,data,result);return {data,plan,result,context:ctx};}};
}
test('reported transcript keeps recording instruction, empathizes, and updates one story draft from real statements',()=>{
 const s=session(),start=s.turn('앞으로 우리 대화 기록해줘');assert.equal(start.result.intent,'general');assert.match(start.result.answer,/초안/);assert.equal(s.context.awaiting,null);assert.equal(s.context.directives[0].value,'enabled');
 const feeling=s.turn('나 너무 바보야');assert.equal(feeling.result.action,'empathy');assert.equal(feeling.plan.resolvedQuestion,null);assert.equal(feeling.result.recording.date,'2026-11-17');assert.deepEqual(feeling.result.recording.statements,['나 너무 바보야']);
 const id=s.context.pending[0].id,story=s.context.story,reason=s.turn('나 오늘 공부했는데 다 까먹어서');assert.equal(reason.plan.relation,'continue');assert.equal(reason.result.action,'empathy');assert.equal(s.context.pending.length,1);assert.equal(s.context.pending[0].id,id);assert.equal(s.context.story,story);assert.deepEqual(reason.result.recording.statements,['나 너무 바보야','나 오늘 공부했는데 다 까먹어서']);
 const draft=s.turn('오늘 내 기분을 기록하고 싶어');assert.equal(draft.result.action,'draft');assert.match(draft.result.answer,/나 너무 바보야/);assert.match(draft.result.answer,/공부했는데/);assert(!draft.result.answer.includes('12-01'));assert(!draft.result.answer.includes('기분을 기록하고 싶다'));assert.equal(s.context.pending.length,1);
 const last=s.turn('나 오늘 공부한거 다 까먹어서 바보 같아');assert.equal(last.plan.relation,'continue');assert.equal(last.result.action,'empathy');assert.equal(last.result.recording.statements.length,3);assert.equal(s.context.pending.length,1);
});
test('short calculation completes without overriding instructions or capturing a new personal fact',()=>{
 const s=session();s.turn('앞으로 우리 대화 기록해줘');s.turn('나 너무 바보야');s.turn('나 오늘 공부했는데 다 까먹어서');const story=s.context.story,pending=structuredClone(s.context.pending);
 const q=s.turn('7에 5를 더하면?',{intent:'general',action:'answer',answer:'12입니다.',citations:[]});assert.equal(q.plan.kind,'general');assert.equal(q.result.recording,undefined);assert.equal(s.context.task.status,'completed');assert.deepEqual(s.context.pending,pending);assert.equal(s.context.story,story);assert.equal(s.context.directives[0].value,'enabled');
 const returned=s.turn('아까 공부 이야기로 돌아가자');assert.equal(returned.plan.relation,'return');assert.equal(s.context.story,story);assert.equal(returned.result.recording,undefined);
 const draft=s.turn('아까 내 기분을 기록해줘');assert.match(draft.result.answer,/공부했는데/);assert(!draft.result.answer.includes('7에 5'));
});
test('temporary exclusion never disables the persistent instruction and never enters the draft',()=>{
 const s=session();s.turn('앞으로 대화 기록해줘');s.turn('나 너무 바보야');const before=structuredClone(s.context.pending);
 s.turn('이번 이야기는 기록하지 마');assert.equal(s.context.directives[0].value,'enabled');assert.deepEqual(s.context.pending,before);
 const next=s.turn('나 오늘 공부한거 다 까먹어서 바보 같아');assert.equal(next.result.recording,undefined);assert.deepEqual(s.context.pending,before);
 s.turn('7에 5를 더하면?');const other=s.turn('어제 친구를 만났어');assert(other.result.recording);assert(!JSON.stringify(other.result.recording).includes('기록하지 마'));
});
test('stopping future capture preserves previous drafts, changing style does not restart capture',()=>{
 const s=session();s.turn('앞으로 우리 대화 기록해줘');s.turn('나 너무 바보야');const pending=structuredClone(s.context.pending);
 s.turn('이제 기록 그만해줘');assert.equal(s.context.directives.find(d=>d.type==='record').value,'disabled');assert.deepEqual(s.context.pending,pending);
 s.turn('앞으로 답변은 짧게 해줘');const q=s.turn('오늘 너무 속상해');assert.equal(q.plan.discourse.style,'brief');assert.equal(q.result.recording,undefined);assert.deepEqual(s.context.pending,pending);
 s.turn('이번 답변만 자세히 설명해줘');assert.equal(s.context.directives.find(d=>d.type==='style').value,'brief');assert.equal(s.turn('7에 5를 더하면?').plan.discourse.style,'brief');
 s.turn('답변 길이는 원래대로 해줘');assert.equal(s.context.directives.find(d=>d.type==='style').value,'normal');
});
test('new unrelated personal story has a separate draft, while old stories remain selectable',()=>{
 const s=session();s.turn('앞으로 우리 대화 기록해줘');s.turn('나 너무 바보야');s.turn('나 오늘 공부했는데 다 까먹어서');const old=s.context.story;
 s.turn('7에 5를 더하면?');const next=s.turn('어제 친구를 만났어');assert.notEqual(s.context.story,old);assert.equal(next.result.recording.statements.length,1);assert.equal(s.context.pending.length,2);
 const returned=s.turn('아까 공부 이야기로 돌아가자');assert.equal(returned.plan.topic.id,old);
});
test('many completed short tasks cannot expire a persistent instruction or the current story',()=>{
 const s=session();s.turn('앞으로 우리 대화 기록해줘');s.turn('나 너무 바보야');const id=s.context.story;
 for(let i=0;i<12;i++)s.turn(i+'에 5를 더하면?');assert(s.context.topics.some(t=>t.id===id));assert.equal(s.context.directives[0].value,'enabled');assert.equal(s.context.pending.length,1);
});
test('instruction and personal content in one message are processed separately',()=>{
 const s=session(),r=s.turn('앞으로 우리 대화 기록해줘. 나 너무 바보야');assert.equal(r.result.action,'empathy');assert.equal(s.context.directives[0].value,'enabled');assert.deepEqual(r.result.recording.statements,['나 너무 바보야']);
 s.turn('나 오늘 공부했는데 다 까먹어서');s.turn('7에 5를 더하면?');const before=structuredClone(s.context.pending),summary=s.turn('아까 내 기분 정리해줘');assert.equal(summary.result.action,'answer');assert.match(summary.result.answer,/공부했는데/);assert(!summary.result.answer.includes('앞으로 우리 대화'));assert.deepEqual(s.context.pending,before);
});
test('cancelling a draft preserves the ongoing recording instruction and an untouched new input',()=>{
 const s=session();s.turn('앞으로 대화 기록해줘');s.turn('나 너무 바보야');const id=s.context.pending[0].id,ctx=s.context,data={thread_id:'flow',request_id:'cancel',text:'그 작업 취소해줘',pending_target:id,context:ctx,collection_id:'samples'};
 const plan=dialogue.resolve(data,scope,clock),result=dialogue.policy(plan),next=dialogue.update(plan,data,result);assert.equal(next.pending[0].status,'cancelled');assert.equal(next.directives[0].value,'enabled');
 const thread={id:'flow',draft:'새로 작성 중',context:ctx,contextRequest:'cancel'};assert.equal(context.apply(thread,data,next),true);assert.equal(thread.draft,'새로 작성 중');
});
test('restarting recording cannot retroactively capture statements made while it was off',()=>{
 const s=session();s.turn('나 너무 바보야');s.turn('앞으로 대화 기록해줘');const first=s.turn('오늘 공부했는데 다 까먹어서');assert.deepEqual(first.result.recording.statements,['오늘 공부했는데 다 까먹어서']);
 s.turn('기록 그만해줘');s.turn('오늘은 특히 속상해');s.turn('앞으로 대화 기록해줘');const next=s.turn('그래도 이제 괜찮아');assert(!next.result.recording.statements.includes('오늘은 특히 속상해'));assert(!next.result.recording.statements.includes('나 너무 바보야'));assert(next.result.recording.statements.includes('그래도 이제 괜찮아'));
});
test('new emotion overrides a pending target clarification rather than becoming a person selection',()=>{
 const s=session();const ctx=s.context;ctx.awaiting={question:'그 사람은 누구야?',topic_id:null,intent:'memory_query',scope:'samples'};
 const r=s.turn('나 너무 바보야');assert.equal(r.plan.resolvedQuestion,null);assert.equal(r.result.action,'empathy');assert.equal(r.context.awaiting,null);
});
test('quoted instructions, other conversations and other collections cannot activate capture',()=>{
 const s=session();s.turn('“앞으로 우리 대화 기록해줘”라는 문장이야');assert.equal(s.context.directives.length,0);
 s.turn('앞으로 우리 대화 기록해줘');const other=dialogue.resolve({thread_id:'flow',request_id:'other',text:'나 너무 바보야',collection_id:'personal',context:s.context},scope,clock);assert.equal(other.discourse.record,'disabled');
 const clean=session('another');assert.equal(clean.turn('나 너무 바보야').result.recording,undefined);assert.throws(()=>context.normalize(s.context,'another'));
});
test('backup and conflict copy preserve directives, user statements, drafts and recording metadata',()=>{
 const s=session(),first=s.turn('앞으로 우리 대화 기록해줘'),last=s.turn('나 너무 바보야');
 const result={...last.result,request_id:last.data.request_id,thread_id:'flow',context:s.context,scope:{mode:'all-originals',accessible_count:199,retrieved_count:0},stored:false};
 const row={id:'flow',title:'지속 기록',context:s.context,messages:[{kind:'assistant',status:'success',submission:last.data,result}]};
 const restored=readBackup(makeBackup({threads:[row]},'chat'));assert.deepEqual(restored.threads[0].context,s.context);assert.deepEqual(restored.threads[0].messages[0].result.recording,result.recording);
 const copy=merge({threads:[{...row,title:'다른 이름'}],records:[]},restored,{conflicts:'copy'}).state.threads[1];assert.equal(copy.context.thread_id,copy.id);assert.equal(copy.context.directives[0].text,first.data.text);
});
async function client(t,run){
 const api=createChatApi(root,{runtime:async()=>({chat:run}),scope:async()=>scope,now:()=>clock}),server=http.createServer((req,res)=>api.handle(req,res,new URL(req.url,'http://127.0.0.1')));
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));t.after(()=>new Promise(resolve=>server.close(resolve)));const url='http://127.0.0.1:'+server.address().port,{token}=await(await fetch(url+'/api/chat/bootstrap')).json();
 return async data=>{const response=await fetch(url+'/api/chat/respond',{method:'POST',headers:{'Content-Type':'application/json','X-Plant-Token':token},body:JSON.stringify(data)});return {status:response.status,result:await response.json()};};
}
test('API carries durable instructions into a short model task and uses actual time for current feelings',async t=>{
 let calls=0;const post=await client(t,async messages=>{calls++;const input=JSON.parse(messages[1].content);assert.equal(input.conversation_context.ongoing_instructions.record,'enabled');assert.equal(input.conversation_context.ongoing_instructions.response_style,'brief');assert.deepEqual(input.previous_user_questions,[]);assert.equal(input.now,clock);assert.equal(input.lookup_reference_time,scope.now);return {parsed:{intent:'general',action:'answer',answer:'12입니다.',citations:[]}};});
 let ctx=context.empty('api'),seq=0;
 async function turn(text){const data={thread_id:'api',request_id:'api-'+(++seq),text,context:ctx,collection_id:'samples',profile:'development',example_id:'',history:[],input_version:seq,inspect:true};const r=await post(data);assert.equal(r.status,200,JSON.stringify(r.result));ctx=r.result.context;assert.equal(r.result.stored,false);return r.result;}
 await turn('앞으로 우리 대화 기록해줘');await turn('앞으로 답변은 짧게 해줘');const a=await turn('나 너무 바보야');assert.equal(a.recording.date,'2026-11-17');
 await turn('나 오늘 공부했는데 다 까먹어서');await turn('7에 5를 더하면?');await turn('아까 공부 이야기로 돌아가자');const draft=await turn('오늘 내 기분을 기록하고 싶어');assert.match(draft.answer,/공부했는데/);assert.equal(calls,1);
});
