const path=require('node:path'),fs=require('node:fs'),{spawn}=require('node:child_process');
function processControl(root,exe,models,mode){
 return new Promise((resolve,reject)=>{
  const shell=path.join(process.env.SystemRoot||'C:\\Windows','System32','WindowsPowerShell','v1.0','powershell.exe');
  const script=fs.readFileSync(path.join(__dirname,'model-processes.ps1'),'utf8');
  const child=spawn(shell,['-NoProfile','-NonInteractive','-Command',script],{windowsHide:true,env:{...process.env,MEMORY_LAB_PROCESS_REQUEST:JSON.stringify({root,exe,models:models.map(m=>({file:m.file,role:m.role})),mode})},stdio:['ignore','pipe','pipe']});let out='',err='',settled=false;
  const timer=setTimeout(()=>{child.kill();finish(Error('프로세스 확인 시간 초과. 종료 완료로 표시하지 않습니다.'));},45000);
  function finish(error,value){if(settled)return;settled=true;clearTimeout(timer);error?reject(error):resolve(value);}
  child.on('error',e=>finish(e));child.stdout.on('data',b=>out+=b);child.stderr.on('data',b=>err+=b);
  child.on('close',code=>{if(code!==0)return finish(Error('프로세스 확인 실패: '+err.trim().slice(0,400)));try{const d=JSON.parse(out.replace(/^\uFEFF/,''));if(!d.verified||!Array.isArray(d.remaining)||!Array.isArray(d.terminated_pids))throw Error('프로세스 응답 형식 오류');finish(null,d);}catch(e){finish(e);}});
 });
}
module.exports={processControl};
