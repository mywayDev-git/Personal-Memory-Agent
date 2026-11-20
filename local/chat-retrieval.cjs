'use strict';
const {hash}=require('./core.cjs');
const modes=require('../ui/plant-thought/search-modes.js');
const {prepareSummaryBatch}=require('./summary-batch.cjs');
const summaryRoutes=new Set(['M0','M1','G1','G2']);
const issue=message=>Object.assign(Error(message),{stage:'retrieval'});

// Search representations select evidence; chat citations always point to actual originals.
function originalEvidence(retrieval,sources){
 const byId=new Map(sources.map(source=>[source.id,source])),seen=new Set(),evidence=[];
 for(const hit of retrieval.evidence||[]){
  const source=byId.get(hit.source_id);
  if(!source||source.revision!==hit.revision)throw issue('검색 결과의 원문 버전이 현재 자료함과 다릅니다.');
  let {start,end}=hit;
  if(hit.origin==='summary'){
   const record=retrieval.summary_records?.find(record=>record.summary_id===hit.summary_id&&record.source_id===source.id);
   const ranges=record?.excerpt_selection?.ranges.filter(range=>range.excerpt_start<hit.end&&range.excerpt_end>hit.start);
   if(ranges?.length){
    for(const range of ranges){
     const offset=Math.max(hit.start,range.excerpt_start),limit=Math.min(hit.end,range.excerpt_end);
     const rawStart=range.start+offset-range.excerpt_start,rawEnd=range.start+limit-range.excerpt_start;
     if(source.text.slice(rawStart,rawEnd)!==record.summary.slice(offset,limit))throw issue('발췌문의 원문 연결을 확인하지 못했습니다.');
     const key=source.id+'@'+rawStart+':'+rawEnd;if(seen.has(key))continue;seen.add(key);
     evidence.push({source_id:source.id,revision:source.revision,start:rawStart,end:rawEnd,text:source.text.slice(rawStart,rawEnd),metadata:source.metadata,evidence_id:'E'+(evidence.length+1)});
    }
    continue;
   }
   // Generated summaries have no trustworthy raw-text offsets. Verify the selected original instead.
   start=0;end=source.text.length;
  }else if(!Number.isSafeInteger(start)||!Number.isSafeInteger(end)||start<0||end<=start||end>source.text.length||source.text.slice(start,end)!==hit.text){
   throw issue('검색 근거가 실제 원문 구간과 일치하지 않습니다.');
  }
  const key=source.id+'@'+start+':'+end;if(seen.has(key))continue;seen.add(key);
  evidence.push({source_id:source.id,revision:source.revision,start,end,text:source.text.slice(start,end),metadata:source.metadata,evidence_id:'E'+(evidence.length+1)});
 }
 return evidence;
}

