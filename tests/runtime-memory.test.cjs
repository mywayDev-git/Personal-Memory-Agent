const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),{EventEmitter}=require('node:events');
const root=process.env.PMA_APP_ROOT||path.resolve(__dirname,'..');
const runtimeFile=process.env.PMA_RUNTIME_FILE||path.join(root,'local','runtime.cjs');
const models=require(path.join(root,'local','model-registry.cjs')),core=require(path.join(root,'local','core.cjs'));
function offline(){
 const launches=[],fakeFs={existsSync:()=>true,mkdirSync(){},openSync:()=>7,closeSync(){},writeFileSync(){},statSync:file=>({size:models.find(m=>file.endsWith(m.file)).bytes,mtimeMs:1})};
 const mockRequire=name=>{
  if(name==='node:fs')return fakeFs;
  if(name==='node:net')return {createServer:()=>({once(){return this;},listen(p,h,cb){cb();},close(cb){cb();}})};
  if(name==='node:child_process')return {spawnSync:()=>({stdout:'OFFLINE-VERSION',stderr:''}),spawn:(exe,args,options)=>{launches.push({exe,args,options});const child=new EventEmitter();child.pid=9000+launches.length;child.exitCode=null;return child;}};
  if(name==='./model-registry.cjs')return models;
  if(name==='./download.cjs')return {fileHash:async file=>models.find(m=>file.endsWith(m.file)).sha256};
  if(name==='./core.cjs')return core;
  if(name==='./request-diagnostics.cjs')return require('../local/request-diagnostics.cjs');
  if(name==='./token-budget.cjs')return require('../local/token-budget.cjs');
  if(name==='./process-control.cjs')return {processControl:()=>{throw Error('No real process control allowed');}};
  return require(name);
 };
 const context=vm.createContext({require:mockRequire,module:{exports:{}},process,console,AbortSignal,setTimeout,clearTimeout,fetch:async url=>{assert.ok(url.endsWith('/health'),'Only a mocked health check is permitted');return {ok:true};}});
 vm.runInContext(fs.readFileSync(runtimeFile,'utf8'),context,{filename:runtimeFile});
 return {runtime:new context.module.exports.Runtime('C:\\offline-memory-fixture'),launches};
}
function expectedArgs(role,model){const file=path.join('C:\\offline-memory-fixture','.models',model.file),key=path.join('C:\\offline-memory-fixture','.local','baseline','runtime',role+'.key');return ['-m',file,'--host','127.0.0.1','--port',role==='generation'?'18491':'18492','-c','8192','-np','1','--no-warmup','--api-key-file',key,'--cors-origins','http://127.0.0.1:'+(process.env.PORT||4319),'--no-cors-credentials',...(role==='generation'?['-b','512','-ub','256','-ngl','99','--reasoning','off','--cache-ram','0']:['-b','8192','-ub','8192','-ngl','0','--embedding','--pooling','last'])];}

test('both supported generation models disable only host prompt cache and record the exact launch settings',async()=>{
 for(const model of models.filter(m=>m.role==='generation')){
  const {runtime,launches}=offline();await runtime.ensure('generation',model.id);
  assert.equal(launches.length,1);assert.deepEqual(Array.from(launches[0].args),expectedArgs('generation',model));
  const state=runtime.status().states.generation;
  assert.equal(state.status,'ready');assert.equal(state.args[state.args.indexOf('--cache-ram')+1],'0');
  assert.equal(state.runtime_hash,core.hash({version:runtime.version,args:launches[0].args,model_sha256:model.sha256}));
  const previousArgs=Array.from(launches[0].args).slice(0,-2);
  assert.notEqual(state.runtime_hash,core.hash({version:runtime.version,args:previousArgs,model_sha256:model.sha256}),'New runs must distinguish the changed cache setting');
 }
});

test('embedding launch configuration remains unchanged in optimization step one',async()=>{
 const {runtime,launches}=offline(),model=models.find(m=>m.role==='embedding');await runtime.ensure('embedding',model.id);
 assert.deepEqual(Array.from(launches[0].args),expectedArgs('embedding',model));assert.ok(!launches[0].args.includes('--cache-ram'));
});

test('reusing the ready generation model does not start an additional process',async()=>{
 const {runtime,launches}=offline();await runtime.ensure('generation','qwen35-4b-q4');await runtime.ensure('generation','qwen35-4b-q4');assert.equal(launches.length,1);
});
