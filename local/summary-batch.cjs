const usage=require('./token-usage.cjs');
const {datasetNamespace,originalKey,VERSION}=require('./summary.cjs');
const {prepareExcerptVectors}=require('./extractive.cjs');
const BATCH_VERSION='all-summaries-before-questions-v1';

async function prepareSummaryBatch(engine,run,ds,signal){
 const started=performance.now(),batch=run.summary_batch={version:BATCH_VERSION,status:'PLANNING',scope:'selected_questions_accessible_sources',total_sources:0,completed_sources:0,generated_sources:0,reused_sources:0,total_contexts:0,prepared_contexts:0,started_at:new Date().toISOString()};
 const progress=message=>engine.update(run,message,{stage:'summary_prepare',unit_done:batch.completed_sources,unit_total:batch.total_sources,unit_label:'원문',source_id:batch.active_source_id||null});
 const contexts=new Map(),unique=new Map(),records=new Map(),prepared=new Map();
 try{
  progress('1단계 · 실행 범위의 전체 원문 확인 · 질문 검색·답변 대기');
  const questions=new Map(ds.d.questions.questions.map(q=>[q.id,q])),registered=new Map(ds.d.contexts.contexts.map(c=>[c.id,c]));
  for(const id of run.question_ids){
   signal.throwIfAborted();const question=questions.get(id),context=registered.get(question?.context_id);if(!context)throw Error('전체 요약의 질문·기억 범위를 확인할 수 없습니다.');
   if(contexts.has(context.id))continue;
   // Each question retains its own owner/revision/deletion scope after the shared preparation.
   const sources=ds.lib.materialize(context,ds.d.sources.records).accessible,keys=[];
   for(const source of sources){const key=originalKey(source);keys.push(key);if(!unique.has(key))unique.set(key,source);}
   contexts.set(context.id,{context,sources,keys});
  }
  batch.total_contexts=contexts.size;batch.total_sources=unique.size;batch.status='RUNNING';
  progress(`1단계 · 전체 원문 요약·저장 0/${batch.total_sources} · 질문 검색·답변 대기`);
  engine.summaryProgress=(id,part,total)=>progress(`1단계 · 전체 원문 요약·저장 ${batch.completed_sources}/${batch.total_sources} · ${id} 구간 ${part}/${total}`);
  for(const [key,source]of unique){
   signal.throwIfAborted();batch.active_source_id=source.id;batch.active_source_revision=source.revision;
   progress(`1단계 · 전체 원문 요약·저장 ${batch.completed_sources}/${batch.total_sources} · ${source.id}`);
   const row=await engine.summary.save(datasetNamespace(ds.fingerprint,run.config),source,run.config,signal,{force:run.config.summary_force});
   records.set(key,{...engine.summary.record(row),reused:!!row.reused,timestamp:source.metadata.created_at||null});batch.completed_sources++;batch[row.reused?'reused_sources':'generated_sources']++;
   progress(`1단계 · 전체 원문 요약·저장 ${batch.completed_sources}/${batch.total_sources}`);
  }
  signal.throwIfAborted();batch.active_source_id=null;batch.active_source_revision=null;
  const manifest={version:BATCH_VERSION,phase:'all_source_summaries_saved',run_id:run.id,dataset_fingerprint:ds.fingerprint,source_count:unique.size,records:[...records.values()],question_ids:run.question_ids};
  batch.artifact_id=engine.store.artifact('summary-batch',manifest);
  const useMetadata=run.config.route==='M1'&&!run.config.excerpt_only;
 let indexRefs=[];if(run.config.route==='M1'){
   batch.indexing={status:'RUNNING',completed:0,total:records.size,started_at:new Date().toISOString(),...(run.config.excerpt_only?{kind:'excerpt_vectors'}:{})};
   if(useMetadata)indexRefs=await engine.structured.prepare([...records.values()],run.config,signal,(done,total,source,attempt)=>{batch.indexing.active_attempt=attempt||null;batch.indexing.completed=done;batch.indexing.total=total;batch.indexing.active_source_id=source;engine.update(run,`2단계 · 전체 메타정보 색인 ${done}/${total}${attempt?.attempt>1?' · 검증 보완 '+attempt.attempt+'/'+attempt.max_attempts:''} · 질문 처리 대기`,{stage:'index_prepare',unit_done:done,unit_total:total,unit_label:'요약',source_id:source});});
   else await prepareExcerptVectors(engine,[...records.values()],signal,(done,total,source)=>{
    batch.indexing.completed=done;
    batch.indexing.active_source_id=source;
    engine.update(run,`2단계 · 발췌문 임베딩 ${done}/${total} · 질문 처리 대기`,{stage:'index_prepare',unit_done:done,unit_total:total,unit_label:'발췌문',source_id:source});
   });
   batch.indexing.status='COMPLETED';batch.indexing.finished_at=new Date().toISOString();if(useMetadata)batch.structured_batch_artifact_id=engine.store.artifact('structured-index-batch',{version:require('./metadata-schema.cjs').VERSION,indexes:indexRefs});
  }
  for(const [id,plan]of contexts){
   signal.throwIfAborted();const at=performance.now(),selected=plan.keys.map(key=>records.get(key));engine.summary.validate(selected,plan.sources);
   const data={kind:VERSION,context_id:id,dataset_fingerprint:ds.fingerprint,config:run.config,records:selected,source_refs:plan.sources.map(s=>({source_id:s.id,revision:s.revision})),extraction_state:'COMPLETED',semantic_status:'PENDING_REVIEW',elapsed_ms:null,binding_elapsed_ms:performance.now()-at,summary_batch_artifact_id:batch.artifact_id,preparation_scope:BATCH_VERSION,...(useMetadata?{structured_version:require('./metadata-schema.cjs').VERSION,structured_indexes:indexRefs.filter(i=>selected.some(r=>r.summary_id===i.summary_id)),structured_batch_artifact_id:batch.structured_batch_artifact_id}:{})};
   const artifact_id=engine.store.artifact('extraction',data);prepared.set(id,{...data,artifact_id});batch.prepared_contexts++;
  }
  signal.throwIfAborted();batch.status='COMPLETED';batch.finished_at=new Date().toISOString();batch.elapsed_ms=performance.now()-started;batch.context_artifact_ids=[...prepared.values()].map(a=>a.artifact_id);
  progress(`1단계 완료 · 전체 원문 ${batch.completed_sources}/${batch.total_sources}개 요약·저장 완료 · ${run.config.excerpt_only?'발췌문 임베딩 완료 · 3':useMetadata?'전체 메타정보 색인 완료 · 3':'2'}단계 질문별 ${run.stage==='extract'?'결과 연결':'검색·답변'} 시작`);
  return prepared;
 }catch(error){
  batch.status=signal.aborted?'CANCELLED':'ERROR';batch.error=error.message;batch.finished_at=new Date().toISOString();batch.elapsed_ms=performance.now()-started;
  if(batch.indexing?.status==='RUNNING'){batch.indexing.status=batch.status;batch.indexing.error=error.message;batch.indexing.error_artifact_id=error.metadata_artifact_id||null;batch.indexing.validation_failure=error.index_validation||null;run.error_stage='index_prepare';}else run.error_stage='summary_prepare';progress((run.error_stage==='index_prepare'?'전체 색인이':'전체 요약이')+' 완료되지 않아 질문 검색·답변을 시작하지 않았습니다. '+error.message);throw error;
 }finally{engine.summaryProgress=null;}
}
module.exports={BATCH_VERSION,prepareSummaryBatch};
