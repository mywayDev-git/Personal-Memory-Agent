'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),http=require('node:http'),path=require('node:path');
const root=process.env.PMA_APP_ROOT||path.resolve(__dirname,'..'),{createChatApi}=require(path.join(root,'ui/chat-api.cjs'));
const data=(id='request-a',thread='thread-a')=>({request_id:id,thread_id:thread,text:'안녕',input_version:1,profile:'personal',example_id:'',collection_id:'personal',history:[]});
const output=()=>({parsed:{intent:'general',action:'answer',answer:'안녕하세요.',citations:[]}});
const gate=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};
async function client(t,chat){const api=createChatApi(root,{runtime:async()=>({chat}),scope:async()=>({id:'personal',now:'2026-11-19',sources:[]})});const server=http.createServer((req,res)=>api.handle(req,res,new URL(req.url,'http://127.0.0.1')));await new Promise(r=>server.listen(0,'127.0.0.1',r));t.after(()=>new Promise(r=>server.close(r)));const url='http://127.0.0.1:'+server.address().port,token=(await(await fetch(url+'/api/chat/bootstrap')).json()).token;return {post:async(route,value,{signal,key=token}={})=>{const r=await fetch(url+'/api/chat/'+route,{method:'POST',headers:{'Content-Type':'application/json','X-Plant-Token':key},body:JSON.stringify(value),signal});return {status:r.status,data:await r.json()};}};}
test('stop aborts the model request, releases the busy slot and allows immutable retry',async t=>{
 const started=gate();let signal,calls=0;
 const c=await client(t,async(m,s,cfg,sig)=>{calls++;if(calls>1)return output();signal=sig;started.resolve();return new Promise((resolve,reject)=>sig.addEventListener('abort',()=>reject(sig.reason),{once:true}));});
 const pending=c.post('respond',data());await started.promise;
 assert.equal((await c.post('cancel',{request_id:'request-a',thread_id:'thread-a'},{key:'wrong'})).status,403);assert.equal(signal.aborted,false);
 assert.equal((await c.post('cancel',{request_id:'request-a',thread_id:'other-thread'})).status,409);assert.equal(signal.aborted,false);
 const stopped=await c.post('cancel',{request_id:'request-a',thread_id:'thread-a'});assert.equal(stopped.data.cancelled,true);assert.equal(signal.aborted,true);assert.equal((await pending).status,499);
 assert.equal((await c.post('respond',data())).status,200);assert.equal(calls,2);
 assert.equal((await c.post('cancel',{request_id:'request-a',thread_id:'thread-a'})).data.cancelled,false);
});
test('a late model completion after stop never becomes a successful cached response',async t=>{
 const started=gate(),late=gate();let calls=0;const c=await client(t,async()=>{if(++calls>1)return output();started.resolve();await late.promise;return output();});
 const pending=c.post('respond',data());await started.promise;await c.post('cancel',data());assert.equal((await pending).status,499);late.resolve();
 assert.equal((await c.post('respond',data('request-b'))).status,200);assert.equal((await c.post('respond',data())).status,200);assert.equal(calls,3);
});
test('disconnecting one duplicate consumer does not cancel a request still being viewed',async t=>{
 const started=gate(),finish=gate();let modelSignal,calls=0;const c=await client(t,async(m,s,cfg,signal)=>{calls++;modelSignal=signal;started.resolve();await finish.promise;return output();});
 const firstAbort=new AbortController(),first=c.post('respond',data(),{signal:firstAbort.signal}).catch(e=>e);await started.promise;
 const second=c.post('respond',data());
 // Let the second HTTP handler subscribe before disconnecting the first.
 await c.post('cancel',{request_id:'unknown',thread_id:'thread-a'});firstAbort.abort();await first;
 assert.equal(modelSignal.aborted,false);finish.resolve();assert.equal((await second).status,200);assert.equal(calls,1);
});
test('disconnecting the final consumer aborts inference and unlocks the next request',async t=>{
 const started=gate(),aborted=gate();let calls=0;const c=await client(t,async(m,s,cfg,signal)=>{if(++calls>1)return output();started.resolve();return new Promise((resolve,reject)=>signal.addEventListener('abort',()=>{aborted.resolve();reject(signal.reason);},{once:true}));});
 const controller=new AbortController(),pending=c.post('respond',data(),{signal:controller.signal}).catch(e=>e);await started.promise;controller.abort();await pending;await aborted.promise;
 assert.equal((await c.post('respond',data('request-b'))).status,200);
});
