'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),http=require('node:http'),path=require('node:path');
const root=path.resolve(__dirname,'..'),{createChatApi}=require('../ui/chat-api.cjs'),state=require('../ui/plant-thought/chat-state.js'),maps=require('../ui/plant-thought/dialogue-map.js'),context=require('../ui/plant-thought/conversation-context.js'),{makeBackup,readBackup,merge}=require('../ui/library.cjs');
const now='2026-11-18T04:00:00+09:00';
function decision(text,userId,old,batch){
 let id='P2',kind='story',title='공부와 마음',operation='reply',intent='emotion',source='conversation',relation=old.some(p=>p.id===id)?'continue':'new_topic',status='open',speech='statement',scope='selected_parts',selected=['P2'];
 if(/앞으로/.test(text)){id='P1';kind='directive';title='기록 지시';operation='directive';intent='general';source='none';relation='directive';speech='instruction';selected=[];}
 if(/끝|여기까지/.test(text)){id='P2';operation='close';intent='general';source='none';relation='close';speech='closing';status='closed';}
 if(/기록해|내용들|기분을 기록/.test(text)&&!/앞으로/.test(text)){id='P3';kind='task';title='대화 기록 요청';operation='draft';intent='experience';source='conversation';relation='target';speech='reference';scope='all_conversation';}
 if(/더하면/.test(text)){id='P4';kind='task';title='계산';operation='reply';intent='general';source='none';relation='new_topic';speech='question';selected=[];}
 const ids=batch.filter(t=>t.role==='user').map(t=>t.id);
 let parts=[{id,title,summary:kind==='story'?'사용자가 힘듦과 공부의 어려움을 이야기함.':title,kind,status,turn_ids:ids.length?ids:[userId],related_ids:[]}];
 if(batch.filter(t=>t.role==='user').length>1){const grouped=new Map();for(const t of batch.filter(t=>t.role==='user')){const p=decision(t.text,t.id,old,[]).parts[0],previous=grouped.get(p.id);if(previous)p.turn_ids=[...previous.turn_ids,...p.turn_ids];grouped.set(p.id,p);}parts=[...grouped.values()];}
 return {parts,decision:{operation,intent,source,relation,scope,speech,selected_part_ids:selected,augmented_request:operation==='draft'?'현재 대화에서 지금까지 사용자가 말한 내용을 기록 초안으로 정리한다.':text,clarification:''}};
}
async function app(t,change,options={}){
 const thread={id:'map-test',draft:'',inputVersion:0,messages:[]};let modelCalls=0,scopeCalls=0;
 const runtime={chat:async(messages,schema)=>{const input=JSON.parse(messages[1].content);modelCalls++;
  if(input.phase==='semantic_speech'){const v=decision(input.latest_input,'current',[],[]).decision;return {parsed:{kind:/내 기록에서/.test(input.latest_input)?'question':v.operation==='directive'||v.operation==='draft'?'instruction':v.operation==='close'?'reference':v.intent==='emotion'?'statement':'question'}};}
  if(input.phase==='semantic_report')return {parsed:{state_kind:'feeling',affirmed_quote:input.latest_input,rejected_quote:'',corrects_prior_interpretation:false}};
  if(input.phase==='semantic_duration')return {parsed:{duration:'once'}};
  if(input.phase==='semantic_frame')return {parsed:{subject:'',domain:'none'}};
  if(input.phase==='latest_turn'){
   const d=decision(input.latest_input,'current',[],[]),v=d.decision;
   const task=/내 기록에서/.test(input.latest_input)?'question_personal_memory':v.operation==='directive'?'change_recording':v.operation==='draft'?'request_fact_draft':v.operation==='close'?'close_topic':v.intent==='emotion'?'statement_emotion':'question_information';
   return {parsed:{task}};
  }
  if(input.phase==='semantic_setting')return {parsed:{value:'enabled'}};
  if(input.phase==='semantic_scope')return {parsed:{scope:'all_conversation'}};
  if(input.phase==='semantic_facts')return {parsed:{facts:input.conversation.filter(t=>t.role==='user'&&decision(t.text,t.id,[],[]).parts[0].kind==='story'&&!/끝|여기까지/.test(t.text)).map(t=>({turn_id:t.id,quote:t.text}))}};
  if(input.phase==='interpretation_review')return {parsed:{is_correct:true,needs_clarification:false,reason:''}};
  if(input.phase==='response_review')return {parsed:{verdict:'valid',reason:''}};
  if(input.phase==='dialogue_map'){const text=[...input.new_turns].reverse().find(t=>t.role==='user')?.text||input.current_input;const out=decision(text,input.latest_user_id,input.parts,input.new_turns);if(input.latest_request)for(const key of ['intent','operation','source','speech'])out.decision[key]=input.latest_request[key];if(schema.properties.decision.properties.scope.enum.length===1)out.decision.scope=schema.properties.decision.properties.scope.enum[0];return {parsed:change?change(out,input):out};}
  assert.equal(typeof input.question,'string');assert(input.conversation_context.augmented_request);if(input.evidence.length)return {parsed:{intent:'memory_query',action:'answer',answer:'회사 하린입니다.',citations:[{evidence_id:input.evidence[0].evidence_id,sentence_id:'S1'}]}};
  assert.equal(schema.properties.citations.maxItems,0);
  return {parsed:{intent:input.request_contract.expected_intents[0],action:input.request_contract.expected_intents[0]==='emotion'?'empathy':'answer',answer:input.question.includes('더하면')?'12입니다.':'말씀하신 내용을 들었어요.',citations:[]}};
 }};
 const api=createChatApi(root,{runtime:async()=>runtime,now:()=>now,conversation:data=>maps.turns(thread,data.collection_id),scope:async data=>{scopeCalls++;if(options.scope)return options.scope(data);throw Error('현재 대화에서 보관소 검색이 실행됨');}}),server=http.createServer((req,res)=>api.handle(req,res,new URL(req.url,'http://127.0.0.1')));
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));t.after(()=>new Promise(resolve=>server.close(resolve)));const url='http://127.0.0.1:'+server.address().port,{token}=await(await fetch(url+'/api/chat/bootstrap')).json();
 async function post(data){const response=await fetch(url+'/api/chat/respond',{method:'POST',headers:{'Content-Type':'application/json','X-Plant-Token':token},body:JSON.stringify(data)});return {status:response.status,value:await response.json()};}
 async function turn(text){thread.draft=text;thread.inputVersion++;const submission=state.submission(thread,{profile:'personal',collectionId:'personal'},{version:'v2',inspect:true});const m={kind:'assistant',status:'pending',submission,createdAt:now};thread.contextRequest=submission.request_id;thread.messages.push({kind:'user',text,requestId:submission.request_id,createdAt:now},m);const result=await post(submission);if(result.status===200){m.result=result.value;m.status='success';state.applyContext(thread,submission,result.value.context,result.value.map_context);}return {...result,submission};}
 return {thread,post,turn,get modelCalls(){return modelCalls;},get scopeCalls(){return scopeCalls;}};
}
test('reported conversation uses LLM part selection and real user turns without any archive retrieval',async t=>{
 const a=await app(t);for(const text of ['앞으로 대화들 저장해줘','나 너무 힘들어','나 너무 바보 같아서','공부가 잘안돼','이야기 끝이야']){const r=await a.turn(text);assert.equal(r.status,200,JSON.stringify(r.value));assert.equal(r.value.analysis_version,'v2');}
 const closed=a.thread.mapContext.parts.find(p=>p.id==='P2');assert.equal(closed.status,'closed');assert.equal(a.thread.mapContext.flow.directives[0].value,'enabled');
 await a.turn('대화 기록해줘');const final=await a.turn('지금까지 이야기한 내용들');assert.equal(final.status,200,JSON.stringify(final.value));assert.match(final.value.answer,/공부가 잘안돼/);assert.match(final.value.answer,/나 너무 힘들어/);assert(!final.value.answer.includes('공방'));assert.equal(final.value.dialogue_trace.source,'conversation');assert.equal(final.value.dialogue_trace.original,'지금까지 이야기한 내용들');assert.equal(final.value.scope.mode,'conversation');assert.equal(a.scopeCalls,0);assert.equal(final.value.stored,false);
 assert(a.modelCalls>=7);assert.equal(final.value.map_context.revision,7);assert.equal(final.value.map_context.parts[0].id,'P1');
});
test('version snapshots and late response guards keep V1, V2 and a new draft independent',()=>{
 const thread={id:'thread',messages:[],draft:'새 질문',inputVersion:1,context:context.empty('thread')};thread.context.directives.push({id:'d',type:'style',value:'brief',scope:'personal',request_id:'old',text:'짧게',turn:1});
 const a=state.submission(thread,{profile:'personal',collectionId:'personal'},{version:'v2'}),old=JSON.stringify(thread.context);assert.equal(a.context.directives.length,0);assert.equal(a.analysis_version,'v2');assert(Object.isFrozen(a.map_context));
 const next={...a.map_context,revision:1,last_request:a.request_id,flow:a.context};thread.contextRequest='later';assert.equal(state.applyContext(thread,a,a.context,next),false);thread.contextRequest=a.request_id;assert.equal(state.applyContext(thread,a,a.context,next),true);assert.equal(JSON.stringify(thread.context),old);assert.equal(thread.draft,'새 질문');
 const b=state.submission(thread,{profile:'personal',collectionId:'personal'},{version:'v1'});assert.equal(b.analysis_version,undefined);assert.equal(b.context.directives[0].value,'brief');
});
test('first switch to V1 never migrates V2 result context as its legacy state',()=>{
 const thread={id:'v2-only',messages:[],draft:'질문',inputVersion:0},c=context.empty('v2-only');c.revision=7;c.directives=[{id:'d',type:'record',value:'enabled',scope:'personal',request_id:'old',text:'기록해줘',turn:1}];thread.messages.push({kind:'assistant',status:'success',submission:{analysis_version:'v2'},result:{context:c,citations:[]}});
 const next=state.submission(thread,{profile:'personal',collectionId:'personal'},{version:'v1'});assert.equal(next.context.revision,0);assert.deepEqual(next.context.directives,[]);
});
test('a model cannot attach invented or other-conversation turn IDs',async t=>{
 const a=await app(t,out=>{out.parts[0].turn_ids=['foreign-user'];return out;});const r=await a.turn('나 너무 힘들어');assert.equal(r.status,502);assert.equal(r.value.stage,'context');assert.equal(r.value.answer,undefined);assert.equal(a.scopeCalls,0);assert.equal(a.thread.mapContext,undefined);
});
test('current conversation cannot be silently changed to archive search by an interpretation error',async t=>{
 const a=await app(t,(out,input)=>{if(input.current_input.includes('지금까지'))out.decision.source='archive';return out;});await a.turn('나 너무 힘들어');const r=await a.turn('지금까지 이야기한 내용들');assert.equal(r.status,502);assert.equal(r.value.stage,'context');assert.equal(a.scopeCalls,0);
});
test('failed map analysis retries the immutable submission and never substitutes the current draft',async t=>{
 let broken=true;const a=await app(t,out=>{if(broken)out.parts[0].turn_ids=['missing'];return out;});const failed=await a.turn('나 너무 힘들어');a.thread.draft='새로 쓰는 입력';broken=false;const r=await a.post(failed.submission);assert.equal(r.status,200);assert.equal(r.value.dialogue_trace.original,'나 너무 힘들어');assert.equal(a.thread.draft,'새로 쓰는 입력');assert.equal((await a.post({...failed.submission,analysis_version:'v1'})).status,409);
});
test('first use rebuilds a chronological map and a summary beyond the legacy eight-utterance window',async t=>{
 const a=await app(t);for(let i=0;i<13;i++)a.thread.messages.push({kind:'user',text:'공부 이야기 '+i,requestId:'old-'+i,createdAt:now});const r=await a.turn('지금까지 대화 기록해줘');assert.equal(r.status,200,JSON.stringify(r.value));assert.match(r.value.answer,/공부 이야기 0/);assert.match(r.value.answer,/공부 이야기 12/);assert(r.value.dialogue_trace.analysis_calls>=2);assert.equal(a.scopeCalls,0);
});
test('backups and copied threads preserve both version states and dialogue-map provenance',async t=>{
 const a=await app(t);await a.turn('앞으로 대화들 저장해줘');await a.turn('나 너무 힘들어');const snapshot=readBackup(makeBackup({threads:[a.thread]},'chat'));assert.deepEqual(snapshot.threads[0].mapContext,a.thread.mapContext);assert.deepEqual(snapshot.threads[0].messages.at(-1).result.dialogue_trace,a.thread.messages.at(-1).result.dialogue_trace);
 const copied=merge({threads:[{...a.thread,title:'다른 제목'}],records:[]},snapshot,{conflicts:'copy'}).state.threads[1];assert.notEqual(copied.id,a.thread.id);assert.equal(copied.mapContext.thread_id,copied.id);assert.equal(copied.messages.at(-1).submission.map_context.thread_id,copied.id);assert.equal(copied.messages.at(-1).result.map_context.thread_id,copied.id);
 context.rebind(copied,'new-copy');assert.equal(copied.mapContext.thread_id,'new-copy');assert.doesNotThrow(()=>makeBackup({threads:[copied]},'chat'));
});
test('chronology is based on message order rather than the dates mentioned in the text',()=>{
 const thread={messages:[{kind:'user',requestId:'first',text:'어제 공부했어',createdAt:'2026-11-18T01:00:00Z'},{kind:'user',requestId:'second',text:'작년 일도 생각났어',createdAt:'2026-11-18T02:00:00Z'}]};assert.deepEqual(maps.turns(thread,'personal').map(t=>t.id),['u-first','u-second']);
});
test('V2 explicitly routed archive questions still retrieve and verify original citations',async t=>{
 const a=await app(t,(out,input)=>{out.parts[0]={id:'P1',title:'보고서 검토',summary:'보고서 담당 조회',kind:'task',status:'open',turn_ids:[input.latest_user_id],related_ids:[]};out.decision={...out.decision,intent:'memory_query',source:'archive',speech:'question',selected_part_ids:['P1']};return out;},{scope:()=>({id:'personal',now,sources:[{id:'report',revision:1,text:'회사 하린이 보고서 검토를 마쳤다.',metadata:{title:'보고서 검토',created_at:now}}]})});
 const r=await a.turn('내 기록에서 보고서 검토 담당자는 누구야?');assert.equal(r.status,200,JSON.stringify(r.value));assert.equal(r.value.dialogue_trace.source,'archive');assert.equal(a.scopeCalls,1);assert.equal(r.value.citations[0].quote,'회사 하린이 보고서 검토를 마쳤다.');assert.equal(r.value.scope.mode,'personal');
});
test('augmented input stays complete even when the model omits its natural-language rewrite',async t=>{
 const a=await app(t,out=>{out.decision.augmented_request='';return out;}),r=await a.turn('나 너무 힘들어');assert.equal(r.status,200);assert.match(r.value.dialogue_trace.augmented_request,/사용자 입력 원문: 나 너무 힘들어/);assert.match(r.value.dialogue_trace.augmented_request,/정보 출처: 현재 대화 원문/);assert.match(r.value.dialogue_trace.augmented_request,/연결한 파트: P2/);
});
test('omitted turns in a batch are individually reanalysed by the LLM rather than dropped',async t=>{
 const a=await app(t,(out,input)=>{const users=input.new_turns.filter(t=>t.role==='user');if(users.length>1)for(const p of out.parts)p.turn_ids=p.turn_ids.filter(id=>id===users.at(-1).id);out.parts=out.parts.filter(p=>p.turn_ids.length);return out;});
 for(let i=0;i<12;i++)a.thread.messages.push({kind:'user',text:'공부 이야기 '+i,requestId:'prior-'+i,createdAt:now});const r=await a.turn('지금까지 대화 기록해줘');assert.equal(r.status,200,JSON.stringify(r.value));assert.match(r.value.answer,/공부 이야기 0/);assert.match(r.value.answer,/공부 이야기 11/);assert(r.value.dialogue_trace.analysis_calls>2);assert.equal(a.scopeCalls,0);
});
test('ambiguous duplicate turn ownership is resolved by per-turn LLM analysis',async t=>{
 const a=await app(t,(out,input)=>{if(input.new_turns.filter(t=>t.role==='user').length>1)out.parts.push({...out.parts[0],id:'P4',kind:'task'});return out;});
 for(let i=0;i<4;i++)a.thread.messages.push({kind:'user',text:'공부 이야기 '+i,requestId:'duplicate-'+i,createdAt:now});const r=await a.turn('지금까지 대화 기록해줘');assert.equal(r.status,200,JSON.stringify(r.value));
 for(let i=0;i<4;i++)assert.equal(r.value.map_context.parts.filter(p=>p.turn_ids.includes('u-duplicate-'+i)).length,1);assert.match(r.value.answer,/공부 이야기 0/);assert.equal(a.scopeCalls,0);
});
test('an older assistant answer arriving later does not invalidate the chronological user map',async t=>{
 const a=await app(t);const first=await a.turn('나 너무 힘들어');await a.turn('나 너무 바보 같아서');a.thread.messages.splice(1,0,{kind:'assistant',status:'success',submission:{request_id:'late-answer',thread_id:a.thread.id,collection_id:'personal'},result:{answer:'늦게 온 참고 응답'}});
 const last=await a.turn('공부가 잘안돼');assert.equal(last.status,200,JSON.stringify(last.value));assert(last.value.map_context.processed_ids.includes('u-'+first.submission.request_id));assert.equal(a.scopeCalls,0);
});
