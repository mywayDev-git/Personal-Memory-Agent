'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),http=require('node:http'),fs=require('node:fs'),vm=require('node:vm'),os=require('node:os'),path=require('node:path');
const root=process.env.PMA_APP_ROOT||path.resolve(__dirname,'..');
const {createChatApi}=require(root+'/ui/chat-api.cjs'),{label,createProgress,normalizeTrace}=require(root+'/ui/chat-progress.cjs');
const gate=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};
const data={request_id:'progress-request',thread_id:'thread-a',text:'1 더하기 1은?',input_version:1,collection_id:'personal',profile:'personal',example_id:'',history:[]};
async function client(t,chat){const api=createChatApi(root,{runtime:async()=>({chat}),scope:async()=>({id:'personal',now:'2026-11-20',sources:[]})}),server=http.createServer((req,res)=>api.handle(req,res,new URL(req.url,'http://127.0.0.1')));await new Promise(r=>server.listen(0,'127.0.0.1',r));t.after(()=>new Promise(r=>server.close(r)));const url='http://127.0.0.1:'+server.address().port,token=(await(await fetch(url+'/api/chat/bootstrap')).json()).token;return async(route,value,key=token)=>{const res=await fetch(url+'/api/chat/'+route,{method:'POST',headers:{'Content-Type':'application/json','X-Plant-Token':key},body:JSON.stringify(value)});return {status:res.status,data:await res.json()};};}
test('progress is authenticated, bound to its request and cleared when the answer completes',async t=>{
 const started=gate(),finish=gate(),post=await client(t,async()=>{started.resolve();await finish.promise;return {parsed:{intent:'general',action:'answer',answer:'2입니다.',citations:[]}};});
 const pending=post('respond',data);await started.promise;
 assert.equal((await post('progress',data,'wrong')).status,403);
 assert.equal((await post('progress',{...data,thread_id:'other'})).status,409);
 const state=await post('progress',data);assert.equal(state.data.status,'pending');assert.match(state.data.progress.label,/1 더하기 1은/);assert.match(state.data.progress.label,/답변/);assert.ok(state.data.progress.steps.length>=2);assert.ok(state.data.progress.elapsed_ms>=0);assert.equal(state.data.progress.steps.at(-1).status,'running');assert.ok(!JSON.stringify(state.data).includes('messages'));
 finish.resolve();const answer=await pending;assert.equal(answer.status,200);assert.equal(answer.data.processing_trace.version,'chat-progress-v1');assert.ok(answer.data.processing_trace.steps.every(s=>s.status==='finished'));assert.equal(answer.data.processing_trace.steps.length,state.data.progress.steps.length+1);const duplicate=await post('respond',data);assert.deepEqual(duplicate.data.processing_trace,answer.data.processing_trace);const done=await post('progress',data);assert.equal(done.data.status,'finished');assert.equal(done.data.progress,null);
});
test('cancellation does not leave live progress or block another request',async t=>{
 const started=gate(),post=await client(t,async(m,s,c,signal)=>{started.resolve();return new Promise((resolve,reject)=>signal.addEventListener('abort',()=>reject(signal.reason),{once:true}));});
 const pending=post('respond',data);await started.promise;assert.equal((await post('cancel',data)).data.cancelled,true);assert.equal((await pending).status,499);assert.equal((await post('progress',data)).data.progress,null);
});
test('real goal stages expose actual search query and returned record titles; skip means no search notice',async t=>{
 const {Library}=require(root+'/ui/library.cjs'),{ActionService}=require(root+'/ui/action-service.cjs'),{respond}=require(root+'/ui/goal-agent.cjs');
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'pma-progress-')),library=new Library(dir),service=new ActionService(library);t.after(()=>{library.close();if(path.dirname(dir)!==path.resolve(os.tmpdir())||!path.basename(dir).startsWith('pma-progress-'))throw Error('Unexpected test directory');fs.rmSync(dir,{recursive:true,force:true});});library.save(0,s=>({...s,threads:[{id:'thread-a',messages:[]}]}));
 for(const search of [true,false]){const events=[],request={...data,request_id:search?'search':'skip',analysis_version:'v2',search_mode:'G1-linked',inspect:true};let searched=0;
  const runtime={async chat(messages){const phase=messages.flatMap(m=>{try{return [JSON.parse(m.content).phase];}catch{return [];}}).find(Boolean);return {parsed:phase==='goal_plan'?{goal:'11월 참석 행사 정리',context_summary:'',related_turn_ids:[],task_id:'',review_proposal_ids:[],reply_guidance:'',steps:search?[{tool:'search',purpose:'행사 확인',query:'11월 참석 행사',target_id:'',source_turn_ids:[]}]:[]}:{support:[],answer:'정리했어요.',outcome:'answered',question:''}};}};
  await respond({data:request,runtime,service,conversation:async()=>[],getScope:async()=>({id:'personal',sources:[]}),retrieve:()=>[],searchRecords:async()=>{searched++;return {evidence:[{source_id:'r',revision:1,start:0,text:'글쓰기 모임에 참석했다.',metadata:{title:'11월 글쓰기 모임'}}],trace:{}};},onProgress:e=>events.push(e)});
  assert.equal(searched,Number(search));assert.equal(events.some(e=>e.phase==='search'),search);assert.equal(events.some(e=>e.phase==='review'||e.phase==='change'),false);
  if(search){assert.equal(events.find(e=>e.phase==='search').target,'11월 참석 행사');assert.deepEqual(events.find(e=>e.phase==='evidence').titles,['11월 글쓰기 모임']);}
  assert.equal(events.find(e=>e.phase==='answer').target,'11월 참석 행사 정리');assert.ok(events.findIndex(e=>e.phase==='validate')>events.findIndex(e=>e.phase==='answer'));
 }
});

