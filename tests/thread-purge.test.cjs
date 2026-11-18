'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),http=require('node:http');
const root=process.env.PMA_APP_ROOT||path.resolve(__dirname,'..');
const {Library,createLibraryApi,makeBackup,payload}=require(path.join(root,'ui/library.cjs'));
const {ActionService}=require(path.join(root,'ui/action-service.cjs'));
const chat=(id,deleted=true)=>({id,title:id,draft:'보관할 초안',messages:[{kind:'user',text:'개인적인 대화 내용',requestId:'request-'+id}],...(deleted?{deletedAt:1}:{})});
const savedRecord={id:'saved-record',title:'별도 개인 기록',body:'보관소에 저장한 기록',search_enabled:true};
function store(t){const dir=fs.mkdtempSync(path.join(os.tmpdir(),'pma-purge-')),library=new Library(dir);t.after(()=>{library.close();if(path.dirname(dir)===os.tmpdir()&&path.basename(dir).startsWith('pma-purge-'))fs.rmSync(dir,{recursive:true,force:true});});return {dir,library};}
async function client(t){const {dir,library}=store(t),api=createLibraryApi(dir,{library}),server=http.createServer((req,res)=>api.handle(req,res,new URL(req.url,'http://127.0.0.1')));await new Promise(r=>server.listen(0,'127.0.0.1',r));t.after(()=>new Promise(r=>server.close(r)));const url='http://127.0.0.1:'+server.address().port,initial=await(await fetch(url+'/api/library/state')).json();return {library,url,post:async(route,body,token=initial.token)=>{const response=await fetch(url+'/api/library/'+route,{method:'POST',headers:{'Content-Type':'application/json','X-Library-Token':token},body:JSON.stringify(body)});return {status:response.status,data:await response.json()};}};}
test('permanent deletion removes only a deleted conversation and preserves saved records',t=>{
 const {library}=store(t),before=library.save(0,()=>({threads:[chat('trash'),chat('active',false),chat('other-trash')],records:[savedRecord]}));
 const result=library.purgeThread(before.revision,'trash');
 assert.deepEqual(result.threads.map(t=>t.id),['active','other-trash']);assert.deepEqual(result.records,before.records);assert.deepEqual(result.purgedThreadIds,['trash']);
 assert.ok(!JSON.stringify(makeBackup(result)).includes('request-trash'));
 const revision=result.revision;assert.equal(library.purgeThread(0,'trash').revision,revision);
});
test('active, unknown, malformed and stale deletion requests leave the database unchanged',t=>{
 const {library}=store(t);library.save(0,()=>({threads:[chat('trash'),chat('active',false)]}));const before=library.read();
 for(const [revision,id,status] of [[0,'trash',409],[1,'active',409],[1,'unknown',404],[1,'../bad',400]]){assert.throws(()=>library.purgeThread(revision,id),e=>e.status===status);assert.deepEqual(library.read(),before);assert.deepEqual(library.purgedThreadIds(),[]);}
});
test('stale autosave cannot resurrect a purged conversation, including after reopening',t=>{
 const {dir,library}=store(t),old=library.save(0,()=>({threads:[chat('trash'),chat('active',false)]}));library.purgeThread(1,'trash');
 assert.throws(()=>library.save(1,()=>old),e=>e.status===409);
 library.close();const reopened=new Library(dir);try{assert.ok(reopened.isThreadPurged('trash'));const result=reopened.save(2,()=>old);assert.deepEqual(result.threads.map(t=>t.id),['active']);}finally{reopened.close();}
});
test('purge clears conversation action caches and category context while retaining other conversations and record history',t=>{
 const {library}=store(t),actions=new ActionService(library),db=library.db;
 library.save(0,()=>({threads:[chat('trash'),chat('other',false)],records:[savedRecord]}));
 db.exec('CREATE TABLE category_context_v3(thread TEXT,scope TEXT,state TEXT,PRIMARY KEY(thread,scope))');
 for(const id of ['trash','other']){
  db.prepare('INSERT INTO action_tasks VALUES(?,?,?,?,?,?)').run('task-'+id,id,'request-'+id,'개인 목표','waiting','{}');
  db.prepare('INSERT INTO action_proposals VALUES(?,?,?,?,?,?)').run('proposal-'+id,id,'request-'+id,1,'pending','{}');
  db.prepare('INSERT INTO action_receipts VALUES(?,?,?,?)').run('receipt-'+id,'proposal-'+id,'fingerprint',JSON.stringify({thread_id:id}));
  db.prepare('INSERT INTO action_requests VALUES(?,?,?)').run('request-'+id,'fingerprint',JSON.stringify({thread_id:id,answer:'개인 답변'}));
  db.prepare('INSERT INTO action_goal_plans VALUES(?,?,?)').run('request-'+id,'fingerprint',JSON.stringify({private:'목표 원문'}));
  db.prepare('INSERT INTO category_context_v3 VALUES(?,?,?)').run(id,'personal','{}');
 }
 db.prepare('INSERT INTO record_history VALUES(?,?,?,?)').run('saved-operation','saved-record',null,JSON.stringify(savedRecord));
 library.purgeThread(1,'trash');
 for(const table of ['action_tasks','action_proposals','action_receipts','action_requests','action_goal_plans','category_context_v3'])assert.equal(db.prepare('SELECT COUNT(*) n FROM '+table).get().n,1,table);
 assert.equal(db.prepare('SELECT COUNT(*) n FROM record_history').get().n,1);assert.equal(library.read().records[0].id,'saved-record');
 for(const fn of [()=>actions.remember({thread_id:'trash',request_id:'late'},{}),()=>actions.rememberGoalPlan({thread_id:'trash',request_id:'late'},{}),()=>actions.task({thread_id:'trash'}, {},{}),()=>actions.propose({thread_id:'trash'}, {},{},[])])assert.throws(fn,e=>e.status===410);
});
test('failed purge rolls back tombstone, conversation and auxiliary changes together',t=>{
 const {library}=store(t),actions=new ActionService(library);library.save(0,()=>({threads:[chat('trash')]}));const before=library.read();
 actions.task({thread_id:'trash',request_id:'request-trash',text:'원문'},{action:'clarify'},{});
 library.db.exec("CREATE TRIGGER reject_purge BEFORE UPDATE ON library BEGIN SELECT RAISE(ABORT,'injected failure'); END");
 assert.throws(()=>library.purgeThread(1,'trash'),/injected failure/);assert.deepEqual(library.read(),before);assert.deepEqual(library.purgedThreadIds(),[]);assert.equal(actions.tasks('trash').length,1);
});
test('HTTP purge requires authentication, returns authoritative tombstones and survives subsequent saves',async t=>{
 const c=await client(t);await c.post('save',{revision:0,threads:[chat('trash'),chat('active',false)]});
 assert.equal((await c.post('thread-purge',{revision:1,threadId:'trash'},'wrong-token')).status,403);
 assert.equal((await c.post('thread-purge',{revision:0,threadId:'trash'})).status,409);
 const purged=await c.post('thread-purge',{revision:1,threadId:'trash'});assert.equal(purged.status,200);assert.deepEqual(purged.data.purgedThreadIds,['trash']);
 const saved=await c.post('save',{revision:2,threads:[chat('trash'),chat('active',false)]});assert.equal(saved.data.threads.length,1);
 const state=await(await fetch(c.url+'/api/library/state')).json();assert.deepEqual(state.purgedThreadIds,['trash']);
});
test('explicit backup import creates a fresh identity rather than reviving a purged conversation ID',async t=>{
 const c=await client(t),backup=makeBackup({threads:[chat('trash')]},'chat');await c.post('save',{revision:0,threads:[chat('trash')]});await c.post('thread-purge',{revision:1,threadId:'trash'});
 const imported=await c.post('import',{revision:2,backup,options:{}});assert.equal(imported.status,200);assert.equal(imported.data.counts.threads,1);assert.notEqual(imported.data.threads[0].id,'trash');assert.ok(c.library.isThreadPurged('trash'));assert.deepEqual(payload(imported.data).threads,imported.data.threads);
});
test('purged conversations cannot replay cached responses, approve operations or read old operation status',async t=>{
 const {library}=store(t),actions=new ActionService(library);library.save(0,()=>({threads:[chat('trash')]}));library.purgeThread(1,'trash');
 const {createChatApi}=require(path.join(root,'ui/chat-api.cjs'));let calls=0;
 const api=createChatApi(root,{actions,runtime:async()=>({chat:async()=>{calls++;throw Error('must not call AI');}})}),server=http.createServer((req,res)=>api.handle(req,res,new URL(req.url,'http://127.0.0.1')));
 await new Promise(r=>server.listen(0,'127.0.0.1',r));t.after(()=>new Promise(r=>server.close(r)));const url='http://127.0.0.1:'+server.address().port,token=(await(await fetch(url+'/api/chat/bootstrap')).json()).token;
 for(const route of ['respond','operation','operation-status']){const response=await fetch(url+'/api/chat/'+route,{method:'POST',headers:{'Content-Type':'application/json','X-Plant-Token':token},body:JSON.stringify({thread_id:'trash'})});assert.equal(response.status,410);}
 assert.equal(calls,0);
});
