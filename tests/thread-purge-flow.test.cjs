'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),vm=require('node:vm'),http=require('node:http');
const root=process.env.PMA_APP_ROOT||path.resolve(__dirname,'..'),{Library}=require(path.join(root,'ui/library.cjs'));
const deleted=id=>({id,title:id,messages:[{kind:'user',text:'임시 검증용 메시지'}],draft:'',deletedAt:1});
class Element{
 constructor(tag,doc){this.tag=tag;this.doc=doc;this.children=[];this.dataset={};this.hidden=false;this.disabled=false;this.classList={add(){},remove(){}};}
 set id(value){this._id=value;this.doc.ids.set(value,this);}get id(){return this._id;}
 append(...children){for(const child of children){child.parent=this;this.children.push(child);}}
 replaceChildren(...children){this.children=[];this.append(...children);}setAttribute(name,value){this[name]=value;}addEventListener(name,fn){(this.events??={})[name]=fn;}
 remove(){this.doc.ids.delete(this.id);if(this.parent)this.parent.children=this.parent.children.filter(e=>e!==this);}showModal(){this.open=true;}close(){this.open=false;this.events?.close?.();}focus(){}
}
function documentStub(){const doc={ids:new Map(),createElement:tag=>new Element(tag,doc),getElementById:id=>doc.ids.get(id),querySelector:()=>null,body:null};doc.body=doc.createElement('body');for(const id of ['settings','chatInput']){const el=doc.createElement('div');el.id=id;doc.body.append(el);}return doc;}
function between(source,start,end){const a=source.indexOf(start),b=source.indexOf(end,a);assert.ok(a>=0&&b>a,start);return source.slice(a,b);}
async function app(t){
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'pma-purge-flow-'));fs.mkdirSync(path.join(dir,'ui'));
 const library=new Library(dir);library.save(0,()=>({threads:[deleted('trash-a'),deleted('trash-b'),{id:'active',title:'유지할 대화',messages:[],draft:'유지할 입력'}],records:[{id:'keep-record',title:'유지할 개인 기록',body:'별도로 저장한 기록',search_enabled:true}]}));library.close();
 // Execute the real connected-server routing stack against an isolated SQLite database.
 const source=fs.readFileSync(path.join(root,'ui/connected.cjs'),'utf8').replace(/require\('(\.\/[^']+)'\)/g,(_,name)=>'require('+JSON.stringify(path.join(root,'ui',name))+')');
 fs.writeFileSync(path.join(dir,'ui/connected.cjs'),source);const server=require(path.join(dir,'ui/connected.cjs')).server;
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));t.after(async()=>{await new Promise(resolve=>server.close(resolve));assert.equal(path.dirname(dir),os.tmpdir());assert.ok(path.basename(dir).startsWith('pma-purge-flow-'));fs.rmSync(dir,{recursive:true,force:true});});
 const address='http://127.0.0.1:'+server.address().port,requests=[],sent=[];
 const request=(url,options={})=>new Promise((resolve,reject)=>{if(options.body)sent.push({path:url,body:JSON.parse(options.body)});const req=http.request(address+url,{method:options.method||'GET',headers:{...options.headers,host:'127.0.0.1:4330',origin:'http://127.0.0.1:4330'}},res=>{const chunks=[];res.on('data',chunk=>chunks.push(chunk));res.on('end',()=>{requests.push({path:url,status:res.statusCode});resolve({status:res.statusCode,ok:res.statusCode<400,json:async()=>JSON.parse(Buffer.concat(chunks).toString())});});});req.on('error',reject);req.end(options.body);});
 const initial=await(await request('/api/library/state')).json();return {dir,request,requests,sent,initial};
}
function frontend(app){
 const doc=documentStub(),notices=[],initial=app.initial,source=fs.readFileSync(path.join(root,'ui/plant-thought/data-transfer.js'),'utf8'),preview=fs.readFileSync(path.join(root,'ui/plant-thought/preview.js'),'utf8');
 const ctx=vm.createContext({document:doc,window:{},console,fetch:app.request,setTimeout,clearTimeout,previewThreads:structuredClone(initial.threads),previewActiveId:'active',previewSnapshot(){},previewToast:message=>notices.push(message),previewRemember(){},previewThread(){return ctx.previewThreads.find(t=>t.id===ctx.previewActiveId&&!t.deletedAt);},previewRenderMessages(){ctx.previewRenderDeletedChats();}});
 vm.runInContext(`let ready=true,locked=false,dirty=false,timer,saveFailure=null,queue=Promise.resolve(),token=${JSON.stringify(initial.token)},revision=${initial.revision},storageEpoch=${JSON.stringify(initial.storage_epoch)},personalRecords=${JSON.stringify(initial.records)},persistedThreads=${JSON.stringify(JSON.stringify(initial.threads))};const status=document.createElement('p');function showError(error){throw error;}`,ctx);
 vm.runInContext(between(preview,'function previewRenderDeletedChats(){','function previewGroupThread('),ctx);
 vm.runInContext(between(source,' function available(){',' function lock(')+between(source,' async function api(',' function clearForReset('),ctx);
 return {ctx,doc,notices};
}
test('confirmation button reaches production routing and permanently deletes trash, including after reloading the database',async t=>{
 const a=await app(t),f=frontend(a);vm.runInContext('previewRenderDeletedChats();previewConfirmPurgeThread();',f.ctx);
 const dialog=f.doc.getElementById('chatPurgeDialog'),button=dialog.children.at(-1).children.at(-1);assert.equal(button.textContent,'완전 삭제');await button.onclick();
 assert.ok(f.notices.includes('삭제한 대화 2개를 모두 삭제했어요.'));assert.equal(dialog.open,false);assert.equal(f.doc.getElementById('purgeDeletedChats').disabled,true);
 assert.deepEqual(a.requests.filter(r=>r.path.includes('purge')),[{path:'/api/library/thread-purge',status:200}]);
 const state=await(await a.request('/api/library/state')).json();assert.deepEqual(state.threads,a.initial.threads.filter(t=>!t.deletedAt));assert.deepEqual(state.records,a.initial.records);assert.deepEqual(new Set(state.purgedThreadIds),new Set(['trash-a','trash-b']));
 const reopened=new Library(a.dir);try{assert.deepEqual(reopened.read().threads,state.threads);assert.deepEqual(reopened.read().records,state.records);}finally{reopened.close();}
});
test('cancel never submits a delete; individual permanent delete still keeps other trash',async t=>{
 const a=await app(t),f=frontend(a);vm.runInContext('previewRenderDeletedChats();previewConfirmPurgeThread();',f.ctx);f.doc.getElementById('chatPurgeDialog').children.at(-1).children[0].onclick();assert.equal(a.requests.filter(r=>r.path.includes('purge')).length,0);
 vm.runInContext("previewConfirmPurgeThread('trash-a');",f.ctx);await f.doc.getElementById('chatPurgeDialog').children.at(-1).children.at(-1).onclick();
 const state=await(await a.request('/api/library/state')).json();assert.deepEqual(state.threads.map(t=>t.id),['trash-b','active']);assert.deepEqual(state.records,a.initial.records);
});

