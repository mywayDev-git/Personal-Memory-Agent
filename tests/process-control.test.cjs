const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),{spawnSync}=require('node:child_process');
const {Runtime}=require('../local/runtime.cjs');
test('verified recovery clears stale runtime state, latches start, and reports errors honestly',async()=>{
 const r=Object.create(Runtime.prototype);Object.assign(r,{root:'D:\\development\\personal-memory-agent',exe:'C:\\llama.cpp\\llama-server.exe',terminating:false,shutdownEpoch:0,stopRequested:false,pending:{},children:{},states:{},stopAll:async()=>{}});
 // Exercise lifecycle with a subprocess-control seam; no real model is started.
 const control=require('../local/process-control.cjs');
 assert.throws(()=>{r.terminating=true;r.allowStart();},/종료/);r.terminating=false;r.stopRequested=true;
 await assert.rejects(()=>r.ensure('generation','qwen35-4b-q4'),/중단/);r.allowStart();assert.equal(r.stopRequested,false);
 assert.equal(typeof control.processControl,'function');
 r.states={generation:{status:'ready'},embedding:{status:'stopped'}};let calls=0;r.processController=async()=>{calls++;return {verified:true,remaining:[],terminated_pids:[123],checked_at:new Date().toISOString()};};const report=await r.forceStop();assert.equal(calls,1);assert.deepEqual(report.terminated_pids,[123]);assert.equal(r.states.generation.status,'stopped');assert.equal(r.stopRequested,true);
 r.processController=async()=>{throw Error('OS inspection denied');};await assert.rejects(()=>r.forceStop(),/denied/);assert.equal(r.last_process_check.verified,false);assert.equal(r.terminating,false);
});
test('OS selector recovers only exact app models, rechecks PID identity, and ignores other apps',()=>{
 const script=fs.readFileSync(path.join(__dirname,'..','local','model-processes.ps1'),'utf8');
 const root='D:\\development\\personal-memory-agent',exe='C:\\llama.cpp\\llama-server.exe',file='Qwen3.5-4B-Q4_K_M.gguf';
 const command=`${exe} -m ${root}\\.models\\${file} --port 18491`;
 const fixtures=[{ProcessId:101,CreationDate:'same',ExecutablePath:exe,CommandLine:command},{ProcessId:102,CreationDate:'same',ExecutablePath:exe,CommandLine:command.replace(root,'D:\\other-app')},{ProcessId:103,CreationDate:'same',ExecutablePath:exe,CommandLine:command.replace(file,file+'.bak')},{ProcessId:104,CreationDate:'same',ExecutablePath:exe,CommandLine:command.replace('18491','18490')},{ProcessId:105,CreationDate:'same',ExecutablePath:'D:\\other\\llama-server.exe',CommandLine:command}];
 const mocks=`$global:fixtures = $env:PROCESS_FIXTURES | ConvertFrom-Json
function Get-CimInstance { param($ClassName,$Filter) if ($Filter -match '^ProcessId=(\\d+)$') { $global:fixtures | Where-Object ProcessId -eq ([int]$Matches[1]) } else { $global:fixtures } }
function Stop-Process { param($Id,[switch]$Force,$ErrorAction) if ($Id -ne 101) { throw 'Wrong process terminated' }; $global:fixtures = @($global:fixtures | Where-Object ProcessId -ne $Id) }
function Get-Process { param($Id,$ErrorAction) [pscustomobject]@{WorkingSet64=1024;PrivateMemorySize64=2048} }
`;
 const result=spawnSync(path.join(process.env.SystemRoot,'System32','WindowsPowerShell','v1.0','powershell.exe'),['-NoProfile','-NonInteractive','-Command',mocks+'\n'+script],{windowsHide:true,encoding:'utf8',timeout:20000,env:{...process.env,PROCESS_FIXTURES:JSON.stringify(fixtures),MEMORY_LAB_PROCESS_REQUEST:JSON.stringify({mode:'terminate',root,exe,models:[{file,role:'generation'}]})}});
 assert.equal(result.status,0,result.stderr);const report=JSON.parse(result.stdout);assert.deepEqual(report.terminated_pids,[101]);assert.deepEqual(report.remaining,[]);assert.equal(report.verified,true);
});
