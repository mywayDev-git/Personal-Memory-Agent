'use strict';
const {createPlantServer}=require('./preview.cjs');
const {start}=require('./backend.cjs');
async function ready(url,header){
  try{const response=await fetch(url,{signal:AbortSignal.timeout(2500)});return response.ok&&(!header||response.headers.get(header[0])===header[1]);}catch{return false;}
}
async function main(){
  const backendPort=Number(process.env.PLANT_BACKEND_PORT||4321),port=Number(process.env.PLANT_PORT||4180);
  let backend;
  if(!await ready('http://127.0.0.1:'+backendPort+'/api/baseline/bootstrap',['X-Plant-Backend','conversation-ux-v1']))backend=await start();
  if(await ready('http://127.0.0.1:'+port+'/memory.js')){console.log('이미 실행 중인 화면: http://127.0.0.1:'+port);if(backend)await backend.close();return;}
  const server=createPlantServer({backendPort});
  let closing=false;
  async function close(){if(closing)return;closing=true;server.close();if(backend)await backend.close();}
  process.on('SIGINT',()=>void close());process.on('SIGTERM',()=>void close());
  server.on('error',error=>{console.error(error.message);void close();process.exitCode=1;});
  server.listen(port,'127.0.0.1',()=>{
    console.log('화면: http://127.0.0.1:'+port);
    console.log('모델 준비: http://127.0.0.1:'+backendPort+'/baseline');
    console.log('종료: Ctrl+C');
  });
}
main().catch(error=>{console.error(error.message);process.exitCode=1;});
