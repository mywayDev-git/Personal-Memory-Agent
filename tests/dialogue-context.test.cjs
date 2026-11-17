'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),path=require('node:path'),http=require('node:http');
const root=process.env.PMA_APP_ROOT||path.resolve(__dirname,'..');
const context=require(path.join(root,'ui/plant-thought/conversation-context.js')),dialogue=require(path.join(root,'ui/dialogue-context.cjs'));
const state=require(path.join(root,'ui/plant-thought/chat-state.js')),{createChatApi}=require(path.join(root,'ui/chat-api.cjs'));
const {makeBackup,readBackup,merge}=require(path.join(root,'ui/library.cjs'));
const a={id:'deployment',revision:1,text:'민수는 인계를 요청했다. 지연이 서버 배포 담당을 수락했다. 운영 배포 완료 보고는 아직 없다.',metadata:{title:'루멘 서버와 모바일 알림',created_at:'2026-11-17T00:00:00+09:00'}};
const b={id:'travel',revision:1,text:'누리 숙소는 18만 원을 결제해 예약했다.',metadata:{title:'11월 여행 일정',created_at:'2026-11-17T00:00:00+09:00'}};
const scope={id:'personal',now:'2026-11-17T12:00:00+09:00',sources:[a,b]};
const citation=(s=a)=>({source_id:s.id,revision:s.revision,title:s.metadata.title,start:0,end:s.text.length,quote:s.text});
const request=(text,id='one',ctx=context.empty('thread-a'))=>({request_id:id,thread_id:'thread-a',text,input_version:1,collection_id:'personal',profile:'personal',example_id:'',history:[],context:ctx,inspect:true});
function remember(base,text,result,id='one'){const data=request(text,id,base),plan=dialogue.resolve(data,scope);return dialogue.update(plan,data,{intent:'memory_query',action:'answer',answer:'지연입니다.',citations:[citation()],...result});}
test('follow-up uses only the selected topic, verified raw references and a citation-backed name',()=>{
 const ctx=remember(context.empty('thread-a'),'서버 배포 인계를 수락한 사람은?',{}),plan=dialogue.resolve(request('그 사람이 맡은 서버는 배포가 끝났어?','two',ctx),scope);
 assert.equal(plan.relation,'continue');assert.equal(plan.topic.focus,'지연');assert.deepEqual(plan.history,['서버 배포 인계를 수락한 사람은?']);assert.equal(plan.references[0].quote,a.text);assert(!JSON.stringify(plan.modelContext).includes('지연입니다.'));
});
test('same-title records about another person or task are not valid follow-up evidence',()=>{
 const ctx=remember(context.empty('thread-a'),'루멘 서버 배포 인계를 수락한 사람은?',{}),data=request('그 사람이 맡은 서버는 배포가 끝났어?','two',ctx),plan=dialogue.resolve(data,scope);
 const status={evidence_id:'E1',source_id:a.id,text:'지연은 수정 후 재검사하겠다고 했다. 운영 배포 완료 보고는 아직 없다.'},other={evidence_id:'E2',source_id:'mobile',text:'도윤은 모바일 알림 기능을 배포했다.'};
 const target=dialogue.targetEvidence(plan,data,[status,other]);assert.deepEqual(target.allowed,['E1']);assert.equal(target.quoteCompatible('운영 배포 완료 보고는 아직 없다.'),true);assert.equal(target.quoteCompatible(other.text),false);
 const constrained=dialogue.constrainEvidence(require(path.join(root,'ui/chat-api.cjs')).schema,target);assert.deepEqual(constrained.properties.citations.items.properties.evidence_id.enum,['E1']);
 const contract=dialogue.completionContract(plan,data,[status,other],target);assert.deepEqual(contract.allowed_actions,['abstain']);assert.deepEqual(contract.evidence_ids,['E1']);
});
test('real catalog follow-up retrieves progress records and never treats handoff as completion',async()=>{
 const fs=require('node:fs'),{loadScope,retrieve}=require(path.join(root,'ui/chat-api.cjs'));
 const q=JSON.parse(fs.readFileSync(path.join(root,'datasets/pma-generalization-v1.0.0/questions.json'),'utf8')).questions.find(q=>q.profile==='development');
 const catalog=await loadScope(root,{profile:q.profile,example_id:q.id}),handoff=catalog.sources.find(s=>s.text.includes('지연이 담당을 수락하고 남은 검사부터 확인'));
 assert(handoff);const ctx=context.empty('thread-a'),first={...request('루멘 서버 배포 인계를 수락한 사람은?'),collection_id:'samples'},p=dialogue.resolve(first,catalog);
 const c={source_id:handoff.id,revision:handoff.revision,title:handoff.metadata.title,start:0,end:handoff.text.length,quote:handoff.text};
 const saved=dialogue.update(p,first,{intent:'memory_query',action:'answer',answer:'지연입니다.',citations:[c]});
 const next={...request('그 사람이 맡은 서버는 배포가 끝났어?','two',saved),collection_id:'samples'},follow=dialogue.resolve(next,catalog),evidence=retrieve(catalog.sources,follow.lookup,[],follow.references.map(r=>r.source_id));
 assert(evidence.some(e=>e.text.includes('운영 배포 완료 보고는 아직 없다')));
 const target=dialogue.targetEvidence(follow,next,evidence),contract=dialogue.completionContract(follow,next,evidence,target);assert.deepEqual(contract.allowed_actions,['abstain']);
 assert(!evidence.filter(e=>target.allowed.includes(e.evidence_id)).some(e=>e.text.includes('도윤은 모바일 알림 기능을 배포했다')));
});
test('topic switch isolates history and explicit return restores the earlier topic after multiple turns',()=>{
 let ctx=remember(context.empty('thread-a'),'서버 배포 인계를 수락한 사람은?',{});
 let plan=dialogue.resolve(request('업무 이야기는 잠시 두고, 7에 5를 더하면?','two',ctx),scope);assert.equal(plan.expected.expected_intents[0],'general');assert.deepEqual(plan.history,[]);assert.deepEqual(plan.references,[]);
 ctx=dialogue.update(plan,request('업무 이야기는 잠시 두고, 7에 5를 더하면?','two',ctx),{intent:'general',action:'answer',answer:'12입니다.',citations:[]});
 plan=dialogue.resolve(request('아까 서버 배포 이야기로 돌아가자','three',ctx),scope);assert.equal(plan.relation,'return');assert.equal(plan.topic.label,a.metadata.title);assert(!plan.history.some(q=>q.includes('7에 5')));
 const fresh=dialogue.resolve(request('누리 숙소 예약 상태는?','four',ctx),scope);assert.equal(fresh.relation,'new_topic');assert.deepEqual(fresh.history,[]);
});
test('feelings, advice and newly stated experiences do not search unrelated past records',()=>{
 const ctx=remember(context.empty('thread-a'),'서버 배포 담당은?',{});
 for(const [text,intent]of [['오늘 너무 힘들어','emotion'],['독서를 시작하려면 어떻게 하면 좋을까?','advice'],['오늘 도예 수업을 들었어','experience']]){const p=dialogue.resolve(request(text,'two',ctx),scope);assert.equal(p.expected.expected_intents[0],intent);assert.equal(p.expected.retrieval,'skip');assert.deepEqual(p.history,[]);}
 const query=dialogue.resolve(request('서버 배포는 누가 했어?','two',ctx),scope);assert.notEqual(query.expected?.expected_intents[0],'experience');
 const draft=dialogue.policy(dialogue.resolve(request('오늘 도예 수업을 들은 일을 기록해줘','draft',ctx),scope));assert.equal(draft.action,'draft');assert.match(draft.answer,/오늘 도예 수업을 들은 일/);assert.match(draft.answer,/저장하지 않았/);
 assert.equal(dialogue.resolve(request('오늘 산책 20분을 기록해줘','walk',ctx),scope).expected?.draft_text,undefined);
});
test('multiple people require clarification and a user answer resumes the unresolved question',()=>{
 const ctx=remember(context.empty('thread-a'),'서버 배포 인계는 누가 했어?',{answer:'민수가 요청하고 지연이 수락했습니다.'});
 assert.equal(ctx.topics[0].focus,'');const data=request('그 사람이 맡은 일은 끝났어?','two',ctx),p=dialogue.resolve(data,scope);assert(p.clarification);
 const waiting=dialogue.update(p,data,dialogue.policy(p)),next=dialogue.resolve(request('지연','three',waiting),scope);assert.equal(next.resolvedQuestion,data.text);assert.equal(next.modelContext.user_selection,'지연');assert.equal(next.clarification,null);
});
test('ambiguous returns clarify and selecting a candidate cannot select another conversation',()=>{
 let ctx=remember(context.empty('thread-a'),'서버 배포 담당은?',{});
 ctx=remember(ctx,'누리 숙소 예약 상태는?',{answer:'예약했습니다.',citations:[citation(b)]},'two');
 const p=dialogue.resolve(request('아까 이야기로 돌아가자','three',ctx),scope);assert(p.clarification);assert.equal(p.choices.length,2);
 const selected=dialogue.resolve({...request('아까 이야기로 돌아가자','four',ctx),context_selection:ctx.topics[0].id},scope);assert.equal(selected.topic.label,a.metadata.title);
 assert.throws(()=>dialogue.resolve({...request('그 사람은?','four',ctx),context_selection:'foreign-topic'},scope));
 assert.throws(()=>context.normalize(ctx,'thread-b'));
});
test('stale, fabricated and unavailable references cannot become current facts or keep a selected person',()=>{
 const ctx=remember(context.empty('thread-a'),'서버 배포 담당은?',{});
 const newer={...scope,sources:[{...a,revision:2,text:'현재는 수진이 담당한다.'},b]};
 const p=dialogue.resolve(request('그 사람이 맡은 일은 끝났어?','two',ctx),newer);assert(p.clarification);assert.deepEqual(p.references,[]);assert.equal(p.topic.focus,'');
 const forged=structuredClone(ctx);forged.topics[0].references[0].quote='운영 배포를 완료했다.';const q=dialogue.resolve(request('그 사람이 끝냈어?','two',forged),scope);assert(q.clarification);assert.deepEqual(q.references,[]);
 const crossed=dialogue.resolve({...request('그 사람은?','two',ctx),collection_id:'samples',profile:'development'},scope);assert(crossed.clarification);assert.equal(crossed.topic,null);
});
test('user correction updates discourse selection without editing raw records',()=>{
 const ctx=remember(context.empty('thread-a'),'서버 배포 담당은?',{}),data=request('지연이 아니라 수진이야','two',ctx),plan=dialogue.resolve(data,scope),app=dialogue.policy(plan),out=dialogue.update(plan,data,app);
 assert.equal(plan.relation,'correction');assert.equal(out.topics[0].focus,'수진');assert.deepEqual(out.topics[0].references,[]);assert.match(app.answer,/원문은 바꾸지/);assert(a.text.includes('지연'));
});
test('cancel affects only the selected pending proposal, and confirmation never performs an unconnected write',()=>{
 let ctx=remember(context.empty('thread-a'),'오늘 도예 수업을 들었어. 기록해줘',{intent:'experience',action:'draft',answer:'도예 수업을 들었다. 저장 전 초안입니다.',citations:[]});
 ctx=remember(ctx,'어제 산 책을 기억해줘',{intent:'experience',action:'draft',answer:'어제 책을 샀다. 저장 전입니다.',citations:[]},'two');
 const ambiguous=dialogue.resolve(request('그 작업 취소해줘','three',ctx),scope);assert(ambiguous.clarification);assert.equal(ambiguous.cancelled.length,0);
 const target=ctx.pending[0].id,data={...request('그 작업 취소해줘','three',ctx),pending_target:target},plan=dialogue.resolve(data,scope),out=dialogue.update(plan,data,dialogue.policy(plan));
 assert.equal(out.pending.find(p=>p.id===target).status,'cancelled');assert.equal(out.pending[1].status,'awaiting_confirmation');
 const confirmation=dialogue.policy(dialogue.resolve(request('수정 반영','four',out),scope));assert.equal(confirmation.action,'clarify');assert.match(confirmation.answer,/직접 실행할 수 없/);
});
test('explicit mixed requests split independent tasks without splitting quoted user content',()=>{
 assert.deepEqual(dialogue.splitTasks('내 기록에서 누리 숙소 결제 금액을 알려주고 오늘 도예 수업을 들은 일을 기록해줘'),['내 기록에서 누리 숙소 결제 금액을 알려줘','오늘 도예 수업을 들은 일을 기록해줘']);
 assert.deepEqual(dialogue.splitTasks('“A. B.”를 기록해줘'),['“A. B.”를 기록해줘']);
 assert.equal(dialogue.splitTasks('서버 배포 담당을 알려주고 오늘 도예 수업을 들은 일을 기록해줘').length,2);
});
test('late A responses cannot replace B context, another conversation, or a newly edited draft',()=>{
 const thread={id:'thread-a',draft:'A',inputVersion:1,messages:[]},a=state.submission(thread,{collectionId:'personal',profile:'personal'}),out={...a.context,revision:1,last_request:a.request_id};
 thread.draft='B';thread.contextRequest='newer-request';assert.equal(context.apply(thread,a,out),false);assert.equal(thread.draft,'B');
 thread.contextRequest=a.request_id;assert.equal(context.apply(thread,a,out),true);assert.equal(thread.draft,'B');assert.equal(context.apply({id:'thread-b'},a,out),false);
 const serialized=JSON.stringify(a.context);thread.context.topics.push({});assert.equal(JSON.stringify(a.context),serialized);assert(Object.isFrozen(a.context.topics));
});
test('context, pending proposals, task results and reference IDs survive backup and conflict-copy remapping',()=>{
 const ctx=remember(context.empty('thread-a'),'서버 배포 담당은?',{}),s=request('서버 배포 담당은?'),r={request_id:s.request_id,thread_id:s.thread_id,intent:'memory_query',action:'answer',answer:'지연입니다.',citations:[citation()],scope:{mode:'personal',accessible_count:2,retrieved_count:1},context:ctx,context_info:{relation:'new_topic',topic:null,choices:[]}};
 const t={id:'thread-a',draft:'새 초안',context:ctx,messages:[{kind:'assistant',status:'success',submission:s,result:r}]},restored=readBackup(makeBackup({threads:[t]},'chat'));
 assert.deepEqual(restored.threads[0].context,ctx);assert.deepEqual(restored.threads[0].messages[0].submission.context,s.context);
 const changed=structuredClone(t);changed.title='다른 내용';const merged=merge({threads:[changed],records:[]},restored,{conflicts:'copy'}),copy=merged.state.threads[1];assert.notEqual(copy.id,'thread-a');assert.equal(copy.context.thread_id,copy.id);assert.equal(copy.messages[0].submission.context.thread_id,copy.id);
 const local=context.rebind(structuredClone(t),'local-copy');assert.equal(local.context.thread_id,'local-copy');assert.equal(local.messages[0].result.context.thread_id,'local-copy');assert.doesNotThrow(()=>makeBackup({threads:[local]},'chat'));
});
async function client(t,run,options={}){
 const api=createChatApi(root,{runtime:async()=>({chat:run}),scope:async()=>scope,...options});const server=http.createServer((req,res)=>api.handle(req,res,new URL(req.url,'http://127.0.0.1')));await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));t.after(()=>new Promise(resolve=>server.close(resolve)));
 const url='http://127.0.0.1:'+server.address().port,{token}=await(await fetch(url+'/api/chat/bootstrap')).json();return async body=>{const res=await fetch(url+'/api/chat/respond',{method:'POST',headers:{'Content-Type':'application/json','X-Plant-Token':token},body:JSON.stringify(body)});return {status:res.status,value:await res.json()};};
}
test('real API carries verified follow-up context, clears unrelated history, and validates the citation topic',async t=>{
 let mode='good';const post=await client(t,async(messages,outputSchema)=>{const input=JSON.parse(messages[1].content);assert.equal(input.conversation_context.topic,a.metadata.title);assert.equal(input.conversation_context.selected_target,'지연');assert(!JSON.stringify(input).includes('잘못된 이전 AI 답변'));const evidence=input.evidence.find(e=>e.source_id===(mode==='good'?a.id:b.id));return {parsed:{intent:'memory_query',action:outputSchema.properties.action.enum[0],answer:outputSchema.properties.answer.enum?.[0]||'운영 배포 완료 보고는 아직 없습니다.',citations:[{evidence_id:evidence?.evidence_id||'outside-task',sentence_id:mode==='good'?'S3':'S1'}]}};});
 const ctx=remember(context.empty('thread-a'),'서버 배포 담당은?',{}),data={...request('그 사람이 맡은 서버는 배포가 끝났어?','two',ctx),history:['잘못된 이전 AI 답변']};
 const r=await post(data);assert.equal(r.status,200);assert.equal(r.value.inspection.checks.conversation_context,'passed');assert.equal(r.value.context_info.relation,'continue');
 mode='wrong';const bad=await post({...data,request_id:'three'});assert.equal(bad.status,502);assert(bad.value.inspection.checks.conversation_context==='failed'||bad.value.inspection.checks.citation_references==='failed');assert.equal(bad.value.answer,undefined);
});
test('mixed request partial failure retries only the failed task and preserves completed work',async t=>{
 let queries=0,drafts=0;
 const post=await client(t,async messages=>{const p=JSON.parse(messages[1].content);if(p.question.includes('금액')){queries++;const e=p.evidence.find(e=>e.source_id===b.id);return {parsed:{intent:'memory_query',action:'answer',answer:'18만 원입니다.',citations:[{evidence_id:e.evidence_id,sentence_id:'S1'}]}};}drafts++;assert.deepEqual(p.evidence,[]);if(drafts===1)throw Error('검증용 일시 오류');return {parsed:{intent:'experience',action:'draft',answer:'오늘 산책을 20분 했다. 아직 저장 전입니다.',citations:[]}};});
 const data=request('내 기록에서 누리 숙소 결제 금액을 알려주고 오늘 산책 20분을 기록해줘','mixed');
 const first=await post(data);assert.equal(first.status,200);assert.equal(first.value.parts[0].status,'success');assert.equal(first.value.parts[1].status,'error');assert.equal(first.value.context.pending.length,0);
 const second=await post(data);assert.equal(second.status,200);assert.equal(second.value.parts[1].status,'success');assert.equal(queries,1);assert.equal(drafts,2);assert.equal(second.value.context.pending.length,1);assert.equal(second.value.stored,false);
 assert.equal((await post({...data,text:'다른 요청'})).status,409);
 const s={...data},trow={id:data.thread_id,messages:[{kind:'assistant',status:'success',submission:s,result:second.value}]};assert.equal(readBackup(makeBackup({threads:[trow]},'chat')).threads[0].messages[0].result.parts.length,2);
});
test('saved completed subtasks resume after server restart without replaying success',async t=>{
 let queries=0,drafts=0,failed=true;
 const run=async messages=>{const input=JSON.parse(messages[1].content);if(input.question.includes('금액')){queries++;const e=input.evidence.find(e=>e.source_id===b.id);return {parsed:{intent:'memory_query',action:'answer',answer:'18만 원입니다.',citations:[{evidence_id:e.evidence_id,sentence_id:'S1'}]}};}drafts++;if(failed)throw Error('일시 오류');return {parsed:{intent:'experience',action:'draft',answer:'오늘 산책을 20분 했다. 저장 전입니다.',citations:[]}};};
 const data=request('내 기록에서 누리 숙소 결제 금액을 알려주고 오늘 산책 20분을 기록해줘','restart');
 const firstPost=await client(t,run),first=await firstPost(data);assert.equal(first.value.parts[1].status,'error');
 const receipt=readBackup(makeBackup({threads:[{id:data.thread_id,messages:[{kind:'assistant',status:'pending',submission:data,result:first.value}]}]},'chat')).threads[0].messages[0];
 failed=false;const restarted=await client(t,run,{resume:()=>({submission:receipt.submission,parts:receipt.result.parts})});
 const result=await restarted(data);assert.equal(result.status,200);assert.equal(queries,1);assert.equal(drafts,2);assert.equal(result.value.context.pending.length,1);
 assert.equal((await restarted({...data,request_id:'different',text:'내 기록에서 다른 금액을 알려주고 오늘 일을 저장해줘'})).status,409);
});
test('ambiguous references are an explicit clarification outcome and never trigger a model lookup',async t=>{
 let calls=0;const post=await client(t,async()=>{calls++;throw Error('must not run');});const r=await post(request('그 사람은 누구야?'));
 assert.equal(r.status,200);assert.equal(r.value.action,'clarify');assert.equal(calls,0);assert.equal(r.value.inspection.model_response_received,false);assert.equal(r.value.inspection.checks.conversation_context,'passed');
});