class Element{
 constructor(tag,text='',cls=''){this.tag=tag;this._text=text||'';this.className=cls;this.children=[];this.dataset={};this.attrs={};this.listeners={};}
 get textContent(){return this._text+this.children.map(c=>c.textContent).join('');}set textContent(value){this._text=String(value);this.children=[];}
 addEventListener(name,fn){(this.listeners[name]??=[]).push(fn);}emit(name){for(const listener of this.listeners[name]||[])listener();}
 append(...children){this.children.push(...children);}replaceChildren(...children){this._text='';this.children=children;}setAttribute(name,value){this.attrs[name]=value;}
 querySelectorAll(selector){const result=[];for(const child of this.children){if(child.className.split(' ').includes(selector.slice(1)))result.push(child);result.push(...child.querySelectorAll(selector));}return result;}
 querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
}
function watcher(){
 const source=fs.readFileSync(root+'/ui/plant-thought/chat-connect.js','utf8'),start=source.indexOf('  function progressDuration('),end=source.indexOf('  async function run(',start),controller=new AbortController(),message={status:'pending',submission:{request_id:'r',thread_id:'t'}},controllers=new Map([['r',{controller,startedAt:0}]]),panels=[new Element('details'),new Element('details')];panels[0].dataset.requestId='r';panels[1].dataset.requestId='other';
 let tick,cleared=false,result,clock=0,jsonHook=null,polls=0;const node=(tag,text,cls)=>new Element(tag,text,cls),sandbox={token:'token',controllers,node,performance:{now:()=>clock},window:{},document:{querySelector:()=>null,querySelectorAll:()=>panels},setInterval:fn=>(tick=fn,1),clearInterval:()=>{cleared=true;},fetch:async()=>{polls++;return {ok:true,json:async()=>jsonHook?jsonHook():result};}};
 vm.runInNewContext(source.slice(start,end)+';this.watch=watchProgress;this.render=renderProgress;this.duration=progressDuration;this.completed=completedProgress;this.retain=retainProcessingTrace;',sandbox);const stop=sandbox.watch(message,controller);
 return {message,controller,controllers,panels,stop,tick:()=>tick(),advance:ms=>{clock+=ms;},set:r=>{result=r;},json:fn=>{jsonHook=fn;},cleared:()=>cleared,polls:()=>polls,render:panel=>sandbox.render(panel,message,controllers.get('r')),duration:sandbox.duration,completed:sandbox.completed,retain:result=>sandbox.retain(result,controllers.get('r'))};
}
const activity=(sequence,steps,elapsed=1500)=>({request_id:'r',thread_id:'t',status:'pending',progress:{label:steps.at(-1).label,sequence,elapsed_ms:elapsed,steps:steps.map((step,i)=>({phase:'test',sequence:i+1,started_ms:i*1000,elapsed_ms:500,status:i===steps.length-1?'running':'finished',...step}))}});
test('short server stages are retained with fixed finished durations and a live running duration',()=>{
 let clock=10;const progress=createProgress(()=>clock);progress.update({phase:'understand',target:'11월 행사'});clock=25;progress.update({phase:'search',target:'11월 참석 행사',scope:'personal'});clock=26;progress.update({phase:'evidence',titles:['글쓰기 모임']});clock=1026;
 const snap=progress.snapshot();assert.equal(snap.steps.length,3);assert.equal(snap.elapsed_ms,1016);assert.deepEqual(snap.steps.map(s=>s.elapsed_ms),[15,1,1000]);assert.deepEqual(snap.steps.map(s=>s.status),['finished','finished','running']);
 progress.update({phase:'evidence',titles:['글쓰기 모임']});assert.equal(progress.snapshot().steps.length,3);snap.steps[0].label='mutated';clock=2026;assert.notEqual(progress.snapshot().steps[0].label,'mutated');assert.equal(progress.snapshot().steps[2].elapsed_ms,2000);
});
test('UI stacks every stage, wraps its text and advances clocks without another server response',async()=>{
 const w=watcher();w.set(activity(2,[{label:'질문 확인',elapsed_ms:1000},{label:'11월 행사 검색 중'}]));await w.tick();const panel=w.panels[0];assert.equal(panel.querySelectorAll('.ai-progress-step').length,2);assert.equal(w.panels[1].children.length,0);assert.match(panel.querySelector('.ai-progress-total').textContent,/1.5초/);
 w.advance(250);await w.tick();assert.equal(w.polls(),1);assert.match(panel.querySelector('.ai-progress-total').textContent,/1.8초/);const times=panel.querySelectorAll('.ai-progress-time');assert.equal(times[0].textContent,'1.0초');assert.match(times[1].textContent,/0.8초/);
 w.advance(250);w.set(activity(3,[{label:'질문 확인',elapsed_ms:1000},{label:'11월 행사 검색 중',elapsed_ms:900},{label:'찾은 기록 검토 중'}],2200));await w.tick();assert.equal(panel.querySelectorAll('.ai-progress-step').length,3);assert.match(panel.textContent,/찾은 기록 검토 중/);
 const recreated=new Element('section');w.render(recreated);assert.equal(recreated.querySelectorAll('.ai-progress-step').length,3);assert.equal(recreated.querySelector('.ai-progress-current').textContent,'찾은 기록 검토 중');
 assert.equal(w.duration(65100),'1분 5.1초');w.stop();assert.equal(w.cleared(),true);
});
test('stopped or superseded requests cannot redraw the activity panel',async()=>{
 for(const kind of ['success','stop','retry']){const w=watcher();if(kind==='success')w.message.status='success';if(kind==='stop')w.controller.abort();if(kind==='retry')w.controllers.set('r',{controller:new AbortController()});w.set(activity(1,[{label:'늦은 안내'}]));await w.tick();assert.equal(w.panels[0].children.length,0);assert.equal(w.polls(),0);}
});
test('public summaries are single-line and describe changes as drafts, never completed writes',()=>{
 assert.match(label({phase:'change',target:'보관함\n번호',tool:'delete'}),/삭제 초안/);assert.ok(!label({phase:'change',target:'보관함\n번호',tool:'delete'}).includes('\n'));assert.equal(label({phase:'unknown',target:'private prompt'}),'');
});


