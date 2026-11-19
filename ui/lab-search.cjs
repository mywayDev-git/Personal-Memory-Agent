'use strict';
const {hash}=require('../local/core.cjs');
const modes=require('./plant-thought/search-modes.js');
const base='http://127.0.0.1:4319/api/baseline';
async function search(data,scope,query,signal){
 const mode=modes.normalize(data.search_mode);if(mode==='legacy')throw Error('검색 방식 연결 오류');
 try{
  const boot=await fetch(base+'/bootstrap',{signal});if(!boot.ok)throw Error('Memory Lab 연결을 확인해 주세요.');const {token}=await boot.json();
  const response=await fetch(base+'/chat-search',{method:'POST',headers:{'Content-Type':'application/json','X-Memory-Lab-Token':token},body:JSON.stringify({request_id:data.request_id,collection_id:data.collection_id||'samples',query,search_mode:mode,scope_hash:hash(scope.sources)}),signal});
  const result=await response.json();if(!response.ok)throw Error(result.error||'선택한 검색 방식을 실행하지 못했습니다.');
  if(result.trace?.mode!==mode||result.trace.accessible_count!==scope.sources.length||!Array.isArray(result.evidence))throw Error('검색 결과가 제출한 방식·범위와 일치하지 않습니다.');
  for(const e of result.evidence){const source=scope.sources.find(s=>s.id===e.source_id&&s.revision===e.revision);if(!source||!Number.isSafeInteger(e.start)||!Number.isSafeInteger(e.end)||e.start<0||e.end<=e.start||e.end>source.text.length||e.end>source.text.length||source.text.slice(e.start,e.end)!==e.text)throw Error('검색 결과의 원문 출처를 확인하지 못했습니다.');}
  return result;
 }catch(error){throw Object.assign(error,{stage:'retrieval'});}
}
module.exports={search};
