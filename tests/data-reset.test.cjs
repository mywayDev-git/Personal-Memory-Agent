'use strict';
// Manual execution only. All data lives in new temp folders; no real models or app server are used.
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),http=require('node:http');
const root=path.resolve(__dirname,'..'),{Library}=require(path.join(root,'ui/library.cjs'));
const {createBaselineReset,emptyOwnedDirectory}=require(path.join(root,'local/baseline-data-reset.cjs'));
const {createDataReset}=require(path.join(root,'ui/data-reset.cjs'));
function temporary(t){const dir=fs.mkdtempSync(path.join(os.tmpdir(),'pma-reset-'));t.after(()=>{assert.equal(path.dirname(path.resolve(dir)),path.resolve(os.tmpdir()));assert.ok(path.basename(dir).startsWith('pma-reset-'));fs.rmSync(dir,{recursive:true,force:true});});return dir;}
function library(t){const dir=temporary(t),store=new Library(dir);t.after(()=>store.close());return store;}
function managed(t){const closers=[];const harness={after:fn=>closers.push(fn)};t.after(async()=>{for(const fn of closers.reverse())await fn();});return harness;}
function seed(store){store.save(0,s=>({...s,threads:[{id:'thread',title:'개인 대화',messages:[{kind:'user',text:'보존하지 않을 개인 내용'}],draft:'작성 중'}],records:[{id:'record',revision:1,title:'개인 기록',body:'원문 내용',date:null,created_at:null,search_enabled:true}]}));store.db.exec("CREATE TABLE IF NOT EXISTS reset_extra(value TEXT); INSERT INTO reset_extra VALUES('개인 이력')");}
test('bulk erase clears records, conversations and auxiliary data and changes the storage epoch',t=>{
 const h=managed(t),store=library(h);seed(store);const before=store.storageInfo(),rev=store.read().revision,result=store.eraseAll(rev,'reset-a');
 assert.deepEqual(store.read(),{revision:rev+1,threads:[],records:[]});assert.equal(store.db.prepare('SELECT count(*) n FROM reset_extra').get().n,0);
 assert.notEqual(store.storageInfo().storage_epoch,before.storage_epoch);assert.equal(store.storageInfo().storage_reset_count,1);
 assert.throws(()=>store.assertEpoch(before.storage_epoch),/전체 삭제/);assert.throws(()=>store.assertEpoch(undefined),/전체 삭제/);assert.doesNotThrow(()=>store.assertEpoch(store.storageInfo().storage_epoch));
 assert.deepEqual(store.eraseAll(rev,'reset-a'),result);assert.equal(store.read().revision,rev+1);store.completeReset('reset-a');assert.equal(store.lastReset().completed,true);
});
test('stale confirmation and reset-time writes leave data intact',t=>{
 const h=managed(t),store=library(h);seed(store);const before=store.read(),epoch=store.storageInfo();assert.throws(()=>store.eraseAll(0,'wrong'),/변경/);assert.deepEqual(store.read(),before);assert.deepEqual(store.storageInfo(),epoch);
 store.resetting=true;assert.throws(()=>store.save(before.revision,s=>s),/정리 중/);assert.throws(()=>store.assertEpoch(epoch.storage_epoch),/정리 중/);store.resetting=false;assert.deepEqual(store.read(),before);
});
test('baseline reset requires a lease, empties virtual tables and removes only generated directories',async t=>{
 const h=managed(t),dir=temporary(h),{Store}=require(path.join(root,'local/store.cjs')),store=new Store(dir);h.after(()=>store.db.close());
 store.db.exec("CREATE VIRTUAL TABLE reset_fts USING fts5(text); INSERT INTO reset_fts VALUES('검색 원문')");
 for(const relative of ['.local/baseline/artifacts/a.json','.local/baseline/runtime/generation.log','datasets/sources.json','.models/model.gguf']){const target=path.join(dir,relative);fs.mkdirSync(path.dirname(target),{recursive:true});fs.writeFileSync(target,'fixture');}
 let paused=0,stopped=0,resumed=0,forgotten=0;
 const reset=createBaselineReset({root:dir,store,busy:null},{async stopAll(){stopped++;}},{indexes:{async suspend(){paused++;},resume(){resumed++;}},forget(){forgotten++;}});
 await assert.rejects(reset.clear('reset-a'),/먼저 준비/);await reset.begin('reset-a');await reset.clear('reset-a');reset.release('reset-a');
 assert.equal(store.db.prepare('SELECT count(*) n FROM reset_fts').get().n,0);assert.equal(fs.readdirSync(path.join(dir,'.local/baseline/artifacts')).length,0);assert.equal(fs.readdirSync(path.join(dir,'.local/baseline/runtime')).length,0);
 assert.ok(fs.existsSync(path.join(dir,'datasets/sources.json')));assert.ok(fs.existsSync(path.join(dir,'.models/model.gguf')));assert.equal(paused,1);assert.equal(stopped,1);assert.equal(resumed,1);assert.equal(forgotten,1);
});
test('directory cleanup rejects paths outside the owned app data folder',t=>{
 const h=managed(t),dir=temporary(h),outside=temporary(h),file=path.join(outside,'keep.txt');fs.writeFileSync(file,'keep');
 assert.throws(()=>emptyOwnedDirectory(dir,outside),/폴더 밖/);assert.equal(fs.readFileSync(file,'utf8'),'keep');
});
async function client(t,{failClear=false}={}){
 const h=managed(t),store=library(h);seed(store);let clears=0;
 const reset=createDataReset({library:store,chat:{async suspend(){},resume(){}},baselineRequest:async action=>{if(action==='preview')return {runs:2,artifacts:3};if(action==='clear'&&failClear&&++clears===1)throw Error('stub cleanup error');return {};}});
 const server=http.createServer((req,res)=>reset.handle(req,res,new URL(req.url,'http://127.0.0.1')));await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));h.after(()=>new Promise(resolve=>server.close(resolve)));
 const url='http://127.0.0.1:'+server.address().port,preview=await(await fetch(url+'/api/data-reset/preview')).json();
 const body={reset_id:'reset-a',revision:preview.revision,storage_epoch:preview.storage_epoch,confirmation:'전체 삭제'};
 return {store,body,preview,async post(value=body,key=preview.token){const response=await fetch(url+'/api/data-reset',{method:'POST',headers:{'Content-Type':'application/json','X-Data-Reset-Token':key},body:JSON.stringify(value)});return {status:response.status,data:await response.json()};},async status(){return (await fetch(url+'/api/data-reset/status?id=reset-a')).json();}};
}
test('preview and failed confirmation never delete; valid confirmation reports completed',async t=>{
 const c=await client(t);assert.equal(c.store.read().records.length,1);assert.equal((await c.post(c.body,'wrong')).status,403);assert.equal((await c.post({...c.body,confirmation:'삭제'})).status,400);assert.equal(c.store.read().records.length,1);
 assert.equal((await c.post()).data.deleted,true);assert.equal(c.store.read().records.length,0);assert.equal((await c.status()).status,'completed');
 const epoch=c.store.storageInfo().storage_epoch;assert.equal((await c.post()).data.deleted,true);assert.equal(c.store.storageInfo().storage_epoch,epoch);
});
test('partial cleanup stays partial until the same authorized operation succeeds',async t=>{
 const c=await client(t,{failClear:true}),first=await c.post();assert.equal(first.status,503);assert.equal(first.data.partial,true);assert.equal(c.store.read().records.length,0);assert.equal((await c.status()).status,'partial');
 assert.equal((await c.post()).data.deleted,true);assert.equal((await c.status()).status,'completed');
});
