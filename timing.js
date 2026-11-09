(function(root){
 'use strict';
 const ACTIVE=new Set(['QUEUED','RUNNING']);
 function stamp(value){if(typeof value!=='string'||!value.trim())return null;const n=Date.parse(value);return Number.isFinite(n)?n:null;}
 function elapsed(record,now=Date.now()){
  const start=stamp(record?.started_at||record?.created_at);if(start===null)return null;
  let end=stamp(record?.finished_at);
  if(end===null){if(!ACTIVE.has(record?.status))return null;end=now;}
  return Number.isFinite(end)&&end>=start?end-start:null;
 }
 function format(ms){
  if(!Number.isFinite(ms)||ms<0)return '기록 없음';
  if(ms<1000)return (ms/1000).toFixed(2)+'초';
  if(ms<60000)return String(Math.floor(ms/100)/10)+'초';
  const seconds=Math.floor(ms/1000),hours=Math.floor(seconds/3600),minutes=Math.floor(seconds%3600/60),rest=seconds%60;
  return (hours?hours+'시간 ':'')+(minutes||hours?minutes+'분 ':'')+rest+'초';
 }
 function stage(result,key,now=Date.now()){
  const t=result?.stage_timings?.[key],output=result?.stages?.[key];
  if(t){
   if(t.reused){const original=t.original_elapsed_ms??output?.elapsed_ms;return {ms:Number.isFinite(original)&&original>=0?original:null,reused:true,status:'REUSED'};}
   if(t.status==='RUNNING'&&result?.status==='RUNNING'){const ms=elapsed({...t,status:'RUNNING'},now);return {ms,reused:false,status:'RUNNING',started_at:t.started_at};}
   if(Number.isFinite(t.elapsed_ms)&&t.elapsed_ms>=0)return {ms:t.elapsed_ms,reused:false,status:t.status==='COMPLETED'?'RECORDED':t.status};
  }
  const ms=output?.elapsed_ms;
  if(Number.isFinite(ms)&&ms>=0)return {ms,reused:!!output.reused,status:output.reused?'REUSED':'RECORDED'};
  return {ms:null,reused:!!output?.reused,status:output?.reused?'REUSED':result?.stage_progress?.[key]||'NOT_RECORDED'};
 }
 const api={elapsed,format,stage,isActive:record=>ACTIVE.has(record?.status)};
 if(typeof module==='object'&&module.exports)module.exports=api;
 else root.MemoryTiming=api;
})(typeof globalThis==='object'?globalThis:this);
