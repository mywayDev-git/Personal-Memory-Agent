'use strict';
// These checks use stub model responses only. They never start or call a real LLM.
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const root=path.resolve(__dirname,'..');
const modes=require(path.join(root,'ui/plant-thought/search-modes.js'));
const {createChatRetrieval,originalEvidence}=require(path.join(root,'local/chat-retrieval.cjs'));
const {loadScope}=require(path.join(root,'ui/chat-api.cjs'));
const {Store}=require(path.join(root,'local/store.cjs')),{Engine}=require(path.join(root,'local/engine.cjs'));
const {hash}=require(path.join(root,'local/core.cjs'));
const {Library,makeBackup,readBackup}=require(path.join(root,'ui/library.cjs'));
const {ActionService}=require(path.join(root,'ui/action-service.cjs'));
const {respond}=require(path.join(root,'ui/goal-agent.cjs'));
function temporary(t,prefix){return fs.mkdtempSync(path.join(os.tmpdir(),prefix));}
function removeTemporary(dir){assert.equal(path.dirname(path.resolve(dir)),path.resolve(os.tmpdir()));fs.rmSync(dir,{recursive:true,force:true});}
function backend(t){
 const dir=temporary(t,'pma-chat-search-'),data=path.join(dir,'datasets/pma-generalization-v1.0.0');fs.mkdirSync(data,{recursive:true});
 const sources=[{id:'a',revision:1,text:'지연이 책을 전달했다.',metadata:{title:'책 전달',created_at:'2026-11-01T00:00:00Z'}},{id:'b',revision:1,text:'주말에는 공원에서 산책했다.',metadata:{title:'산책',created_at:'2026-11-02T00:00:00Z'}}];
 for(const [name,value] of Object.entries({sources:{records:sources},questions:{questions:[]},contexts:{contexts:[]}}))fs.writeFileSync(path.join(data,name+'.json'),JSON.stringify(value));
 const calls={ensure:[],embed:0,chat:0},runtime={allowStart(){},async ensure(role){calls.ensure.push(role);},async embed(){calls.embed++;return [1,0,0];},async chat(){calls.chat++;throw Error('A real model must never be called by this test.');},async tokenize(){return 20;},async countChatTokens(){return 100;},contextLimit(){return 8192;}};
 const store=new Store(dir);t.after(()=>{store.db.close();removeTemporary(dir);});const engine=new Engine(dir,store,runtime),api=createChatRetrieval(engine,runtime);
 return {dir,calls,runtime,engine,api,async request(mode,id='request'){const scope=await loadScope(dir,{collection_id:'samples',analysis_version:'v2'});return {request_id:id,collection_id:'samples',search_mode:mode,query:'책 전달',scope_hash:hash(scope.sources)};}};
}
test('R0 uses the real Lab keyword/vector retrieval and keeps raw citations',async t=>{
 const f=backend(t),result=await f.api.search(await f.request('R0'));
 assert.equal(result.trace.mode,'R0');assert.equal(result.trace.accessible_count,2);assert.ok(f.calls.embed>0);assert.equal(f.calls.chat,0);assert.equal(f.engine.busy,null);
 assert.ok(result.evidence.some(e=>e.source_id==='a'&&e.text.includes('지연')));assert.equal(f.api.status('request').status,'completed');
});
test('K1 prepares reusable raw indexes without using embeddings or a generation model',async t=>{
 const f=backend(t),first=await f.api.search(await f.request('K1','first')),second=await f.api.search(await f.request('K1','second'));
 assert.equal(first.trace.route,'K1');assert.equal(first.trace.preparation_reused,false);assert.equal(second.trace.preparation_reused,true);assert.equal(f.calls.embed,0);assert.equal(f.calls.chat,0);assert.ok(first.evidence.length);
});
test('R0-Full returns all originals and blocks when the actual token budget is too small',async t=>{
 const f=backend(t),result=await f.api.search(await f.request('R0-Full'));assert.equal(result.evidence.length,2);assert.equal(f.calls.embed,0);
 f.runtime.countChatTokens=async()=>100000;await assert.rejects(f.api.search(await f.request('R0-Full','too-large')),/예산 초과/);assert.equal(f.engine.busy,null);assert.equal(f.api.status('too-large').status,'failed');
});
test('every selected profile reaches the corresponding Lab configuration, with no silent fallback',async t=>{
 const f=backend(t),original=f.engine.config.bind(f.engine);let config;
 f.engine.config=input=>{config=input;return original(input);};f.runtime.ensure=async()=>{throw Error('stub model unavailable');};
 for(const mode of modes.modes.filter(m=>m.route)){
  await assert.rejects(f.api.search(await f.request(mode.id,mode.id)),['G1','G2'].includes(mode.route)?/그래프 색인/:/stub model unavailable/);
  assert.equal(config.route,mode.route);assert.equal(config.event_graph_mode,mode.event_graph_mode);assert.equal(f.engine.busy,null);assert.equal(f.api.status(mode.id).status,'failed');
 }
});
test('scope changes and unknown modes fail before model preparation',async t=>{
 const f=backend(t),request=await f.request('G1-linked');request.scope_hash='wrong';await assert.rejects(f.api.search(request),/범위가 바뀌/);assert.equal(f.calls.ensure.length,0);assert.equal(f.engine.busy,null);
 assert.throws(()=>modes.normalize('made-up'),/지원하지 않는/);
});
test('derived summary offsets never masquerade as raw citations; excerpts map back exactly',()=>{
 const source={id:'a',revision:1,text:'앞말. 실제 발췌. 뒷말.',metadata:{title:'제목'}};
 const generated={evidence:[{source_id:'a',revision:1,start:0,end:4,text:'모델 요약',origin:'summary'}]};
 assert.equal(originalEvidence(generated,[source])[0].text,source.text);
 const text='실제 발췌.',start=source.text.indexOf(text),record={summary_id:'summary',source_id:'a',summary:text,excerpt_selection:{ranges:[{start,end:start+text.length,excerpt_start:0,excerpt_end:text.length}]}};
 const hit={source_id:'a',revision:1,summary_id:'summary',origin:'summary',start:0,end:text.length,text};
 const result=originalEvidence({evidence:[hit,hit],summary_records:[record]},[source]);assert.equal(result.length,1);assert.equal(result[0].start,start);assert.equal(result[0].text,text);
 assert.throws(()=>originalEvidence({evidence:[{...hit,origin:'raw',text:'틀린 원문'}]},[source]),/일치하지/);
});
async function goal(t,{fail=false,skip=false}={}){
 const dir=temporary(t,'pma-goal-search-'),library=new Library(dir),service=new ActionService(library);t.after(()=>{library.close();removeTemporary(dir);});
 library.save(0,state=>({...state,threads:[{id:'thread',messages:[],draft:'새 초안',inputVersion:2}]}));
 const data={request_id:'request',thread_id:'thread',text:'누가 책을 전달했어?',input_version:1,analysis_version:'v2',conversation_ids:[],collection_id:'samples',profile:'development',example_id:'',history:[],inspect:true,search_mode:'G1-linked'};
 const source={id:'a',revision:1,text:'지연이 책을 전달했다.',metadata:{title:'책 전달'}};let searches=0;
 const runtime={async chat(messages){const phase=messages.map(m=>{try{return JSON.parse(m.content).phase;}catch{}}).find(Boolean);
  if(phase==='goal_plan')return {parsed:{goal:'책 전달자 조회',context_summary:'',related_turn_ids:[],task_id:'',reply_guidance:'',steps:skip?[]:[{tool:'search',purpose:'전달자 확인',query:'책 전달',target_id:'',source_turn_ids:[]}]}};
  if(phase==='goal_response')return {parsed:{support:fail||skip?[]:[{ref_id:'R1',finding:'지연이 전달'}],answer:fail?'확인할 수 없어요.':'지연입니다.',outcome:fail?'not_found':'answered',question:''}};
  throw Error('Unexpected stub phase: '+phase);
 }};
 const args={data,runtime,service,conversation:async()=>[],getScope:async()=>({id:'all-originals',sources:[source]}),retrieve(){throw Error('Legacy search must not run.');},async searchRecords(scope,query){searches++;if(fail)throw Error('그래프 준비 실패');return {evidence:[{source_id:source.id,revision:1,start:0,text:source.text,metadata:source.metadata}],trace:{mode:data.search_mode,query,accessible_count:1}};}};
 return {result:await respond(args),args,data,searches:()=>searches};
}
test('V2 uses only selected search observations; retries and backups retain the submitted mode',async t=>{
 const f=await goal(t);assert.equal(f.searches(),1);assert.equal(f.result.retrieval_trace.mode,'G1-linked');assert.equal(f.result.citations[0].quote,'지연이 책을 전달했다.');
 await respond(f.args);assert.equal(f.searches(),1);
 const backup=makeBackup({threads:[{id:'thread',messages:[{kind:'assistant',status:'success',submission:f.data,result:JSON.parse(JSON.stringify(f.result))}]}],records:[]},'chat');
 const restored=readBackup(backup).threads[0].messages[0];assert.equal(restored.submission.search_mode,'G1-linked');assert.equal(restored.result.retrieval_trace.mode,'G1-linked');
});
test('search failure is shown as failure instead of absent memory',async t=>{const f=await goal(t,{fail:true});assert.equal(f.result.retrieval_trace.status,'failed');assert.equal(f.result.action,'partial_answer');assert.match(f.result.retrieval_trace.searches[0].error,/그래프 준비 실패/);});
test('a goal without a search step records that no retrieval was performed',async t=>{const f=await goal(t,{skip:true});assert.equal(f.searches(),0);assert.equal(f.result.retrieval_trace.status,'skipped');});

