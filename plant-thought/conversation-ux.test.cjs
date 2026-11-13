'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const crypto=require('node:crypto');
const {DatabaseSync}=require('node:sqlite');
const {createConversationUx,parseRecord}=require('./conversation-ux.cjs');
const {memoryKey}=require('../local/summary.cjs');
const {NAMESPACE,OWNER}=require('../local/summary-api-structured.cjs');
const blank={intent:'question',explicit_save:false,query:'어디 갔어?',reply:'',clarification:'',title:'',targets:[],choices:[],correction_before:'',correction_after:'',choice_id:''};
function fixture(t,{plans=[],rows=[],onSave,onSearch,onDelete}={}){
 const db=new DatabaseSync(':memory:'),data=new Map(),sources=new Map(),calls=[];
 t.after(()=>db.close());
 for(const [i,r] of rows.entries()){
  const row={memory_key:r.key||'k'+i,summary_artifact_id:r.version||'v'+i,namespace:r.namespace||NAMESPACE,owner:r.owner||OWNER,source_id:r.source_id||'s'+i,deleted_at:r.deleted_at||null};
  data.set(row.memory_key,row);sources.set(row.memory_key,r.text||'제목: 여행\n기록일: 2026-11-08\n감정: 미지정\n\n학교 민수와 부산에 갔다.');
 }
 const memory={
  get:key=>data.get(key),list:(ns,owner)=>[...data.values()].filter(r=>r.namespace===ns&&r.owner===owner&&!r.deleted_at),
  original:row=>({text:sources.get(row.memory_key)}),record:row=>({summary:parseRecord(sources.get(row.memory_key)).body}),
  view:row=>({...row,summary:parseRecord(sources.get(row.memory_key)).body}),
 };
 const engine={store:{db},summary:memory,busy:null,config:c=>({model:'model',route:'M1',top_k:3,...c})};
 const runtime={allowStart(){},ensure:async()=>{},tokenize:async text=>Math.ceil(text.length/4),chat:async(messages,schema)=>{
  const next=plans.shift();if(!next)throw Error('Unexpected model request');
  const response=typeof next==='function'?next(JSON.parse(messages.at(-1).content),schema):next;
  return {parsed:schema.properties.edits?response:{...blank,title:'',...response}};
 }};
 const base={
  async get(){return {base:true};},
  async post(route,input,options={}){
   calls.push({route,input,options});
   if(route.endsWith('/save')){
    if(onSave)await onSave(input);
    const old=input.key?data.get(input.key):null;
    if(old&&old.summary_artifact_id!==input.expected)throw Error('version conflict');
    const sourceId=old?.source_id||options.sourceId||crypto.randomUUID();
    const key=old?.memory_key||memoryKey(NAMESPACE,OWNER,sourceId);
    const row={memory_key:key,summary_artifact_id:'new-'+calls.length,namespace:NAMESPACE,owner:OWNER,source_id:sourceId,deleted_at:null};
    data.set(key,row);sources.set(key,input.text);return {memory:memory.view(row)};
   }
   if(route.endsWith('/search'))return onSearch?onSearch(input):{answer:{action:'abstain',answer:'찾은 기록에서는 확인하지 못했어요.',citations:[]}};
   if(route.endsWith('/delete')){
    if(onDelete)await onDelete(input);
    const row=data.get(input.key);if(!row||row.summary_artifact_id!==input.expected)throw Error('version conflict');
    row.deleted_at=new Date().toISOString();return {ok:true};
   }
   return {base:true};
  },
 };
 const ux=createConversationUx(engine,runtime,base);
 const request=(action,input={})=>ux.post('/summary-memory/ux/'+action,{session_id:'session-A',config:{model:'model',route:'M1',top_k:3},...input});
 return {db,data,sources,calls,engine,runtime,base,ux,request,plans,memory};
}
test('record headers and untouched body are separated without changing original content',()=>{
 const text='제목: 여행\n기록일: 2026-11-08\n감정: 미지정\n\n민수와 부산에 갔다.\n사진을 찍었다.';
 const p=parseRecord(text);assert.equal(p.header+p.body,text);assert.equal(p.title,'여행');assert.equal(p.date,'2026-11-08');
});

