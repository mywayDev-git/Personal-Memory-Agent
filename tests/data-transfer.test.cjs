'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),http=require('node:http');
const root=process.env.PMA_APP_ROOT||path.resolve(__dirname,'..');
const {Library,createLibraryApi,makeBackup,readBackup,planImport,merge,hash,markdown,payload}=require(process.env.PMA_LIBRARY_FILE||path.join(root,'ui/library.cjs'));
const record=(id='record-a')=>({id,revision:1,title:'한글 기록 🌱',body:'첫 줄\n둘째 줄 — 원문 그대로',date:'2026-11-17',created_at:'2026-11-17T12:00:00+09:00',search_enabled:true});
const thread=(id='thread-a')=>({id,title:'대화 제목',draft:'작성 중인 초안',createdAt:null,messages:[{kind:'user',text:'누가 왔어?',requestId:'request-a'},{kind:'assistant',status:'success',submission:{request_id:'request-a',thread_id:id,text:'누가 왔어?',input_version:1,profile:'personal',example_id:'',collection_id:'personal',history:[]},result:{request_id:'request-a',thread_id:id,intent:'memory_query',action:'answer',model:'Qwen',answer:'하린이 왔어요.\n\n근거입니다.',citations:[{source_id:'record-a',revision:1,title:'기록',quote:'첫 줄',start:0,end:3}],scope:{mode:'personal',accessible_count:1,retrieved_count:1}}}]});
const empty=()=>({threads:[],records:[]});
function temp(t){const dir=fs.mkdtempSync(path.join(os.tmpdir(),'pma-transfer-'));t._stores??=[];t.after(()=>{for(const store of t._stores)store.close();if(path.dirname(dir)===os.tmpdir()&&path.basename(dir).startsWith('pma-transfer-'))fs.rmSync(dir,{recursive:true,force:true});});return dir;}
function open(t){const dir=temp(t),store=new Library(dir);t._stores.push(store);return {dir,store};}
test('JSON round trip preserves Korean, newlines, unknown times, drafts and citation offsets',()=>{
 const input={threads:[thread()],records:[record()]},backup=makeBackup(input);const restored=readBackup(JSON.parse(JSON.stringify(backup)));
 assert.deepEqual(restored,payload(input));assert.equal(restored.threads[0].createdAt,null);assert.equal(restored.records[0].body,input.records[0].body);assert.equal(restored.threads[0].messages[1].result.citations[0].start,0);
 assert.match(markdown(restored),/작성 중인 초안/);assert.match(markdown(restored),/첫 줄\n둘째 줄/);
});
test('foreign, future, modified, malformed and inconsistent backups are rejected',()=>{
 const b=makeBackup({records:[record()]});for(const change of [{format:'chatgpt'},{version:2},{sha256:'0'.repeat(64)},{counts:{threads:0,records:3}},{kind:'chat'}])assert.throws(()=>readBackup({...b,...change}));
 const broken={...b,payload:{threads:[{id:'bad',messages:[null]}],records:[]}};broken.sha256=hash(broken.payload);assert.throws(()=>readBackup(broken));
 assert.throws(()=>makeBackup({records:[{...record(),date:'2026-02-30'}]}));assert.throws(()=>makeBackup({records:[record(),record()]}));
});
test('secrets and arbitrary executable markup stay outside exported metadata; text is retained literally',()=>{
 const t=thread();t.api_key='secret';t.messages[1].result.token='secret';t.messages[0].text='<img src=x onerror=alert(1)>';
 const b=makeBackup({threads:[t]});assert.ok(!JSON.stringify(b).includes('secret'));assert.equal(b.payload.threads[0].messages[0].text,t.messages[0].text);
});
test('merge handles duplicate, keep, copy and remaps citations and thread submissions together',()=>{
 const state=payload({threads:[thread()],records:[record()]});assert.equal(planImport(state,state).records.duplicate.length,1);
 const incoming=payload({threads:[{...thread(),title:'다른 제목'}],records:[{...record(),body:'수정된 원문'}]});
 assert.deepEqual(merge(state,incoming,{conflicts:'keep'}).counts,{threads:0,records:0,skipped:2});
 const copied=merge(state,incoming,{conflicts:'copy',searchEnabled:true});assert.equal(copied.counts.threads,1);assert.equal(copied.counts.records,1);
 const t=copied.state.threads[1],m=t.messages[1];assert.notEqual(t.id,'thread-a');assert.equal(m.submission.thread_id,t.id);assert.equal(m.result.thread_id,t.id);assert.equal(m.result.citations[0].source_id,copied.state.records[1].id);assert.equal(m.archived,true);
 assert.equal(state.records[0].body,record().body);
});
test('repeated imports skip duplicates even when archive search or replay policy changed',()=>{
 const incoming=readBackup(makeBackup({threads:[thread()],records:[record()]}));const first=merge(empty(),incoming,{searchEnabled:false});assert.equal(first.state.records[0].search_enabled,false);
 assert.equal(planImport(first.state,incoming).threads.duplicate.length,1);assert.equal(planImport(first.state,incoming).records.duplicate.length,1);
 assert.deepEqual(merge(first.state,incoming).counts,{threads:0,records:0,skipped:2});
});
test('conflict copies obey search opt-in, and keeping a conflicting original cannot mislink incoming citations',()=>{
 const state=payload({records:[{...record(),body:'기존의 다른 원문'}]}),incoming=payload({records:[record()],threads:[thread()]});
 const copy=merge(state,incoming,{conflicts:'copy',searchEnabled:false});assert.equal(copy.state.records[1].search_enabled,false);
 const keep=merge(state,incoming,{conflicts:'keep'}),c=keep.state.threads[0].messages[1].result.citations[0];assert.match(c.source_id,/^unavailable-/);assert.equal(c.original_source_id,'record-a');assert.equal(c.quote,'첫 줄');assert.equal(keep.state.records.length,1);
});
test('backup preserves response timing, token counts and scope without transport secrets',()=>{
 const t=thread();Object.assign(t.messages[1].result,{elapsed_ms:123.5,usage:{prompt_tokens:12,completion_tokens:3,total_tokens:15,api_key:'secret'}});t.messages[1].result.scope.context_id='personal';const result=readBackup(makeBackup({threads:[t]})).threads[0].messages[1].result;assert.equal(result.elapsed_ms,123.5);assert.deepEqual(result.usage,{prompt_tokens:12,completion_tokens:3,total_tokens:15});assert.equal(result.scope.context_id,'personal');
});
test('pending imported requests remain archived and missing citation originals do not prevent restoring chats',()=>{
 const t=thread();t.messages[1].status='pending';delete t.messages[1].result;const p=readBackup(makeBackup({threads:[t]},'chat'));const imported=merge(empty(),p);
 assert.equal(imported.state.threads[0].messages[1].archived,true);assert.equal(imported.state.records.length,0);assert.equal(imported.state.threads[0].draft,t.draft);
 assert.equal(readBackup(makeBackup({threads:[thread()]},'chat')).threads[0].messages[1].result.citations.length,1);
});
test('SQLite persists across reopen and rejects stale revisions and invalid writes atomically',t=>{
 const dir=temp(t);let s=new Library(dir);s.save(0,()=>({threads:[thread()],records:[record()]}));s.close();s=new Library(dir);t._stores.push(s);assert.equal(s.read().records.length,1);
 assert.throws(()=>s.save(0,()=>empty()),/다른 화면/);const before=s.read();assert.throws(()=>s.save(1,()=>({records:[{...record(),revision:-1}]})));assert.deepEqual(s.read(),before);
});
async function client(t){const {dir,store}=open(t),api=createLibraryApi(dir,{library:store}),server=http.createServer((req,res)=>api.handle(req,res,new URL(req.url,'http://127.0.0.1')));await new Promise(r=>server.listen(0,'127.0.0.1',r));t.after(()=>new Promise(r=>server.close(r)));const url='http://127.0.0.1:'+server.address().port;const bootstrap=await (await fetch(url+'/api/library/state')).json();return {dir,store,url,post:async(route,body,headers={})=>{const response=await fetch(url+'/api/library/'+route,{method:'POST',headers:{'Content-Type':'application/json','X-Library-Token':bootstrap.token,...headers},body:JSON.stringify(body)});return {status:response.status,data:await response.json()};}};}
test('API validates origin and token; import preview has no writes; export filters drafts and trash',async t=>{
 const c=await client(t),backup=makeBackup({threads:[thread(),{...thread('deleted'),deletedAt:1}],records:[record()]});
 assert.equal((await c.post('import',{revision:0,backup},{'X-Library-Token':'bad'})).status,403);assert.equal((await c.post('inspect',{backup},{Origin:'http://bad.example'})).status,403);
 assert.equal((await c.post('inspect',{backup})).status,200);assert.equal(c.store.read().revision,0);
 const imported=await c.post('import',{revision:0,backup,options:{searchEnabled:true}});assert.equal(imported.status,200);
 const exported=await c.post('export',{kind:'chat',includeDrafts:false});assert.equal(exported.status,200);assert.equal(exported.data.backup.counts.threads,1);assert.equal(exported.data.backup.counts.records,0);assert.equal(exported.data.backup.payload.threads[0].draft,'');
 const full=await c.post('export',{kind:'full',includeDeleted:true});assert.equal(full.data.backup.counts.threads,2);assert.equal(full.data.backup.counts.records,1);
 const before=c.store.read();assert.equal((await c.post('import',{revision:0,backup})).status,409);assert.deepEqual(c.store.read(),before);
});
test('personal search uses only enabled imported records; changing settings persists',async t=>{
 const c=await client(t),backup=makeBackup({records:[record('included'),record('excluded')]},'archive');await c.post('import',{revision:0,backup,options:{searchEnabled:false}});
 const changed=await c.post('search-settings',{revision:1,recordIds:['included']});assert.equal(changed.status,200);
 const {loadScope}=require(process.env.PMA_CHAT_API_FILE||path.join(root,'ui/chat-api.cjs'));const scope=await loadScope(c.dir,{collection_id:'personal'});assert.equal(scope.id,'personal');assert.deepEqual(scope.sources.map(r=>r.id),['included']);assert.equal(scope.sources[0].text,record().body);assert.equal(scope.sources[0].gold,undefined);
});
test('normal chat saves cannot replace archive records, and independently opened writers cannot overwrite',async t=>{
 const c=await client(t);await c.post('import',{revision:0,backup:makeBackup({records:[record()]},'archive')});
 const saved=await c.post('save',{revision:1,threads:[thread()],records:[]});assert.equal(saved.status,200);assert.equal(saved.data.records.length,1);
 const other=new Library(c.dir);try{assert.throws(()=>other.save(1,()=>empty()),/다른 화면/);assert.equal(other.read().threads.length,1);}finally{other.close();}
});
test('real sample archive exports all records with synthetic attribution without modifying the dataset',async t=>{
 const {store}=open(t),api=createLibraryApi(root,{library:store}),server=http.createServer((req,res)=>api.handle(req,res,new URL(req.url,'http://127.0.0.1')));await new Promise(r=>server.listen(0,'127.0.0.1',r));t.after(()=>new Promise(r=>server.close(r)));const url='http://127.0.0.1:'+server.address().port;const {token}=await (await fetch(url+'/api/library/state')).json();const res=await fetch(url+'/api/library/export',{method:'POST',headers:{'Content-Type':'application/json','X-Library-Token':token},body:JSON.stringify({kind:'archive',collection:'samples'})});assert.equal(res.status,200);const {backup}=await res.json();assert.equal(backup.counts.records,199);assert.ok(backup.payload.records.every(r=>r.synthetic&&r.origin_id));assert.equal(store.read().revision,0);
});
