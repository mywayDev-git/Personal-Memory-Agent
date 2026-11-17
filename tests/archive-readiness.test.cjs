'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const root=process.env.PMA_APP_ROOT||path.resolve(__dirname,'..'),{buildReadiness,describeRecord,createReadinessApi}=require('../ui/archive-readiness.cjs'),{loadScope}=require('../ui/chat-api.cjs');
const dir=path.join(root,'datasets/pma-generalization-v1.0.0'),questions=JSON.parse(fs.readFileSync(path.join(dir,'questions.json'))).questions;
test('readiness matches actual chat access for all cases and never claims a model run',async()=>{
  for(const q of questions){const result=await buildReadiness(root,{profile:q.profile,example_id:q.id}),scope=await loadScope(root,{profile:q.profile,example_id:q.id});assert.deepEqual(result.records.filter(r=>r.status==='ready').map(r=>r.record_id).sort(),scope.sources.map(s=>s.id).sort());assert.equal(result.model_inference,false);assert.equal(result.records.length,199);assert.equal(result.counts.total,result.counts.ready+result.counts.error);assert.ok(result.records.every(r=>!('text'in r)&&!('gold'in r)&&(!r.search_revision||r.search_revision===r.revision)));}
});
test('valid originals are ready regardless of example scope; invalid originals remain errors',()=>{
  const source={id:'x',revision:1,text:'원문',metadata:{title:'기록'}};
  assert.equal(describeRecord(source).status,'ready');assert.equal(describeRecord({...source,text:''}).status,'error');
});
test('question metadata is validated but even the former empty-memory example searches all originals',async()=>{
  const first=questions.find(q=>q.profile==='development');await assert.rejects(()=>buildReadiness(root,{profile:'confirmation',example_id:first.id}),/범위/);
  const q=questions.find(q=>q.text.includes('새 세션의 기억'));assert.ok(q);const result=await buildReadiness(root,{profile:q.profile,example_id:q.id});assert.equal(result.counts.ready,199);assert.equal(result.counts.error,0);assert.equal(result.scope_mode,'all-originals');assert.ok(!result.records.some(r=>r.status==='excluded'));
});
test('status endpoint is read-only, same-origin and independent of the model service',async t=>{
  const api=createReadinessApi(root),server=http.createServer((req,res)=>api.handle(req,res,new URL(req.url,'http://127.0.0.1')));await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));t.after(()=>new Promise(resolve=>server.close(resolve)));
  const q=questions[0],url='http://127.0.0.1:'+server.address().port+'/api/archive/readiness?profile='+q.profile+'&example_id='+encodeURIComponent(q.id);
  const response=await fetch(url);assert.equal(response.status,200);assert.equal((await response.json()).model_inference,false);assert.equal((await fetch(url,{method:'POST'})).status,405);assert.equal((await fetch(url,{headers:{Origin:'http://untrusted.example'}})).status,403);
});
