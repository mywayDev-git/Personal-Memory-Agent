const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os'),{pathToFileURL}=require('node:url');
const root=path.resolve(__dirname,'..'),dir=path.join(root,'datasets','pma-context-v1.0.0');
const libPromise=import(pathToFileURL(path.join(dir,'lib.mjs')).href);
test('standalone contains exactly 28 natural-only originals, 84 questions and three profiles',async()=>{
 const lib=await libPromise,d=lib.loadDataset(dir),v=lib.validate(d,dir);assert.deepEqual(v.errors,[]);assert.equal(v.ok,true);
 assert.equal(d.sources.records.length,28);assert.equal(d.questions.questions.length,84);assert.equal(d.contexts.contexts.length,24);
 assert.deepEqual(d.manifest.profiles,{natural_single:48,natural_multi:24,natural_control:12});
 assert.ok(d.questions.questions.every(q=>q.id.startsWith('NC-')));assert.equal(d.manifest.counts.legacy_questions,0);
});
test('question gold, original text and scope are unchanged from the authored natural subset',async()=>{
 const lib=await libPromise,d=lib.loadDataset(dir),old=JSON.parse(fs.readFileSync(path.join(root,'datasets','pma-long-v2.0.0','questions.json')));
 for(const q of d.questions.questions)assert.deepEqual(q,old.questions.find(p=>p.id===q.id));
 const source=JSON.parse(fs.readFileSync(path.join(root,'datasets','pma-long-v2.0.0','sources.json')));
 for(const s of d.sources.records)assert.deepEqual(s,source.records.find(p=>p.id===s.id));
});
test('copying just this dataset directory needs no sibling dataset or application authoring files',async()=>{
 const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'pma-context-portable-'));
 try{fs.cpSync(dir,tmp,{recursive:true});const lib=await import(pathToFileURL(path.join(tmp,'lib.mjs')).href),d=lib.loadDataset(tmp);assert.deepEqual(lib.validate(d,tmp).errors,[]);for(const c of d.contexts.contexts){const result=lib.materialize(c,d.sources.records);assert.equal(result.accessible.length,c.expected_state.accessible_sources.length);assert.ok(result.accessible.every(s=>s.metadata.owner_id===c.actor_id));}}
 finally{fs.rmSync(tmp,{recursive:true,force:true});}
});
test('standalone loader accepts natural profiles and rejects inherited control profiles before execution',async()=>{
 const {Engine}=require('../local/engine.cjs');let writes=0;const e=new Engine(root,{recover(){},putRun(){writes++;}},{version:'OFFLINE_NO_MODELS'});
 const ds=await e.dataset('pma-context-v1.0.0');assert.equal(ds.d.questions.questions.length,84);
 assert.equal(e.config({dataset:'pma-context-v1.0.0'}).dataset_profile,'natural_single');
 for(const p of ['all','natural_single','natural_multi','natural_control'])assert.equal(e.config({dataset:'pma-context-v1.0.0',dataset_profile:p}).dataset_profile,p);
 for(const p of ['smoke','core','sentence','boundary','dependency','stress'])assert.throws(()=>e.config({dataset:'pma-context-v1.0.0',dataset_profile:p}),/독립셋|프로필/);
 await assert.rejects(()=>e.create({config:{dataset:'pma-context-v1.0.0',dataset_profile:'natural_single'},question_ids:['LI-roles-short:Q1']}),/질문 ID/);assert.equal(writes,0);
});
