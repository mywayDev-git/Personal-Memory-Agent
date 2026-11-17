const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {Engine}=require('../local/engine.cjs'),root=path.resolve(__dirname,'..');
test('all 671 real dataset questions are accepted while invalid selections remain rejected',async()=>{
 const runs=new Map(),engine=new Engine(root,{recover(){},putRun(run){runs.set(run.id,run);}},{version:'OFFLINE'});
 let executed;
 engine.execute=async run=>{executed=run;}; // Verify scheduling without model calls or persistent user records.
 const ds=await engine.dataset('pma-memory-v3.0.0'),ids=ds.d.questions.questions.map(q=>q.id),config={dataset:'pma-memory-v3.0.0',dataset_profile:'all'};
 assert.equal(ids.length,671);
 for(const invalid of [[],[ids[0],ids[0]],['UNKNOWN'],null])await assert.rejects(()=>engine.create({config,question_ids:invalid}),/질문 ID/);
 const run=await engine.create({config,question_ids:ids});
 assert.deepEqual(run.question_ids,ids);assert.equal(runs.get(run.id),run);
 await assert.rejects(()=>engine.create({config,question_ids:ids}),/진행 중/);
 await new Promise(r=>setImmediate(r));assert.equal(executed,run);assert.equal(engine.busy,null);
});
test('UI enables whole dataset after selection and status refresh, sends every question, and preserves busy/stage guards',async()=>{
 const nodes=new Map(),el=s=>{if(!nodes.has(s))nodes.set(s,{value:'',classList:{},textContent:''});return nodes.get(s);};
 const ctx=vm.createContext({document:{querySelector:el,querySelectorAll:()=>[],addEventListener(){}},localStorage:{setItem(){}},console,setTimeout,clearTimeout});
 vm.runInContext(fs.readFileSync(path.join(root,'baseline.js'),'utf8').replace('\ninitialize();','\n').replace('\ninitializeSelectionGuide();','\n'),ctx);
 const run=s=>vm.runInContext(s,ctx);
 run(`data={contexts:{contexts:[]},questions:{questions:Array.from({length:671},(_,i)=>({id:'Q'+i}))}};profileQuestions=()=>data.questions.questions;renderSelectionGuide=()=>{};config=()=>({});renderWorkspace=()=>{};notify=()=>{};saveSettings=()=>{};globalThis.posted=null;api=async(route,body)=>{posted=body;return {id:'TEST',progress:''};};`);
 el('#scope').value='all';el('#route').value='R0';el('#stage').value='end_to_end';
 run('renderStageHelp()');assert.equal(el('#run').disabled,false);assert.match(el('#run').textContent,/671/);
 const status={busy:null,runtime:{states:{generation:{status:'stopped'},embedding:{status:'stopped'}},models:[]}};
 ctx.status=status;run('showRuntime(status)');assert.equal(el('#run').disabled,false);
 status.busy='ACTIVE';run('showRuntime(status)');assert.equal(el('#run').disabled,true);
 status.busy=null;el('#route').value='R0-Full';el('#stage').value='extract';run('showRuntime(status);renderStageHelp()');assert.equal(el('#run').disabled,true);
 el('#route').value='R0';el('#stage').value='end_to_end';run('showRuntime(status);renderStageHelp()');
 await run('run()');assert.equal(run('posted.question_ids.length'),671);assert.equal(el('#run').disabled,true);
});