test('an in-flight progress response cannot redraw the final answer, and elapsed time still updates during slow polling',async()=>{
 const w=watcher(),arrived=gate(),finish=gate();w.json(async()=>{arrived.resolve();await finish.promise;return activity(1,[{label:'늦게 도착한 안내'}]);});const poll=w.tick();await arrived.promise;w.advance(1750);await w.tick();assert.match(w.panels[0].querySelector('.ai-progress-total').textContent,/1.8초/);assert.equal(w.polls(),1);
 w.message.status='success';w.panels[0].textContent='최종 답변';finish.resolve();await poll;assert.equal(w.panels[0].textContent,'최종 답변');
});

test('finished timings freeze exactly once and late updates cannot change a completed trace',()=>{
 let now=0;const progress=createProgress(()=>now);progress.update({phase:'understand',target:'질문'});now=100;progress.update({phase:'answer',target:'답변'});now=350;const final=progress.finish();assert.equal(final.elapsed_ms,350);assert.deepEqual(final.steps.map(s=>s.elapsed_ms),[100,250]);assert.ok(final.steps.every(s=>s.status==='finished'));
 now=5000;progress.update({phase:'search',target:'늦은 안내'});assert.deepEqual(progress.finish(),final);assert.equal(progress.snapshot().elapsed_ms,350);
});
test('completed details start collapsed, keep a fixed total, and can reveal finished stages',()=>{
 const w=watcher(),progress=createProgress(()=>0);progress.update({phase:'answer',target:'행사 정리'});const result={elapsed_ms:123,processing_trace:progress.finish()};w.advance(8400);w.retain(result);assert.equal(result.processing_trace.elapsed_ms,8400);assert.equal(result.elapsed_ms,123);
 const panel=w.completed(result);assert.equal(panel.tag,'details');assert.ok(!panel.open);assert.match(panel.querySelector('.ai-progress-total').textContent,/전체 소요 8.4초/);assert.equal(panel.querySelectorAll('.ai-progress-step').length,1);assert.equal(panel.querySelectorAll('.is-running').length,0);assert.ok(!panel.textContent.includes('진행 중'));
 panel.open=true;assert.match(panel.querySelector('.ai-progress-list').textContent,/행사 정리/);w.advance(20000);assert.match(panel.querySelector('.ai-progress-total').textContent,/8.4초/);assert.equal(w.completed({elapsed_ms:999}),null);
});
test('saved replies and JSON backups retain the completed trace after reopening the library',t=>{
 const {Library,makeBackup,readBackup}=require(root+'/ui/library.cjs'),dir=fs.mkdtempSync(path.join(os.tmpdir(),'pma-completed-progress-'));let library=new Library(dir);t.after(()=>{library?.close();if(path.dirname(dir)===path.resolve(os.tmpdir())&&path.basename(dir).startsWith('pma-completed-progress-'))fs.rmSync(dir,{recursive:true,force:true});});
 let now=0;const progress=createProgress(()=>now);progress.update({phase:'understand',target:data.text});now=50;progress.update({phase:'answer',target:data.text});now=150;const trace=normalizeTrace(progress.finish());
 const thread={id:data.thread_id,messages:[{kind:'assistant',status:'success',submission:data,result:{request_id:data.request_id,thread_id:data.thread_id,answer:'2입니다.',action:'answer',intent:'general',citations:[],scope:{mode:'personal',accessible_count:0,retrieved_count:0},processing_trace:trace}}]};
 library.save(0,state=>({...state,threads:[thread]}));library.close();library=new Library(dir);const stored=library.read();assert.deepEqual(stored.threads[0].messages[0].result.processing_trace,trace);const backup=makeBackup(stored);assert.deepEqual(readBackup(JSON.parse(JSON.stringify(backup))).threads[0].messages[0].result.processing_trace,trace);
 for(const patch of [{elapsed_ms:-1},{elapsed_ms:NaN},{steps:[{...trace.steps[0],status:'running'}]},{steps:[{...trace.steps[0],elapsed_ms:Infinity}]},{steps:[{...trace.steps[0],started_ms:999}]}])assert.throws(()=>normalizeTrace({...trace,...patch}),/처리 과정/);
});

