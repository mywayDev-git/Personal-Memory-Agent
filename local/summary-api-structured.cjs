const crypto=require('node:crypto'),{hash}=require('./core.cjs'),{VERSION}=require('./summary.cjs'),usage=require('./token-usage.cjs');
const {prepareExcerptVectors}=require('./extractive.cjs');
const NAMESPACE='personal-summary-v1',OWNER='local-user';
function createSummaryApi(engine,runtime){
 const memory=engine.summary;usage.init(engine.store.db);
 function selected(key){const row=memory.get(key);if(!row||row.namespace!==NAMESPACE||row.owner!==OWNER||row.deleted_at)throw Error('사용 가능한 요약 기억이 없습니다.');return row;}
 function view(row){const value=memory.view(row);if(row.structured_index_id){try{const index=engine.structured.load(row.structured_index_id,memory.record(row));value.structured_index={index_id:row.structured_index_id,version:index.version,cards:index.units,...(index.excerpt_manifest?{excerpt_manifest:index.excerpt_manifest}:{})};}catch(e){value.index_error=e.message;}}return value;}
 async function job(action){
  if(engine.busy||engine.creating)throw Error('다른 실행이 진행 중입니다. 완료 후 다시 시도하세요.');engine.busy='SUMMARY-'+crypto.randomUUID();engine.abort=new AbortController();runtime.allowStart?.();
  const operation={id:engine.busy,owner_id:OWNER,transient:true,created_at:new Date().toISOString()};
  try{const result=await usage.track(engine,operation,()=>action(engine.abort.signal,operation));return {...result,operation_id:operation.id,token_usage:operation.token_usage};}catch(error){error.operation_id=operation.id;error.token_usage=operation.token_usage;throw error;}finally{engine.summaryProgress=null;engine.busy=null;engine.abort=null;}
 }
 async function prepare(c,signal,generation=true){if(generation)await runtime.ensure('generation',c.model,signal);await runtime.ensure('embedding',c.embedding_model,signal);}
 const config=data=>{const route=data.config?.route||'M0';if(!['M0','M1'].includes(route))throw Error('요약 검색 방식 오류');return engine.config({...data.config,route});};
 const hook=(c,signal)=>c.route==='M1'?async row=>{if(c.excerpt_only){await prepareExcerptVectors(engine,[memory.record(row)],signal);return;}const index=await engine.structured.build(memory.record(row),c,signal);row.structured_index_id=index.index_id;}:undefined;
 return {
  async get(route,url){
   if(route==='/summary-memory')return {version:VERSION,memories:memory.list(NAMESPACE,OWNER).map(view)};
   if(route==='/summary-memory/usage')return {operations:engine.store.db.prepare('SELECT operation_id,created_at,payload FROM token_usage_operations WHERE owner=? ORDER BY created_at DESC LIMIT 30').all(OWNER).map(r=>({operation_id:r.operation_id,created_at:r.created_at,...JSON.parse(r.payload)}))};
   if(route==='/summary-memory/original'){const row=selected(url.searchParams.get('key'));return {memory_key:row.memory_key,summary_id:row.summary_artifact_id,source:memory.original(row),usage:'검토·재요약 전용. 검색·답변에 사용하지 않습니다.'};}
   throw Error('지원하지 않는 요약 조회');
  },
  async post(route,data){
   if(route==='/summary-memory/save')return job(async signal=>{
    if(typeof data.text!=='string'||!data.text.trim()||data.text.length>60000)throw Error('원본을 1~60,000자로 입력하세요.');
    const previous=data.key?selected(data.key):null;if(previous&&data.expected!==previous.summary_artifact_id)throw Error('수정할 기억이 변경됐습니다. 새로 불러오세요.');const c=config(data);await prepare(c,signal);
    const source={id:previous?.source_id||'MEM-'+crypto.randomUUID(),revision:previous?Number(previous.revision)+1:1,text:data.text,metadata:{owner_id:OWNER,created_at:previous?.source_timestamp||previous?.created_at||new Date().toISOString()}};
    const row=await memory.save(NAMESPACE,source,c,signal,{expected:previous?.summary_artifact_id,beforePublish:hook(c,signal)});return {memory:view(row)};
   });
   if(route==='/summary-memory/resummarize')return job(async signal=>{
    const previous=selected(data.key);if(data.expected!==previous.summary_artifact_id)throw Error('재요약할 기억이 변경됐습니다. 새로 불러오세요.');const c=config(data);await prepare(c,signal);const row=await memory.save(NAMESPACE,memory.original(previous),c,signal,{force:true,expected:data.expected,beforePublish:hook(c,signal)});return {memory:view(row)};
   });
   if(route==='/summary-memory/delete')return job(async()=>{const row=selected(data.key);if(data.expected!==row.summary_artifact_id)throw Error('삭제할 기억이 변경됐습니다.');row.deleted_at=new Date().toISOString();memory.write(row);return {ok:true};});
   if(route==='/summary-memory/search')return job(async(signal,operation)=>{
    if(typeof data.query!=='string'||!data.query.trim()||data.query.length>4000)throw Error('검색 질문을 1~4,000자로 입력하세요.');const c=config(data),answer=data.answer===true;await prepare(c,signal,answer||!!c.answer_pipeline||c.route==='M1'&&!c.excerpt_only);
    const rows=memory.list(NAMESPACE,OWNER).filter(row=>(row.summary_mode||'generated')===(c.summary_mode||'generated')),records=rows.map(row=>memory.record(row)),sources=rows.map(row=>({id:row.source_id,revision:row.revision,original_fingerprint:row.original_fingerprint,metadata:{owner_id:OWNER},gold:{facts:[]}})),extraction={kind:VERSION,extraction_state:'COMPLETED',records};
    if(c.route==='M1'&&!c.excerpt_only){
     extraction.structured_indexes=await engine.structured.prepare(records,c,signal);extraction.structured_version=require('./metadata-schema.cjs').VERSION;
     engine.store.db.exec('BEGIN IMMEDIATE');try{for(const row of rows){if(selected(row.memory_key).summary_artifact_id!==row.summary_artifact_id)throw Error('색인 준비 중 기억이 변경됐습니다.');row.structured_index_id=extraction.structured_indexes.find(i=>i.summary_id===row.summary_artifact_id).index_id;memory.write(row);}engine.store.db.exec('COMMIT');}catch(e){engine.store.db.exec('ROLLBACK');throw e;}
    }
    const context={id:NAMESPACE,actor_id:OWNER,now:new Date().toISOString(),conversation:[],expected_state:{accessible_sources:sources.map(s=>({source_id:s.id,revision:s.revision}))}},gold={evidence_groups:[],required_claims:[],forbidden_claims:[],expected_action:'answer',reference_answer:'개인 입력: 의미 정답 미주석'},q={id:'QUERY-'+crypto.randomUUID(),context_id:context.id,text:data.query.trim(),gold};
    const ds={fingerprint:hash(NAMESPACE),d:{sources:{records:sources},contexts:{contexts:[context]}},lib:{materialize:()=>({accessible:sources})}},run={...operation,config:c,config_hash:hash(c),dataset_fingerprint:ds.fingerprint,question_ids:[q.id],results:[],status:'RUNNING',kind:'summary_search',stage:answer?'end_to_end':'retrieve'};
    const retrieval=await usage.withStage('retrieval',()=>engine.retrieve(run,ds,q,context,sources,extraction,signal),{question_id:q.id,source_id:null}),result=answer?await usage.withStage('answer',()=>engine.answer(run,ds,q,context,retrieval,signal),{question_id:q.id,source_id:null}):null;
    return {query:q.text,retrieval,answer:result,policy:'전체 색인 준비 후 요약문만 검색·답변. 원본은 읽지 않음.'};
   });
   throw Error('지원하지 않는 요약 작업');
  }
 };
}
module.exports={createSummaryApi,NAMESPACE,OWNER};