test('confirmed deletion removes only the selected memory and repeat requests remain idempotent',async t=>{
 const f=fixture(t,{rows:[{},{}]}),request_id=crypto.randomUUID();
 const result=await f.request('delete',{request_id,key:'k0',expected:'v0'});
 assert.equal(result.state,'committed');assert.equal(result.deleted_key,'k0');assert.equal(result.memory,undefined);
 assert.ok(f.data.get('k0').deleted_at);assert.equal(f.data.get('k1').deleted_at,null);
 assert.equal((await f.request('delete',{request_id,key:'k0',expected:'v0'})).state,'committed');assert.equal(f.calls.length,1);
 await assert.rejects(f.request('delete',{request_id,key:'k1',expected:'v1'}),/다른 기억/);
 await assert.rejects(f.request('status',{operation_id:request_id,session_id:'session-B'}),/현재 대화/);
});

test('deletion checks ownership and the reviewed version before making a write',async t=>{
 const f=fixture(t,{rows:[{}, {owner:'another-owner'}]});
 await assert.rejects(f.request('delete',{request_id:crypto.randomUUID(),key:'k0',expected:'old-version'}),/변경/);
 await assert.rejects(f.request('delete',{request_id:crypto.randomUUID(),key:'k1',expected:'v1'}),/사용할 수/);
 assert.equal(f.calls.length,0);assert.equal(f.data.get('k0').deleted_at,null);
});

test('unknown deletion results reconcile after restart without returning deleted source content',async t=>{
 const f=fixture(t,{rows:[{}]}),request_id=crypto.randomUUID();
 await f.request('delete',{request_id,key:'k0',expected:'v0'});
 const op=JSON.parse(f.db.prepare('SELECT payload FROM plant_ux_operations WHERE id=?').get(request_id).payload);
 op.state='running';f.db.prepare('UPDATE plant_ux_operations SET state=?,payload=? WHERE id=?').run('running',JSON.stringify(op),request_id);
 const restarted=createConversationUx(f.engine,f.runtime,f.base);
 const status=await restarted.post('/summary-memory/ux/status',{session_id:'session-A',operation_id:request_id});
 assert.equal(status.state,'committed');assert.equal(status.deleted_key,'k0');assert.equal(status.memory,undefined);assert.equal(f.calls.length,1);
});

