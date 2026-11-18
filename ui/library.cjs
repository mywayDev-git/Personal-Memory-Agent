'use strict';
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {DatabaseSync}=require('node:sqlite');
const {normalizeInspection}=require('./chat-inspection.cjs');
const contextState=require('./plant-thought/conversation-context.js');
const maps=require('./plant-thought/dialogue-map.js');
const FORMAT='plant-thought-backup',MAX_BYTES=20*1024*1024;
const fail=(message,status=400)=>{throw Object.assign(Error(message),{status});};
const canonical=value=>JSON.stringify(value&&typeof value==='object'?Array.isArray(value)?value.map(v=>JSON.parse(canonical(v))):Object.fromEntries(Object.keys(value).sort().map(k=>[k,JSON.parse(canonical(value[k]))])):value);
const hash=value=>crypto.createHash('sha256').update(canonical(value)).digest('hex');
function text(v,max=200000,optional=false){if(optional&&v==null)return null;if(typeof v!=='string'||v.length>max)fail('문자열 형식 또는 길이가 올바르지 않습니다.');return v;}
function id(v){v=text(v,160);if(!/^[\w.-]+$/.test(v))fail('자료 ID가 올바르지 않습니다.');return v;}
function date(v){if(v==null)return null;v=text(v,64);if(!/^\d{4}-\d{2}-\d{2}(?:T.*)?$/.test(v)||!Number.isFinite(Date.parse(v))||new Date(v.slice(0,10)+'T00:00:00Z').toISOString().slice(0,10)!==v.slice(0,10))fail('날짜 형식이 올바르지 않습니다.');return v;}
function integer(v,min=0){if(!Number.isSafeInteger(v)||v<min)fail('정수 값이 올바르지 않습니다.');return v;}
function list(v,max){if(!Array.isArray(v)||v.length>max)fail('자료 목록의 형식 또는 개수가 올바르지 않습니다.');return v;}
function unique(rows){if(new Set(rows.map(r=>r.id)).size!==rows.length)fail('파일 안에 같은 ID가 중복되어 있습니다.');return rows;}
function citation(c){if(!c||typeof c!=='object')fail('인용 형식이 올바르지 않습니다.');const start=integer(c.start),end=integer(c.end);if(end<start)fail('인용 구간이 올바르지 않습니다.');return {source_id:id(c.source_id),revision:integer(c.revision,1),title:text(c.title??'',1000),quote:text(c.quote),start,end,...(c.original_source_id?{original_source_id:id(c.original_source_id)}:{})};}
function mapSubmission(s,threadId){if(s.analysis_version==null||s.analysis_version==='v1')return s.analysis_version?{analysis_version:'v1'}:{};if(!['v2','v3'].includes(s.analysis_version))fail('지원하지 않는 대화 버전입니다.');return {analysis_version:s.analysis_version,map_context:maps.normalize(s.map_context,threadId,contextState),conversation_ids:list(s.conversation_ids,10000).map(v=>text(v,180))};}
function submission(s,threadId){if(!s||typeof s!=='object')fail('대화 제출 정보가 없습니다.');if(s.thread_id!==threadId)fail('대화와 제출 정보의 ID가 다릅니다.');return {request_id:id(s.request_id),thread_id:threadId,text:text(s.text,8000),input_version:integer(s.input_version??0),profile:text(s.profile??'personal',80),example_id:text(s.example_id??'',160),collection_id:s.collection_id==='personal'?'personal':'samples',history:list(s.history??[],4).map(v=>text(v,8000)),...(s.context?{context:contextState.normalize(s.context,threadId)}:{}),...(s.context_selection?{context_selection:id(s.context_selection)}:{}),...(s.pending_target?{pending_target:id(s.pending_target)}:{}),...(s.inspect===true?{inspect:true}:{}),...mapSubmission(s,threadId)};}
function thread(t){
 if(!t||typeof t!=='object')fail('대화 형식이 올바르지 않습니다.');const threadId=id(t.id);
 const messages=list(t.messages,10000).map(m=>{
  if(!m||typeof m!=='object')fail('메시지 형식이 올바르지 않습니다.');
  if(!['user','assistant','notice'].includes(m.kind))fail('지원하지 않는 메시지 종류입니다.');
  const row={kind:m.kind,createdAt:date(m.createdAt)};
  if(m.kind!=='assistant'){row.text=text(m.text);if(m.requestId)row.requestId=id(m.requestId);return row;}
  if(!['pending','success','error','cancelled'].includes(m.status))fail('AI 응답 상태가 올바르지 않습니다.');
  row.status=m.status;row.submission=submission(m.submission,threadId);row.archived=m.archived===true;
  if(typeof m.evidenceExpanded==='boolean')row.evidenceExpanded=m.evidenceExpanded;
  if(typeof m.inspectionExpanded==='boolean')row.inspectionExpanded=m.inspectionExpanded;
  if(m.inspection!=null)row.inspection=normalizeInspection(m.inspection);
  if(m.error!=null)row.error=text(m.error,4000);if(m.stage!=null)row.stage=text(m.stage,100);
  if(m.result){const r=m.result;if(r.request_id!==row.submission.request_id||r.thread_id!==threadId)fail('AI 응답 ID가 일치하지 않습니다.');row.result={request_id:r.request_id,thread_id:threadId,answer:text(r.answer),action:text(r.action,80),intent:text(r.intent,80),model:text(r.model??'',200),citations:list(r.citations??[],100).map(citation),scope:{mode:text(r.scope?.mode??'restored',80),accessible_count:integer(r.scope?.accessible_count??0),retrieved_count:integer(r.scope?.retrieved_count??0)},stored:r.stored===true};}
  if(row.result){const r=m.result;for(const field of ['profile','example_id','context_id'])if(r.scope?.[field]!=null)row.result.scope[field]=text(r.scope[field],160);if(r.elapsed_ms!=null){if(typeof r.elapsed_ms!=='number'||!Number.isFinite(r.elapsed_ms)||r.elapsed_ms<0)fail('응답 시간 형식이 올바르지 않습니다.');row.result.elapsed_ms=r.elapsed_ms;}if(r.usage){row.result.usage={};for(const field of ['prompt_tokens','completion_tokens','total_tokens'])if(r.usage[field]!=null)row.result.usage[field]=integer(r.usage[field]);}}
  if(row.result)for(const field of ['proposal','execution','proposals','executions','action_trace','task_id'])if(m.result[field]!=null){const value=m.result[field];if(Buffer.byteLength(JSON.stringify(value))>300000)fail('작업 정보가 너무 큽니다.');row.result[field]=structuredClone(value);}
  if(row.result&&m.result.analysis_version)row.result.analysis_version=text(m.result.analysis_version,10);
  if(row.result&&m.result.map_context)row.result.map_context=maps.normalize(m.result.map_context,threadId,contextState);
  if(row.result&&m.result.dialogue_trace)row.result.dialogue_trace=maps.trace(m.result.dialogue_trace);
  if(row.result&&m.result.context)row.result.context=contextState.normalize(m.result.context,threadId);
  if(row.result&&m.result.recording)row.result.recording=contextState.recording(m.result.recording);
  if(row.result&&m.result.context_info)row.result.context_info=contextState.trace(m.result.context_info);
  if(row.result&&m.result.parts){row.result.parts=list(m.result.parts,3).map(p=>{
    if(!['success','error'].includes(p.status)||p.result?.parts)fail('복합 작업 결과 형식이 올바르지 않습니다.');
    const s={...row.submission,request_id:id(p.id),text:text(p.text,8000)},child=thread({id:threadId,messages:[{kind:'assistant',status:p.status,submission:s,result:p.result,error:p.error,stage:p.stage,inspection:p.inspection}]}).messages[0];
    return {id:s.request_id,text:s.text,status:child.status,...(child.result?{result:child.result}:{}),...(child.error?{error:child.error}:{}),...(child.stage?{stage:child.stage}:{}),...(child.inspection?{inspection:child.inspection}:{})};
  });}
  if(row.result&&m.result.inspection!=null)row.result.inspection=normalizeInspection(m.result.inspection);
  if(row.status==='success'&&!row.result)fail('완료된 AI 답변의 내용이 없습니다.');return row;
 });
 const out={id:threadId,title:text(t.title??'새 대화',1000),draft:text(t.draft??'',8000),inputVersion:integer(t.inputVersion??0),createdAt:date(t.createdAt),updatedAt:date(t.updatedAt),messages};
 if(t.mapContext)out.mapContext=maps.normalize(t.mapContext,threadId,contextState);
 if(t.context)out.context=contextState.normalize(t.context,threadId);
 if(t.deletedAt!=null)out.deletedAt=integer(t.deletedAt,1);
 if(t.sampleScope)out.sampleScope={profile:text(t.sampleScope.profile??'personal',80),questionId:text(t.sampleScope.questionId??'',160),collectionId:t.sampleScope.collectionId==='personal'?'personal':'samples'};
 return out;
}
function record(r){
 if(!r||typeof r!=='object')fail('기록 형식이 올바르지 않습니다.');
 return {id:id(r.id),revision:integer(r.revision??1,1),title:text(r.title??'',1000),body:text(r.body),date:date(r.date),created_at:date(r.created_at),updated_at:date(r.updated_at),origin_id:r.origin_id==null?null:id(r.origin_id),synthetic:r.synthetic===true,search_enabled:r.search_enabled===true,...(r.deleted_at!=null?{deleted_at:date(r.deleted_at)}:{}),...(r.kind?{kind:text(r.kind,40)}:{}),...(r.sources?{sources:list(r.sources,10000).map(s=>({turn_id:text(s.turn_id,180),role:['user','assistant'].includes(s.role)?s.role:fail('출처 역할이 올바르지 않습니다.'),quote:text(s.quote)}))}:{})};
}
function payload(p){if(!p||typeof p!=='object')fail('백업 내용이 없습니다.');const out={threads:unique(list(p.threads??[],2000).map(thread)),records:unique(list(p.records??[],10000).map(record))};if(out.threads.reduce((n,t)=>n+t.messages.length,0)>50000)fail('대화 메시지는 최대 50,000개까지 지원합니다.');return out;}
function makeBackup(data,kind='full'){
 if(!['chat','archive','full'].includes(kind))fail('백업 종류가 올바르지 않습니다.');const p=payload(data);
 if(kind==='chat'&&p.records.length||kind==='archive'&&p.threads.length)fail('백업 종류와 내용이 다릅니다.');
 const backup={format:FORMAT,version:1,kind,exported_at:new Date().toISOString(),time_zone:'Asia/Seoul',counts:{threads:p.threads.length,records:p.records.length},payload:p,sha256:hash(p)};
 if(Buffer.byteLength(JSON.stringify(backup))>MAX_BYTES)fail('백업 파일이 20MB를 넘습니다. 내보낼 범위를 나누어 주세요.',413);return backup;
}
function readBackup(b){
 if(!b||b.format!==FORMAT||b.version!==1||!['chat','archive','full'].includes(b.kind))fail('이 앱에서 내보낸 버전 1 JSON 백업만 불러올 수 있습니다.');
 date(b.exported_at);if(!/^[a-f0-9]{64}$/.test(b.sha256||'')||hash(b.payload)!==b.sha256)fail('백업 파일의 무결성 확인에 실패했습니다.');
 const p=payload(b.payload);if(b.counts?.threads!==p.threads.length||b.counts?.records!==p.records.length)fail('백업의 자료 개수가 일치하지 않습니다.');
 if(b.kind==='chat'&&p.records.length||b.kind==='archive'&&p.threads.length)fail('백업 종류와 내용이 다릅니다.');return p;
}
const comparable=row=>{const out=structuredClone(row);delete out.search_enabled;if(out.messages)for(const m of out.messages)delete m.archived;return out;};
const same=(a,b)=>hash(comparable(a))===hash(comparable(b));
function planImport(state,incoming){const result={threads:{add:[],duplicate:[],conflict:[]},records:{add:[],duplicate:[],conflict:[]}};for(const kind of ['threads','records'])for(const row of incoming[kind]){const old=state[kind].find(r=>r.id===row.id);result[kind][!old?'add':same(old,row)?'duplicate':'conflict'].push({id:row.id,title:row.title});}return result;}
function merge(state,incoming,options={}){
 if(!['keep','copy'].includes(options.conflicts??'keep'))fail('충돌 처리 방식이 올바르지 않습니다.');
 const out=structuredClone(state),mapping=new Map(),counts={threads:0,records:0,skipped:0};
 for(const kind of ['records','threads'])for(const original of incoming[kind]){
  const old=out[kind].find(r=>r.id===original.id);if(old&&same(old,original)){counts.skipped++;continue;}if(old&&options.conflicts!=='copy'){if(kind==='records')mapping.set(original.id,'unavailable-'+crypto.randomUUID());counts.skipped++;continue;}
  const row=structuredClone(original);if(old)row.id=crypto.randomUUID();
  if(kind==='records'){mapping.set(original.id,row.id);row.search_enabled=options.searchEnabled===true;}
  else for(const m of row.messages)if(m.kind==='assistant'){
   m.archived=true;
   m.submission.thread_id=row.id;if(m.result){m.result.thread_id=row.id;for(const c of m.result.citations){const mapped=mapping.get(c.source_id);if(mapped?.startsWith('unavailable-'))c.original_source_id=c.source_id;c.source_id=mapped||c.source_id;}}
  }
  if(kind==='threads'){
    if(row.mapContext)row.mapContext=maps.rebind(row.mapContext,row.id,contextState,mapping);
    for(const m of row.messages)if(m.kind==='assistant'){if(m.submission.map_context)m.submission.map_context=maps.rebind(m.submission.map_context,row.id,contextState,mapping);if(m.result?.map_context)m.result.map_context=maps.rebind(m.result.map_context,row.id,contextState,mapping);}
    if(row.context)row.context=contextState.remap(row.context,row.id,mapping);
    for(const m of row.messages)if(m.kind==='assistant'){
      if(m.submission.context)m.submission.context=contextState.remap(m.submission.context,row.id,mapping);
      if(m.result?.context)m.result.context=contextState.remap(m.result.context,row.id,mapping);
      for(const p of m.result?.parts||[])if(p.result){p.result.thread_id=row.id;if(p.result.context)p.result.context=contextState.remap(p.result.context,row.id,mapping);for(const c of p.result.citations)c.source_id=mapping.get(c.source_id)||c.source_id;}
    }
  }
  out[kind].push(row);counts[kind]++;
 }
 return {state:out,counts};
}
class Library{
 constructor(root){const dir=path.join(root,'.local','library');fs.mkdirSync(dir,{recursive:true});this.db=new DatabaseSync(path.join(dir,'library.sqlite'));this.db.exec('PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000; CREATE TABLE IF NOT EXISTS library (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, payload TEXT NOT NULL)');this.db.prepare('INSERT OR IGNORE INTO library VALUES(1,0,?)').run(JSON.stringify({threads:[],records:[]}));}
 read(){const row=this.db.prepare('SELECT * FROM library WHERE id=1').get();return {revision:row.revision,...JSON.parse(row.payload)};}
 save(revision,transform){this.db.exec('BEGIN IMMEDIATE');try{const before=this.read();if(before.revision!==revision)fail('다른 화면에서 자료가 변경되었습니다. 새로고침 후 다시 시도해 주세요. 현재 대화는 이 탭에 남아 있습니다.',409);const result=transform(before),data=payload(result.state??result);if(Buffer.byteLength(JSON.stringify(data))>MAX_BYTES)fail('저장 자료가 20MB 제한을 넘었습니다.',413);this.db.prepare('UPDATE library SET revision=?,payload=? WHERE id=1').run(before.revision+1,JSON.stringify(data));this.db.exec('COMMIT');return {revision:before.revision+1,...data,...(result.counts?{counts:result.counts}:{})};}catch(e){this.db.exec('ROLLBACK');throw e;}}
 close(){if(!this.closed){this.db.close();this.closed=true;}}
}
function sampleRecords(root){return JSON.parse(fs.readFileSync(path.join(root,'datasets/pma-generalization-v1.0.0/sources.json'),'utf8')).records.map(s=>record({id:s.id,revision:s.revision,title:s.metadata.title,body:s.text,date:s.metadata.created_at?new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Seoul'}).format(new Date(s.metadata.created_at)):null,created_at:s.metadata.created_at,origin_id:s.id,synthetic:true}));}
function markdown(data){const lines=[];for(const t of data.threads){lines.push('# '+t.title,'','생성 시각: '+(t.createdAt||'시각 미상'),'');for(const m of t.messages){lines.push('## '+({user:'사용자',assistant:'AI',notice:'안내'}[m.kind]),'',m.result?.answer??m.text??m.error??'중단된 요청','');for(const c of m.result?.citations??[])lines.push('> '+c.title+' · '+c.source_id+' · v'+c.revision,'> '+c.quote.replaceAll('\n','\n> '),'');}if(t.draft)lines.push('## 작성 중인 초안','',t.draft,'');}for(const r of data.records)lines.push('# '+r.title,'','기록일: '+(r.date||'날짜 미상')+' · '+(r.synthetic?'가상 예시':'개인 기록'),'',r.body,'');return lines.join('\n');}
function createLibraryApi(root,{library=new Library(root)}={}){
 const token=crypto.randomBytes(32).toString('hex');
 const json=(res,status,value)=>{res.writeHead(status,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'});res.end(JSON.stringify(value));};
 return {library,close:()=>library.close(),async handle(req,res,url){
  if(!url.pathname.startsWith('/api/library/'))return false;
  try{
   const host=req.headers.host||'';if(!/^(127\.0\.0\.1|localhost):\d+$/.test(host)||(req.headers.origin&&req.headers.origin!=='http://'+host))fail('현재 로컬 화면에서만 요청할 수 있습니다.',403);
   const route=url.pathname.slice('/api/library/'.length);
   if(req.method==='GET'&&route==='state'){json(res,200,{token,...library.read()});return true;}
   if(req.method!=='POST')fail('지원하지 않는 요청입니다.',405);
   if(req.headers['x-library-token']!==token)fail('연결 정보가 만료됐습니다. 새로고침해 주세요.',403);
   if(!String(req.headers['content-type']).startsWith('application/json'))fail('JSON 요청이 필요합니다.',415);
   const parts=[];let bytes=0;for await(const part of req){bytes+=part.length;if(bytes>MAX_BYTES)fail('파일 또는 요청은 20MB까지 지원합니다.',413);parts.push(part);}let body;try{body=JSON.parse(Buffer.concat(parts).toString('utf8'));}catch{fail('JSON 파일을 읽을 수 없습니다.');}
   const current=library.read();
   if(route==='save'){const threads=unique(list(body.threads,2000).map(thread));json(res,200,library.save(body.revision,state=>({...state,threads})));}
   else if(route==='export'){
    const kind=body.kind??'full',data={threads:kind==='archive'?[]:current.threads.filter(t=>(body.includeDeleted===true||!t.deletedAt)&&(!body.threadIds||body.threadIds.includes(t.id))).map(t=>({...t,draft:body.includeDrafts===false?'':t.draft})),records:kind==='chat'?[]:(body.collection==='samples'?sampleRecords(root):current.records).filter(r=>!body.recordIds||body.recordIds.includes(r.id))};
    const backup=makeBackup(data,kind);json(res,200,{backup,markdown:body.markdown===true?markdown(backup.payload):null});
   }else if(route==='inspect'){const incoming=readBackup(body.backup);json(res,200,{revision:current.revision,plan:planImport(current,incoming),counts:body.backup.counts});}
   else if(route==='import'){const incoming=readBackup(body.backup);json(res,200,library.save(body.revision,state=>merge(state,incoming,body.options)));}
   else if(route==='record'){const r=record({...body.record,id:crypto.randomUUID(),revision:1,created_at:new Date().toISOString(),synthetic:false});if(!r.body.trim())fail('기록 내용을 입력해 주세요.');json(res,200,library.save(body.revision,state=>({...state,records:[...state.records,r]})));}
   else if(route==='search-settings'){const ids=list(body.recordIds,10000).map(id);json(res,200,library.save(body.revision,state=>({...state,records:state.records.map(r=>({...r,search_enabled:ids.includes(r.id)}))})));}
   else fail('지원하지 않는 요청입니다.',404);
  }catch(e){json(res,e.status||500,{error:e.status?e.message:'자료를 처리하지 못했습니다. 기존 자료는 유지됩니다.'});}
  return true;
 }};
}
module.exports={Library,createLibraryApi,makeBackup,readBackup,planImport,merge,hash,markdown,record,payload,MAX_BYTES};
