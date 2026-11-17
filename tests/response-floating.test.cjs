'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),path=require('node:path');
const root=process.env.PMA_APP_ROOT||path.resolve(__dirname,'..');
const {selectResponse,isVisible}=require(path.join(root,'ui/plant-thought/response-floating.js'));
const response=(id,status='success')=>({kind:'assistant',status,submission:{request_id:id,text:'질문 '+id},result:status==='success'?{intent:'memory_query',action:'answer',answer:'답변 '+id,citations:[]}:undefined});
test('floating follows the newest response, including pending, failed and cancelled requests',()=>{
 const a=response('a'),b=response('b','pending'),thread={id:'thread-a',messages:[{kind:'user',text:'질문'},a,b]};
 let current=selectResponse(thread);assert.equal(current.message,b);assert.equal(current.index,1);assert.equal(current.messages.length,2);
 b.status='error';current=selectResponse(thread);assert.equal(current.message.status,'error');b.status='cancelled';assert.equal(selectResponse(thread).message.status,'cancelled');
});
test('selecting a previous response stays on that response when a new answer arrives',()=>{
 const a=response('a'),thread={id:'thread-a',messages:[a,response('b')]};let current=selectResponse(thread,'a');assert.equal(current.message,a);thread.messages.push(response('c','pending'));current=selectResponse(thread,current.selection);assert.equal(current.message,a);assert.equal(current.selection,'a');assert.equal(selectResponse(thread,'latest').message.submission.request_id,'c');
});
test('switching or deleting conversations never shows a response from another conversation',()=>{
 const a={id:'thread-a',messages:[response('a')]},b={id:'thread-b',messages:[response('b')]};const selected=selectResponse(a,'a');const changed=selectResponse(b,selected.selection);assert.equal(changed.selection,'latest');assert.equal(changed.message.submission.request_id,'b');assert.equal(selectResponse({...a,deletedAt:1},'a').message,null);assert.equal(selectResponse({id:'empty',messages:[]},'a').message,null);assert.equal(selectResponse(null,'a').message,null);
});
test('opening a panel only selects existing objects and does not mutate or run a request',()=>{
 const a=response('a'),thread={id:'thread-a',messages:[a]};Object.freeze(a);Object.freeze(thread.messages);Object.freeze(thread);assert.equal(selectResponse(thread,'a').message,a);assert.equal(selectResponse(thread,'missing').selection,'latest');
});
test('floating visibility is restricted to test-mode chat across all navigation targets',()=>{
 for(const page of ['home','chat','emotion','archive','memorylab','settings','recordDetail','login']){assert.equal(isVisible(page,false),false);assert.equal(isVisible(page,true),page==='chat');}assert.equal(isVisible('chat',undefined),false);
});
