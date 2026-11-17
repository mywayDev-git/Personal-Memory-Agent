'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),http=require('node:http'),path=require('node:path');
const root=process.env.PMA_APP_ROOT||path.resolve(__dirname,'..');
const {createChatApi,schema,instruction}=require(path.join(root,'ui/chat-api.cjs'));
const {chatRequest}=require(path.join(root,'local/token-budget.cjs'));
const {createInspection,normalizeInspection}=require(path.join(root,'ui/chat-inspection.cjs'));
const inspector=require(path.join(root,'ui/plant-thought/response-inspector.js'));
const state=require(path.join(root,'ui/plant-thought/chat-state.js'));
const {makeBackup,readBackup}=require(path.join(root,'ui/library.cjs'));
const source={id:'source-a',revision:1,text:'하린이 서재 백업을 확인했다.',metadata:{title:'백업 기록',created_at:'2026-11-17T10:00:00+09:00'}};
const submission=(overrides={})=>({request_id:'request-a',thread_id:'thread-a',text:'누가 백업을 확인했어?',input_version:1,collection_id:'personal',profile:'personal',example_id:'',history:['어제 백업 이야기를 했어.'],...overrides});
const response=(overrides={})=>({parsed:{intent:'memory_query',action:'answer',answer:'**하린**입니다.\n\n| 항목 | 값 |\n| --- | --- |\n| 확인자 | 하린 |',citations:[{evidence_id:'E1',sentence_id:'S1'}],...overrides},elapsed_ms:12,usage:{prompt_tokens:40,completion_tokens:20,total_tokens:60}});
async function client(t,run,scope){const api=createChatApi(root,{runtime:async()=>({chat:run}),scope:scope||(async()=>({id:'personal',now:'2026-11-17T10:00:00+09:00',sources:[source]}))});const server=http.createServer((req,res)=>api.handle(req,res,new URL(req.url,'http://127.0.0.1')));await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));t.after(()=>new Promise(resolve=>server.close(resolve)));const url='http://127.0.0.1:'+server.address().port;const {token}=await (await fetch(url+'/api/chat/bootstrap')).json();return async body=>{const res=await fetch(url+'/api/chat/respond',{method:'POST',headers:{'Content-Type':'application/json','X-Plant-Token':token},body:JSON.stringify(body)});return {status:res.status,data:await res.json()};};}
test('test request captures the exact instruction, input, schema and generation settings used by the call',async t=>{
 let called;const post=await client(t,async(messages,outputSchema,config)=>{called=chatRequest(messages,outputSchema,config);return response();});
 const r=await post(submission({inspect:true}));assert.equal(r.status,200);const s=r.data.inspection;assert.deepEqual(s.request_body,called);assert.equal(s.request_body.messages[0].content,instruction);assert.deepEqual(s.request_body.response_format.json_schema.schema,schema);assert.equal(s.model_response_received,true);assert.equal(s.stage,'complete');assert.equal(s.checks.schema,'passed');assert.equal(s.checks.citation_references,'passed');assert.deepEqual(s.output,response().parsed);
 const input=JSON.parse(s.request_body.messages[1].content);assert.equal(input.question,submission().text);assert.deepEqual(input.previous_user_questions,submission().history);assert.equal(input.evidence[0].source_id,source.id);assert.equal(input.evidence[0].sentences[0].text,source.text);assert.equal(input.gold,undefined);assert.equal(input.answer,undefined);
});
test('normal requests have no execution snapshot and inspection never adds model calls or modifies the answer',async t=>{
 let calls=0;const post=await client(t,async()=>{calls++;return response();});const a=await post(submission());assert.equal(a.data.inspection,undefined);const b=await post(submission({request_id:'request-b',inspect:true}));assert.equal(calls,2);assert.equal(a.data.answer,b.data.answer);const again=await post(submission({request_id:'request-b',inspect:true}));assert.deepEqual(again.data,b.data);assert.equal(calls,2);
 assert.equal((await post(submission({inspect:'true',request_id:'bad'}))).status,400);
});
test('schema, citation and write-policy failures report only checks actually completed',async t=>{
 let mode='schema';const post=await client(t,async()=>mode==='schema'?response({intent:'invalid'}):mode==='citation'?response({citations:[{evidence_id:'E404',sentence_id:'S1'}]}):response({intent:'delete',action:'answer'}));
 const a=await post(submission({inspect:true}));assert.equal(a.status,502);assert.equal(a.data.inspection.stage,'validation');assert.equal(a.data.inspection.checks.schema,'failed');assert.equal(a.data.inspection.checks.citation_references,'not_run');assert.equal(a.data.inspection.output,undefined);
 mode='citation';const b=await post(submission({inspect:true}));assert.equal(b.status,502);assert.equal(b.data.inspection.checks.schema,'passed');assert.equal(b.data.inspection.checks.citation_references,'failed');assert.equal(b.data.inspection.checks.required_citations,'not_run');assert.equal(b.data.answer,undefined);
 mode='write';const c=await post(submission({inspect:true}));assert.equal(c.status,502);assert.equal(c.data.inspection.checks.write_policy,'failed');assert.equal(c.data.inspection.checks.citation_references,'not_run');
});
test('scope failures do not invent prepared input, model output or completed validation',async t=>{
 let calls=0;const post=await client(t,async()=>{calls++;return response();},async()=>{throw Error('범위 확인 실패');});const r=await post(submission({inspect:true}));assert.equal(r.status,502);assert.equal(calls,0);assert.equal(r.data.inspection.stage,'scope');assert.equal(r.data.inspection.input_prepared,false);assert.equal(r.data.inspection.model_response_received,false);assert.equal(r.data.inspection.request_body.messages.length,1);assert.ok(Object.values(r.data.inspection.checks).every(v=>v==='not_run'));
});
test('missing facts and draft actions remain successful outcomes with the corresponding classification',async t=>{
 let mode='missing';const post=await client(t,async()=>mode==='missing'?response({action:'abstain',answer:'확인할 수 없습니다.',citations:[]}):response({intent:'experience',action:'draft',answer:'기록 초안입니다.',citations:[]}));const a=await post(submission({inspect:true}));assert.equal(a.status,200);assert.equal(a.data.inspection.output.action,'abstain');assert.equal(a.data.inspection.checks.required_citations,'not_required');mode='draft';const b=await post(submission({inspect:true,request_id:'b'}));assert.equal(b.data.stored,false);assert.equal(b.data.inspection.output.action,'draft');
});
test('test mode is captured in the immutable submission and cannot drift on retries',()=>{
 const t={id:'thread-a',draft:'질문',messages:[]};const normal=state.submission(t,{collectionId:'personal',profile:'personal',questionId:''});assert.equal(normal.inspect,undefined);const inspected=state.submission(t,{collectionId:'personal',profile:'personal',questionId:''},{inspect:true});assert.equal(inspected.inspect,true);assert.equal(Object.isFrozen(inspected),true);t.draft='다른 질문';assert.equal(inspected.text,'질문');assert.equal(inspected.inspect,true);
});
test('saved and exported conversations retain historical execution snapshots, including failed requests',async t=>{
 const post=await client(t,async()=>response()),r=await post(submission({inspect:true}));const success={kind:'assistant',status:'success',submission:submission({inspect:true}),result:r.data,inspectionExpanded:true};const failed={kind:'assistant',status:'error',submission:submission({inspect:true}),inspection:{...r.data.inspection,stage:'model',model_response_received:false,output:undefined},error:'검증용 오류',stage:'model'};
 const backup=makeBackup({threads:[{id:'thread-a',title:'테스트',messages:[success,failed]}]},'chat');const restored=readBackup(JSON.parse(JSON.stringify(backup))).threads[0].messages;assert.deepEqual(restored[0].result.inspection,r.data.inspection);assert.equal(restored[0].submission.inspect,true);assert.equal(restored[0].inspectionExpanded,true);assert.equal(restored[1].inspection.stage,'model');assert.equal(restored[1].inspection.output,undefined);assert.ok(!JSON.stringify(backup).includes('Authorization'));
});
test('historical responses without snapshots show only known output classification',()=>{
 const d=inspector.describe({status:'success',submission:submission(),result:{intent:'emotion',action:'empathy',answer:'수고했어요.',citations:[]}});assert.equal(d.snapshot,null);assert.match(d.intent,/감정 공유/);assert.match(d.action,/공감/);assert.equal(d.input,null);
});
class Element{
 constructor(tag){this.tag=tag;this.children=[];this.ownText='';}
 set textContent(v){this.ownText=String(v);}get textContent(){return this.ownText+this.children.map(c=>c.textContent).join('');}
 set innerHTML(v){throw Error('Untrusted inspection text must never become HTML');}
 append(...nodes){this.children.push(...nodes);}querySelector(){return null;}
}
test('inspector is absent in normal mode and renders hostile model/input text only as literal text',()=>{
 assert.equal(inspector.render({createElement(){throw Error('Normal mode must not build debug DOM');}},{},null,false),null);
 const hostile='<img src=x onerror=alert(1)>',m={status:'success',submission:{text:hostile,history:[]},result:{intent:'general',action:'advice',answer:hostile,citations:[]}};const doc={createElement:tag=>new Element(tag)},answer={querySelector:selector=>['p','table'].includes(selector)?{}:null};const panel=inspector.render(doc,m,answer,true);assert.equal(panel.tag,'details');assert.ok(panel.textContent.includes(hostile));assert.match(panel.textContent,/문단 · 표/);assert.match(panel.textContent,/실행 기록이 없습니다/);assert.ok(!panel.textContent.includes('JSON Schema · 필수 항목'));
});
test('snapshot normalization whitelists the contract and strips unrelated transport metadata',()=>{
 const body=chatRequest([{role:'system',content:instruction}],schema,{seed:42,context_tokens:8192,output_tokens:1536});const s=createInspection(body,8192);s.api_key='secret';s.request_body.Authorization='secret';s.request_body.messages[0].reasoning='hidden';const copy=normalizeInspection(s);assert.ok(!JSON.stringify(copy).includes('secret'));assert.ok(!JSON.stringify(copy).includes('hidden'));assert.throws(()=>normalizeInspection({...s,checks:{schema:'passed'}}));
});
