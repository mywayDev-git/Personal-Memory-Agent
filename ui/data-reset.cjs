'use strict';
const crypto=require('node:crypto');
const base='http://127.0.0.1:4319/api/baseline';
function createDataReset({library,chat,invalidate=()=>{},baselineRequest=null}){
 const token=crypto.randomBytes(32).toString('hex');let operation=null;
 const json=(res,status,data)=>{if(res.destroyed)return;res.writeHead(status,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'});res.end(JSON.stringify(data));};
 async function baseline(action,body){
  if(baselineRequest)return baselineRequest(action,body);
  const bootstrap=await fetch(base+'/bootstrap',{signal:AbortSignal.timeout(10000)});if(!bootstrap.ok)throw Error('Memory Lab 연결을 확인해 주세요. 전체 삭제는 아직 완료되지 않았습니다.');
  const {token}=await bootstrap.json(),response=await fetch(base+'/data-reset/'+action,body?{method:'POST',headers:{'Content-Type':'application/json','X-Memory-Lab-Token':token},body:JSON.stringify(body),signal:AbortSignal.timeout(120000)}:{signal:AbortSignal.timeout(10000)});
  const result=await response.json();if(!response.ok)throw Error(result.error||'Memory Lab 데이터 정리에 실패했습니다.');return result;
 }
 async function preview(){
  const state=library.read(),info=library.storageInfo();let lab=null,note='';try{lab=await baseline('preview');}catch(error){note=error.message;}
  return {token,revision:state.revision,...info,counts:{threads:state.threads.length,records:state.records.length,drafts:state.threads.reduce((n,t)=>n+(t.recordDrafts?.length||0),0)},lab,available:!!lab,note};
 }
 async function reset(data){
  if(data.confirmation!=='전체 삭제'||typeof data.reset_id!=='string'||!/^[-\w]{1,80}$/.test(data.reset_id))throw Object.assign(Error('삭제 범위를 확인하고 ‘전체 삭제’를 입력해 주세요.'),{status:400});
  if(operation){if(operation.id===data.reset_id)return operation.promise;throw Object.assign(Error('다른 전체 삭제 작업이 진행 중입니다.'),{status:409});}
  const resumed=library.lastReset()?.id===data.reset_id;
  if(resumed&&library.lastReset().completed)return {deleted:true,...library.lastReset(),...library.storageInfo()};
  if(!resumed){library.assertEpoch(data.storage_epoch);if(data.revision!==library.read().revision)throw Object.assign(Error('데이터가 변경되었습니다. 삭제 창을 다시 열어 확인해 주세요.'),{status:409});}
  else if(library.lastReset().revision!==library.read().revision)throw Object.assign(Error('삭제 이후 새 데이터가 생겼습니다. 삭제 창을 다시 열어 확인해 주세요.'),{status:409});
  const promise=(async()=>{
   library.resetting=true;let leased=false,personalCleared=resumed;
   try{
    await chat.suspend();await baseline('begin',{reset_id:data.reset_id});leased=true;
    const receipt=library.eraseAll(data.revision,data.reset_id);personalCleared=true;
    await baseline('clear',{reset_id:data.reset_id});invalidate();await baseline('release',{reset_id:data.reset_id});leased=false;
    library.completeReset(data.reset_id);return {deleted:true,...receipt,...library.storageInfo()};
   }catch(error){
    if(leased)await baseline('release',{reset_id:data.reset_id}).catch(()=>{});
    throw Object.assign(error,{status:error.status||503,partial:personalCleared,...library.storageInfo()});
   }finally{library.resetting=false;chat.resume();}
  })();operation={id:data.reset_id,promise};try{return await promise;}finally{if(operation?.promise===promise)operation=null;}
 }
 async function handle(req,res,url){
  if(!url.pathname.startsWith('/api/data-reset'))return false;
  try{
   const host=req.headers.host||'';if(!/^(127\.0\.0\.1|localhost):\d+$/.test(host)||(req.headers.origin&&req.headers.origin!=='http://'+host))throw Object.assign(Error('현재 로컬 화면에서만 사용할 수 있습니다.'),{status:403});
   if(req.method==='GET'&&url.pathname==='/api/data-reset/preview'){json(res,200,await preview());return true;}
   if(req.method==='GET'&&url.pathname==='/api/data-reset/status'){
    const requested=url.searchParams.get('id'),last=library.lastReset();
    json(res,200,{status:last?.id===requested&&last.completed?'completed':operation?.id===requested?'running':last?.id===requested?'partial':'not_started',...library.storageInfo()});return true;
   }
   if(req.method!=='POST'||url.pathname!=='/api/data-reset')throw Object.assign(Error('지원하지 않는 삭제 요청입니다.'),{status:405});
   if(req.headers['x-data-reset-token']!==token)throw Object.assign(Error('삭제 확인 정보가 만료됐습니다. 창을 다시 열어 주세요.'),{status:403});
   if(!String(req.headers['content-type']).startsWith('application/json'))throw Object.assign(Error('JSON 요청이 필요합니다.'),{status:415});
   let size=0,parts=[];for await(const part of req){size+=part.length;if(size>10000)throw Object.assign(Error('삭제 요청이 너무 큽니다.'),{status:413});parts.push(part);}
   const data=JSON.parse(Buffer.concat(parts).toString('utf8'));json(res,200,await reset(data));
  }catch(error){json(res,error.status||500,{error:error.message,...(error.partial?{partial:true,...library.storageInfo()}:{} )});}
  return true;
 }
 return {handle};
}
module.exports={createDataReset};
