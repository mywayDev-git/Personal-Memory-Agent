'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const crypto=require('node:crypto');
const http=require('node:http');
const dates=require('./diary-dates.js');

// Exercise the real integration against a small DOM and an isolated API fixture.
class Element{
  constructor(tag='div'){this.tagName=tag.toLowerCase();this.children=[];this.dataset={};this.attributes={};this.value='';this._text='';this.style={removeProperty(name){delete this[name];}};this.isConnected=true;}
  get childNodes(){return this.children;}
  get textContent(){return this._text+this.children.map(node=>node.textContent||'').join('');}
  set textContent(value){this._text=String(value);this.children=[];}
  set innerHTML(value){this.html=value;this.children=[];this._text='';}
  get innerHTML(){return this.html||'';}
  append(...nodes){for(let node of nodes){if(typeof node==='string'){const text=new Element();text.textContent=node;node=text;}this.children.push(node);node.parent=this;}}
  appendChild(node){this.append(node);return node;}
  prepend(...nodes){this.children.unshift(...nodes);for(const node of nodes)node.parent=this;}
  replaceChildren(...nodes){this.children=[];this._text='';this.append(...nodes);}
  after(...nodes){const parent=this.parent;if(!parent)return;const index=parent.children.indexOf(this);parent.children.splice(index+1,0,...nodes);for(const node of nodes)node.parent=parent;}
  remove(){if(this.parent)this.parent.children=this.parent.children.filter(node=>node!==this);this.isConnected=false;}
  setAttribute(name,value){this.attributes[name]=value;}
  addEventListener(event,handler){this['on'+event]=handler;}
  focus(){}
  add(option){this.append(option);this.value||=option.value;}
  get classList(){return {contains:name=>(this.className||'').split(' ').includes(name)};}
  matches(selector){return selector.startsWith('.')?this.classList.contains(selector.slice(1)):this.tagName===selector;}
  querySelectorAll(selector){const nodes=this.children.flatMap(node=>[node,...node.querySelectorAll('*')]);if(selector==='*')return nodes;return nodes.filter(node=>selector.split(',').some(part=>node.matches(part.trim())));}
  querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
}
async function fixture(handler=()=>({intent:'diary'}),options={}){
  const elements=new Map(),created=[];
  const get=name=>{if(!elements.has(name))elements.set(name,new Element());return elements.get(name);};
  const create=tag=>{const element=new Element(tag);created.push(element);return element;};
  const saved=options.archive||[],calls=[],navigation=[],storage=new Map();
  let failSave=false,failModels=false;
  const context={
    document:{getElementById:get,createElement:create,
      querySelector:get,
      querySelectorAll:selector=>selector==='[onclick="newChat()"]'?[get('newChat1'),get('newChat2')]:created.filter(node=>selector==='.message-sources'?node.classList.contains('message-sources'):selector==='.chat-followups button'?node.tagName==='button'&&node.parent?.classList.contains('chat-followups'):false),
    },
    Option:class extends Element{constructor(text,value){super('option');this.textContent=text;this.value=value;}},
    localStorage:{getItem:key=>storage.get(key)||null,setItem:(key,value)=>storage.set(key,value)},
    location:{protocol:'http:'},crypto:crypto.webcrypto,performance,AbortController,setInterval,clearInterval,setTimeout,clearTimeout,
    requestAnimationFrame:fn=>fn(),
    ...dates,records:[],year:2026,month:10,selected:'2026-11-13',searchFilter:'all',archiveSearchActive:false,
    renderCalendar(){},renderTimeline(){},renderRecent(){},renderSelected(){},scrollChatToBottom(){},updateChatInput(){},closeChatSidebar(){},
    selectArchiveDate(date){context.selected=date;},go:page=>navigation.push(page),syncArchivePanel(){},scrollToSearchResults(){},
    openRecord(index){const r=context.records[index];get('detailTitle').textContent=r.title;get('detailBody').textContent=r.body;context.go('recordDetail');},
    safe:value=>String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;'),
    recordIndex:record=>context.records.indexOf(record),
    renderBotText(text){const result=create('div'),paragraph=create('p');paragraph.textContent=text;result.append(paragraph);return result;},
    fetch:async(url,init)=>{
      let value;
      if(url.endsWith('/bootstrap'))value={token:'test-only-token',runtime:{models:failModels?[]:[{role:'generation',present:true,id:'qwen35-4b-q4',default:true}],states:{generation:{}}}};
      else if(url.includes('/original?key=')){const key=url.split('key=')[1],row=saved.find(row=>row.memory_key===key);value={source:{text:row.text},summary_id:row.summary_artifact_id};}
      else if(url.includes('/progress?id='))value={stage:'answering'};
      else if(url.endsWith('/summary-memory')&&!init)value={memories:saved.map(({text,...row})=>row)};
      else{
        const payload=JSON.parse(init.body);calls.push({url,payload});
        assert.equal(init.headers['X-Memory-Lab-Token'],'test-only-token');
        if(url.endsWith('/save')){
          if(failSave)return {ok:false,json:async()=>({error:'저장 시험 실패'})};
          const key=crypto.createHash('sha256').update(payload.text).digest('hex');
          const record={memory_key:key,source_id:'source-'+key,text:payload.text,summary:'저장된 요약'};
          const index=saved.findIndex(row=>row.memory_key===key);if(index<0)saved.push(record);else saved[index]=record;
          value={memory:record};
        }else value=await handler(url,payload);
      }
      return {ok:true,json:async()=>value};
    },
  };
  vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(__dirname,'memory.js'),'utf8'),context);
  await vm.runInContext('memoryReady',context);
  if(options.ux)vm.runInContext(fs.readFileSync(path.join(__dirname,'conversation-ux.js'),'utf8'),context);
  const value=code=>vm.runInContext(code,context);
  return {context,get,saved,calls,navigation,storage,value,failSave(){failSave=true;},failModels(){failModels=true;value("modelPicker.value=''");}};
}

