'use strict';
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {hash}=require('./core.cjs'),modes=require('../ui/plant-thought/search-modes.js');
const {prepareSummaryBatch}=require('./summary-batch.cjs');
const summary=require('./summary.cjs');
const VERSION='chat-graph-on-write-v1';
const isGraph=id=>['G1','G2'].includes(modes.get(id)?.route);
const loadScope=(root,collection)=>require('../ui/chat-api.cjs').loadScope(root,{collection_id:collection,analysis_version:'v2'});
const sourcesFor=(scope,collection)=>scope.sources.map(source=>({...source,metadata:{...source.metadata,owner_id:'chat-local-'+collection},gold:{facts:[]}}));
function configFor(engine,id){const mode=modes.get(modes.normalize(id));if(!isGraph(id))throw Error('그래프 검색 방식을 선택해 주세요.');return engine.config({route:mode.route,model:'qwen35-4b-q4',top_k:5,...(mode.summary_mode?{summary_mode:mode.summary_mode}:{}),...(mode.event_graph_mode?{event_graph_mode:mode.event_graph_mode}:{})});}
// Query, Top-K, answer prompt and the complete engine code hash do not define an index.
const buildFiles=['summary.cjs','extractive.cjs','structured-memory.cjs','metadata-schema.cjs','metadata-extraction.cjs','metadata-grounding.cjs','event-graph.cjs','event-linking.cjs','claim-graph.cjs'];
const buildCode=hash(buildFiles.map(file=>({file,hash:hash(fs.readFileSync(path.join(__dirname,file),'utf8'))})));
function signature(config){return hash({version:VERSION,buildCode,route:config.route,event_graph_mode:config.event_graph_mode||null,summary_mode:config.summary_mode,summary_settings_hash:config.summary_settings_hash,metadata_settings_hash:config.metadata_settings_hash,model:config.model,model_hash:require('./model-registry.cjs').find(model=>model.id===config.model)?.sha256,seed:config.seed});}
function dataset(scope,collection,query='색인 준비'){
 const sources=sourcesFor(scope,collection),context={id:'chat-'+collection,actor_id:'chat-local-'+collection,now:scope.now,conversation:[]};
 const question={id:'chat-query',context_id:context.id,text:query,gold:{evidence_groups:[]}};
 // Keep per-record summaries in a stable collection namespace as the collection grows.
 const ds={fingerprint:hash({version:VERSION,collection}),d:{sources:{records:sources},questions:{questions:[question]},contexts:{contexts:[context]}},lib:{materialize:()=>({accessible:sources})}};
 return {sources,context,question,ds};
}
function createGraphIndex(parent,runtime){
 const db=parent.store.db;
 db.exec(`CREATE TABLE IF NOT EXISTS chat_graph_indexes(collection TEXT NOT NULL,mode TEXT NOT NULL,scope_hash TEXT NOT NULL,build_hash TEXT NOT NULL,artifact_id TEXT NOT NULL,updated_at TEXT NOT NULL,PRIMARY KEY(collection,mode));
 CREATE TABLE IF NOT EXISTS chat_graph_jobs(collection TEXT NOT NULL,mode TEXT NOT NULL,revision INTEGER NOT NULL,status TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(collection,mode));
 CREATE TABLE IF NOT EXISTS chat_graph_profiles(mode TEXT PRIMARY KEY);
 CREATE TABLE IF NOT EXISTS chat_graph_state(name TEXT PRIMARY KEY,value TEXT NOT NULL);`);
 db.prepare('INSERT OR IGNORE INTO chat_graph_profiles VALUES(?)').run('G1-linked');
 // An interrupted build must be resumed as an indexing job, never by a search request.
 db.prepare("UPDATE chat_graph_jobs SET status='queued' WHERE status='indexing'").run();
 let timer,running=null,active=null,closed=false,paused=false,checking=false,watchLibrary=null,canRun=()=>!parent.busy;
 const readJob=(collection,mode)=>{const row=db.prepare('SELECT * FROM chat_graph_jobs WHERE collection=? AND mode=?').get(collection,mode);return row?{...JSON.parse(row.payload),revision:row.revision,status:row.status}:null;};
 function saveJob(job){db.prepare('INSERT INTO chat_graph_jobs VALUES(?,?,?,?,?) ON CONFLICT(collection,mode) DO UPDATE SET revision=excluded.revision,status=excluded.status,payload=excluded.payload').run(job.collection,job.mode,job.revision,job.status,JSON.stringify(job));}
 function enable(mode){if(!isGraph(mode))throw Error('그래프 검색 방식을 선택해 주세요.');db.prepare('INSERT OR IGNORE INTO chat_graph_profiles VALUES(?)').run(mode);}
 function validate(collection,mode){if(!['personal','samples'].includes(collection)||!isGraph(mode))throw Error('색인을 준비할 자료함과 그래프 방식을 확인해 주세요.');}
 function enqueue(collection,mode,reason='manual'){
  validate(collection,mode);enable(mode);const previous=readJob(collection,mode);
  if(reason==='manual'&&['queued','indexing'].includes(previous?.status))return previous;
  const job={collection,mode,revision:(previous?.revision||0)+1,status:'queued',reason,progress:'색인 준비 대기',queued_at:new Date().toISOString(),updated_at:new Date().toISOString(),error:null};saveJob(job);return job;
 }
 function seedSummaries(engine,scope,collection,config){
  const {ds}=dataset(scope,collection),namespace=summary.datasetNamespace(ds.fingerprint,config),settingsHash=config.summary_settings_hash;
  for(const source of sourcesFor(scope,collection)){
   const key=summary.memoryKey(namespace,source.metadata.owner_id,source.id),current=engine.summary.get(key),fingerprint=summary.originalKey(source);
   if(current?.original_fingerprint===fingerprint)continue;
   const rows=db.prepare('SELECT payload FROM summary_memories WHERE owner=? AND source_id=? AND deleted_at IS NULL ORDER BY rowid DESC').all(source.metadata.owner_id,source.id);
   for(const row of rows){
    const candidate=JSON.parse(row.payload);if(candidate.original_fingerprint!==fingerprint)continue;
    const artifact=parent.store.readArtifact(candidate.summary_artifact_id);if(artifact.settings_hash!==settingsHash)continue;
    engine.summary.write({...candidate,memory_key:key,namespace});break;
   }
  }
 }
 function cached(scope,collection,mode,config=configFor(parent,mode)){
  const scopeHash=hash(scope.sources),buildHash=signature(config),row=db.prepare('SELECT * FROM chat_graph_indexes WHERE collection=? AND mode=?').get(collection,mode);
  if(row?.scope_hash===scopeHash&&row.build_hash===buildHash){const extraction=parent.store.readArtifact(row.artifact_id);parent.checkSourceScope(extraction,{id:'chat-'+collection},scope.sources);return {extraction,updated_at:row.updated_at};}
  // Preserve compatible work already completed by the old search-time implementation.
  const oldTable=db.prepare("SELECT 1 FROM sqlite_master WHERE type='table' AND name='chat_search_preparations'").get();
  if(oldTable)for(const entry of db.prepare('SELECT artifact_id FROM chat_search_preparations ORDER BY rowid DESC').all()){
   const extraction=parent.store.readArtifact(entry.artifact_id);
   if(extraction.context_id!=='chat-'+collection||extraction.extraction_state!=='COMPLETED'||extraction.dataset_fingerprint!==scopeHash||extraction.config?.code_hash!==config.code_hash||signature(extraction.config)!==buildHash)continue;
   parent.checkSourceScope(extraction,{id:'chat-'+collection},scope.sources);parent.summary.validate(extraction.records,sourcesFor(scope,collection));
   const updated_at=new Date().toISOString();db.prepare('INSERT OR REPLACE INTO chat_graph_indexes VALUES(?,?,?,?,?,?)').run(collection,mode,scopeHash,buildHash,extraction.artifact_id,updated_at);
   return {extraction,updated_at};
  }
  return null;
 }
 async function status(collection,mode){
  validate(collection,mode);const scope=await loadScope(parent.root,collection),job=readJob(collection,mode),index=cached(scope,collection,mode);
  const currentStatus=index?'ready':job?.status==='ready'?'stale':job?.status||'not_prepared';
  return {collection,mode,status:currentStatus,source_count:scope.sources.length,indexed_count:index?scope.sources.length:job?.done||0,progress:index?'저장된 색인 준비 완료':job?.progress||'한 번 색인을 준비해 주세요.',error:index?null:job?.error||null,updated_at:index?.updated_at||job?.updated_at||null,index_policy:'on_record_change'};
 }
 async function build(job){
  if(parent.busy||closed)return;const controller=new AbortController();active={job,controller};
  const run={id:'chat-index-'+crypto.randomUUID(),transient:true,created_at:new Date().toISOString(),results:[],question_ids:['chat-query'],events:[]};parent.busy=run.id;parent.abort=controller;
  job={...job,status:'indexing',progress:'기록 변경에 따른 색인 갱신 중',updated_at:new Date().toISOString(),error:null};saveJob(job);
  const signal=controller.signal,engine=Object.create(parent);Object.assign(engine,{_summary:undefined,_structured:undefined,_rawChunks:undefined,_attention:undefined,summaryProgress:null});
  let lastProgressWrite=0;
  engine.update=(r,message,detail={})=>{signal.throwIfAborted();job.progress=message;job.done=detail.unit_done??job.done;job.total=detail.unit_total??job.total;job.updated_at=new Date().toISOString();if(Date.now()-lastProgressWrite>250){const latest=readJob(job.collection,job.mode);if(latest?.revision===job.revision)saveJob(job);lastProgressWrite=Date.now();}};
  try{
   await require('./token-usage.cjs').track(engine,run,async()=>{
    const scope=await loadScope(parent.root,job.collection),scopeHash=hash(scope.sources),config=configFor(parent,job.mode);run.config=config;
    if(!cached(scope,job.collection,job.mode,config)){
     const {sources,ds}=dataset(scope,job.collection);
     if(sources.length){runtime.allowStart?.();await runtime.ensure('generation',config.model,signal);await runtime.ensure('embedding',config.embedding_model,signal);}
     seedSummaries(engine,scope,job.collection,config);
     const prepared=await prepareSummaryBatch(engine,run,ds,signal),extraction=prepared.get('chat-'+job.collection);signal.throwIfAborted();
     const currentScope=await loadScope(parent.root,job.collection),latest=readJob(job.collection,job.mode);
     if(hash(currentScope.sources)!==scopeHash||latest?.revision!==job.revision){if(latest?.revision===job.revision)enqueue(job.collection,job.mode,'records_changed');return;}
     db.prepare('INSERT OR REPLACE INTO chat_graph_indexes VALUES(?,?,?,?,?,?)').run(job.collection,job.mode,scopeHash,signature(config),extraction.artifact_id,new Date().toISOString());
    }
    const latest=readJob(job.collection,job.mode);if(latest?.revision===job.revision)saveJob({...job,status:'ready',done:scope.sources.length,total:scope.sources.length,progress:'저장된 색인으로 검색할 수 있습니다.',updated_at:new Date().toISOString(),token_usage:require('./token-usage.cjs').report()});
   });
  }catch(error){const latest=readJob(job.collection,job.mode);if(latest?.revision===job.revision)saveJob({...job,status:signal.aborted?'cancelled':'failed',progress:signal.aborted?'색인 준비를 중지했습니다.':'색인 준비 실패',error:error.message,updated_at:new Date().toISOString()});}
  finally{if(parent.busy===run.id){parent.busy=null;parent.abort=null;}active=null;}
 }
 async function tick(){
  if(closed||paused||checking)return;checking=true;
  try{
   if(!watchLibrary)watchLibrary=new (require('../ui/library.cjs').Library)(parent.root);
   {
    const notice=watchLibrary.indexNotice(),last=Number(db.prepare("SELECT value FROM chat_graph_state WHERE name='personal-change'").get()?.value||0);
    if(notice&&notice.sequence>last){
     for(const profile of db.prepare('SELECT mode FROM chat_graph_profiles').all())enqueue('personal',profile.mode,'records_changed');
     db.prepare("INSERT OR REPLACE INTO chat_graph_state VALUES('personal-change',?)").run(String(notice.sequence));
    }
   }
   if(!running&&canRun()&&!parent.busy){
    const row=db.prepare("SELECT collection,mode FROM chat_graph_jobs WHERE status='queued' ORDER BY rowid LIMIT 1").get();
    if(row){running=build(readJob(row.collection,row.mode)).catch(error=>{console.error('Graph index build:',error.message);}).finally(()=>{running=null;});}
   }
  }catch(error){if(!closed)console.error('Graph index queue:',error.message);}
  finally{checking=false;}
 }
 function cancel(collection,mode){validate(collection,mode);const job=readJob(collection,mode);if(!job||!['queued','indexing'].includes(job.status))return false;
  saveJob({...job,revision:job.revision+1,status:'cancelled',progress:'색인 준비를 중지했습니다.',updated_at:new Date().toISOString()});if(active?.job.collection===collection&&active.job.mode===mode)active.controller.abort();return true;
 }
 return {isGraph,configFor:mode=>configFor(parent,mode),dataset,cached,status,enable,enqueue,cancel,
  start(options={}){canRun=options.canRun||canRun;if(!timer){timer=setInterval(()=>{void tick();},1500);timer.unref?.();}},
  async suspend(){paused=true;active?.controller.abort();await running;},
  resume(){db.prepare('INSERT OR IGNORE INTO chat_graph_profiles VALUES(?)').run('G1-linked');paused=false;},
  async close(){closed=true;clearInterval(timer);active?.controller.abort();await running;watchLibrary?.close();}};
}
module.exports={createGraphIndex,isGraph,configFor,signature,dataset,sourcesFor};
