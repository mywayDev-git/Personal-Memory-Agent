const {auditAnswer}=require('./answer-audit.cjs');
const {focusAllEvidence,focusEvidence,moneyProof}=require('./evidence-focus.cjs');
const {citationPlan,resolveCitations}=require('./summary-citations.cjs');
const {applySummaryDialogue,arithmeticTask}=require('./summary-dialogue.cjs');
const scopedAnswer=require('./scoped-answer.cjs');
const compoundSearch=require('./compound-search.cjs');
const rawChunkSearch=require('./raw-chunk-search.cjs');
const questionAttention=require('./question-attention.cjs');
const isChunkRoute=route=>[rawChunkSearch.ROUTE,questionAttention.ROUTE].includes(route);
const chronologicalAnswer=require('./chronological-answer.cjs');
const questionDigest=require('./question-digest.cjs');
const evidenceInterpreter=require('./evidence-interpretation.cjs');
const eventGraph=require('./event-graph.cjs');
const multiAnchor=require('./multi-anchor.cjs');
const {MODE:LINKED_GRAPH_MODE}=require('./event-linking.cjs');
const {filterEvidence:filterEventEvidence}=require('./event-evidence.cjs');
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),{DatabaseSync}=require('node:sqlite'),{pathToFileURL}=require('node:url');
const {hash,sentences,validateNative,chunks,unitText,cosine,rrf,queryText,safeConversation,validateCitations}=require('./core.cjs');
const {validateDialogueSelection,applyDialogue,dialogueSummaries}=require('./dataset-dialogue.cjs');
const {BUDGET_VERSION,FULL_POLICY}=require('./token-budget.cjs');
const {VERSION:EVALUATION_VERSION,CRITERIA_VERSION,CRITERIA_HASH,criteriaFor,automaticEvaluation}=require('./answer-evaluation.cjs');
const prompts=require('./prompts.cjs'),registry=require('./model-registry.cjs');
const {errorCode,extractionChecks}=require('./review.cjs');
const {isFull,isRaw,FULL_VERSION,fullEvidence,fullBudget,budgetError,assertFullEvidence,fullReviewEvidence}=require('./raw-full.cjs');
const summary=require('./summary.cjs');
const {BATCH_VERSION,prepareSummaryBatch}=require('./summary-batch.cjs');
const diagnostics=require('./request-diagnostics.cjs'),usage=require('./token-usage.cjs'),structured=require('./structured-memory.cjs');
class Engine{
  constructor(root,store,runtime){this.root=root;this.store=store;this.runtime=runtime;usage.attach(runtime);this.busy=null;this.abort=null;this.store.recover();this.code_hash=hash(['engine.cjs','core.cjs','prompts.cjs','runtime.cjs','review.cjs','raw-full.cjs','dataset-dialogue.cjs','token-budget.cjs','answer-evaluation.cjs','answer-criteria-v2.json','summary.cjs','extractive.cjs','summary-api.cjs','request-diagnostics.cjs','summary-batch.cjs','token-usage.cjs','structured-memory.cjs','structured-retrieve.cjs','metadata-schema.cjs','metadata-schema-v2.cjs','metadata-grounding.cjs','metadata-extraction.cjs','temporal-precision.cjs','relation-references.cjs','metadata-recovery.cjs','summary-dialogue.cjs','summary-citations.cjs','evidence-focus.cjs','answer-audit.cjs','scoped-answer.cjs','chronological-answer.cjs','question-digest.cjs','event-graph.cjs','multi-anchor.cjs','claim-graph.cjs','event-linking.cjs','event-evidence.cjs','summary-api-structured.cjs','compound-search.cjs','chunk-keywords.cjs','keyword-query.cjs','raw-chunk-search.cjs','question-attention.cjs','evidence-interpretation.cjs'].map(name=>({name,sha256:hash(fs.readFileSync(path.join(__dirname,name)).toString())})));}
 get structured(){return this._structured??=new structured.StructuredMemory(this);}
 get summary(){return this._summary??=new summary.SummaryMemory(this);}
 get attention(){return this._attention??=new questionAttention.QuestionAttention(this);}
 get rawChunks(){return this._rawChunks??=new rawChunkSearch.RawChunkSearch(this);}
 async dataset(id='pma-dev-v0.1.0'){
  if(!['pma-dev-v0.1.0','pma-dev-v0.2.0','pma-long-v1.0.1','pma-long-v2.0.0','pma-context-v1.0.0','pma-memory-v2.0.0','pma-memory-v3.0.0','pma-generalization-v1.0.0'].includes(id))throw Error('등록되지 않은 데이터셋');const dir=path.join(this.root,'datasets',id);const lib=await import(pathToFileURL(path.join(this.root,'datasets',['pma-long-v1.0.1','pma-long-v2.0.0','pma-context-v1.0.0','pma-memory-v2.0.0','pma-memory-v3.0.0','pma-generalization-v1.0.0'].includes(id)?id:'pma-dev-v0.1.0','lib.mjs')).href);
  const d=lib.loadDataset(dir),v=lib.validate(d,dir);if(!v.ok)throw Error('데이터셋 무결성 검사 실패: '+v.errors.slice(0,3).join(', '));
  return {d,dir,lib,fingerprint:hash(fs.readFileSync(path.join(dir,'manifest.json')).toString())};
 }
 config(input={}){
  if([eventGraph.ROUTE,multiAnchor.ROUTE].includes(input.route))input={...input,summary_mode:'extractive-v1'};
  const c={dataset:input.dataset||'pma-dev-v0.1.0',model:input.model||'qwen35-4b-q4',embedding_model:'qwen3-embedding-06b-q8',method:input.method||'triples',structure_version:input.structure_version||'v1',extraction_prompt:input.extraction_prompt||'extract-conservative-v1',answer_prompt:input.answer_prompt||'answer-grounded-v1',query_prompt:input.query_prompt||'query-original-v1',route:input.route||'R0',top_k:Number(input.top_k||5),candidate_k:20,seed:Number(input.seed??42),evidence_char_budget:6000,answer_evidence_tokens:['M1',eventGraph.ROUTE,multiAnchor.ROUTE].includes(input.route)?3072:2048,extraction_output_tokens:4096,answer_output_tokens:2048,context_tokens:8192,request_diagnostics_version:diagnostics.VERSION,answer_evaluation_version:EVALUATION_VERSION,answer_criteria_version:CRITERIA_VERSION,answer_criteria_hash:CRITERIA_HASH,token_budget_version:BUDGET_VERSION,pipeline_version:'baseline-v1',code_hash:this.code_hash,chunk_version:'sentence-window-700utf16-overlap100-v1',fusion:'equal-weight-rrf-k60',embedding_profile:'qwen-instruct-en-last-eos-v1',temperature:0};
  if(['pma-long-v1.0.1','pma-long-v2.0.0','pma-context-v1.0.0'].includes(c.dataset)){c.dataset_profile=input.dataset_profile||(['pma-long-v2.0.0','pma-context-v1.0.0'].includes(c.dataset)?'natural_single':'smoke');c.input_path='raw_original_v1';if(input.input_path&&input.input_path!==c.input_path)throw Error('이 데이터셋은 원문 전체 경로만 지원합니다.');if(!['all','smoke','core','sentence','boundary','dependency','stress',...(['pma-long-v2.0.0','pma-context-v1.0.0'].includes(c.dataset)?['natural_single','natural_multi','natural_control']:[])].includes(c.dataset_profile))throw Error('데이터 프로필 오류');}
  if(c.dataset==='pma-context-v1.0.0'&&!['all','natural_single','natural_multi','natural_control'].includes(c.dataset_profile))throw Error('독립셋에는 자연 문맥 프로필만 있습니다.');
  if(c.dataset==='pma-memory-v2.0.0'){c.dataset_profile=input.dataset_profile||'development_a';c.input_path='raw_original_v1';if(input.input_path&&input.input_path!==c.input_path)throw Error('원문 전체 입력 경로만 지원합니다.');if(!['all','development_a','development_b','controlled','final'].includes(c.dataset_profile))throw Error('누적 기억 데이터 프로필 오류');}
  if(['pma-memory-v3.0.0','pma-generalization-v1.0.0'].includes(c.dataset)){const m=JSON.parse(fs.readFileSync(path.join(this.root,'datasets',c.dataset,'manifest.json'),'utf8'));c.dataset_profile=input.dataset_profile||m.default_profile;c.input_path='raw_original_v1';if(input.input_path&&input.input_path!==c.input_path)throw Error('원문 입력 경로 오류');if(c.dataset_profile!=='all'&&!Object.hasOwn(m.profiles,c.dataset_profile))throw Error('누적 장문 프로필 오류');}
  if(!registry.some(m=>m.id===c.model&&m.role==='generation'))throw Error('지원하지 않는 생성 모델');
  if(c.route==='R0-Chunk')c.route='R0';
  if(isFull(c.route)){c.raw_delivery_version=FULL_VERSION;c.full_budget_policy=FULL_POLICY;}
  if(!['triples','events','entities'].includes(c.method)||!['v1','v2'].includes(c.structure_version)||!['R0','R0-Full','S0','H1','M0','M1',eventGraph.ROUTE,multiAnchor.ROUTE,rawChunkSearch.ROUTE,questionAttention.ROUTE].includes(c.route))throw Error('구조화/검색 설정 오류');
  if(isChunkRoute(c.route)){
   c.chunk_search_mode=input.chunk_search_mode||'filtered';
   if(!rawChunkSearch.MODES.includes(c.chunk_search_mode))throw Error('원문 구간 검색 비교 방식이 올바르지 않습니다.');
   if(input.retrieval_strategy&&input.retrieval_strategy!=='single')throw Error('K1은 키워드 증강 방식에서 문항당 검색을 네 번 이내로 구성합니다.');
   c.chunk_version=rawChunkSearch.VERSION;c.top_k_unit='chunk';
   if(c.route===questionAttention.ROUTE)questionAttention.configure(c,input);
  }
  if(c.route===multiAnchor.ROUTE)c.multi_anchor_version=multiAnchor.VERSION;
  if(input.excerpt_only===true){
   if(c.route!=='M1'||input.summary_mode!=='extractive-v1')throw Error('발췌문만 검색하려면 M1의 원문 발췌 방식을 선택하세요.');
   c.excerpt_only=true;
  }
  if(input.answer_pipeline!=null&&input.answer_pipeline!=='existing'){
   if(![scopedAnswer.MODE,chronologicalAnswer.MODE,questionDigest.MODE,...evidenceInterpreter.MODES].includes(input.answer_pipeline))
    throw Error('지원하지 않는 답변 방식입니다.');
   c.answer_pipeline=input.answer_pipeline;
   if(evidenceInterpreter.MODES.includes(c.answer_pipeline))evidenceInterpreter.configure(c);
  }
  if(isFull(c.route)&&!c.answer_pipeline)c.answer_evidence_tokens=null;
  if(input.retrieval_strategy!=null&&input.retrieval_strategy!=='single'){
   if(isFull(c.route)||input.retrieval_strategy!==compoundSearch.MODE)throw Error('지원하지 않는 질문 검색 방식입니다.');
   c.retrieval_strategy=input.retrieval_strategy;
  }
  if(input.event_graph_mode!=null&&input.event_graph_mode!=='existing'){
   if(c.route!==eventGraph.ROUTE||![LINKED_GRAPH_MODE,eventGraph.CLAIM_MODE].includes(input.event_graph_mode))
    throw Error('지원하지 않는 사건 그래프 설정입니다.');
   c.event_graph_mode=input.event_graph_mode;
  }
  if(input.all_candidates===true&&!isFull(c.route))c.all_candidates=true;
  if(!Number.isInteger(c.top_k)||c.top_k<1||c.top_k>20||!Number.isInteger(c.seed)||c.seed<0||c.seed>2147483647)throw Error('Top-K/seed 범위 오류');
  for(const [key,list] of [['extraction_prompt',prompts.extractionPrompts],['answer_prompt',prompts.answerPrompts],['query_prompt',prompts.queryPrompts]]){if(!list.some(p=>p.id===c[key]))throw Error('프롬프트 ID 오류');}
  c.extraction_prompt_text=String(input.extraction_prompt_text??prompts.extractionPrompts.find(p=>p.id===c.extraction_prompt).text);
  c.answer_prompt_text=String(input.answer_prompt_text??prompts.answerPrompts.find(p=>p.id===c.answer_prompt).text);
  if(!c.extraction_prompt_text.trim()||!c.answer_prompt_text.trim()||c.extraction_prompt_text.length>20000||c.answer_prompt_text.length>20000)throw Error('프롬프트 길이 오류');
  c.prompt_hashes={extraction:hash(c.extraction_prompt_text),answer:hash(c.answer_prompt_text),query:hash(prompts.queryPrompts.find(p=>p.id===c.query_prompt).text)};
  c.schema_hash=hash(prompts.schemas[c.method]);if(['M0','M1',eventGraph.ROUTE,multiAnchor.ROUTE].includes(c.route)){summary.configure(c,input);c.summary_execution_order=BATCH_VERSION;if(['M1',eventGraph.ROUTE,multiAnchor.ROUTE].includes(c.route)&&!c.excerpt_only)structured.configure(c,input);}return c;
 }
 async previewBudget(body){
  if(this.busy||this.creating)throw Error('테스트 실행 중에는 사전 계산을 하지 않습니다.');
  const c=this.config(body.config);if(!isFull(c.route))throw Error('사전 계산은 R0-Full에서 지원합니다.');
  const state=this.runtime.status().states?.generation;if(state?.status!=='ready'||state.model_id!==c.model)throw Error('선택한 모델 서버를 먼저 켜 주세요. 사전 계산은 서버를 자동으로 켜지 않습니다.');
  const ds=await this.dataset(c.dataset),q=ds.d.questions.questions.find(q=>q.id===body.question_id);if(!q)throw Error('질문 ID 오류');
  const original=ds.d.contexts.contexts.find(x=>x.id===q.context_id),stateData=ds.lib.materialize(original,ds.d.sources.records),context={...original,conversation:safeConversation(original,stateData.accessible)};
  const pending=!!context.dialogue?.depends_on?.length;
  const evidence=fullEvidence(stateData.accessible),budget=await fullBudget(this.runtime,c,q,context,evidence);
  return {question_id:q.id,dataset_fingerprint:ds.fingerprint,config_hash:hash(c),budget,scope:pending?'SEED_ONLY':'CURRENT_REQUEST',note:pending?'앞 턴 답변은 아직 포함하지 않은 기본 입력입니다. 실제 후속 턴마다 다시 계산합니다.':'선택 질문과 현재 프롬프트의 실제 요청 토큰입니다. 답변은 생성하지 않았습니다.',sources:evidence.length,model_inference:false};
 }
 async create(body){if(this.busy||this.creating)throw Error('현재 실행을 준비하거나 진행 중입니다.');this.creating=true;try{return await this.createInternal(body);}finally{this.creating=false;}}
 async createInternal(body){
  if(this.busy)throw Error('현재 실행이 진행 중입니다. 완료하거나 중단한 뒤 실행하세요.');
  const stage=body.stage||'end_to_end',ids=body.question_ids;
  if(!['extract','retrieve','answer','end_to_end'].includes(stage))throw Error('실행 단계 오류');
  if(!Array.isArray(ids)||!ids.length)throw Error('실행할 질문을 선택하세요.');
  const artifacts=Array.isArray(body.artifacts)?body.artifacts:[];
  const limit=['answer','retrieve'].includes(stage)?Math.max(300,Math.min(ids.length,2000)):300;
  if(artifacts.length>limit)throw Error('산출물 선택 수 초과');
  const saved=new Map(),requested=new Set(ids);
  for(const id of artifacts){
   const a=this.store.readArtifact(id);
   if(stage==='answer'&&a.type==='retrieval'&&requested.has(a.question_id)&&!saved.has(a.question_id))
    saved.set(a.question_id,{id,config:a.config,dataset_fingerprint:a.dataset_fingerprint});
  }
  const input=body.config||{};
  let searchConfig=input,frozenFingerprint;
  if(stage==='answer'){
   const selected=ids.map(id=>saved.get(id));
   if(selected.some(a=>!a))throw Error('선택 질문의 검색 결과가 저장된 실행을 선택하세요.');
   const keys=['route','summary_mode','excerpt_only','event_graph_mode','retrieval_strategy','all_candidates','top_k','method','structure_version','query_prompt','chunk_search_mode','attention_candidate_limit','attention_max_calls'];
   const first=selected[0];
   frozenFingerprint=first.dataset_fingerprint;
   if(selected.some(a=>a.dataset_fingerprint!==first.dataset_fingerprint||keys.some(key=>a.config[key]!==first.config[key])))
    throw Error('같은 검색 구성에서 저장한 결과를 선택하세요.');
   searchConfig={...input,...Object.fromEntries(keys.map(key=>[key,first.config[key]]))};
  }
  if(stage==='retrieve'||stage==='extract')searchConfig={...searchConfig,answer_pipeline:undefined};
  const config=this.config(searchConfig),dataset=await this.dataset(config.dataset);
  if(frozenFingerprint&&frozenFingerprint!==dataset.fingerprint)throw Error('현재 데이터셋에서 저장한 검색 결과를 선택하세요.');
  if(!Array.isArray(ids)||!ids.length||new Set(ids).size!==ids.length||ids.some(id=>!dataset.d.questions.questions.some(q=>q.id===id)))throw Error('실행할 질문 ID가 올바르지 않습니다.');
  if(config.dataset_profile&&config.dataset_profile!=='all'&&ids.some(id=>dataset.d.questions.questions.find(q=>q.id===id).profile!==config.dataset_profile))throw Error('선택 프로필 밖의 질문은 실행할 수 없습니다.');
  if(isFull(config.route)&&stage==='extract')throw Error('R0-Full은 구조화를 수행하지 않습니다. 전체 실행 또는 원문 제공·답변 단계를 선택하세요.');
  validateDialogueSelection(dataset.d,ids,stage);
  const run={id:'RUN-'+Date.now()+'-'+crypto.randomBytes(3).toString('hex'),kind:'actual_local_baseline',created_at:new Date().toISOString(),status:'QUEUED',stage,config,question_ids:ids,dataset_fingerprint:dataset.fingerprint,config_hash:hash(config),runtime_version:this.runtime.version,model_hash:registry.find(m=>m.id===config.model).sha256,embedding_hash:registry.find(m=>m.role==='embedding').sha256,results:[],progress:'사용자 실행 요청 접수',input_artifacts:artifacts,limitations:['의미 정답은 작성자 초안: 사람 검토 필요','합성 fixture 범위의 상태·owner 필터 검사; 실제 제품의 인증·동의·캐시 통합 검증을 대체하지 않음'],deleted_at:null};
  if(stage==='answer')run.frozen_retrieval_artifacts=Object.fromEntries([...saved].map(([question,a])=>[question,a.id]));
  if(['pma-long-v1.0.1','pma-long-v2.0.0','pma-context-v1.0.0','pma-memory-v2.0.0','pma-memory-v3.0.0','pma-generalization-v1.0.0'].includes(config.dataset))run.limitations.push(...dataset.d.manifest.limits);
  this.store.putRun(run);this.busy=run.id;this.abort=new AbortController();setImmediate(()=>this.execute(run,dataset).catch(e=>{run.status=this.abort?.signal.aborted?'CANCELLED':'ERROR';run.error=e.message;run.error_details=diagnostics.failure(e,{context:{run_id:run.id,stage:run.error_stage||'runtime',route:run.config.route}},{logDir:path.join(this.root,'.local/baseline/runtime')});run.finished_at=new Date().toISOString();this.update(run,e.message,{stage:'finished'});}).finally(()=>{this.busy=null;this.abort=null;}));return run;
 }
 update(run,message,detail={}){
  const at=new Date().toISOString(),previous=run.progress_detail||{};
  const available=require('node:os').freemem(),rss=process.memoryUsage().rss;run.resources??={measurement:'event-sampled-system-available-ram-and-web-rss-v1',min_available_ram_bytes:available,peak_web_rss_bytes:rss,samples:0};run.resources.min_available_ram_bytes=Math.min(run.resources.min_available_ram_bytes,available);run.resources.peak_web_rss_bytes=Math.max(run.resources.peak_web_rss_bytes,rss);run.resources.samples++;
  const changed=detail.stage&&detail.stage!==previous.stage;
  run.progress=message;run.progress_detail={...(changed?{}:previous),...detail,question_id:run.active_result?.question_id||detail.question_id||previous.question_id||null,question_index:run.active_question_index??null,processed:run.results.length,total:run.question_ids.length,phase_started_at:changed?at:(previous.phase_started_at||at),updated_at:at};
  run.events=[...(run.events||[]),{at,message,...run.progress_detail}].slice(-150);if(!run.transient)this.store.putRun(run);
 }
 markStage(run,result,stage,status){
  diagnostics.setContext({stage});usage.set({stage:stage==='extraction'?'summary':stage==='retrieval'?'retrieval':'answer',question_id:result.question_id,source_id:null});
  this.stageClocks??=new WeakMap();let clocks=this.stageClocks.get(result);if(!clocks){clocks=new Map();this.stageClocks.set(result,clocks);}
  const at=new Date().toISOString(),output=result.stages?.[stage],reused=status==='REUSED'||!!output?.reused;
  result.stage_timings??={};
  if(status==='RUNNING'){clocks.set(stage,performance.now());result.stage_timings[stage]={started_at:at,status:'RUNNING'};}
  else{const prior=result.stage_timings[stage]||{},start=clocks.get(stage);result.stage_timings[stage]={...prior,finished_at:at,status:reused?'REUSED':status,reused,elapsed_ms:Number.isFinite(start)?Math.max(0,performance.now()-start):null,...(reused&&Number.isFinite(output?.elapsed_ms)?{original_elapsed_ms:output.elapsed_ms}:{})};clocks.delete(stage);}
  const state=reused?'REUSED':status;result.stage_progress={...(result.stage_progress||{}),[stage]:state};this.update(run,result.question_id+' · '+{extraction:isChunkRoute(run.config.route)?'구간 색인':['M0','M1',eventGraph.ROUTE,multiAnchor.ROUTE].includes(run.config.route)?'요약':'구조화',retrieval:'검색',answer:'답변'}[stage]+' · '+state,{stage});
 }
 async execute(run,ds){return usage.track(this,run,()=>this.executeScoped(run,ds));}
 async executeScoped(run,ds){
  const signal=this.abort.signal,c=run.config;run.status='RUNNING';this.update(run,'실행 환경 준비',{stage:'runtime'});
  if(isFull(c.route)&&this.runtime.stop)await this.runtime.stop('embedding');
  if((['retrieve','end_to_end'].includes(run.stage)||['M0','M1',eventGraph.ROUTE,multiAnchor.ROUTE].includes(c.route)&&run.stage==='extract')&&!isFull(c.route)&&!isChunkRoute(c.route))await this.runtime.ensure('embedding',c.embedding_model,signal);
  if((run.stage!=='retrieve'||isFull(c.route)||c.route===questionAttention.ROUTE||c.retrieval_strategy===compoundSearch.MODE||c.event_graph_mode===LINKED_GRAPH_MODE)&&
   !(isChunkRoute(c.route)&&(run.stage==='extract'||c.route===rawChunkSearch.ROUTE&&run.stage==='retrieve')))await this.runtime.ensure('generation',c.model,signal);
  run.runtime_snapshot=this.runtime.status();this.store.putRun(run);
  const extractionCache=new Map();
  const preparedSummaries=isChunkRoute(c.route)&&['extract','end_to_end'].includes(run.stage)
   ?await usage.withStage('indexing',()=>this.rawChunks.prepareBatch(run,ds,signal))
   :['M0','M1',eventGraph.ROUTE,multiAnchor.ROUTE].includes(c.route)&&['extract','end_to_end'].includes(run.stage)?await diagnostics.withContext({run_id:run.id,question_id:null,route:c.route,stage:'summary_prepare'},()=>prepareSummaryBatch(this,run,ds,signal)):null;
  for(const [i,id]of run.question_ids.entries()){
   if(signal.aborted)break;const q=ds.d.questions.questions.find(q=>q.id===id),original=ds.d.contexts.contexts.find(x=>x.id===q.context_id),state=ds.lib.materialize(original,ds.d.sources.records),context={...original,conversation:['M0','M1',eventGraph.ROUTE,multiAnchor.ROUTE].includes(c.route)?[]:safeConversation(original,state.accessible)};
   const result={question_id:q.id,context_id:context.id,question:q.text,status:'RUNNING',started_at:new Date().toISOString(),stages:{},fixture_trace:state.trace,accessible_source_ids:state.accessible.map(s=>s.id),unobserved_system_assertions:context.required_observations.filter(x=>/cache|consent|persistent|new_session|restore_index|server_authorization/.test(x)),corpus_warning:!isFull(c.route)&&!c.all_candidates&&state.accessible.length<=c.top_k?'검색 가능한 원문 수가 Top-K 이하입니다. 검색 재현율로 순위 성능을 판단하지 마세요.':null};
   run.active_result=result;run.active_question_index=i+1;result.stage_progress={extraction:(run.stage==='end_to_end'&&isRaw(c.route))?'SKIPPED':'NOT_RUN',retrieval:'NOT_RUN',answer:'NOT_RUN'};this.update(run,`${i+1}/${run.question_ids.length} ${q.id} 준비`,{stage:'prepare'});
   try{await diagnostics.withContext({run_id:run.id,question_id:q.id,route:c.route,stage:'prepare'},async()=>{
    if(['M0','M1',eventGraph.ROUTE,multiAnchor.ROUTE].includes(c.route)){result.dialogue_trace=applySummaryDialogue(context,run,state.accessible);if(context.dialogue){result.dialogue_id=context.dialogue.id;result.dialogue_turn=context.dialogue.turn;}}else if(context.dialogue){result.dialogue_id=context.dialogue.id;result.dialogue_turn=context.dialogue.turn;result.dialogue_trace=applyDialogue(context,run,state.accessible);}
    let extraction=null,retrieval=null;
    if(run.stage==='extract'||(run.stage==='end_to_end'&&!isRaw(c.route))){
     if(preparedSummaries){
      extraction=preparedSummaries.get(context.id);if(!extraction)throw Error('전체 사전 색인에서 준비하지 않은 기억 범위입니다.');
      this.checkSourceScope(extraction,context,state.accessible);
      if(isChunkRoute(c.route))this.rawChunks.indexes(extraction,state.accessible);else this.summary.validate(extraction.records,state.accessible);
      result.stages.extraction={...extraction,reused:true,reuse_reason:isChunkRoute(c.route)?'chunk_keyword_batch':'summary_batch'};this.markStage(run,result,'extraction','REUSED');
     }else{this.markStage(run,result,'extraction','RUNNING');if(extractionCache.has(context.id))extraction={...extractionCache.get(context.id),reused:true,reuse_reason:'context_cache'};else{extraction=await this.extract(run,ds,context,state.accessible,signal);extractionCache.set(context.id,extraction);}result.stages.extraction=extraction;this.markStage(run,result,'extraction','COMPLETED');}
    }else if(run.stage==='retrieve'&&!isRaw(c.route)){
     extraction=this.findArtifact(run,'extraction',context.id,null,ds.fingerprint);this.checkSourceScope(extraction,context,state.accessible);result.stages.extraction={artifact_id:extraction.artifact_id,reused:true,elapsed_ms:extraction.elapsed_ms};this.markStage(run,result,'extraction','REUSED');
    }
    if(['retrieve','end_to_end'].includes(run.stage)){this.markStage(run,result,'retrieval','RUNNING');retrieval=await this.retrieve(run,ds,q,context,state.accessible,extraction,signal);result.stages.retrieval=retrieval;this.markStage(run,result,'retrieval','COMPLETED');}
    else if(run.stage==='answer'){retrieval=this.findArtifact(run,'retrieval',context.id,q.id,ds.fingerprint);this.checkSourceScope(retrieval,context,state.accessible);result.stages.retrieval={artifact_id:retrieval.artifact_id,reused:true,elapsed_ms:retrieval.elapsed_ms};this.markStage(run,result,'retrieval','REUSED');}
    if(['answer','end_to_end'].includes(run.stage)){this.markStage(run,result,'answer','RUNNING');result.stages.answer=await this.answer(run,ds,q,context,retrieval,signal);this.markStage(run,result,'answer','COMPLETED');}
    result.status='PENDING_REVIEW';result.review_reason='실제 실행 완료. 의미 정확도와 응답 행동은 사람 판정 필요.';
    const citation=result.stages.answer?.assessment?.axes?.citation;if(citation?.status==='FAIL')result.review_reason='인용 오류 있음 · 답변 의미는 미판정. 분리 판정에서 각각 확인하세요.';
   });}catch(e){result.error_details=diagnostics.failure(e,{context:{run_id:run.id,question_id:q.id,route:c.route,stage:Object.keys(result.stage_progress).find(key=>result.stage_progress[key]==='RUNNING')||'runtime'}},{logDir:path.join(this.root,'.local/baseline/runtime')});result.status=signal.aborted?'CANCELLED':e.blocked?'BLOCKED':e.not_applicable?'NOT_APPLICABLE':e.validation_failed?'VALIDATION_FAILED':'ERROR';if(e.token_budget)result.token_budget=e.token_budget;if(e.attention_trace)result.attention_trace=e.attention_trace;if(e.full_delivery)result.stages.retrieval=e.full_delivery;result.error=e.message;result.error_code=e.code||errorCode(e.message);result.error_stage=Object.keys(result.stage_progress).find(key=>result.stage_progress[key]==='RUNNING')||'runtime';for(const key of Object.keys(result.stage_progress))if(result.stage_progress[key]==='RUNNING')this.markStage(run,result,key,result.status);if(e.raw)result.raw_error_output=e.raw;if(e.extraction)result.stages.extraction=e.extraction;if(e.evidence_interpretation){result.evidence_interpretation=e.evidence_interpretation;result.evidence_interpretation.artifact_id=this.store.artifact('evidence-interpretation',e.evidence_interpretation);}for(const next of ['retrieval','answer'])if(result.stage_progress[next]==='NOT_RUN'&&['end_to_end','retrieve','answer'].includes(run.stage))result.stage_progress[next]='BLOCKED';}
   result.finished_at=new Date().toISOString();run.results.push(result);run.dialogue_summaries=dialogueSummaries(ds.d,run.results);run.active_result=null;this.update(run,q.id+' 처리 완료 · '+result.status,{stage:'question_finished'});
  }
  run.status=signal.aborted?'CANCELLED':run.results.some(r=>['ERROR','VALIDATION_FAILED'].includes(r.status))?'COMPLETED_WITH_ERRORS':'COMPLETED';run.finished_at=new Date().toISOString();run.active_result=null;this.update(run,signal.aborted?'사용자 요청으로 중단':'실행 종료 · 의미 판정은 검토 대기',{stage:'finished'});
 }
 checkSourceScope(a,c,sources){if(a.context_id!==c.id)throw Error('산출물 context 불일치');const available=new Set(sources.map(s=>s.id+':'+s.revision));for(const s of a.source_refs||[])if(!available.has(s.source_id+':'+s.revision))throw Error('다른 사용자·삭제·구버전 원문 산출물은 재사용할 수 없습니다.');const exact=sources.map(s=>s.id+':'+s.revision).sort().join('|'),saved=(a.source_refs||[]).map(s=>s.source_id+':'+s.revision).sort().join('|');if(exact!==saved)throw Error('산출물의 기억 범위가 현재 context와 다릅니다.');}
 findArtifact(run,type,contextId,questionId,fingerprint){const ids=type==='retrieval'&&run.frozen_retrieval_artifacts?[run.frozen_retrieval_artifacts[questionId]]:run.input_artifacts;for(const id of ids){const a=this.store.readArtifact(id);if(a.type===type&&a.context_id===contextId&&(!questionId||a.question_id===questionId)&&a.dataset_fingerprint===fingerprint){if((['M0','M1',eventGraph.ROUTE,multiAnchor.ROUTE].includes(run.config.route))!==(a.kind===summary.VERSION))throw Error('요약과 원문·구조화 산출물은 서로 재사용할 수 없습니다.');if(['M0','M1',eventGraph.ROUTE,multiAnchor.ROUTE].includes(run.config.route)&&a.config?.route!==run.config.route&&!(type==='extraction'&&(run.config.route===eventGraph.ROUTE&&a.config?.route==='M1'&&Array.isArray(a.structured_indexes)||multiAnchor.compatibleExtraction(run.config,a))))throw Error('같은 검색 경로의 산출물을 선택하세요.');if(['M1',eventGraph.ROUTE,multiAnchor.ROUTE].includes(run.config.route)&&(a.config?.summary_mode||'generated')!==(run.config.summary_mode||'generated'))throw Error('같은 기억 방식에서 만든 산출물을 선택하세요.');if(type==='retrieval'&&a.config?.route!==run.config.route)throw Error('저장된 검색 경로가 실행 설정과 다릅니다.');if(type==='retrieval'&&a.config?.event_graph_mode!==run.config.event_graph_mode)throw Error('같은 G1 방식으로 저장한 검색 결과를 선택하세요.');if(type==='retrieval'&&!!a.config?.excerpt_only!==!!run.config.excerpt_only)throw Error('같은 검색 방식에서 만든 검색 결과를 선택하세요.');if(isChunkRoute(run.config.route)&&a.kind!==rawChunkSearch.VERSION)throw Error('원문 구간 키워드 산출물을 선택하세요.');return {...a,artifact_id:id};}}throw Error(`${contextId} ${questionId||''}: 재사용할 ${type} 산출물을 실행 기록에서 선택하세요.`);}
 async extract(run,ds,context,sources,signal){
  if(isChunkRoute(run.config.route))return this.rawChunks.extraction(run,ds,context,sources,signal);
  if(['M0','M1',eventGraph.ROUTE,multiAnchor.ROUTE].includes(run.config.route))return this.summary.extract(run,ds,context,sources,signal);
  const c=run.config,records=[];const start=performance.now();
  const save=state=>{const data={context_id:context.id,dataset_fingerprint:ds.fingerprint,config:c,source_refs:sources.map(s=>({source_id:s.id,revision:s.revision})),records,elapsed_ms:performance.now()-start,semantic_status:'PENDING_REVIEW',extraction_state:state};const id=this.store.artifact('extraction',data);return {...data,artifact_id:id};};
  for(const [i,source]of sources.entries()){
   this.update(run,`${context.id} 구조화 ${i+1}/${sources.length} · ${source.id}`,{stage:'extraction',unit_done:i,unit_total:sources.length,unit_label:'원문',source_id:source.id});
   const messages=prompts.extractMessages(c,source,sentences(source.text));let recorded=false,response;
   try{
    response=await this.runtime.chat(messages,prompts.schemas[c.method],{...c,output_tokens:c.extraction_output_tokens},signal);
    const validated=validateNative(c.method,response.parsed,source);records.push({...validated,request_messages:messages,response,source_snapshot:{id:source.id,revision:source.revision,text:source.text,metadata:source.metadata,gold:source.gold},checks:extractionChecks(validated)});recorded=true;
    if(!validated.valid)throw Object.assign(Error('원문 근거/구조화 검증 실패: '+validated.errors.join('; ')),{raw:response.raw,validation_failed:true,code:errorCode(validated.errors.join('; '))});
   }catch(e){
    if(!recorded){let native=response?.parsed;try{native??=JSON.parse(e.raw);}catch{}records.push({source_id:source.id,revision:source.revision,text:source.text,native,units:[],error:e.message,cancelled:!!signal?.aborted,error_code:signal?.aborted?'EXEC.CONTROL':errorCode(e.message),raw_error_output:response?.raw||e.raw||'',source_snapshot:{id:source.id,revision:source.revision,text:source.text,metadata:source.metadata,gold:source.gold},request_messages:messages,checks:[{code:signal?.aborted?'EXEC.CONTROL':errorCode(e.message),label:signal?.aborted?'사용자 실행 중단':'구조화 실행·출력 오류',status:signal?.aborted?'CANCELLED':'ERROR',detail:e.message}]});}
    try{e.extraction=save(signal?.aborted?'CANCELLED':e.validation_failed?'VALIDATION_FAILED':'ERROR');}catch(storageError){e.extraction={context_id:context.id,config:c,records,extraction_state:'ERROR',preservation_error:storageError.message};}
    throw e;
   }
  }
  return save('COMPLETED');
 }
 async vector(text,query,signal){const m=registry.find(m=>m.role==='embedding'),key=hash({sha256:m.sha256,profile:'qwen-instruct-en-last-eos-v1',query,text});let v=this.store.vector(key);if(v){usage.cache('embedding',m.id);return {vector:v,cached:true};}v=await this.runtime.embed(text,query,signal);this.store.putVector(key,v);return {vector:v,cached:false};}
 lexical(items,text){
  if(!items.length)return [];const db=new DatabaseSync(':memory:');try{
   db.exec("CREATE VIRTUAL TABLE docs USING fts5(id UNINDEXED, text, tokenize='trigram')");const insert=db.prepare('INSERT INTO docs VALUES(?,?)');for(const item of items)insert.run(item.id,item.text);
   const terms=[...new Set(text.match(/[\p{L}\p{N}_:+./?=*-]+/gu)||[])].slice(0,40),long=terms.filter(t=>[...t].length>=3),short=terms.filter(t=>[...t].length<3);let matches=[];
   if(long.length){const match=long.map(t=>'"'+t.replaceAll('"','""')+'"').join(' OR ');matches=db.prepare('SELECT id,bm25(docs) score FROM docs WHERE docs MATCH ? ORDER BY score LIMIT 1000').all(match);}
   const found=new Map(matches.map(m=>[m.id,{id:m.id,bm25_score:m.score,exact_terms:0}]));
   for(const item of items){const n=short.filter(t=>item.text.toLocaleLowerCase().includes(t.toLocaleLowerCase())).length;if(n){const old=found.get(item.id)||{id:item.id,bm25_score:0,exact_terms:0};old.exact_terms=n;found.set(item.id,old);}}
   return [...found.values()].sort((a,b)=>b.exact_terms-a.exact_terms||a.bm25_score-b.bm25_score||a.id.localeCompare(b.id));
  }finally{db.close();}
 }
 async fullOriginals(run,ds,q,context,sources,signal){
  const c=run.config,start=performance.now(),evidence=fullEvidence(sources);
  this.update(run,q.id+' 원문 전체 제공 · 토큰 예산 확인',{stage:'full_prepare',unit_total:sources.length,unit_label:'원문'});
  const budget=await fullBudget(this.runtime,c,q,context,evidence,signal);
  const delivery={version:FULL_VERSION,search_performed:false,status:budget.eligible?'ELIGIBLE':'BUDGET_EXCEEDED',candidate_sources:sources.length,candidate_characters:sources.reduce((n,s)=>n+s.text.length,0),planned_spans:evidence.map(e=>({source_id:e.source_id,revision:e.revision,start:e.start,end:e.end})),budget};
  const data={context_id:context.id,question_id:q.id,dataset_fingerprint:ds.fingerprint,source_refs:sources.map(s=>({source_id:s.id,revision:s.revision})),source_snapshots:sources.map(s=>({id:s.id,revision:s.revision,text:s.text})),config:c,query_original:q.text,query_used:q.text,delivery,extraction_artifact_id:null,index_units:[],lexical_candidates:[],vector_candidates:[],fused_candidates:[],ranked_sources:[],selected_sources:budget.eligible?sources.map(s=>({source_id:s.id,revision:s.revision})):[],evidence:budget.eligible?evidence:[],cache_hits:0,elapsed_ms:performance.now()-start,metrics:{required_groups:null,source_groups_found:null,span_groups_fully_covered:null,source_group_recall:null,first_relevant_source_rank:null,mrr:null,search_performed:false,scope:'검색 생략: 전체 원문 제공. 검색 순위·Recall 지표 해당 없음.'},warning:budget.eligible?'검색 없이 접근 가능한 원문 전체를 제공하는 기준선입니다. 검색 성능 평가가 아닙니다.':'전체 제공 예산 초과 · 답변 미생성 · 짝 비교에서 별도 제외'};
  const artifact_id=this.store.artifact('retrieval',data),artifact={...data,artifact_id};
  return artifact;
 }
 async retrieve(run,ds,q,context,sources,extraction,signal){
  if(run.config.retrieval_strategy===compoundSearch.MODE)
   return compoundSearch.retrieve(this,run,ds,q,context,sources,signal,
    sub=>this.retrieveSingle(run,ds,sub,context,sources,extraction,signal,false));
  return this.retrieveSingle(run,ds,q,context,sources,extraction,signal);
 }
 async retrieveSingle(run,ds,q,context,sources,extraction,signal,persist=true){
  if(run.config.route===questionAttention.ROUTE)return this.attention.retrieve(run,ds,q,context,sources,extraction,signal,persist);
  if(isChunkRoute(run.config.route))return this.rawChunks.retrieve(run,ds,q,context,sources,extraction,signal,persist);
  if(['M1',eventGraph.ROUTE,multiAnchor.ROUTE].includes(run.config.route))return require('./structured-retrieve.cjs').retrieve(this,run,ds,q,context,sources,extraction,signal,persist);
  if(isFull(run.config.route)){
   const artifact=await this.fullOriginals(run,ds,q,context,sources,signal);
   if(!artifact.delivery.budget.eligible&&!run.config.answer_pipeline)throw budgetError(artifact.delivery.budget,artifact);
   return artifact;
  }
  const c=run.config,start=performance.now(),items=[];
  if(['M0','M1',eventGraph.ROUTE,multiAnchor.ROUTE].includes(c.route))items.push(...this.summary.units(extraction,sources));
  if(!['S0','M0','M1'].includes(c.route))for(const s of sources)for(const chunk of chunks(s))items.push({...chunk,origin:'raw'});
  if(!['R0','M0','M1'].includes(c.route)){
   if(!extraction)throw Error('구조화 검색에는 추출 산출물이 필요합니다.');
   if(extraction.extraction_state&&extraction.extraction_state!=='COMPLETED'||!Array.isArray(extraction.records)||extraction.records.length!==sources.length||extraction.records.some(r=>r.valid!==true||r.error))throw Error('검증 실패·부분 구조화 산출물은 검토 전용이며 검색에 재사용할 수 없습니다.');
   for(const r of extraction.records||[])for(const u of r.units||[])if(!u.validation_errors.length)items.push({id:r.source_id+':'+u.id,source_id:r.source_id,revision:r.revision,start:Math.min(...u.evidence.map(e=>e.start)),end:Math.max(...u.evidence.map(e=>e.end)),text:unitText(u),origin:'structured',unit_id:u.id});
  }
  const unstructuredSources=[];
  if(c.all_candidates&&c.route==='S0'){
   const indexed=new Set(items.map(item=>item.source_id));
   for(const source of sources){
    if(indexed.has(source.id))continue;
    unstructuredSources.push(source.id);
    items.push(...chunks(source).map(chunk=>({...chunk,origin:'raw'})));
   }
  }
  const query=['M0','M1',eventGraph.ROUTE,multiAnchor.ROUTE].includes(c.route)?q.text:queryText(q,context,c.query_prompt);this.update(run,q.id+' 키워드 검색 · '+items.length+'개 단위',{stage:'lexical',unit_total:items.length});
  const lexical=this.lexical(items,query).slice(0,c.candidate_k),vector=[];let cacheHits=0;
  if(items.length){this.update(run,q.id+' 질문 임베딩 생성',{stage:'query_embedding'});const qv=await this.vector(query,true,signal);for(const [i,item]of items.entries()){if(signal.aborted)throw Error('실행 취소');this.update(run,`${q.id} 의미 검색 · 임베딩 ${i+1}/${items.length}`,{stage:'document_embedding',unit_done:i,unit_total:items.length,unit_label:'검색 단위'});const v=await this.vector(item.text,false,signal);if(v.cached)cacheHits++;vector.push({id:item.id,cosine:cosine(qv.vector,v.vector)});}vector.sort((a,b)=>b.cosine-a.cosine||a.id.localeCompare(b.id));}
  this.update(run,q.id+' 검색 순위 결합',{stage:'fusion',unit_done:items.length,unit_total:items.length,unit_label:'검색 단위'});
  const vectorCandidates=c.all_candidates?vector:vector.slice(0,c.candidate_k);
  const itemById=new Map(items.map(item=>[item.id,item]));
  const fused=rrf([lexical,vectorCandidates]).map((hit,i)=>({...itemById.get(hit.id),...hit,rank:i+1}));
  const rankedSources=[],hitsBySource=new Map();
  for(const item of fused){
   if(!hitsBySource.has(item.source_id)){
    rankedSources.push({source_id:item.source_id,revision:item.revision,rank:rankedSources.length+1,first_unit_rank:item.rank});
    hitsBySource.set(item.source_id,[]);
   }
   hitsBySource.get(item.source_id).push(item);
  }
  const selectedSources=c.all_candidates?rankedSources:rankedSources.slice(0,c.top_k),evidence=[];
  const summaryOnly=c.route==='M0',sourcesById=new Map(sources.map(source=>[source.id,source]));
  let chars=0;
  for(const ranked of selectedSources){
   const source=sourcesById.get(ranked.source_id),hits=hitsBySource.get(ranked.source_id);
   const sourceSentences=!summaryOnly&&!c.all_candidates?sentences(source.text):[];
   const added=[];
   for(const hit of c.all_candidates?hits:hits.slice(0,2)){
    let spans=[hit];
    if(!summaryOnly&&c.all_candidates&&hit.end-hit.start>1000){
     spans=chunks({...source,text:source.text.slice(hit.start,hit.end)}).map(part=>({start:hit.start+part.start,end:hit.start+part.end}));
    }else if(!summaryOnly&&!c.all_candidates){
     const inside=sourceSentences.filter(s=>s.end>hit.start&&s.start<hit.end);
     const start=inside.length?inside[0].start:hit.start,end=inside.length?inside.at(-1).end:hit.end;
     spans=[{start,end:Math.min(end,start+1000)}];
    }
    for(const {start,end} of spans){
     if(!summaryOnly&&added.some(span=>span.start<=start&&span.end>=end))continue;
     const text=summaryOnly?hit.text:source.text.slice(start,end);
     if(!c.all_candidates&&chars+text.length>c.evidence_char_budget)continue;
     chars+=text.length;
     added.push({start,end});
     evidence.push({evidence_id:'E'+(evidence.length+1),source_id:hit.source_id,revision:hit.revision,start,end,text,
      ...(summaryOnly?{origin:'summary',summary_id:hit.summary_id}:{origin:hit.origin,metadata:source.metadata}),unit_id:hit.id});
    }
   }
  }
  const data={context_id:context.id,question_id:q.id,dataset_fingerprint:ds.fingerprint,source_refs:sources.map(s=>({source_id:s.id,revision:s.revision})),query_original:q.text,query_used:query,...(['M0','M1',eventGraph.ROUTE,multiAnchor.ROUTE].includes(c.route)?{kind:summary.VERSION,summary_records:extraction.records,source_snapshots:[]}:{source_snapshots:sources.map(s=>({id:s.id,revision:s.revision,text:s.text}))}),config:c,extraction_artifact_id:extraction?.artifact_id||null,index_units:items,lexical_candidates:lexical,vector_candidates:vectorCandidates,fused_candidates:fused,ranked_sources:rankedSources,selected_sources:selectedSources,evidence,cache_hits:cacheHits,elapsed_ms:performance.now()-start,metrics:this.retrievalMetrics(ds.d,q,rankedSources,evidence),...(unstructuredSources.length?{unstructured_source_fallback:unstructuredSources}:{}),warning:c.all_candidates?'접근 가능한 전체 출처의 검색 후보를 조회했습니다.':sources.length<=c.top_k?'원문 수가 Top-K 이하: 재현율은 순위 성능의 증거가 아닙니다.':null};if(['M0','M1',eventGraph.ROUTE,multiAnchor.ROUTE].includes(c.route)){data.metrics.span_groups_fully_covered=null;data.metrics.scope='요약 출처 존재만 측정. 원본 구간 포함은 해당 없음; 요약 의미 보존은 사람 검토 필요.';this.summary.assertRetrieval(data,sources);}return persist?{...data,artifact_id:this.store.artifact('retrieval',data)}:data;
 }
 retrievalMetrics(d,q,ranked,evidence){const facts=new Map(d.sources.records.flatMap(s=>s.gold.facts.map(f=>[f.id,{...f,source_id:s.id}]))),groups=q.gold.evidence_groups,sourceCovered=groups.map(g=>g.any_of_fact_ids.some(id=>evidence.some(e=>e.source_id===facts.get(id).source_id))),spanCovered=groups.map(g=>g.any_of_fact_ids.some(id=>facts.get(id).evidence.every(gold=>evidence.some(e=>e.source_id===gold.source_id&&e.start<=gold.start&&e.end>=gold.end))));const relevant=new Set(groups.flatMap(g=>g.any_of_fact_ids.map(id=>facts.get(id).source_id))),first=ranked.find(s=>relevant.has(s.source_id));return {required_groups:groups.length,source_groups_found:sourceCovered.filter(Boolean).length,span_groups_fully_covered:spanCovered.filter(Boolean).length,source_group_recall:groups.length?sourceCovered.filter(Boolean).length/groups.length:null,first_relevant_source_rank:first?.rank||null,mrr:groups.length?(first?1/first.rank:0):null,scope:'Gold source/span presence only; not semantic answer correctness. Unjudged sources are not automatically negatives.'};}
 async answer(run,ds,q,context,retrieval,signal){
  const c=run.config,start=performance.now(),used=[...retrieval.evidence],omitted=[];
  const chronological=c.answer_pipeline===chronologicalAnswer.MODE,digest=c.answer_pipeline===questionDigest.MODE;
  const timelineAnswer=chronological||digest,arithmetic=arithmeticTask(q.text);
  const interpreted=evidenceInterpreter.MODES.includes(c.answer_pipeline)&&!arithmetic;
  const summaryRoute=['M0','M1',eventGraph.ROUTE,multiAnchor.ROUTE].includes(c.route),full=isFull(c.route);
  const scoped=c.answer_pipeline===scopedAnswer.MODE&&!arithmetic;
  const accessible=summaryRoute||timelineAnswer||full||isChunkRoute(c.route)?ds.lib.materialize(
   ds.d.contexts.contexts.find(x=>x.id===context.id),ds.d.sources.records).accessible:[];
  let timeline=[],scopedPlan;
  if(c.route===questionAttention.ROUTE)questionAttention.assertRetrieval(this,retrieval,accessible);
  else if(isChunkRoute(c.route))this.rawChunks.assertRetrieval(retrieval,accessible);
  if(full){
   const pool=assertFullEvidence(retrieval,accessible,!!c.answer_pipeline);
   used.splice(0,used.length,...(!arithmetic&&(scoped||digest||interpreted)?fullReviewEvidence(pool):pool));
  }
  if(summaryRoute){
   this.summary.assertRetrieval(retrieval,accessible);
   if(['M1',eventGraph.ROUTE,multiAnchor.ROUTE].includes(c.route)){
    if(!retrieval.config.excerpt_only)this.structured.indexes({records:retrieval.summary_records,structured_indexes:retrieval.structured_indexes,structured_version:retrieval.structured_version},accessible);
    if(!timelineAnswer)context.summary_topic_groups=Object.fromEntries(accessible.map(s=>[s.id,hash({owner:s.metadata.owner_id,title:s.metadata.title||s.id}).slice(0,16)]));
   }
  }else if(retrieval.kind===summary.VERSION)throw Error('요약 답변에는 M0 요약 경로를 선택하세요.');
  if(retrieval.compound_search?.status==='DECOMPOSED')context.compound_parts=retrieval.compound_search.parts.map(part=>part.focus);
  let evidenceFocus,eventScope;
  if(c.event_graph_mode===LINKED_GRAPH_MODE&&!arithmetic&&!interpreted){
   const groups=retrieval.event_graph_search?.unit_graph_ids;
   if(!groups||used.some(item=>!Object.hasOwn(groups,item.unit_id)))throw Error('사건 연결 방식의 검색 결과와 근거 연결을 확인할 수 없습니다.');
   context.event_unit_groups=groups;
   this.update(run,q.id+' · 다른 사건의 근거 확인',{stage:'answer',evidence_count:used.length});
   const filtered=await filterEventEvidence(this,q,context,used,c,signal);
   used.splice(0,used.length,...filtered.evidence);
   eventScope=filtered.trace;
  }
  if(arithmetic)used.length=0;
  else if(timelineAnswer){
   const {ordered,input}=chronologicalAnswer.chronologicalEvidence(used,accessible);
   used.splice(0,used.length,...ordered);timeline=input;
  }
  else if(scoped){
   this.update(run,q.id+' · 질문 범위와 후보 근거 대조',{stage:'answer',evidence_count:used.length});
   scopedPlan=await scopedAnswer.planQuestion(this.runtime,q,context,c,signal);
   const focused=await scopedAnswer.selectEvidence(this.runtime,q,scopedPlan,used,c,signal);
   used.splice(0,used.length,...focused.evidence);
   evidenceFocus=focused.trace;
  }
  else if(!interpreted&&(['M1',eventGraph.ROUTE,multiAnchor.ROUTE].includes(c.route)||retrieval.config.all_candidates===true&&c.route!==questionAttention.ROUTE)){
   const allCandidates=retrieval.config.all_candidates===true;
   if(allCandidates)this.update(run,q.id+' · 검색 후보 전체 검토',{stage:'answer',evidence_count:used.length});
   const select=allCandidates?focusAllEvidence:focusEvidence;
   const focused=await select(this,q,context,used,c,signal);
   const selected=compoundSearch.prioritizeBranches(retrieval.compound_search,focused.evidence);
   used.splice(0,used.length,...selected);
   evidenceFocus=focused.trace;
  }
  let tokenBudget,attentionPacking;
  if(c.route===questionAttention.ROUTE&&!arithmetic&&!interpreted){
   const packed=await usage.withStage('evidence_packing',()=>questionAttention.packEvidence(this.runtime,q,context,used,retrieval,c,signal),{question_id:q.id});
   used.splice(0,used.length,...packed.evidence);attentionPacking=packed.trace;
   if(timelineAnswer){const ordered=chronologicalAnswer.chronologicalEvidence(used,accessible);used.splice(0,used.length,...ordered.ordered);timeline=ordered.input;}
  }
  if(full&&!c.answer_pipeline){
   tokenBudget=await fullBudget(this.runtime,c,q,context,used,signal);if(!tokenBudget.eligible)throw budgetError(tokenBudget);
  }else if(!timelineAnswer&&!interpreted&&c.route!==questionAttention.ROUTE)while(used.length&&await this.runtime.tokenize(JSON.stringify(used),signal)>c.answer_evidence_tokens)omitted.push(used.pop());
  let calculation=timelineAnswer||interpreted?null:moneyProof(q.text,used);
  if(calculation&&context.event_unit_groups){
   const groupFor=id=>context.event_unit_groups[used.find(item=>item.evidence_id===id)?.unit_id];
   if(groupFor(calculation.total.evidence_id)!==groupFor(calculation.already_paid.evidence_id))calculation=null;
  }
  let digestPlan,digestTrace;
  if(digest){
   const output=await questionDigest.digest(this.runtime,q,context,used,timeline,c,signal,(done,total)=>
    this.update(run,q.id+' · 질문별 핵심 요약 '+done+'/'+total,{stage:'answer',evidence_count:total}));
   used.splice(0,used.length,...output.used);
   digestPlan=output.plan;digestTrace=output.trace;
  }
  this.update(run,q.id+' 근거 기반 답변 생성 중',{stage:'answer',evidence_count:used.length});
  let messages,response,answerAudit,scopedResponse,interpretationTrace;
  if(interpreted){
   const output=await evidenceInterpreter.interpret(this.runtime,q,context,used,c,signal,(stage,done,total)=>
    this.update(run,q.id+' · '+({interpretation_plan:'답변 항목 분석',evidence_alignment:'항목별 근거 연결',interpretation_answer:'근거 충분성·답변 구성',claim_verification:'최종 주장 검증'}[stage]||stage)+' · 요청 '+done+'/'+total,{stage:'answer',interpretation_stage:stage}));
   ({messages,response}=output);
   used.splice(0,used.length,...output.evidence_used);
   interpretationTrace={...output.trace,retrieval_artifact_id:retrieval.artifact_id};
   interpretationTrace.artifact_id=this.store.artifact('evidence-interpretation',interpretationTrace);
  }else if(scoped){
   const output=await scopedAnswer.composeAnswer(this.runtime,q,scopedPlan,used,evidenceFocus.excluded_sentence_ids,calculation,c,signal);
   ({messages,response,trace:scopedResponse}=output);
  }else if(timelineAnswer){
   messages=prompts.answerMessages(c,q,context,used,digestPlan,null,chronological?timeline:undefined);
   response=await this.runtime.chat(messages,digestPlan?.schema||prompts.answerSchema,{...c,output_tokens:1024},signal);
   if(digestPlan){
    response.model_parsed=response.parsed;
    response.parsed=resolveCitations(response.parsed,digestPlan);
   }
   tokenBudget=response.request_budget;
  }else{
   const plan=['M1',eventGraph.ROUTE,multiAnchor.ROUTE].includes(c.route)?citationPlan(used,prompts.answerSchema):null;
   messages=prompts.answerMessages(c,q,['M0','M1',eventGraph.ROUTE,multiAnchor.ROUTE].includes(c.route)?summary.summaryContext(context):context,used,plan,calculation);
   response=await this.runtime.chat(messages,plan?.schema||prompts.answerSchema,c,signal);
   if(plan&&used.length&&!arithmeticTask(q.text)){const audited=await auditAnswer(this.runtime,q,context,used,plan,calculation,response,c,signal);response=audited.response;answerAudit=audited.trace;}
   if(plan){response.model_parsed=response.parsed;response.parsed=resolveCitations(response.parsed,plan);}
  }
  if(attentionPacking?.partial){
   response.parsed={...response.parsed,action:response.parsed.action==='answer'?'partial_answer':response.parsed.action,
    answer:'일부 근거가 입력 한도로 제외됐습니다. '+response.parsed.answer};
  }
  const criteria=criteriaFor(run,q.id,q.text,q.gold),validated=automaticEvaluation(response.parsed,used,criteria);
  if(['M0','M1',eventGraph.ROUTE,multiAnchor.ROUTE].includes(c.route))validated.citations=validated.citations.map(x=>({...x,basis:'summary',summary_id:used.find(e=>e.evidence_id===x.evidence_id)?.summary_id}));
  const data={context_id:context.id,question_id:q.id,dataset_fingerprint:ds.fingerprint,retrieval_artifact_id:retrieval.artifact_id,config:c,evidence_used:used,evidence_focus:evidenceFocus,answer_audit:answerAudit,calculation,...(tokenBudget?{token_budget:tokenBudget}:{}),omitted_by_token_budget:omitted.map(e=>e.evidence_id),request_messages:messages,response,answer:response.parsed.answer,action:response.parsed.action,citations:validated.citations,citation_errors:validated.errors,elapsed_ms:performance.now()-start,token_usage:usage.report({stage:'answer',question_id:q.id}),assessment:{status:'PENDING_REVIEW',evaluation_version:EVALUATION_VERSION,axes:validated.axes,criteria_snapshot:criteria,provenance_valid:!validated.errors.length,semantic_correct:null,required_claims:q.gold.required_claims,forbidden_claims:q.gold.forbidden_claims,expected_action:q.gold.expected_action,...(q.gold.acceptable_actions?{acceptable_actions:q.gold.acceptable_actions}:{}),...(q.gold.completeness_scope?{completeness_scope:q.gold.completeness_scope}:{}),reference_answer:q.gold.reference_answer,...(q.gold.structured_expectations?{structured_expectations:q.gold.structured_expectations,annotation_status:q.gold.annotation_status,coverage:q.gold.coverage}:{})}};
  if(attentionPacking)data.attention_packing=attentionPacking;
  if(interpretationTrace){
   data.evidence_interpretation=interpretationTrace;
   data.token_usage=usage.report({question_id:q.id});
  }else if(evidenceInterpreter.MODES.includes(c.answer_pipeline)&&arithmetic){
   data.evidence_interpretation={version:evidenceInterpreter.VERSION,mode:c.answer_pipeline,
    status:'ARITHMETIC_BYPASS',note:'개인 기억과 무관한 순수 산술은 기존 산술 답변으로 처리합니다.'};
  }
  if(scopedResponse)data.scoped_response=scopedResponse;
  if(scopedPlan)data.answer_question_plan=scopedPlan;
  if(eventScope)data.event_scope=eventScope;
  if(chronological)data.chronological_input=timeline.map(({text,...item})=>item);
  if(digestTrace)data.question_digest=digestTrace;
  const id=this.store.artifact('answer',data);return {...data,artifact_id:id};
 }
 cancel(id){if(id!==this.busy)throw Error('현재 실행이 아닙니다.');const run=this.store.run(id);if(run){run.cancel_requested_at=new Date().toISOString();this.update(run,'중단 요청 · 현재 작업을 정리하는 중');}this.abort.abort();}
}
module.exports={Engine};