test('opening a source from chat returns to the same chat, while archive sources return to archive',async()=>{
 const row={memory_key:'key-1',summary_artifact_id:'version-1',source_id:'source-1',text:'제목: 시험 원문\n기록일: 2026-11-13\n감정: 미지정\n\n민수와 도서관에 갔다.'};
 const f=await fixture(undefined,{ux:true,archive:[row]});
 f.value("addBubble('user','내 기록을 보여줘.');addBubble('bot','도서관에 간 기록이 있어요.');chatHistoryState.activeId='same-chat';");
 const before=f.get('conversation').textContent;
 await f.value("uxOpenKey('key-1','version-1')");
 const back=f.get('#recordDetail .record-detail > button');
 assert.match(back.textContent,/사색 대화/);back.onclick();
 assert.equal(f.navigation.at(-1),'chat');assert.equal(f.get('conversation').textContent,before);assert.equal(f.value('chatHistoryState.activeId'),'same-chat');
 f.value('openRecord(0)');assert.match(back.textContent,/서재 보관소/);back.onclick();assert.equal(f.navigation.at(-1),'archive');
});
test('delete button requires confirmation, cancel makes no request, and success removes only its record',async()=>{
 const record=(key,title)=>({memory_key:key,summary_artifact_id:'version-'+key,source_id:'source-'+key,text:'제목: '+title+'\n기록일: 2026-11-13\n감정: 미지정\n\n보존할 내용'});
 let f;
 f=await fixture(async(url,payload)=>{
  if(url.endsWith('/ux/delete')){const i=f.saved.findIndex(r=>r.memory_key===payload.key);f.saved.splice(i,1);return {kind:'delete',state:'committed',deleted_key:payload.key};}
  return {};
 },{ux:true,archive:[record('one','삭제 대상'),record('two','남길 기억')]});
 const button=label=>f.get('#recordDetail .card').querySelectorAll('button').find(b=>b.textContent===label);
 f.value('openRecord(0)');button('기억 삭제').onclick();
 assert.ok(button('삭제하기'));assert.ok(button('취소'));assert.equal(f.calls.filter(c=>c.url.endsWith('/ux/delete')).length,0);
 button('취소').onclick();assert.equal(f.saved.length,2);assert.ok(button('기억 삭제'));
 button('기억 삭제').onclick();await button('삭제하기').onclick();
 assert.equal(f.saved.length,1);assert.equal(f.saved[0].memory_key,'two');assert.equal(f.context.records.length,1);
 assert.equal(f.calls.filter(c=>c.url.endsWith('/ux/delete')).length,1);assert.equal(f.get('detailTitle').textContent,'기억을 삭제했어요.');
 assert.ok(!button('기억 삭제'));
});