// The tests below are prepared for manual execution; they do not call a real model.
test('graph search never prepares a missing index',async t=>{
 const f=backend(t);await assert.rejects(f.api.search(await f.request('G1-linked')),/색인 준비 버튼/);
 assert.equal(f.calls.ensure.length,0);assert.equal(f.calls.embed,0);assert.equal(f.calls.chat,0);
 assert.equal((await f.api.indexes.status('samples','G1-linked')).status,'not_prepared');
});
test('index identity ignores query/answer settings but includes extraction settings',t=>{
 const f=backend(t),{signature}=require(path.join(root,'local/chat-graph-index.cjs')),config=f.api.indexes.configFor('G1-linked');
 assert.equal(signature(config),signature({...config,top_k:1,query_prompt:'changed',answer_prompt_text:'changed',code_hash:'answer-only-change'}));
 assert.notEqual(signature(config),signature({...config,metadata_settings_hash:'new-extraction'}));
 assert.notEqual(signature(config),signature({...config,event_graph_mode:'claim-v1'}));
});
test('index jobs survive recreation and cancel only the selected job',async t=>{
 const f=backend(t);f.api.indexes.enqueue('samples','G1-linked');f.api.indexes.enqueue('samples','G1-claim');
 const restored=require(path.join(root,'local/chat-graph-index.cjs')).createGraphIndex(f.engine,f.runtime);
 assert.equal((await restored.status('samples','G1-linked')).status,'queued');
 restored.cancel('samples','G1-linked');assert.equal((await restored.status('samples','G1-linked')).status,'cancelled');assert.equal((await restored.status('samples','G1-claim')).status,'queued');
 assert.equal(f.calls.chat,0);await restored.close();
});
test('record changes emit a transactional notification; chat saves and excluded records do not',t=>{
 const dir=temporary(t,'pma-record-index-'),library=new Library(dir);t.after(()=>{library.close();removeTemporary(dir);});
 const change=fn=>{const state=library.read();return library.save(state.revision,fn);};
 assert.equal(library.indexNotice(),null);
 change(state=>({...state,records:[{id:'record',revision:1,title:'제목',body:'원문',date:null,created_at:null,search_enabled:true}]}));assert.equal(library.indexNotice().sequence,1);
 change(state=>({...state,threads:[]}));assert.equal(library.indexNotice().sequence,1);
 change(state=>({...state,records:state.records.map(r=>({...r,revision:2,body:'수정 원문'}))}));assert.equal(library.indexNotice().sequence,2);
 change(state=>({...state,records:state.records.map(r=>({...r,search_enabled:false}))}));assert.equal(library.indexNotice().sequence,3);
 change(state=>({...state,records:state.records.map(r=>({...r,revision:3,body:'검색 제외된 원문 수정'}))}));assert.equal(library.indexNotice().sequence,3);
 change(state=>({...state,records:state.records.map(r=>({...r,search_enabled:true}))}));assert.equal(library.indexNotice().sequence,4);
 change(state=>({...state,records:state.records.map(r=>({...r,revision:4,deleted_at:new Date().toISOString()}))}));assert.equal(library.indexNotice().sequence,5);
});
