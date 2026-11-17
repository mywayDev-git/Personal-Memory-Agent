const {setImmediate:yieldTurn}=require('node:timers/promises');
const {hash,rrf}=require('./core.cjs');
const {VERSION,indexSource,validateIndex}=require('./chunk-keywords.cjs');
const {planQuestion,filterChunk,VERSION:QUERY_VERSION}=require('./keyword-query.cjs');
const {queryText}=require('./core.cjs');
const usage=require('./token-usage.cjs');

const ROUTE='K1';
const MODES=['original','expanded','filtered'];

class RawChunkSearch{
 constructor(engine){
  this.engine=engine;this.store=engine.store;this.loaded=new Map();
  this.store.db.exec('CREATE TABLE IF NOT EXISTS original_chunk_keyword_indexes(cache_key TEXT PRIMARY KEY,artifact_id TEXT NOT NULL)');
 }

 sourceIndex(source,signal){
  signal?.throwIfAborted();
  const key=hash({version:VERSION,source:source.id,revision:source.revision,owner:source.metadata.owner_id,text:hash(source.text)});
  if(this.loaded.has(key))return {...this.loaded.get(key),reused:true};
  const row=this.store.db.prepare('SELECT artifact_id FROM original_chunk_keyword_indexes WHERE cache_key=?').get(key);
  let index,index_id;
  if(row){
   index=validateIndex(this.store.readArtifact(row.artifact_id),source);index_id=row.artifact_id;
  }else{
   index=indexSource(source);
   index_id=this.store.artifact('original-chunk-keyword-index',index);
   this.store.db.prepare('INSERT OR IGNORE INTO original_chunk_keyword_indexes VALUES(?,?)').run(key,index_id);
  }
  const result={...index,index_id};
  this.loaded.set(key,result);
  return {...result,reused:!!row};
 }

 extraction(run,ds,context,sources,signal){
  const start=performance.now(),records=sources.map(source=>{
   const index=this.sourceIndex(source,signal);
   return {source_id:source.id,revision:source.revision,owner_id:source.metadata.owner_id,
    index_id:index.index_id,reused:index.reused,valid:true,errors:[],chunk_count:index.units.length,text:source.text,units:[]};
  });
  const data={kind:VERSION,context_id:context.id,dataset_fingerprint:ds.fingerprint,config:run.config,
   source_refs:sources.map(source=>({source_id:source.id,revision:source.revision})),records,
   extraction_state:'COMPLETED',elapsed_ms:performance.now()-start,model_calls:0};
  return {...data,artifact_id:this.store.artifact('extraction',data)};
 }

 async prepareBatch(run,ds,signal){
  const contexts=new Map(),unique=new Map(),questions=new Map(ds.d.questions.questions.map(q=>[q.id,q]));
  for(const id of run.question_ids){
   const question=questions.get(id),context=ds.d.contexts.contexts.find(c=>c.id===question.context_id);
   if(contexts.has(context.id))continue;
   const sources=ds.lib.materialize(context,ds.d.sources.records).accessible;
   contexts.set(context.id,{context,sources});
   for(const source of sources)unique.set(source.id+':'+source.revision,source);
  }
  const batch=run.chunk_keyword_batch={version:VERSION,status:'RUNNING',total_sources:unique.size,
   completed_sources:0,reused_sources:0,total_chunks:0,model_calls:0,started_at:new Date().toISOString()};
  for(const source of unique.values()){
   signal?.throwIfAborted();
   const index=this.sourceIndex(source,signal);
   batch.completed_sources++;batch.total_chunks+=index.units.length;
   if(index.reused)batch.reused_sources++;
   this.engine.update(run,'원문 구간·키워드 색인 '+batch.completed_sources+'/'+batch.total_sources,
    {stage:'chunk_indexing',unit_done:batch.completed_sources,unit_total:batch.total_sources,unit_label:'원문'});
   await yieldTurn();
  }
  const prepared=new Map();
  for(const {context,sources}of contexts.values()){
   signal?.throwIfAborted();
   prepared.set(context.id,this.extraction(run,ds,context,sources,signal));
   await yieldTurn();
  }
  batch.status='COMPLETED';batch.finished_at=new Date().toISOString();
  return prepared;
 }

 indexes(extraction,sources){
  if(extraction?.kind!==VERSION||extraction.extraction_state!=='COMPLETED'||extraction.records.length!==sources.length)
   throw Error('현재 기억 범위의 원문 구간·키워드 색인이 필요합니다.');
  const seen=new Set();
  return extraction.records.map(record=>{
   const source=sources.find(s=>s.id===record.source_id&&s.revision===record.revision);
   if(!source||seen.has(record.source_id))throw Error('다른 사용자·삭제·구버전 원문의 색인은 사용할 수 없습니다.');
   seen.add(record.source_id);
   const index=this.sourceIndex(source);
   if(record.index_id!==index.index_id||record.owner_id!==source.metadata.owner_id)
    throw Error('원문 구간 색인의 출처·소유자·버전이 현재 기억 범위와 다릅니다.');
   return index;
  });
 }