test('trash deletion does not serialize unrelated unsaved messages or discard the local draft after a failed autosave',async t=>{
 const a=await app(t),f=frontend(a);
 f.ctx.previewThreads.find(t=>t.id==='active').messages.push({kind:'user',text:undefined});
 f.ctx.previewThreads.find(t=>t.id==='active').draft='작성 중인 내용은 그대로 유지';
 vm.runInContext("dirty=true;saveFailure=Error('문자열 형식 또는 길이가 올바르지 않습니다.');previewRenderDeletedChats();previewConfirmPurgeThread();",f.ctx);
 await f.doc.getElementById('chatPurgeDialog').children.at(-1).children.at(-1).onclick();
 assert.ok(f.notices.includes('삭제한 대화 2개를 모두 삭제했어요.'));
 assert.equal(f.ctx.previewThreads.find(t=>t.id==='active').draft,'작성 중인 내용은 그대로 유지');assert.equal(f.ctx.previewThreads.find(t=>t.id==='active').messages.length,1);
 assert.equal(vm.runInContext('dirty',f.ctx),true);assert.equal(vm.runInContext('!!saveFailure',f.ctx),true);
 assert.equal(a.requests.filter(r=>r.path==='/api/library/save').length,0);
 const state=await(await a.request('/api/library/state')).json();assert.deepEqual(state.threads,a.initial.threads.filter(t=>!t.deletedAt));assert.deepEqual(state.records,a.initial.records);
});
test('a pending autosave validation failure cannot block purging already saved trash',async t=>{
 const a=await app(t),f=frontend(a);
 vm.runInContext("queue=Promise.resolve().then(()=>{saveFailure=Error('문자열 형식 또는 길이가 올바르지 않습니다.');dirty=true;throw saveFailure;});queue.catch(()=>{});previewRenderDeletedChats();previewConfirmPurgeThread();",f.ctx);
 await f.doc.getElementById('chatPurgeDialog').children.at(-1).children.at(-1).onclick();
 assert.ok(f.notices.includes('삭제한 대화 2개를 모두 삭제했어요.'));const state=await(await a.request('/api/library/state')).json();assert.equal(state.threads.length,1);assert.equal(vm.runInContext('!!saveFailure',f.ctx),true);
});