test('all original CSS is preserved and inline code remains valid',()=>{
  const before=fs.readFileSync(path.join(__dirname,'fixtures/original-style.css'),'utf8');
  const after=fs.readFileSync(path.join(__dirname,'index.html'),'utf8');
  assert.equal(after.match(/<style>([\s\S]*?)<\/style>/)[1],before);
  for(const match of after.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g))new vm.Script(match[1]);
  assert.ok(!after.includes('demoCases'));
});
test('writing stores the original title, explicit date and body, and restores after reopening',async()=>{
  const f=await fixture();
  assert.equal(f.context.records.length,0);
  f.get('recordTitle').value='시험 제목';f.get('recordBody').value='어제 도서관에서 책을 읽었다.';f.get('recordDate').value='2026-11-08';
  await f.context.addRecord();
  assert.match(f.saved[0].text,/^제목: 시험 제목\n기록일: 2026-11-08\n감정: 미지정\n\n어제 도서관에서 책을 읽었다\.$/);
  assert.equal(f.context.records[0].date,'2026-11-08');assert.equal(f.get('recordBody').value,'');
  const reopened=await fixture(undefined,{archive:f.saved});
  assert.equal(reopened.context.records.length,1);assert.equal(reopened.context.records[0].title,'시험 제목');
  assert.equal(reopened.context.records[0].type,'일기');
});
test('home diary requires confirmation, prevents duplicate saves and keeps separate conversations',async()=>{
  const f=await fixture();f.get('homeSearch').value='2026-11-08 도서관에 갔다.';
  await f.context.startChatFromHome();assert.equal(f.saved.length,0);assert.ok(f.value('pendingRecord'));
  await f.context.handleChatInput('네');assert.equal(f.saved.length,1);
  f.context.newChat();assert.equal(f.value('currentConversation().length'),0);
  assert.equal(f.value('chatHistoryState.threads.length'),1);
  assert.ok(f.value('chatHistoryState.threads[0].messages.some(message=>message.text.includes("저장했어요"))'));
  f.get('homeSearch').value='2026-11-08 도서관에 갔다.';await f.context.startChatFromHome();
  assert.equal(f.saved.length,1);assert.equal(f.value('pendingRecord'),null);
  f.context.newChat();f.value('openChat(chatHistoryState.threads[1])');
  assert.ok(f.get('conversation').textContent.includes('저장했어요'));
});
test('retrieval sends recent context, renders citations and clears context for a new chat',async()=>{
  const f=await fixture((url,payload)=>url.endsWith('/intent')?{intent:'question'}:{answer:{answer:'도서관에서 책을 읽었어요.',citations:[{quote:'도서관에서 책을 읽었다.',diary_date:'2026-11-08'}]}});
  await f.context.handleChatInput('11월 8일 어디 갔어?');
  await f.context.handleChatInput('그때 뭐 했어?');
  const searches=f.calls.filter(call=>call.url.endsWith('/search'));
  assert.equal(searches[0].payload.conversation.length,0);assert.equal(searches[1].payload.conversation.length,2);
  assert.equal(searches[1].payload.config.route,'M1');assert.equal(searches[1].payload.config.top_k,3);
  assert.equal(f.get('conversation').querySelectorAll('.message-sources').length,2);
  f.context.newChat();await f.context.handleChatInput('다른 기억을 찾아줘');
  assert.equal(f.calls.filter(call=>call.url.endsWith('/search')).at(-1).payload.conversation.length,0);
});
test('ambiguous schedule time is clarified before saving',async()=>{
  const f=await fixture(()=>({intent:'schedule',title:'회의'}));
  await f.context.handleChatInput('내일 3시에 회의 일정 기록해 줘');
  assert.equal(f.value('pendingClarification.kind'),'time');assert.equal(f.saved.length,0);
  await f.context.handleChatInput('오후 3시');assert.ok(f.value('pendingRecord'));
  await f.context.handleChatInput('네');assert.match(f.saved[0].text,/일정 시각: 15:00/);
});
test('save failures retain the draft and never report a successful save',async()=>{
  const f=await fixture();f.failSave();f.get('recordTitle').value='보존';f.get('recordBody').value='남겨야 할 원문';f.get('recordDate').value='2026-11-08';
  await f.context.addRecord();assert.equal(f.saved.length,0);assert.equal(f.get('recordBody').value,'남겨야 할 원문');assert.match(f.get('#emotion .notice').textContent,/저장 실패/);
});
test('archive semantic search maps backend source IDs and does not inherit chat context',async()=>{
  const archive=[{memory_key:'a'.repeat(64),source_id:'SOURCE-A',summary:'요약',text:'제목: 산책\n기록일: 2026-11-08\n감정: 미지정\n\n공원을 걸었다.'}];
  const f=await fixture(()=>({retrieval:{selected_sources:[{source_id:'SOURCE-A'}]}}),{archive});
  f.get('archiveInput').value='걷기';await f.context.runSearch(true);
  assert.match(f.get('searchResults').innerHTML,/산책/);assert.match(f.get('searchResults').innerHTML,/의미 유사/);
  assert.equal(f.calls.at(-1).payload.conversation.length,0);
  f.context.searchFilter='exact';await f.context.runSearch(true);assert.ok(!f.get('searchResults').innerHTML.includes('산책'));
});
test('settings persist and missing models produce visible errors instead of fake replies',async()=>{
  const f=await fixture();f.get('showSources').onchange({target:{checked:false}});
  assert.equal(JSON.parse(f.storage.get('plant-thought-preferences-v1')).showSources,false);
  f.failModels();await f.context.handleChatInput('새 질문');assert.match(f.get('conversation').textContent,/모델 준비 화면/);
  assert.equal(f.get('chatInput').value,'새 질문');assert.equal(f.saved.length,0);
});
test('proxy serves assets, forwards authenticated requests and rejects unrelated paths and origins',async t=>{
  const {createPlantServer}=require('./preview.cjs');let forwarded;
  const upstream=http.createServer((req,res)=>{forwarded={origin:req.headers.origin,token:req.headers['x-memory-lab-token']};res.setHeader('Content-Type','application/json');res.end('{"ok":true}');});
  await new Promise(resolve=>upstream.listen(0,'127.0.0.1',resolve));t.after(()=>upstream.close());
  const server=createPlantServer({backendPort:upstream.address().port});await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));t.after(()=>server.close());
  const base='http://127.0.0.1:'+server.address().port;
  assert.equal((await fetch(base+'/memory.js')).status,200);
  assert.equal((await fetch(base+'/../AGENTS.md')).status,404);
  assert.equal((await fetch(base+'/api/baseline/summary-memory/save',{method:'POST',headers:{Origin:'http://other.test','Content-Type':'application/json','X-Memory-Lab-Token':'test-token'},body:'{}'})).status,403);
  assert.equal((await fetch(base+'/api/baseline/summary-memory/save',{method:'POST',headers:{Origin:base,'Content-Type':'application/json','X-Memory-Lab-Token':'test-token'},body:'{}'})).status,200);
  assert.equal(forwarded.origin,'http://127.0.0.1:'+upstream.address().port);assert.equal(forwarded.token,'test-token');
});