 assertRetrieval(retrieval,sources){
  if(retrieval.kind!==VERSION||retrieval.config?.route!==ROUTE||!Array.isArray(retrieval.evidence))
   throw Error('원문 구간 검색 산출물이 필요합니다.');
  const units=new Map(sources.flatMap(source=>this.sourceIndex(source).units.map(unit=>[unit.id,unit])));
  for(const evidence of retrieval.evidence){
   const canonical=units.get(evidence.unit_id);
   if(!canonical||evidence.source_id!==canonical.source_id||evidence.revision!==canonical.revision||
    evidence.start!==canonical.start||evidence.end!==canonical.end||evidence.text!==canonical.text||evidence.origin!=='raw')
    throw Error('선택한 원문 구간의 출처·버전·근거 위치가 현재 기억 범위와 다릅니다.');
  }
 }

 async retrieve(run,ds,q,context,sources,extraction,signal,persist=true){
  const start=performance.now(),c=run.config;
  const indexes=this.indexes(extraction,sources),units=indexes.flatMap(index=>index.units);
  const sourcesById=new Map(sources.map(source=>[source.id,source]));
  const original=queryText(q,context,c.query_prompt);
  const plan=planQuestion(original,units,c.chunk_search_mode);
  const items=units.map(unit=>({id:unit.id,text:unit.keywords.map(keyword=>keyword.text).join('\n')}));
  this.engine.update(run,q.id+' · 원문 구간 키워드 검색',{stage:'retrieval',unit_total:units.length,unit_label:'구간'});
  const branches=plan.queries.map(query=>{
   signal?.throwIfAborted();
   const used=[query.text,...query.keywords].join(' ');
   return {...query,query_used:used,hits:this.engine.lexical(items,used)};
  });
  const byId=new Map(units.map(unit=>[unit.id,unit]));
  const fused=rrf(branches.map(branch=>branch.hits)).map((hit,i)=>({...byId.get(hit.id),...hit,rank:i+1}));
  if(c.all_candidates){
   const ranked=new Set(fused.map(unit=>unit.id));
   const rest=units.filter(unit=>!ranked.has(unit.id));
   for(const unit of rest)fused.push({...unit,fusion_score:0,rank:fused.length+1});
  }
  const excluded=[],uncertain=[],retained=[];
  for(const item of fused){
   const verdict=c.chunk_search_mode==='filtered'?filterChunk(item,sourcesById.get(item.source_id),plan):{keep:true,reason:'FILTER_DISABLED'};
   if(!verdict.keep){excluded.push({chunk_id:item.id,...verdict});continue;}
   if(verdict.reason==='UNKNOWN_SCOPE_RETAINED')uncertain.push(item.id);
   retained.push(item);
  }
  const selected=c.all_candidates?retained:retained.slice(0,c.top_k),evidence=[];
  let chars=0;
  for(const unit of selected){
   if(!c.all_candidates&&chars+unit.text.length>c.evidence_char_budget)continue;
   chars+=unit.text.length;
   evidence.push({evidence_id:'E'+(evidence.length+1),source_id:unit.source_id,revision:unit.revision,
    start:unit.start,end:unit.end,text:unit.text,origin:'raw',unit_id:unit.id,metadata:sourcesById.get(unit.source_id).metadata});
  }
  const rankedSources=[],seen=new Set();
  for(const unit of retained)if(!seen.has(unit.source_id)){
   seen.add(unit.source_id);rankedSources.push({source_id:unit.source_id,revision:unit.revision,
    rank:rankedSources.length+1,first_unit_rank:unit.rank});
  }
  const selectedSourceIds=new Set(evidence.map(item=>item.source_id));
  const data={kind:VERSION,context_id:context.id,question_id:q.id,dataset_fingerprint:ds.fingerprint,config:c,
   source_refs:sources.map(source=>({source_id:source.id,revision:source.revision})),
   source_snapshots:sources.map(source=>({id:source.id,revision:source.revision,text:source.text})),
   extraction_artifact_id:extraction.artifact_id,index_units:units.map(({keywords,identifiers,chunk_id,...unit})=>unit),
   keyword_index_refs:indexes.map(index=>({source_id:index.source_id,revision:index.revision,index_id:index.index_id})),
   lexical_candidates:branches[0].hits,vector_candidates:[],
   fused_candidates:retained.map(({id,rank,fusion_score})=>({id,rank,fusion_score})),
   ranked_sources:rankedSources,selected_sources:rankedSources.filter(source=>selectedSourceIds.has(source.source_id)),
   evidence,cache_hits:0,query_original:q.text,query_used:branches.map(branch=>branch.query_used).join('\n'),
   elapsed_ms:performance.now()-start,metrics:this.engine.retrievalMetrics(ds.d,q,rankedSources,evidence),
   chunk_keyword_search:{version:VERSION,query_version:QUERY_VERSION,plan,
    branches:branches.map(({hits,...branch})=>({...branch,candidate_count:hits.length,ranked_chunk_ids:hits.map(hit=>hit.id)})),
    total_chunks:units.length,matched_chunks:fused.length,selected_chunk_ids:evidence.map(item=>item.unit_id),
    filter:{excluded,uncertain_kept:uncertain,fallback:'Uncertain scopes remain eligible. Explicit mismatches remain excluded.'},
    top_k_unit:'chunk',generation_calls:0,embedding_calls:0},
   token_usage:usage.report({stage:'retrieval',question_id:q.id}),
   warning:'원문 전체를 구간으로 색인했습니다. Top-K는 구간 기준이며 답변에는 선택한 원문 구간을 전달합니다.'};
  return persist?{...data,artifact_id:this.store.artifact('retrieval',data)}:data;
 }
}

module.exports={ROUTE,MODES,VERSION,RawChunkSearch};
