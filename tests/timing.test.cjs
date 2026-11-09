const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const timing=require('../timing.js');
test('completed durations use fixed end time; active durations use now; interrupted missing end stays unknown',()=>{
 const created_at='2026-11-03T00:00:00Z',finished_at='2026-11-03T00:02:03.500Z',now=Date.parse('2026-11-03T00:10:00Z');
 assert.equal(timing.elapsed({created_at,finished_at,status:'COMPLETED'},now),123500);
 assert.equal(timing.elapsed({created_at,status:'RUNNING'},now),600000);
 assert.equal(timing.elapsed({created_at,status:'INTERRUPTED'},now),null);
 assert.equal(timing.elapsed({created_at,status:'ERROR'},now),null);
 assert.equal(timing.elapsed({created_at:'bad',finished_at,status:'COMPLETED'},now),null);
 assert.equal(timing.elapsed({created_at:finished_at,finished_at:created_at,status:'COMPLETED'},now),null);
});
test('formatting distinguishes unrecorded, subsecond, minute and hour durations without 60-second labels',()=>{
 assert.equal(timing.format(null),'기록 없음');assert.equal(timing.format(NaN),'기록 없음');assert.equal(timing.format(-1),'기록 없음');
 assert.equal(timing.format(0),'0.00초');assert.equal(timing.format(125),'0.13초');assert.equal(timing.format(59999),'59.9초');
 assert.equal(timing.format(60000),'1분 0초');assert.equal(timing.format(123500),'2분 3초');assert.equal(timing.format(3661000),'1시간 1분 1초');
});
test('stage times identify reused output and never invent a value for skipped or failed stages',()=>{
 const r={stages:{extraction:{elapsed_ms:1234,reused:true},answer:{elapsed_ms:0}},stage_progress:{retrieval:'ERROR'}};
 assert.deepEqual(timing.stage(r,'extraction'),{ms:1234,reused:true,status:'REUSED'});
 assert.deepEqual(timing.stage(r,'retrieval'),{ms:null,reused:false,status:'ERROR'});
 assert.equal(timing.stage(r,'answer').ms,0);
 assert.equal(timing.stage({stage_progress:{extraction:'SKIPPED'}},'extraction').ms,null);
});
test('history projection returns saved end time without changing original run records',()=>{
 const {Store}=require('../local/store.cjs'),dir=fs.mkdtempSync(path.join(os.tmpdir(),'pma-timing-')),store=new Store(dir);
 try{
  const run={id:'R',created_at:'2026-11-03T00:00:00Z',finished_at:'2026-11-03T00:02:03Z',status:'COMPLETED',stage:'end_to_end',config:{},question_ids:['Q'],results:[],progress:'done'};
  store.putRun(run);const original=JSON.stringify(store.run(run.id)),listed=store.list()[0];
  assert.equal(listed.finished_at,run.finished_at);assert.equal(timing.elapsed(listed),123000);assert.equal(JSON.stringify(store.run(run.id)),original);
  store.putRun({...run,id:'RUNNING',finished_at:undefined,status:'RUNNING'});assert.equal(store.list().find(r=>r.id==='RUNNING').finished_at,null);
 }finally{store.db.close();fs.rmSync(dir,{recursive:true,force:true});}
});