function createChatRetrieval(parent,runtime){
 const jobs=new Map(),indexes=require('./chat-graph-index.cjs').createGraphIndex(parent,runtime);
 parent.store.db.exec('CREATE TABLE IF NOT EXISTS chat_search_preparations(cache_key TEXT PRIMARY KEY,artifact_id TEXT NOT NULL)');
 async function search(data,externalSignal){
  const mode=modes.get(modes.normalize(data.search_mode));
  if(!mode.route)throw issue('Memory Lab 검색 방식을 선택해 주세요.');
  if(typeof data.request_id!=='string'||!/^[-\w]{1,80}$/.test(data.request_id)||typeof data.query!=='string'||!data.query.trim()||data.query.length>12000||!['samples','personal'].includes(data.collection_id))throw issue('검색 제출 정보가 올바르지 않습니다.');
  if(parent.busy)throw issue('Memory Lab에서 앞선 작업을 처리 중입니다. 완료 후 재시도해 주세요.');
  externalSignal?.throwIfAborted();
  const controller=new AbortController(),signal=externalSignal?AbortSignal.any([externalSignal,controller.signal]):controller.signal;
  const job={request_id:data.request_id,mode:mode.id,label:mode.label,status:'running',progress:'검색 자료함을 확인하고 있어요.',started_at:new Date().toISOString()};
  jobs.delete(data.request_id);jobs.set(data.request_id,job);if(jobs.size>128)jobs.delete(jobs.keys().next().value);
  // Reserve the existing engine, including model preparation, so Lab and chat cannot interleave.
  const run={id:'chat-search-'+data.request_id,transient:true,created_at:job.started_at,results:[],question_ids:['chat-query'],events:[]};
  parent.busy=run.id;parent.abort=controller;
  let stage='scope';
  try{
   const scope=await require('../ui/chat-api.cjs').loadScope(parent.root,{collection_id:data.collection_id,analysis_version:'v2'});
   if(hash(scope.sources)!==data.scope_hash)throw issue('검색 준비 중 기록 범위가 바뀌었습니다. 새 질문으로 다시 조회해 주세요.');
   const sources=scope.sources.map(source=>({...source,metadata:{...source.metadata,owner_id:'chat-local-'+data.collection_id},gold:{facts:[]}}));
   const config=parent.config({route:mode.route,model:'qwen35-4b-q4',top_k:5,...(mode.summary_mode?{summary_mode:mode.summary_mode}:{}),...(mode.event_graph_mode?{event_graph_mode:mode.event_graph_mode}:{})});run.config=config;
   const context={id:'chat-'+data.collection_id,actor_id:'chat-local-'+data.collection_id,now:scope.now,conversation:[]};
   const question={id:'chat-query',context_id:context.id,text:data.query,gold:{evidence_groups:[]}};
   const ds={fingerprint:hash(scope.sources),d:{sources:{records:sources},questions:{questions:[question]},contexts:{contexts:[context]}},lib:{materialize:()=>({accessible:sources})}};
   const engine=Object.create(parent);
   // Each request owns its helpers/progress; the Store and model runtime are shared with Lab.
   Object.assign(engine,{_summary:undefined,_structured:undefined,_rawChunks:undefined,_attention:undefined,summaryProgress:null});
   engine.update=(r,message,detail={})=>{signal.throwIfAborted();job.progress=message;job.stage=detail.stage||stage;job.done=detail.unit_done??null;job.total=detail.unit_total??null;job.updated_at=new Date().toISOString();};
   engine.retrievalMetrics=()=>({scope:'Interactive chat search; no gold answers or evaluation annotations used.'});
   const started=Date.now();let extraction=null,reused=false;
   const graphMode=indexes.isGraph(mode.id);
   if(graphMode){
    const index=indexes.cached(scope,data.collection_id,mode.id,config);
    if(!index){const state=await indexes.status(data.collection_id,mode.id);throw issue(['queued','indexing'].includes(state.status)?'기록 변경 후 그래프 색인을 준비 중입니다. 준비 완료 뒤 다시 조회해 주세요.':'준비된 그래프 색인이 없습니다. 상단의 색인 준비 버튼으로 먼저 준비해 주세요. 검색 중에는 색인을 만들지 않습니다.');}
    extraction=index.extraction;reused=true;
   }
   if(sources.length){
    stage='connection';job.progress='검색에 필요한 로컬 모델을 준비하고 있어요.';
    runtime.allowStart?.();await runtime.ensure('generation',config.model,signal);
    if(!['R0-Full','K1','A1'].includes(mode.route))await runtime.ensure('embedding',config.embedding_model,signal);
    stage='preparation';
    if(!graphMode&&!['R0','R0-Full'].includes(mode.route)){
     const key=hash({scope:ds.fingerprint,config}),saved=parent.store.db.prepare('SELECT artifact_id FROM chat_search_preparations WHERE cache_key=?').get(key);
     if(saved){extraction=parent.store.readArtifact(saved.artifact_id);parent.checkSourceScope(extraction,context,sources);reused=true;}
     else{
      extraction=summaryRoutes.has(mode.route)?(await prepareSummaryBatch(engine,run,ds,signal)).get(context.id):await engine.extract(run,ds,context,sources,signal);
      signal.throwIfAborted();parent.store.db.prepare('INSERT OR REPLACE INTO chat_search_preparations VALUES(?,?)').run(key,extraction.artifact_id);
     }
    }
   }
   stage='retrieval';job.progress='선택한 방식으로 근거를 찾고 있어요.';
   const retrieval=sources.length?await engine.retrieve(run,ds,question,context,sources,extraction,signal):{evidence:[],selected_sources:[]};
   signal.throwIfAborted();
   const evidence=originalEvidence(retrieval,sources);
   const trace={mode:mode.id,label:mode.label,route:mode.route,event_graph_mode:config.event_graph_mode||null,summary_mode:config.summary_mode||null,query:data.query,accessible_count:sources.length,native_evidence_count:retrieval.evidence.length,evidence_count:evidence.length,selected_source_ids:[...new Set(evidence.map(e=>e.source_id))],preparation_reused:reused,index_policy:graphMode?'on_record_change':'search_time',extraction_artifact_id:extraction?.artifact_id||null,retrieval_artifact_id:retrieval.artifact_id||null,elapsed_ms:Date.now()-started,answer_grounding:'originals',token_usage:require('./token-usage.cjs').report(),summary_expanded_to_originals:retrieval.evidence.some(e=>e.origin==='summary'),...(retrieval.event_graph_search?{graph_search:retrieval.event_graph_search}:{}),...(retrieval.multi_anchor_search?{multi_anchor_search:retrieval.multi_anchor_search}:{}),...(retrieval.question_attention?{question_attention:retrieval.question_attention}:{})};
   job.status='completed';job.progress='검색 완료';return {evidence,trace};
  }catch(error){job.status=signal.aborted?'cancelled':'failed';job.progress=error.message;job.stage=stage;throw Object.assign(error,{stage:error.stage||'retrieval'});}
  finally{job.finished_at=new Date().toISOString();if(parent.busy===run.id){parent.busy=null;parent.abort=null;}}
 }
 return {search,status:id=>jobs.get(id)||null,indexes,forget(){jobs.clear();}};
}
module.exports={createChatRetrieval,originalEvidence};