test('a failed delete can retry the same operation but cannot delete a revised record',async t=>{
 let fail=true;const f=fixture(t,{rows:[{}],onDelete:()=>{if(fail)throw Error('offline');}}),request_id=crypto.randomUUID();
 assert.equal((await f.request('delete',{request_id,key:'k0',expected:'v0'})).state,'failed');assert.equal(f.data.get('k0').deleted_at,null);
 f.data.get('k0').summary_artifact_id='new-version';fail=false;
 assert.equal((await f.request('delete',{request_id,key:'k0',expected:'v0'})).state,'conflict');assert.equal(f.data.get('k0').deleted_at,null);assert.equal(f.calls.length,1);
});
test('duplicate save submissions and repeated status checks produce exactly one write',async t=>{
 const f=fixture(t);const request_id=crypto.randomUUID(),text='동일 작업의 본문';
 const a=await f.request('save',{request_id,text}),b=await f.request('save',{request_id,text});
 assert.equal(a.state,'committed');assert.equal(b.memory.memory_key,a.memory.memory_key);assert.equal(f.calls.length,1);assert.equal(f.data.size,1);
 assert.equal((await f.request('status',{operation_id:request_id})).state,'committed');
});
test('distinct intentional saves with identical content remain distinct operations',async t=>{
 const f=fixture(t);await f.request('save',{request_id:crypto.randomUUID(),text:'같은 내용'});await f.request('save',{request_id:crypto.randomUUID(),text:'같은 내용'});
 assert.equal(f.data.size,2);
});
test('same request ID cannot be reused with changed content or another conversation',async t=>{
 const f=fixture(t),id=crypto.randomUUID();await f.request('save',{request_id:id,text:'원문'});
 await assert.rejects(f.request('save',{request_id:id,text:'다른 원문'}),/다른 내용/);
 await assert.rejects(f.request('status',{operation_id:id,session_id:'session-B'}),/현재 대화/);
});
test('concurrent duplicate submissions join the same in-flight operation',async t=>{
 let release;const waiting=new Promise(resolve=>release=resolve);
 const f=fixture(t,{onSave:()=>waiting}),id=crypto.randomUUID();
 const first=f.request('save',{request_id:id,text:'본문'});const second=f.request('save',{request_id:id,text:'본문'});
 release();const [a,b]=await Promise.all([first,second]);assert.equal(f.calls.length,1);assert.equal(a.memory.memory_key,b.memory.memory_key);
});
test('commit result is reconciled after response bookkeeping loss and service recreation',async t=>{
 const f=fixture(t),id=crypto.randomUUID();const result=await f.request('save',{request_id:id,text:'보존할 원문'});
 const op=JSON.parse(f.db.prepare('SELECT payload FROM plant_ux_operations WHERE id=?').get(id).payload);op.state='running';delete op.result_key;
 f.db.prepare('UPDATE plant_ux_operations SET state=?,payload=? WHERE id=?').run('running',JSON.stringify(op),id);
 const restarted=createConversationUx(f.engine,f.runtime,f.base);
 const status=await restarted.post('/summary-memory/ux/status',{session_id:'session-A',operation_id:id});
 assert.equal(status.state,'committed');assert.equal(status.memory.memory_key,result.memory.memory_key);assert.equal(f.calls.length,1);
});
test('failed write retains request and retries without changing operation identity',async t=>{
 let fail=true;const f=fixture(t,{onSave:()=>{if(fail)throw Error('쓰기 실패');}}),id=crypto.randomUUID();
 assert.equal((await f.request('save',{request_id:id,text:'보존할 원문'})).state,'failed');
 assert.equal(f.data.size,0);fail=false;
 assert.equal((await f.request('save',{request_id:id,text:'보존할 원문'})).state,'committed');assert.equal(f.data.size,1);
});
test('edit prepares an immutable reviewable draft, then checks expected version on commit',async t=>{
 const f=fixture(t,{rows:[{}],plans:[{intent:'edit',targets:['R1']},{edits:[{before:'민수',after:'지수',occurrence:1}],clarification:''}]});
 const prepared=await f.request('plan',{text:'학교 민수를 학교 지수로 수정해줘.'});
 assert.equal(prepared.intent,'edit');assert.match(prepared.before,/민수/);assert.match(prepared.after,/지수/);assert.equal(f.calls.length,0);
 f.data.get('k0').summary_artifact_id='changed-by-another-request';
 const result=await f.request('commit',{operation_id:prepared.operation_id});
 assert.equal(result.state,'conflict');assert.equal(f.calls.length,0);
});
test('edit cancellation performs no writes and committed cancellation is not a rollback',async t=>{
 const f=fixture(t,{rows:[{}],plans:[{intent:'edit',targets:['R1']},{edits:[{before:'민수',after:'지수',occurrence:1}],clarification:''}]});
 const p=await f.request('plan',{text:'동행인을 지수로 수정해줘.'});
 assert.equal((await f.request('cancel',{operation_id:p.operation_id})).state,'cancelled');
 await assert.rejects(f.request('commit',{operation_id:p.operation_id}),/취소/);assert.equal(f.calls.length,0);
 const id=crypto.randomUUID();await f.request('save',{request_id:id,text:'새 기록'});
 assert.equal((await f.request('cancel',{operation_id:id})).state,'committed');
});
test('homonym choices use actual record refs and do not change or merge stored people',async t=>{
 const f=fixture(t,{rows:[{}, {text:'제목: 회의\n기록일: 2026-11-09\n감정: 미지정\n\n회사 민수와 서울 회의에 갔다.'}],plans:[{intent:'unclear',clarification:'학교 관련 기록인가요, 회사 관련 기록인가요?',choices:[{label:'학교 관련 기록',ids:['R1']},{label:'회사 관련 기록',ids:['R2']}]}]});
 const result=await f.request('plan',{text:'민수랑 어디 갔었지?'});
 assert.equal(result.choices.length,2);
 const selected=await f.request('plan',{text:result.choices[0].label,decision_id:result.decision_id,choice_id:result.choices[0].id});
 assert.equal(selected.intent,'question');assert.ok(selected.scope_id);assert.equal(f.calls.length,0);
 await f.request('search',{query:selected.query,scope_id:selected.scope_id});
 assert.deepEqual(f.calls.at(-1).input.ux_source_keys,['k0']);
});
test('natural language and button selection resolve the same saved candidate scope',async t=>{
 const f=fixture(t,{rows:[{},{}],plans:[
 {intent:'unclear',clarification:'어느 기록인가요?',choices:[{label:'학교 관련 기록',ids:['R1']},{label:'회사 관련 기록',ids:['R2']}]},
 {intent:'question',choice_id:'C0'},
 ]});
 const p=await f.request('plan',{text:'민수랑 어디 갔어?'});
 const choice=await f.request('plan',{text:'학교에서 만난 민수 말이야.',decision_id:p.decision_id});
 await f.request('search',{query:choice.query,scope_id:choice.scope_id});
 assert.deepEqual(f.calls.at(-1).input.ux_source_keys,['k0']);
});
test('removed or revised records invalidate old scope and assistant conversation evidence',async t=>{
 const f=fixture(t,{rows:[{}]});
 f.data.get('k0').deleted_at='2026-11-13';
 await f.request('search',{query:'아까 위치가 어디였지?',conversation:[{role:'assistant',text:'책상 왼쪽 서랍',refs:[{key:'k0',version:'v0'}]}]});
 assert.equal(f.calls.at(-1).input.conversation.length,0);
 assert.equal((await f.request('access')).records.length,0);
});
test('current-conversation correction does not modify original or fabricate corrected source quote',async t=>{
 const f=fixture(t,{rows:[{}],plans:[{intent:'correction',targets:['R1'],correction_before:'민수',correction_after:'지수'}],
 onSearch:()=>({answer:{action:'answer',answer:'민수와 부산에 갔어요.',citations:[{source_id:'s0',quote:'학교 민수와 부산에 갔다.'}]}})});
 const before=f.sources.get('k0');
 const response=await f.request('plan',{text:'민수가 아니라 지수였어. 이번 대화에서만 바꿔줘.'});assert.equal(response.intent,'assistant');
 const result=await f.request('search',{query:'누구와 갔어?'});
 assert.match(result.answer.answer,/정정/);assert.match(result.answer.answer,/지수/);assert.match(result.answer.citations[0].quote,/민수/);assert.equal(f.sources.get('k0'),before);
 const other=await f.request('search',{query:'누구와 갔어?',session_id:'session-B'});assert.ok(!other.user_correction);
});
test('additional search widens one request without changing the default config',async t=>{
 const rows=Array.from({length:10},()=>({}));const f=fixture(t,{rows}),config={model:'model',route:'M1',top_k:3};
 await f.request('search',{query:'숙소는?',expand:true,config});assert.equal(f.calls.at(-1).input.config.top_k,8);assert.equal(config.top_k,3);
 await f.request('search',{query:'다른 질문',config});assert.equal(f.calls.at(-1).input.config.top_k,3);
});
test('unknown source choices and cross-owner records cannot become valid candidates',async t=>{
 const f=fixture(t,{rows:[{owner:'other-user'},{}],plans:[{intent:'unclear',clarification:'어느 사건인가요?',choices:[{label:'없는 기록',ids:['NONE']}]}]});
 await assert.rejects(f.request('plan',{text:'누구였지?'}),/형식/);
 assert.equal((await f.request('access')).records.length,1);
});
test('editing preserves unrelated sentences and adjusts a name particle without rewriting the body',async t=>{
 const text='제목: 여행\n기록일: 2026-11-08\n감정: 미지정\n\n지수와 부산에 갔다. 민수는 동행하지 않았다.';
 const f=fixture(t,{rows:[{text}],plans:[{intent:'edit',targets:['R1']},{edits:[{before:'지수',after:'예린',occurrence:1}],clarification:''}]});
 const p=await f.request('plan',{text:'동행인 지수를 예린으로 수정해줘.'});
 assert.equal(p.after,'예린과 부산에 갔다. 민수는 동행하지 않았다.');assert.equal(f.calls.length,0);
});
test('a proposed replacement not present in the user request is clarified instead of prepared',async t=>{
 const f=fixture(t,{rows:[{}],plans:[{intent:'edit',targets:['R1']},{edits:[{before:'민수',after:'지수는 부산을 방문한 유일한 사람',occurrence:1}],clarification:''}]});
 await assert.rejects(f.request('plan',{text:'민수를 지수로 수정해줘.'}),/형식/);
 assert.equal(f.calls.length,0);
});
test('an explicitly named record date resolves one record when the planner omits target IDs',async t=>{
 const f=fixture(t,{rows:[{}],plans:[{intent:'edit',targets:[]},{edits:[{before:'민수',after:'지수',occurrence:1}],clarification:''}]});
 const p=await f.request('plan',{text:'2026년 11월 8일 여행 기록의 민수를 지수로 수정해줘.'});
 assert.equal(p.intent,'edit');assert.equal(f.calls.length,0);
});
test('a model cannot authorize automatic saving from a quoted instruction',async t=>{
 const f=fixture(t,{plans:[{intent:'diary',explicit_save:true}]});
 const p=await f.request('plan',{text:'교육에서 “이 내용을 저장해줘”라는 말이 나왔는데 무슨 뜻이야?'});
 assert.equal(p.explicit_save,false);assert.equal(f.calls.length,0);
});
