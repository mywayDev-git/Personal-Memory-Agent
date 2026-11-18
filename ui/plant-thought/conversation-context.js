'use strict';
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.PlantConversationContext=api;})(typeof window==='undefined'?null:window,function(){
 const VERSION='conversation-context-v1';
 function invalid(){throw Error('대화 맥락의 형식이 올바르지 않습니다.');}
 const string=(v,max=1000)=>{if(typeof v!=='string'||v.length>max)invalid();return v;};
 const number=v=>{if(!Number.isSafeInteger(v)||v<0)invalid();return v;};
 const array=(v,max)=>{if(!Array.isArray(v)||v.length>max)invalid();return v;};
 function empty(threadId){return {version:VERSION,thread_id:threadId,revision:0,active:null,story:null,topics:[],pending:[],directives:[],exclusions:[],task:null,last_request:null,awaiting:null};}
 function reference(r){const start=number(r.start),end=number(r.end);if(end<start)invalid();return {source_id:string(r.source_id,160),revision:number(r.revision),start,end,quote:string(r.quote,1000)};}
 function normalize(value,threadId){
  if(!value)return empty(threadId);if(value.version!==VERSION||value.thread_id!==threadId)invalid();
  const out=empty(threadId);out.revision=number(value.revision);out.active=value.active==null?null:string(value.active,160);out.last_request=value.last_request==null?null:string(value.last_request,160);
  out.story=value.story==null?null:string(value.story,160);
  out.exclusions=array(value.exclusions||[],8).map(e=>({topic_id:string(e.topic_id,160),scope:string(e.scope,20)}));
  out.directives=array(value.directives||[],12).map(d=>({id:string(d.id,160),type:['record','style'].includes(d.type)?d.type:invalid(),value:['enabled','disabled','brief','normal'].includes(d.value)?d.value:invalid(),scope:string(d.scope,20),request_id:string(d.request_id,160),text:string(d.text,600),turn:number(d.turn)}));
  if(value.task)out.task={request_id:string(value.task.request_id,160),intent:string(value.task.intent,30),status:['completed','waiting'].includes(value.task.status)?value.task.status:invalid(),topic_id:value.task.topic_id==null?null:string(value.task.topic_id,160)};
  out.topics=array(value.topics,6).map(t=>({id:string(t.id,160),label:string(t.label,200),scope:string(t.scope,20),kind:string(t.kind,30),questions:array(t.questions,3).map(q=>string(q,600)),utterances:array(t.utterances||[],8).map(q=>string(q,600)),category:t.category==='story'?'story':'request',references:array(t.references,4).map(reference),focus:string(t.focus||'',100),correction:string(t.correction||'',300),turn:number(t.turn),needs_target:t.needs_target===true}));
  if(new Set(out.topics.map(t=>t.id)).size!==out.topics.length)invalid();
  out.pending=array(value.pending,8).map(p=>({id:string(p.id,160),request_id:string(p.request_id,160),topic_id:string(p.topic_id,160),intent:string(p.intent,30),proposal:string(p.proposal,2000),targets:array(p.targets,12).map(id=>string(id,160)),status:['awaiting_confirmation','cancelled'].includes(p.status)?p.status:invalid(),scope:string(p.scope,20),...(p.save_target?{save_target:['personal_facts','transcript','summary','none'].includes(p.save_target)?p.save_target:invalid(),source_turn_ids:array(p.source_turn_ids||[],10000).map(v=>string(v,180))}:{}),...(p.origin==='ongoing_recording'?{origin:p.origin}:{}),...(p.recording?{recording:recording(p.recording)}:{})}));
  if(new Set(out.pending.map(p=>p.id)).size!==out.pending.length)invalid();
  if(value.awaiting)out.awaiting={question:string(value.awaiting.question,8000),topic_id:value.awaiting.topic_id==null?null:string(value.awaiting.topic_id,160),intent:string(value.awaiting.intent,30),scope:string(value.awaiting.scope,20),type:value.awaiting.type==='target'||value.awaiting.intent==='memory_query'?'target':'content'};
  return out;
 }
 function recording(value){
  if(!['draft','skipped'].includes(value.status)||!/^\d{4}-\d{2}-\d{2}$/.test(value.date))invalid();
  return {status:value.status,date:string(value.date,10),statements:array(value.statements||[],8).map(s=>string(s,600)),reason:string(value.reason||'',200),...(value.sources?{sources:array(value.sources,8).map(s=>({turn_id:string(s.turn_id,180),text:string(s.text,600)}))}:{})};
 }
 function snapshot(thread,scope){
  if(thread.context)return normalize(thread.context,thread.id);
  const latest=thread.messages?.findLast(m=>m.status==='success'&&!m.archived&&!['v2','v3'].includes(m.submission?.analysis_version)&&m.result?.context)?.result.context;
  if(latest)return normalize(latest,thread.id);
  const out=empty(thread.id);
  // Old conversations can contribute user questions and citation references, never old answer prose.
  for(const m of (thread.messages||[]).filter(m=>m.status==='success'&&!m.archived&&!['v2','v3'].includes(m.submission?.analysis_version)&&m.result?.citations?.length).slice(-5)){
   const r=m.result,id='legacy-'+m.submission.request_id,mode=m.submission.collection_id||'samples';
   const refs=r.citations.filter(c=>c.quote.length<=1000).slice(0,4).map(reference);
   out.topics.push({id,label:r.citations[0].title.slice(0,200),scope:mode,kind:'memory_query',questions:[m.submission.text.slice(0,600)],references:refs,focus:'',correction:'',turn:out.topics.length});out.active=id;
  }
  return out;
 }
 function apply(thread,submission,value){
  if(thread.deletedAt||thread.id!==submission.thread_id||!submission.context||!value||(thread.contextRequest&&thread.contextRequest!==submission.request_id))return false;
  const next=normalize(value,thread.id),current=thread.context?normalize(thread.context,thread.id):submission.context;
  // A retry may replace its own partial outcome; a late response cannot replace a later turn's context.
  if(current.revision!==submission.context.revision&&current.last_request!==submission.request_id)return false;
  if(next.last_request!==submission.request_id||next.revision!==submission.context.revision+1)return false;
  thread.context=next;return true;
 }
 function remap(value,threadId,mapping=new Map()){
  const copy=JSON.parse(JSON.stringify(value));copy.thread_id=threadId;
  for(const t of copy.topics||[])for(const r of t.references||[])r.source_id=mapping.get(r.source_id)||r.source_id;
  for(const p of copy.pending||[])p.targets=p.targets.map(id=>mapping.get(id)||id);
  return normalize(copy,threadId);
 }
 function trace(v){if(!['new_topic','related','continue','return','correction','cancel','mixed'].includes(v.relation))invalid();return {relation:v.relation,topic:v.topic==null?null:string(v.topic,200),choices:array(v.choices||[],8).map(c=>({id:string(c.id,160),label:string(c.label,200),...(c.pending?{pending:true}:{})}))};}
 function rebind(thread,newId){
  thread.id=newId;if(thread.context)thread.context=remap(thread.context,newId);
  const maps=typeof module==='object'&&module.exports?require('./dialogue-map.js'):window.PlantDialogueMap;
  if(thread.mapContext)thread.mapContext=maps.rebind(thread.mapContext,newId,{normalize,remap});
  for(const m of thread.messages||[])if(m.kind==='assistant'){
   m.submission.thread_id=newId;if(m.submission.context)m.submission.context=remap(m.submission.context,newId);
   if(m.submission.map_context)m.submission.map_context=maps.rebind(m.submission.map_context,newId,{normalize,remap});
   if(m.result){m.result.thread_id=newId;if(m.result.context)m.result.context=remap(m.result.context,newId);
    if(m.result.map_context)m.result.map_context=maps.rebind(m.result.map_context,newId,{normalize,remap});
    for(const p of m.result.parts||[])if(p.result){p.result.thread_id=newId;if(p.result.context)p.result.context=remap(p.result.context,newId);}
   }
  }return thread;
 }
 return {VERSION,empty,normalize,snapshot,apply,remap,trace,rebind,recording};
});