test('invalid unsaved text is never sent or validated while trash is permanently deleted',async t=>{
 const a=await app(t),f=frontend(a);const active=f.ctx.previewThreads.find(t=>t.id==='active');active.messages.push({kind:'user',text:undefined});active.draft='이 입력을 버리지 않습니다';
 vm.runInContext('dirty=true;previewRenderDeletedChats();previewConfirmPurgeThread();',f.ctx);await f.doc.getElementById('chatPurgeDialog').children.at(-1).children.at(-1).onclick();
 assert.ok(f.notices.includes('삭제한 대화 2개를 모두 삭제했어요.'));assert.equal(vm.runInContext('saveFailure',f.ctx),null);
 assert.deepEqual(a.requests.filter(r=>r.path==='/api/library/save'||r.path.includes('purge')),[{path:'/api/library/thread-purge',status:200}]);
 assert.equal(active.draft,'이 입력을 버리지 않습니다');assert.equal(active.messages.length,1);const state=await(await a.request('/api/library/state')).json();assert.deepEqual(state.threads,a.initial.threads.filter(t=>!t.deletedAt));assert.deepEqual(state.records,a.initial.records);
});
test('a conversation still active on the server is not saved or re-trashed during permanent deletion',async t=>{
 const a=await app(t),f=frontend(a);f.ctx.previewThreads.find(t=>t.id==='active').deletedAt=2;
 vm.runInContext('dirty=true;previewRenderDeletedChats();previewConfirmPurgeThread();',f.ctx);await f.doc.getElementById('chatPurgeDialog').children.at(-1).children.at(-1).onclick();
 assert.equal(f.notices.length,0);assert.deepEqual(a.requests.slice(1),[{path:'/api/library/thread-purge',status:409}]);
 const state=await(await a.request('/api/library/state')).json();assert.deepEqual(state.threads,a.initial.threads);assert.deepEqual(state.records,a.initial.records);
});

test('confirmation sends exactly one purge request containing IDs and no content or deletion-state save',async t=>{
 const a=await app(t),f=frontend(a),active=f.ctx.previewThreads.find(t=>t.id==='active');active.messages.push({kind:'user',text:undefined});active.draft='아직 저장하지 않은 입력';
 vm.runInContext('dirty=true;previewRenderDeletedChats();previewConfirmPurgeThread();',f.ctx);await f.doc.getElementById('chatPurgeDialog').children.at(-1).children.at(-1).onclick();
 assert.ok(f.notices.includes('삭제한 대화 2개를 모두 삭제했어요.'));assert.deepEqual(a.requests.map(r=>r.path),['/api/library/state','/api/library/thread-purge']);
 assert.deepEqual(Object.keys(a.sent[0].body).sort(),['revision','storage_epoch','threadIds']);assert.deepEqual(a.sent[0].body.threadIds,['trash-a','trash-b']);
 assert.ok(!JSON.stringify(a.sent).includes('아직 저장하지 않은 입력'));const state=await(await a.request('/api/library/state')).json();assert.deepEqual(state.threads,a.initial.threads.filter(t=>!t.deletedAt));assert.deepEqual(state.records,a.initial.records);
});

