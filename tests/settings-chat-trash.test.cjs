'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),vm=require('node:vm');
const root=process.env.PMA_APP_ROOT||path.resolve(__dirname,'..'),{Library}=require(root+'/ui/library.cjs');
class Element{
 constructor(tag,doc){this.tag=tag;this.doc=doc;this.children=[];this.dataset={};this.value='';this.checked=false;this.disabled=false;this._text='';}
 set id(value){this._id=value;this.doc.ids.set(value,this);}get id(){return this._id;}
 set textContent(value){this._text=String(value);this.children=[];}get textContent(){return this._text+this.children.map(c=>c.textContent).join('');}
 append(...children){for(const child of children){child.parent=this;this.children.push(child);}}replaceChildren(...children){this.children=[];this._text='';this.append(...children);}setAttribute(name,value){this[name]=value;}
 before(child){const siblings=this.parent.children;child.parent=this.parent;siblings.splice(siblings.indexOf(this),0,child);}
 focus(){this.doc.focused=this;}
}
function documentStub(){const doc={ids:new Map(),events:new Map(),createElement:tag=>new Element(tag,doc),getElementById:id=>doc.ids.get(id)||null,addEventListener(name,fn){if(!this.events.has(name))this.events.set(name,[]);this.events.get(name).push(fn);},dispatchEvent(event){for(const fn of this.events.get(event.type)||[])fn(event);}};doc.body=doc.createElement('body');for(const id of ['settings','chatInput']){const el=doc.createElement('div');el.id=id;doc.body.append(el);}return doc;}
function section(source,start,end){const a=source.indexOf(start),b=source.indexOf(end,a);assert.ok(a>=0&&b>a);return source.slice(a,b);}
function fixture(t){
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'pma-settings-trash-')),library=new Library(dir);t.after(()=>{library.close();if(path.dirname(dir)===path.resolve(os.tmpdir())&&path.basename(dir).startsWith('pma-settings-trash-'))fs.rmSync(dir,{recursive:true,force:true});});
 const pending={kind:'assistant',status:'pending',submission:{request_id:'request-alpha',thread_id:'alpha',text:'질문',input_version:1,collection_id:'personal',profile:'personal',example_id:'',history:[]}};
 library.save(0,s=>({...s,threads:[{id:'alpha',title:'업무 이야기',draft:'아직 보내지 않은 입력',group:'업무',pinned:true,messages:[{kind:'user',text:'질문',requestId:'request-alpha'},pending]},{id:'beta',title:'여행 계획',draft:'여행 초안',messages:[]},{id:'gamma',title:'업무 메모',draft:'',messages:[]},{id:'trash',title:'이전 휴지통',deletedAt:1,messages:[]}],records:[{id:'record',title:'개인 기록',body:'유지할 내용',search_enabled:true}]}));
 const initial=library.read(),doc=documentStub(),notices=[],controller=new AbortController(),source=fs.readFileSync(root+'/ui/plant-thought/preview.js','utf8'),chat=fs.readFileSync(root+'/ui/plant-thought/chat-connect.js','utf8');
 const sandbox={document:doc,Date,Set,CustomEvent,controllers:new Map([['request-alpha',{threadId:'alpha',controller}]]),previewThreads:structuredClone(initial.threads),previewActiveId:'alpha',previewToast:(message,action)=>notices.push({message,action}),previewConfirmPurgeThread(){throw Error('Must not permanently delete');},newChat(){throw Error('Must not navigate or create a conversation');}};
 sandbox.previewThread=()=>sandbox.previewThreads.find(thread=>thread.id===sandbox.previewActiveId&&!thread.deletedAt);
 sandbox.previewRemember=()=>{const current=sandbox.previewThread();if(current)current.draft=doc.getElementById('chatInput').value;const threads=JSON.parse(JSON.stringify(sandbox.previewThreads));library.save(library.read().revision,s=>({...s,threads}));};
 sandbox.previewRenderHistory=()=>{sandbox.previewRenderChatManagement();sandbox.previewRenderDeletedChats();};sandbox.previewRenderMessages=sandbox.previewRenderHistory;
 const ctx=vm.createContext(sandbox);vm.runInContext(section(source,"let previewManagedQuery=",'async function previewPermanentlyDeleteThreads'),ctx);vm.runInContext(section(chat,"  document.addEventListener('plant:thread-deleted'",'  function progressDuration'),ctx);doc.getElementById('chatInput').value='아직 보내지 않은 입력';sandbox.previewRenderHistory();
 const checkbox=id=>doc.getElementById('settingsChatList').children.flatMap(row=>row.children).find(el=>el.dataset.selectThread===id);
 const select=(id,checked=true)=>{const el=checkbox(id);el.checked=checked;el.onchange();};return {ctx: sandbox,doc,dir,library,initial,notices,controller,select,checkbox};
}
test('settings selection supports search, filtered select all and mixed checkbox state without including existing trash',t=>{
 const f=fixture(t),button=f.doc.getElementById('trashSelectedChats'),all=f.doc.getElementById('selectAllSettingsChats'),search=f.doc.getElementById('settingsChatSearch');assert.equal(button.disabled,true);assert.equal(f.checkbox('trash'),undefined);
 f.select('alpha');assert.equal(button.disabled,false);assert.equal(all.indeterminate,true);assert.match(f.doc.getElementById('settingsChatSelectionCount').textContent,/선택 1개/);
 search.value='업무';search.oninput();assert.equal(f.doc.getElementById('settingsChatList').children.length,2);assert.equal(f.doc.getElementById('settingsChatSelectLabel').textContent,'검색 결과 전체 선택');all.checked=true;all.onchange();assert.equal(all.checked,true);assert.match(f.doc.getElementById('settingsChatSelectionCount').textContent,/선택 2개/);
 button.onclick();const stored=f.library.read();assert.ok(stored.threads.find(t=>t.id==='alpha').deletedAt);assert.ok(stored.threads.find(t=>t.id==='gamma').deletedAt);assert.equal(stored.threads.find(t=>t.id==='beta').deletedAt,undefined);assert.equal(stored.threads.find(t=>t.id==='trash').deletedAt,1);assert.deepEqual(stored.records,f.initial.records);
});
test('moving selected active chats aborts generation, preserves drafts and metadata, and notification restores the batch',t=>{
 const f=fixture(t);f.select('alpha');f.select('gamma');f.doc.getElementById('trashSelectedChats').onclick();assert.equal(f.controller.signal.aborted,true);assert.equal(f.ctx.previewActiveId,'beta');assert.equal(f.doc.getElementById('chatInput').value,'여행 초안');
 let stored=f.library.read(),alpha=stored.threads.find(t=>t.id==='alpha');assert.equal(alpha.draft,'아직 보내지 않은 입력');assert.equal(alpha.pinned,true);assert.equal(alpha.group,'업무');assert.equal(alpha.messages[1].status,'cancelled');assert.equal(stored.threads.length,f.initial.threads.length);assert.match(f.doc.getElementById('deletedChatList').textContent,/업무 이야기/);assert.equal(f.doc.getElementById('trashSelectedChats').disabled,true);
 const notice=f.notices.at(-1);assert.match(notice.message,/2개를 휴지통/);assert.equal(notice.action.label,'복원');notice.action.run();stored=f.library.read();assert.equal(stored.threads.find(t=>t.id==='alpha').deletedAt,undefined);assert.equal(stored.threads.find(t=>t.id==='gamma').deletedAt,undefined);assert.equal(stored.threads.find(t=>t.id==='trash').deletedAt,1);assert.deepEqual(stored.records,f.initial.records);assert.ok(f.checkbox('alpha'));assert.equal(stored.threads.find(t=>t.id==='alpha').messages[1].status,'cancelled');
 const reopened=new Library(f.dir);try{assert.deepEqual(reopened.read(),stored);}finally{reopened.close();}
});
test('selecting all chats can empty the active list without leaving settings or creating a replacement conversation',t=>{
 const f=fixture(t),all=f.doc.getElementById('selectAllSettingsChats');all.checked=true;all.onchange();f.doc.getElementById('trashSelectedChats').onclick();assert.equal(f.ctx.previewActiveId,null);assert.equal(f.doc.getElementById('chatInput').value,'');assert.equal(f.ctx.previewThreads.length,4);assert.ok(f.ctx.previewThreads.every(t=>t.deletedAt));assert.equal(f.doc.getElementById('selectAllSettingsChats').disabled,true);assert.match(f.doc.getElementById('settingsChatList').textContent,/관리할 대화가 없습니다/);f.notices.at(-1).action.run();assert.equal(f.ctx.previewThreads.filter(t=>!t.deletedAt).length,3);
});
test('single selection and zero results do not accidentally move other conversations',t=>{
 const f=fixture(t),search=f.doc.getElementById('settingsChatSearch');search.value='없는 제목';search.oninput();assert.equal(f.doc.getElementById('selectAllSettingsChats').disabled,true);assert.equal(f.doc.getElementById('trashSelectedChats').disabled,true);search.value='';search.oninput();f.select('beta');f.doc.getElementById('trashSelectedChats').onclick();assert.equal(f.ctx.previewActiveId,'alpha');assert.equal(f.controller.signal.aborted,false);assert.equal(f.ctx.previewThreads.find(t=>t.id==='alpha').deletedAt,undefined);assert.ok(f.ctx.previewThreads.find(t=>t.id==='beta').deletedAt);assert.deepEqual(f.library.read().records,f.initial.records);
});
