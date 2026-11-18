'use strict';
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.PlantDialogueMap=api;})(typeof window==='undefined'?null:window,function(){
 const VERSION='dialogue-map-v2';
 function invalid(){throw Error('대화 지도의 형식이나 대화 연결을 확인하지 못했습니다.');}
 function text(v,max=1000){if(typeof v!=='string'||v.length>max)invalid();return v;}
 function array(v,max){if(!Array.isArray(v)||v.length>max)invalid();return v;}
 function ids(v,max=10000){const out=array(v,max).map(s=>text(s,180));if(new Set(out).size!==out.length)invalid();return out;}
 function integer(v){if(!Number.isSafeInteger(v)||v<0)invalid();return v;}
 function empty(threadId){return {version:VERSION,thread_id:threadId,revision:0,last_request:null,processed_ids:[],parts:[],flow:null};}
 function normalize(v,threadId,context){
  if(!v)return empty(threadId);if(v.version!==VERSION||v.thread_id!==threadId)invalid();
  const out=empty(threadId);out.revision=integer(v.revision);out.last_request=v.last_request==null?null:text(v.last_request,160);out.processed_ids=ids(v.processed_ids);
  if(v.turn_labels)out.turn_labels=array(v.turn_labels,10000).map(l=>({turn_id:text(l.turn_id,180),recordable:l.recordable===true,correction:l.correction===true}));
  if(v.corrections)out.corrections=array(v.corrections,64).map(c=>({turn_id:text(c.turn_id,180),text:text(c.text,600),part_ids:ids(c.part_ids,64),invalidated_assistant_ids:ids(c.invalidated_assistant_ids,10000),...(c.affirmed_quote!=null?{affirmed_quote:text(c.affirmed_quote,600),rejected_quote:text(c.rejected_quote,600)}:{})}));
  out.parts=array(v.parts,64).map(p=>{if(!['story','task','directive'].includes(p.kind)||!['open','closed','waiting'].includes(p.status)||!['samples','personal'].includes(p.scope))invalid();return {id:text(p.id,100),title:text(p.title,160),summary:text(p.summary,600),kind:p.kind,status:p.status,scope:p.scope,turn_ids:ids(p.turn_ids),related_ids:ids(p.related_ids||[],64)};});
  ids(out.parts.map(p=>p.id),64);if(v.flow)out.flow=context.normalize(v.flow,threadId);return out;
 }
 function turns(thread,scope){
  const out=[];let index=0;
  for(const m of thread.messages||[]){
   const id=m.requestId||m.submission?.request_id||'legacy-'+index;
   const collection=m.submission?.collection_id;
   if(m.kind==='user')out.push({id:'u-'+id,role:'user',text:m.text,created_at:m.createdAt||'',scope:collection||null});
   else if(m.kind==='assistant'&&m.status==='success'&&m.result)out.push({id:'a-'+id,role:'assistant',text:m.result.answer,created_at:m.createdAt||'',scope:collection||null});
   index++;
  }
  // User messages and their receipt share a request ID and collection.
  const collections=new Map((thread.messages||[]).filter(m=>m.kind==='assistant'&&m.submission).map(m=>['u-'+m.submission.request_id,m.submission.collection_id]));
  const operations=new Map((thread.messages||[]).filter(m=>m.kind==='assistant'&&m.submission&&m.result?.dialogue_trace).map(m=>['u-'+m.submission.request_id,m.result.dialogue_trace.operation]));
  return out.map(t=>({...t,scope:t.scope||collections.get(t.id)||scope,...(operations.has(t.id)?{operation:operations.get(t.id)}:{})})).filter(t=>scope==null||t.scope===scope);
 }
 function snapshot(thread,context){return normalize(thread.mapContext||thread.messages?.findLast(m=>m.status==='success'&&!m.archived&&m.result?.map_context)?.result.map_context,thread.id,context);}
 function apply(thread,submission,value,context){
  if(thread.deletedAt||thread.id!==submission.thread_id||!value||thread.contextRequest!==submission.request_id)return false;
  const next=normalize(value,thread.id,context),current=normalize(thread.mapContext||submission.map_context,thread.id,context);
  if(current.revision!==submission.map_context.revision&&current.last_request!==submission.request_id)return false;
  if(next.revision!==submission.map_context.revision+1||next.last_request!==submission.request_id)return false;
  thread.mapContext=next;return true;
 }
 function rebind(v,threadId,context,mapping=new Map()){const copy=JSON.parse(JSON.stringify(v));copy.thread_id=threadId;if(copy.flow)copy.flow=context.remap(copy.flow,threadId,mapping);return normalize(copy,threadId,context);}
 function trace(v){
  if(!['conversation','archive','none'].includes(v.source))invalid();
  return {version:'v2',source:v.source,relation:text(v.relation,40),operation:text(v.operation,40),original:text(v.original,8000),augmented_request:text(v.augmented_request,4000),selected_part_ids:ids(v.selected_part_ids,64),reference_count:integer(v.reference_count),
   parts:array(v.parts,64).map(p=>({id:text(p.id,100),title:text(p.title,160),summary:text(p.summary,600),kind:text(p.kind,20),status:text(p.status,20),start:integer(p.start),end:integer(p.end)})),
   references:array(v.references,64).map(t=>({id:text(t.id,180),role:['user','assistant'].includes(t.role)?t.role:invalid(),text:text(t.text,8000)})),analysis_calls:integer(v.analysis_calls)};
 }
 return {VERSION,empty,normalize,turns,snapshot,apply,rebind,trace};
});