test('snapshot autosave queued before confirmation is skipped instead of saving every chat',async t=>{
 const a=await app(t),f=frontend(a);f.ctx.previewThreads.find(t=>t.id==='active').draft='남겨 둘 입력';
 vm.runInContext('dirty=true;persist();previewRenderDeletedChats();previewConfirmPurgeThread();',f.ctx);await f.doc.getElementById('chatPurgeDialog').children.at(-1).children.at(-1).onclick();
 assert.ok(f.notices.includes('삭제한 대화 2개를 모두 삭제했어요.'));assert.equal(a.requests.filter(r=>r.path==='/api/library/save').length,0);assert.equal(f.ctx.previewThreads[0].draft,'남겨 둘 입력');assert.equal(vm.runInContext('dirty',f.ctx),true);
});
test('a failed purge keeps the dialog and all local chats unchanged',async t=>{
 const a=await app(t),f=frontend(a);vm.runInContext('revision=0;previewRenderDeletedChats();previewConfirmPurgeThread();',f.ctx);await f.doc.getElementById('chatPurgeDialog').children.at(-1).children.at(-1).onclick();
 assert.equal(f.notices.length,0);assert.equal(f.doc.getElementById('chatPurgeDialog').open,true);assert.deepEqual(a.requests.slice(1),[{path:'/api/library/thread-purge',status:409}]);assert.equal(f.ctx.previewThreads.length,3);
 const state=await(await a.request('/api/library/state')).json();assert.deepEqual(state.threads,a.initial.threads);assert.deepEqual(state.records,a.initial.records);
});

test('individual and bulk controls both delete through HTTP, survive reload, and preserve live chats, drafts and records',async t=>{
 const a=await app(t),original=structuredClone(a.initial),individual=frontend(a);
 vm.runInContext('previewRenderDeletedChats();',individual.ctx);
 const row=individual.doc.getElementById('deletedChatList').children.find(row=>row.children.some(button=>button.dataset?.purgeThread==='trash-a'));
 assert.ok(row,'The individual delete button must exist in the rendered trash list.');row.children.find(button=>button.dataset?.purgeThread==='trash-a').onclick();
 const firstDialog=individual.doc.getElementById('chatPurgeDialog');await firstDialog.children.at(-1).children.at(-1).onclick();
 assert.ok(individual.notices.includes('대화를 완전히 삭제했어요.'));assert.equal(firstDialog.open,false);
 const afterIndividual=await(await a.request('/api/library/state')).json();
 assert.deepEqual(afterIndividual.threads.map(t=>t.id),['trash-b','active']);assert.deepEqual(afterIndividual.records,original.records);assert.ok(afterIndividual.purgedThreadIds.includes('trash-a'));
 assert.equal(individual.doc.getElementById('purgeDeletedChats').disabled,false);
 // Rebuild the actual settings handlers from newly fetched server state, like reopening the page.
 a.initial=afterIndividual;const bulk=frontend(a);bulk.ctx.previewThreads.find(t=>t.id==='active').draft='작성 중인 다른 대화 입력';
 vm.runInContext('dirty=true;previewRenderDeletedChats();',bulk.ctx);bulk.doc.getElementById('purgeDeletedChats').onclick();
 const secondDialog=bulk.doc.getElementById('chatPurgeDialog');await secondDialog.children.at(-1).children.at(-1).onclick();
 assert.ok(bulk.notices.includes('삭제한 대화 1개를 모두 삭제했어요.'));assert.equal(secondDialog.open,false);assert.equal(bulk.doc.getElementById('purgeDeletedChats').disabled,true);
 const afterBulk=await(await a.request('/api/library/state')).json();
 assert.deepEqual(afterBulk.threads,original.threads.filter(t=>!t.deletedAt));assert.deepEqual(afterBulk.records,original.records);assert.deepEqual(new Set(afterBulk.purgedThreadIds),new Set(['trash-a','trash-b']));
 assert.equal(bulk.ctx.previewThreads.find(t=>t.id==='active').draft,'작성 중인 다른 대화 입력');assert.equal(vm.runInContext('dirty',bulk.ctx),true);
 assert.deepEqual(a.sent.map(req=>({path:req.path,ids:req.body.threadIds})),[{path:'/api/library/thread-purge',ids:['trash-a']},{path:'/api/library/thread-purge',ids:['trash-b']}]);
 const reopened=new Library(a.dir);try{assert.deepEqual(reopened.read().threads,afterBulk.threads);assert.deepEqual(reopened.read().records,original.records);assert.deepEqual(new Set(reopened.purgedThreadIds()),new Set(['trash-a','trash-b']));}finally{reopened.close();}
});
