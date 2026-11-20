'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),http=require('node:http');
const {Library}=require('../ui/library.cjs'),{buildReadiness,createReadinessApi}=require('../ui/archive-readiness.cjs');
function fixture(t,empty=false){const dir=fs.mkdtempSync(path.join(os.tmpdir(),'pma-ready-personal-'));let library;
 if(!empty){library=new Library(dir);library.save(0,()=>({threads:[],records:[
  {id:'ready',revision:2,title:'준비된 기록',body:'검색할 개인 기록',search_enabled:true},
  {id:'excluded',title:'검색 제외',body:'보관만 하는 개인 기록',search_enabled:false},
  {id:'deleted',title:'삭제된 기록',body:'숨긴 원문',search_enabled:true,deleted_at:'2026-11-19T00:00:00Z'},
  {id:'invalid',title:'빈 원문',body:'',search_enabled:true}
 ]}));}
 t.after(()=>{library?.close();if(path.dirname(dir)===os.tmpdir()&&path.basename(dir).startsWith('pma-ready-personal-'))fs.rmSync(dir,{recursive:true,force:true});});return {dir,library};}
test('normal mode reports personal readiness, exclusions and invalid originals without samples or model work',async t=>{
 const {dir,library}=fixture(t),before=library.read(),notice=library.indexNotice();const result=await buildReadiness(dir,{collection:'personal'});
 assert.equal(result.collection,'personal');assert.deepEqual(result.counts,{total:3,ready:1,error:1,excluded:1});assert.equal(result.model_inference,false);
 assert.deepEqual(result.records.map(r=>r.record_id),['ready','excluded','invalid']);assert.equal(result.records[0].search_revision,2);assert.equal(result.records[1].search_revision,null);assert.equal(result.records[1].original_checked,true);
 assert.ok(result.records.every(r=>!('body'in r)&&!('text'in r)));assert.deepEqual(library.read(),before);assert.deepEqual(library.indexNotice(),notice);
});
test('empty personal library reports zero records and creates no database',async t=>{
 const {dir}=fixture(t,true),result=await buildReadiness(dir,{collection:'personal'});assert.deepEqual(result.records,[]);assert.equal(result.counts.total,0);assert.equal(fs.existsSync(path.join(dir,'.local')),false);
});
test('personal readiness refresh observes changes to search settings and record revisions',async t=>{
 const {dir,library}=fixture(t);await buildReadiness(dir,{collection:'personal'});library.save(library.read().revision,state=>({...state,records:state.records.map(r=>r.id==='excluded'?{...r,revision:4,search_enabled:true}:r)}));
 const result=await buildReadiness(dir,{collection:'personal'});assert.equal(result.counts.ready,2);assert.equal(result.records.find(r=>r.record_id==='excluded').search_revision,4);
 await assert.rejects(()=>buildReadiness(dir,{collection:'other'}),/자료함/);
});
test('personal endpoint is read-only and rejects cross-origin and write requests',async t=>{
 const {dir,library}=fixture(t),api=createReadinessApi(dir),server=http.createServer((req,res)=>api.handle(req,res,new URL(req.url,'http://127.0.0.1')));await new Promise(r=>server.listen(0,'127.0.0.1',r));t.after(()=>new Promise(r=>server.close(r)));
 const url='http://127.0.0.1:'+server.address().port+'/api/archive/readiness?collection=personal',revision=library.read().revision;
 const response=await fetch(url);assert.equal(response.status,200);assert.equal((await response.json()).records.length,3);
 assert.equal((await fetch(url,{method:'POST'})).status,405);assert.equal((await fetch(url,{headers:{Origin:'http://elsewhere.invalid'}})).status,403);assert.equal(library.read().revision,revision);
});
