'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),http=require('node:http'),path=require('node:path'),fs=require('node:fs');
const root=process.env.PMA_APP_ROOT||path.resolve(__dirname,'..');
const {createChatApi,loadScope,retrieve}=require('../ui/chat-api.cjs');
const state=require('../ui/plant-thought/chat-state.js');
const source={id:'source-a',revision:1,text:'회사 하린이 표 두 개의 검토를 마쳤다.',metadata:{title:'보고서',created_at:'2026-10-30T00:00:00Z'}};
const data=()=>({request_id:'request-a',thread_id:'thread-a',text:'누가 검토했어?',input_version:1,profile:'development',example_id:'example-a',history:[]});
const result=(sentence_id='S1')=>({parsed:{intent:'memory_query',action:'answer',answer:'회사 하린입니다.',citations:[{evidence_id:'E1',sentence_id}]},usage:{total_tokens:42},elapsed_ms:1});
async function client(t,chatFn){
  const api=createChatApi(root,{runtime:async()=>({chat:chatFn}),scope:async()=>({id:'context-a',now:'2026-10-30',sources:[source]})});
  const server=http.createServer((req,res)=>api.handle(req,res,new URL(req.url,'http://127.0.0.1')));
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));t.after(()=>new Promise(resolve=>server.close(resolve)));
  const url='http://127.0.0.1:'+server.address().port,token=(await (await fetch(url+'/api/chat/bootstrap')).json()).token;
  return {post:async(value,headers={})=>{const response=await fetch(url+'/api/chat/respond',{method:'POST',headers:{'Content-Type':'application/json','X-Plant-Token':token,...headers},body:JSON.stringify(value)});return {status:response.status,value:await response.json()};}};
}
test('response validates citations and deduplicates only the identical immutable submission',async t=>{
  let calls=0;const app=await client(t,async messages=>{calls++;const prompt=JSON.parse(messages[1].content);assert.equal(prompt.question,'누가 검토했어?');assert.equal(prompt.evidence[0].sentences[0].text,source.text);assert.equal(prompt.gold,undefined);return result();});
  const a=await app.post(data()),b=await app.post(data());assert.equal(a.status,200);assert.deepEqual(a.value,b.value);assert.equal(calls,1);assert.equal(a.value.stored,false);assert.equal(a.value.citations[0].start,0);
  assert.equal((await app.post({...data(),text:'다른 질문'})).status,409);
});
test('invalid citations are processing failures, and retry can recover without changing the submission',async t=>{
  let calls=0;const app=await client(t,async()=>result(++calls===1?'S99':'S1'));
  const failed=await app.post(data());assert.equal(failed.status,502);assert.equal(failed.value.stage,'validation');assert.equal(failed.value.answer,undefined);
  assert.equal((await app.post(data())).status,200);assert.equal(calls,2);
});
test('normal missing evidence remains distinct from model failure',async t=>{
  let fail=false;const app=await client(t,async()=>{if(fail)throw Error('모델 출력 한도 초과');return {parsed:{intent:'memory_query',action:'abstain',answer:'현재 원문에서는 확인할 수 없습니다.',citations:[]}};});
  const absent=await app.post(data());assert.equal(absent.status,200);assert.equal(absent.value.action,'abstain');fail=true;
  const failed=await app.post({...data(),request_id:'request-b'});assert.equal(failed.status,502);assert.equal(failed.value.stage,'model');
});
test('concurrent repeats share inference and cross-origin or untrusted tokens never run it',async t=>{
  let calls=0;const app=await client(t,async()=>{calls++;await new Promise(resolve=>setTimeout(resolve,30));return result();});
  const pair=await Promise.all([app.post(data()),app.post(data())]);assert.equal(pair[0].status,200);assert.equal(pair[1].status,200);assert.equal(calls,1);
  assert.equal((await app.post(data(),{Origin:'http://untrusted.example'})).status,403);
  assert.equal((await app.post(data(),{'X-Plant-Token':'invalid'})).status,403);assert.equal(calls,1);
});
test('all examples search all 199 originals without gold answers or annotations',async()=>{
  const dir=path.join(root,'datasets/pma-generalization-v1.0.0'),questions=JSON.parse(fs.readFileSync(path.join(dir,'questions.json'))).questions;
  for(const q of questions){const scope=await loadScope(root,{profile:q.profile,example_id:q.id});assert.equal(scope.example_id,q.id);assert.equal(scope.id,'all-originals');assert.equal(scope.sources.length,199);assert.ok(scope.sources.some(s=>s.id==='D-EMPTY-PRIVATE'));assert.ok(scope.sources.some(s=>s.id==='C-EMPTY-PRIVATE'));assert.ok(scope.sources.every(s=>!('gold'in s)&&!('provenance'in s)));const evidence=retrieve(scope.sources,q.text);assert.ok(evidence.every(e=>scope.sources.some(s=>s.id===e.source_id&&s.text.slice(e.start,e.start+e.text.length)===e.text)));}
  await assert.rejects(()=>loadScope(root,{profile:'confirmation',example_id:questions.find(q=>q.profile==='development').id}),/선택한 사례/);
});
test('A fails, B is edited, then A retry succeeds: preserve B and the submitted history',()=>{
  const thread={id:'thread-a',draft:'A',inputVersion:1,messages:[{kind:'assistant',text:'사실로 쓰면 안 되는 이전 답변'},{kind:'user',text:'앞선 질문'}]};
  const a=state.submission(thread,{profile:'development',questionId:'example-a'});assert.deepEqual(a.history,['앞선 질문']);
  thread.draft='B';thread.inputVersion=2;assert.equal(state.complete(thread,a),false);assert.equal(thread.draft,'B');assert.equal(a.text,'A');
});
test('a development example retrieves confirmation originals from the same full catalog',async()=>{
  const questions=JSON.parse(fs.readFileSync(path.join(root,'datasets/pma-generalization-v1.0.0/questions.json'))).questions;
  const question=questions.find(q=>q.profile==='development'),scope=await loadScope(root,{profile:'development',example_id:question.id});
  const evidence=retrieve(scope.sources,'도서관 다솜이 맡은 일은?',[]);
  assert.ok(evidence.some(e=>e.source_id.startsWith('C-')&&e.text.includes('도서관 다솜')));
});
test('editing back to identical text still preserves a new draft; another conversation never clears',()=>{
  const thread={id:'thread-a',draft:'A',inputVersion:1,messages:[]},a=state.submission(thread,{profile:'development',questionId:'example-a'});
  thread.inputVersion=3;assert.equal(state.complete(thread,a),false);assert.equal(thread.draft,'A');
  assert.equal(state.complete({id:'thread-b',draft:'A',inputVersion:1},a),false);
  thread.inputVersion=1;assert.equal(state.complete(thread,a),true);assert.equal(thread.draft,'');
});
test('returning to a conversation restores its submitted scope; selecting another question changes only that thread',()=>{
  const a={id:'a',draft:'후속 질문',messages:[{submission:{profile:'development',example_id:'case-a'}}]},b={id:'b',sampleScope:{profile:'confirmation',questionId:'case-b'},messages:[]};
  const global={profile:'development',questionId:'case-empty'};
  assert.equal(state.scope(a,global).questionId,'case-a');assert.equal(state.scope(b,global).questionId,'case-b');
  a.sampleScope={profile:'development',questionId:'case-c'};assert.equal(state.scope(a,global).questionId,'case-c');assert.equal(state.scope(b,global).questionId,'case-b');
});

test('a late successful response never clears a deleted conversation draft',()=>{
  const thread={id:'thread-a',draft:'삭제하기 전 초안',inputVersion:1,messages:[]};
  const submitted=state.submission(thread,{profile:'development',questionId:'example-a'});thread.deletedAt=Date.now();
  assert.equal(state.complete(thread,submitted),false);assert.equal(thread.draft,submitted.text);
});