test('live details start closed with the current action and time, and keep the user toggle through updates and redraws',async()=>{
 const w=watcher();w.set(activity(2,[{label:'질문 확인',elapsed_ms:1000},{label:'11월 행사 기록을 찾고 있어요.'}]));await w.tick();const panel=w.panels[0],summary=panel.querySelector('.ai-progress-heading');
 assert.equal(panel.tag,'details');assert.equal(summary.tag,'summary');assert.equal(panel.open,false);assert.match(summary.textContent,/11월 행사 기록을 찾고 있어요/);assert.match(summary.textContent,/전체 경과 1.5초/);assert.ok(!summary.textContent.includes('처리 과정'));assert.equal(panel.querySelectorAll('.ai-progress-step').length,2);
 panel.open=true;panel.emit('toggle');w.advance(500);w.set(activity(3,[{label:'질문 확인'},{label:'11월 행사 기록을 찾고 있어요.'},{label:'글쓰기 모임 원문을 확인하고 있어요.'}],2500));await w.tick();assert.equal(panel.open,true);assert.equal(panel.querySelectorAll('.ai-progress-step').length,3);assert.match(summary.textContent,/글쓰기 모임 원문/);
 const reopened=new Element('details');w.render(reopened);assert.equal(reopened.open,true);reopened.open=false;reopened.emit('toggle');const collapsed=new Element('details');w.render(collapsed);assert.equal(collapsed.open,false);assert.match(collapsed.querySelector('.ai-progress-heading').textContent,/글쓰기 모임 원문/);
 w.advance(250);await w.tick();assert.equal(panel.querySelector('.ai-progress-total').textContent,'전체 경과 2.8초');w.stop();
});
