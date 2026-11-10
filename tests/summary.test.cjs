const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),http=require('node:http');
const {Store}=require('../local/store.cjs'),{Engine}=require('../local/engine.cjs'),{createApi}=require('../local/api.cjs'),{createSummaryApi}=require('../local/summary-api.cjs'),{parts,VERSION}=require('../local/summary.cjs'),{buildReview}=require('../local/review.cjs');
const {dateForDiary}=require('../local/diary-dates.js'),{createDemoServer}=require('../demo-frontend/serve.cjs');
const root=path.resolve(__dirname,'..'),SENTINEL='ORIGINAL_ONLY_9472',SUMMARY='회의는 11월 7일 오후 3시로 변경됐다. 금액 30만원은 확정되지 않았다.';
class Runtime{
 constructor(){this.calls=[];this.version='SUMMARY_OFFLINE';this.states={generation:{status:'stopped'},embedding:{status:'stopped'}};}
 status(){return {version:this.version,states:this.states,models:[]};}
 allowStart(){} async ensure(role,id){this.calls.push({kind:'ensure',role,id});this.states[role]={status:'ready',model_id:id};}async stopAll(){}
 async tokenize(text){return Math.ceil(text.length/2);}
 async embed(text,query,signal){signal?.throwIfAborted();if(this.failEmbed)throw Error('embedding failed');this.calls.push({kind:'embed',text,query});return [1,text.length/100+1,2];}
 async chat(messages,schema,config,signal){signal?.throwIfAborted();this.calls.push({kind:'chat',messages});const payload=JSON.parse(messages[1].content);let parsed;
  if(schema.properties.summary){if(this.failSummary)throw Error('summary failed');if(this.invalid)parsed={summary:' '};else parsed={summary:this.summary||SUMMARY,...(schema.properties.mood?{mood:this.mood||'단서 없음'}:{})};}
  else if(schema.properties.intent){parsed={intent:this.intent||'unclear',title:this.title||'',clarification:this.clarification||''};}
  else if(schema.properties.tone){parsed={tone:'overwhelmed',next_step:'walk',anchor:'산책',reference:this.useEmotionMemory&&payload.memories.length?payload.memories[0].sentences[0].sentence_id:'NONE'};}
  else{const e=payload.evidence[0];parsed=this.abstain?{action:'abstain',answer:'확인 불가',citations:[]}:{action:e?'answer':'abstain',answer:e?e.text:'요약에 정보가 없습니다.',citations:e?[{evidence_id:e.evidence_id,quote:e.text,occurrence:1}]:[]};}
  return {parsed,raw:JSON.stringify(parsed),usage:{prompt_tokens:10,completion_tokens:10},elapsed_ms:1};
 }
}
function fixture(datasets=false){const dir=fs.mkdtempSync(path.join(os.tmpdir(),'summary-memory-'));if(datasets)fs.cpSync(path.join(root,'datasets'),path.join(dir,'datasets'),{recursive:true});const store=new Store(dir),runtime=new Runtime(),engine=new Engine(dir,store,runtime),api=createSummaryApi(engine,runtime);return {dir,store,runtime,engine,api};}
const get=(f,route='/summary-memory')=>f.api.get(new URL('http://localhost'+route).pathname,new URL('http://localhost'+route));
const save=(f,text=SENTINEL+' 회의는 11월 7일로 변경. 30만원은 확정 아님.',extra={})=>f.api.post('/summary-memory/save',{text,...extra});
async function finish(f,body){const run=await f.engine.create(body);for(let i=0;i<600;i++){const r=f.store.run(run.id);if(!f.engine.busy)return r;await new Promise(r=>setTimeout(r,5));}throw Error('timeout');}

test('originals are archived separately; only summaries reach lexical, vector and answer inputs',async()=>{
 const f=fixture();try{
  const {memory}=await save(f),original=await get(f,'/summary-memory/original?key='+memory.memory_key);assert.ok(original.source.text.includes(SENTINEL));assert.equal(memory.summary,SUMMARY);
  const archived=f.store.readArtifact(memory.summary_artifact_id);assert.equal(JSON.stringify(archived).includes(SENTINEL),false);assert.ok(!archived.original_artifact_id);
  const originalReader=f.engine.summary.original;f.engine.summary.original=()=>{throw Error('Search read an original');};
  const lexical=f.engine.lexical.bind(f.engine);f.engine.lexical=(items,text)=>{assert.ok(items.every(i=>i.origin==='summary'&&!i.text.includes(SENTINEL)));return lexical(items,text);};
  const result=await f.api.post('/summary-memory/search',{query:'회의 일정',answer:true});assert.equal(result.retrieval.kind,VERSION);assert.equal(result.retrieval.source_snapshots.length,0);assert.equal(result.retrieval.metrics.span_groups_fully_covered,null);assert.equal(result.answer.citation_errors.length,0);assert.ok(result.answer.citations.every(c=>c.basis==='summary'&&c.summary_id===memory.summary_artifact_id));
  assert.ok(f.runtime.calls.filter(c=>c.kind==='embed').every(c=>!c.text.includes(SENTINEL)));const request=f.runtime.calls.filter(c=>c.kind==='chat').at(-1);assert.ok(!JSON.stringify(request).includes(SENTINEL));assert.deepEqual(JSON.parse(request.messages[1].content).conversation,[]);
  assert.equal(f.store.list().length,0);f.engine.summary.original=originalReader;
 }finally{f.store.db.close();}
});
test('persisted summaries survive restart and search does not summarize again',async()=>{
 const f=fixture();try{await save(f);const count=f.runtime.calls.filter(c=>c.kind==='chat').length;await f.api.post('/summary-memory/search',{query:'회의',answer:false});assert.equal(f.runtime.calls.filter(c=>c.kind==='chat').length,count);f.store.db.close();f.store=new Store(f.dir);f.engine=new Engine(f.dir,f.store,f.runtime);f.api=createSummaryApi(f.engine,f.runtime);assert.equal((await get(f)).memories.length,1);await f.api.post('/summary-memory/search',{query:'회의'});assert.equal(f.runtime.calls.filter(c=>c.kind==='chat').length,count);}finally{f.store.db.close();}
});
test('search progress is scoped to the request and cleared when the answer finishes',async()=>{
 const f=fixture();try{
  await save(f);
  const id=require('node:crypto').randomUUID(),route='/summary-memory/progress?id='+id;
  let release;
  const wait=new Promise(resolve=>{release=resolve;});
  const original=f.engine.retrieve.bind(f.engine);
  f.engine.retrieve=async(...args)=>{await wait;return original(...args);};
  const search=f.api.post('/summary-memory/search',{query:'회의 일정',answer:true,progress_id:id});
  try{
   await new Promise(resolve=>setImmediate(resolve));
   assert.deepEqual(await get(f,route),{stage:'retrieving'});
   assert.deepEqual(await get(f,'/summary-memory/progress?id='+require('node:crypto').randomUUID()),{stage:null});
  }finally{release();await search;}
  assert.deepEqual(await get(f,route),{stage:null});
 }finally{f.store.db.close();}
});
test('demo dates scope searches to the recorded Korean calendar day, including older diary rows',async t=>{
 const now=new Date('2026-11-09T15:00:00Z');t.mock.timers.enable({apis:['Date'],now});
 const f=fixture();try{
  const ask=query=>f.api.post('/summary-memory/search',{query,answer:true,use_diary_dates:true});
  const empty=await ask('어제 어디서 자료를 정리했어');
  assert.equal(empty.diary_date,'2026-11-09');
  assert.equal(empty.answer.action,'abstain');
  assert.deepEqual(empty.answer.citations,[]);
  assert.deepEqual(f.runtime.calls,[]);

  f.runtime.summary='민수와 도서관에서 자료를 정리했다.';
  const body='어제 '+f.runtime.summary;
  const {memory:yesterday}=await save(f,'제목: 일기\n기록일: '+dateForDiary(body)+'\n감정: 미지정\n\n'+body);
  assert.equal(yesterday.diary_date,'2026-11-09');
  const oldRow=f.engine.summary.get(yesterday.memory_key);
  delete oldRow.diary_date;
  f.engine.summary.write(oldRow);
  f.runtime.summary='민수와 카페에서 자료를 정리했다.';
  const {memory:today}=await save(f,'제목: 일기\n기록일: '+dateForDiary('오늘')+'\n감정: 미지정\n\n'+f.runtime.summary);
  assert.equal(today.diary_date,'2026-11-10');
  for(const [word,expected,wrong] of [['어제',yesterday,today],['오늘',today,yesterday],['9일에',yesterday,today],['11월 10일에',today,yesterday]]){
   const result=await ask(word+' 어디서 자료를 정리했어');
   assert.equal(result.diary_date,expected===today?'2026-11-10':'2026-11-09');
   assert.ok(result.answer.citations.some(c=>c.summary_id===expected.summary_artifact_id));
   assert.ok(result.retrieval.evidence.every(e=>e.summary_id!==wrong.summary_artifact_id));
  }
  const before=f.runtime.calls.length;
  const missing=await ask('8일에 어디서 자료를 정리했어');
  assert.equal(missing.diary_date,'2026-11-08');
  assert.equal(missing.answer.action,'abstain');
  assert.equal(missing.answer.answer,'11월 8일에 저장된 기록을 찾지 못했어요.');
  assert.equal(f.runtime.calls.length,before);
 }finally{f.store.db.close();}
});
test('personal chat asks for conversational answers and explains abstention after reading evidence',async()=>{
 const f=fixture();try{
  f.runtime.summary='11 월 8 일에는 도서관에서 책을 읽었어요.';
  await save(f,'제목: 일기\n기록일: 2026-11-08\n감정: 미지정\n\n도서관에서 책을 읽었다.');
  f.runtime.abstain=true;
  const request={query:'2026-11-08에 책 제목이 뭐였어?',answer:true};
  const result=await f.api.post('/summary-memory/search',{...request,use_diary_dates:true});
  assert.equal(result.answer.action,'abstain');
  assert.equal(result.answer.answer,'11월 8일 기록에서 질문에 답할 만한 내용을 찾지 못했어요.');
  assert.equal(result.answer.response.parsed.answer,'확인 불가');
  assert.equal(result.answer.evidence_used.length,1);
  assert.match(result.answer.request_messages[0].content,/해요체/);
  const standard=await f.api.post('/summary-memory/search',request);
  assert.equal(standard.answer.answer,'확인 불가');
  assert.doesNotMatch(standard.answer.request_messages[0].content,/해요체/);
  f.runtime.abstain=false;
  const found=await f.api.post('/summary-memory/search',{query:'2026-11-08에 뭐 했어?',answer:true,use_diary_dates:true});
  assert.equal(found.answer.answer,'11월 8일에는 도서관에서 책을 읽었어요.');
  assert.equal(found.answer.citations[0].quote,f.runtime.summary);
 }finally{f.store.db.close();}
});
test('diary mood is inferred in the summary call, persisted, and available for legacy re-summaries',async()=>{
 const f=fixture();try{
  const text='제목: 일기\n기록일: 2026-11-08\n감정: 미지정\n\n발표가 잘 끝나서 뿌듯했다.';
  f.runtime.mood='기쁨';
  const {memory}=await save(f,text);
  assert.equal(memory.mood,'기쁨');
  assert.equal(f.runtime.calls.filter(c=>c.kind==='chat').length,1);
  const {memory:manual}=await save(f,text.replace('감정: 미지정','감정: 슬픔'));
  assert.equal(manual.mood,undefined);
  const original=(await get(f,'/summary-memory/original?key='+manual.memory_key)).source;
  assert.match(original.text,/감정: 슬픔/);
  const legacy=await f.engine.summary.save(memory.namespace,{id:'LEGACY',revision:1,text,metadata:{owner_id:memory.owner}},f.engine.config({route:'M0'}),new AbortController().signal);
  assert.equal(legacy.mood,undefined);
  const updated=await f.api.post('/summary-memory/resummarize',{key:legacy.memory_key,expected:legacy.summary_artifact_id});
  assert.equal(updated.memory.original_fingerprint,legacy.original_fingerprint);
  assert.equal(updated.memory.mood,'기쁨');
  f.store.db.close();f.store=new Store(f.dir);f.engine=new Engine(f.dir,f.store,f.runtime);f.api=createSummaryApi(f.engine,f.runtime);
  assert.ok((await get(f)).memories.some(item=>item.memory_key===memory.memory_key&&item.mood==='기쁨'));
 }finally{f.store.db.close();}
});
test('a scheduled memory keeps its calendar date and exact start time in storage and search evidence',async t=>{
 t.mock.timers.enable({apis:['Date'],now:new Date('2026-11-09T15:00:00Z')});
 const f=fixture();try{
  f.runtime.summary='캡스톤 회의가 예정되어 있다.';
  const text='제목: 캡스톤 회의\n기록일: 2026-11-12\n감정: 미지정\n일정 시각: 15:30\n\n내일 모레 오후 3시 반 캡스톤 회의';
  const {memory}=await save(f,text);
  assert.equal(memory.diary_date,'2026-11-12');
  assert.deepEqual(memory.schedule,{title:'캡스톤 회의',time:'15:30'});
  assert.equal(memory.summary,'일정: 캡스톤 회의 · 2026-11-12 15:30');
  f.store.db.close();f.store=new Store(f.dir);f.engine=new Engine(f.dir,f.store,f.runtime);f.api=createSummaryApi(f.engine,f.runtime);
  assert.deepEqual((await get(f)).memories[0].schedule,memory.schedule);
  const result=await f.api.post('/summary-memory/search',{query:'내일 모레 일정 뭐 있어?',answer:true,use_diary_dates:true});
  assert.equal(result.diary_date,'2026-11-12');
  assert.ok(result.answer.citations.some(c=>c.quote.includes('15:30')));
  await assert.rejects(()=>save(f,text.replace('15:30','25:30')),/시각/);
 }finally{f.store.db.close();}
});
test('emotion support uses only earlier dates and quotes past actions without inventing facts',async t=>{
 t.mock.timers.enable({apis:['Date'],now:new Date('2026-11-09T15:00:00Z')});
 const f=fixture();try{
  const ask=exclude_memory_key=>f.api.post('/summary-memory/search',{query:'오늘은 과제가 많아서 힘들었다',answer:true,use_diary_dates:true,emotion_support:true,exclude_memory_key});
  const empty=await ask();
  assert.equal(empty.answer.answer.split('\n').length,2);
  assert.deepEqual(empty.answer.citations,[]);
  assert.equal(f.runtime.calls.some(c=>c.role==='embedding'),false);

  f.runtime.useEmotionMemory=true;
  f.runtime.summary='과제가 많아서 힘들었다.';
  const todayText='제목: 일기\n기록일: 2026-11-10\n감정: 미지정\n\n오늘은 과제가 많아서 힘들었다';
  await save(f,todayText);
  const {memory:newest}=await save(f,todayText);
  await save(f,todayText.replace('2026-11-10','2026-11-11'));
  const todayOnly=await ask(newest.memory_key);
  assert.equal(todayOnly.retrieval,null);
  assert.deepEqual(todayOnly.answer.citations,[]);
  assert.doesNotMatch(todayOnly.answer.answer,/과거|이전 기록|가졌어요/);
  assert.match(todayOnly.answer.answer,/걸어보는 건 어때요/);
  assert.deepEqual(JSON.parse(f.runtime.calls.at(-1).messages[1].content).memories,[]);

  f.runtime.summary='마음이 무거웠지만 운동장을 산책하니 기분이 나아졌다.';
  const {memory}=await save(f,'제목: 산책\n기록일: 2026-11-08\n감정: 슬픔\n\n'+SENTINEL+' 운동장을 산책했다.');
  const related=await ask();
  assert.equal(related.diary_date,undefined);
  assert.equal(related.answer.citations[0].basis,'original');
  assert.equal(related.answer.citations[0].original_artifact_id,memory.original_artifact_id);
  assert.equal(related.answer.citations[0].diary_date,'2026-11-08');
  assert.match(related.answer.citations[0].quote,/산책/);
  assert.equal(related.answer.answer.split('\n')[1],'이전 기록에는 “'+related.answer.citations[0].quote+'”라고 적혀 있어요.');
  assert.deepEqual(related.retrieval.source_refs.map(ref=>ref.source_id),[memory.source_id]);
  assert.ok(!f.runtime.calls.at(-1).messages[1].content.includes(SENTINEL));

  const justSaved=await ask(memory.memory_key);
  assert.deepEqual(justSaved.answer.citations,[]);
  assert.equal(justSaved.retrieval,null);

  f.runtime.useEmotionMemory=false;
  const unrelated=await ask();
  assert.deepEqual(unrelated.answer.citations,[]);
  assert.doesNotMatch(unrelated.answer.answer,/이전 기록|과거에도/);

  f.runtime.useEmotionMemory=true;
  await save(f,'제목: 과제\n기록일: 2026-11-07\n감정: 슬픔\n\n과제가 많아서 힘들었다.');
  const unsupported=await ask(memory.memory_key);
  assert.ok(unsupported.retrieval.evidence[0].text.includes('산책'));
  assert.deepEqual(unsupported.answer.citations,[]);
  assert.doesNotMatch(unsupported.answer.answer,/이전 기록|과거에도/);
 }finally{f.store.db.close();}
});
test('failed generation, empty output, embedding failure and cancellation keep the old active summary',async()=>{
 const f=fixture();try{const {memory:m}=await save(f);
  for(const mode of ['failSummary','invalid','failEmbed']){f.runtime[mode]=true;f.runtime.summary='변경된 요약 '+mode;await assert.rejects(()=>f.api.post('/summary-memory/resummarize',{key:m.memory_key,expected:m.summary_artifact_id}));assert.equal((await get(f)).memories[0].summary_artifact_id,m.summary_artifact_id);f.runtime[mode]=false;}
  const controller=new AbortController(),embed=f.runtime.embed.bind(f.runtime);f.runtime.summary='취소 대상 요약';f.runtime.embed=async(...args)=>{controller.abort();return embed(...args);};await assert.rejects(()=>f.engine.summary.save(m.namespace,f.engine.summary.original(m),f.engine.config({route:'M0'}),controller.signal,{force:true}));assert.equal((await get(f)).memories[0].summary_artifact_id,m.summary_artifact_id);assert.ok(f.store.db.prepare('SELECT count(*) n FROM summary_attempts').get().n>=4);
 }finally{f.store.db.close();}
});
test('edit replaces the active summary, stale writes fail, and deletion immediately excludes it',async()=>{
 const f=fixture();try{const {memory:m}=await save(f);f.runtime.summary='회의는 취소됐다.';const {memory:updated}=await save(f,'새 원본 취소 기록',{key:m.memory_key,expected:m.summary_artifact_id});assert.equal(updated.revision,2);assert.notEqual(updated.summary_artifact_id,m.summary_artifact_id);assert.equal((await get(f)).memories.length,1);
  await assert.rejects(()=>save(f,'오래된 화면 수정',{key:m.memory_key,expected:m.summary_artifact_id}),/변경/);const found=await f.api.post('/summary-memory/search',{query:'회의',answer:true});assert.ok(found.retrieval.evidence.every(e=>e.summary_id===updated.summary_artifact_id));assert.ok(!found.answer.answer.includes('30만원'));
  await f.api.post('/summary-memory/delete',{key:updated.memory_key,expected:updated.summary_artifact_id});assert.equal((await get(f)).memories.length,0);const deleted=await f.api.post('/summary-memory/search',{query:'회의',answer:true});assert.equal(deleted.retrieval.evidence.length,0);assert.equal(deleted.answer.action,'abstain');await assert.rejects(()=>get(f,'/summary-memory/original?key='+m.memory_key),/없습니다/);assert.ok(f.store.readArtifact(m.original_artifact_id));
 }finally{f.store.db.close();}
});
test('resummarization reads the preserved original and atomically activates a new summary',async()=>{
 const f=fixture();try{const {memory:m}=await save(f);f.runtime.summary='재요약된 회의 일정.';const {memory:newM}=await f.api.post('/summary-memory/resummarize',{key:m.memory_key,expected:m.summary_artifact_id});assert.notEqual(newM.summary_artifact_id,m.summary_artifact_id);const call=f.runtime.calls.filter(c=>c.kind==='chat').at(-1);assert.ok(call.messages[1].content.includes(SENTINEL));assert.equal((await get(f)).memories[0].summary,f.runtime.summary);}finally{f.store.db.close();}
});
test('summary cache invalidates for content, owner, model and guidance, while unchanged input is reused',async()=>{
 const f=fixture();try{const {memory:m}=await save(f),source=f.engine.summary.original(m),signal=new AbortController().signal,c=f.engine.config({route:'M0'});let count=f.runtime.calls.filter(c=>c.kind==='chat').length;
  const cached=await f.engine.summary.save(m.namespace,source,c,signal);assert.equal(cached.reused,true);assert.equal(f.runtime.calls.filter(c=>c.kind==='chat').length,count);
  for(const patch of [{summary_prompt_text:'날짜를 보존해 요약'},{model:'qwen35-2b-q4'}]){await f.engine.summary.save(m.namespace,source,f.engine.config({route:'M0',...patch}),signal);assert.equal(f.runtime.calls.filter(c=>c.kind==='chat').length,++count);}
  await f.engine.summary.save(m.namespace,{...source,text:source.text+' 추가 입력'},c,signal);assert.equal(f.runtime.calls.filter(c=>c.kind==='chat').length,++count);
  const other=await f.engine.summary.save(m.namespace,{...source,metadata:{...source.metadata,owner_id:'other'}},c,signal);assert.notEqual(other.memory_key,m.memory_key);assert.equal((await get(f)).memories.length,1);
 }finally{f.store.db.close();}
});
test('overlapping summary operations are rejected and cannot overwrite a newer memory',async()=>{
 const f=fixture();try{const {memory:m}=await save(f);const previous=f.engine.summary.original(m),chat=f.runtime.chat.bind(f.runtime);let release;const gate=new Promise(r=>release=r);f.runtime.chat=async(...args)=>{await gate;return chat(...args);};
  const active=f.api.post('/summary-memory/resummarize',{key:m.memory_key,expected:m.summary_artifact_id});await new Promise(r=>setImmediate(r));await assert.rejects(()=>save(f,'concurrent'),/진행 중/);release();await active;assert.equal(f.engine.busy,null);
  const fresh=f.engine.summary.get(m.memory_key);await assert.rejects(()=>f.engine.summary.save(m.namespace,previous,f.engine.config({route:'M0'}),new AbortController().signal,{force:true,expected:'stale'}),/변경/);assert.equal(f.engine.summary.get(m.memory_key).summary_artifact_id,fresh.summary_artifact_id);
 }finally{f.store.db.close();}
});
test('long inputs cover every character without breaking emoji; malformed/partial results never publish',async()=>{
 const text='가'.repeat(2199)+'😀'+'나'.repeat(10000),ps=parts(text);assert.equal(ps[0].start,0);assert.equal(ps.at(-1).end,text.length);for(let i=0;i<ps.length;i++){assert.equal(ps[i].text,text.slice(ps[i].start,ps[i].end));assert.ok(!/[\uD800-\uDBFF]$/.test(ps[i].text));assert.ok(!/^[\uDC00-\uDFFF]/.test(ps[i].text));if(i)assert.ok(ps[i].start<=ps[i-1].end);}
 const f=fixture();try{await save(f,text);assert.equal(f.runtime.calls.filter(c=>c.kind==='chat').length,ps.length);let calls=0;const chat=f.runtime.chat.bind(f.runtime);f.runtime.chat=async(...args)=>{if(++calls===2)throw Error('second part failed');return chat(...args);};await assert.rejects(()=>save(f,text),/second part/);assert.equal((await get(f)).memories.length,1);}finally{f.store.db.close();}
});
test('dataset M0 reuses summaries across runs, excludes owner/deleted inputs and never sends gold',async()=>{
 const f=fixture(true);try{const a=await finish(f,{config:{route:'M0',query_prompt:'query-context-v1'},question_ids:['F02-Q1','F02-Q2','F30-Q1','F28-Q2','F29-Q2']});assert.equal(a.status,'COMPLETED',JSON.stringify(a.results.map(r=>r.error)));assert.ok(a.results.every(r=>r.status==='PENDING_REVIEW'));
  assert.deepEqual(a.results[2].accessible_source_ids,['F30-A']);for(const r of a.results.slice(3))assert.equal(r.stages.retrieval.evidence.length,0);
  const calls=f.runtime.calls.filter(c=>c.kind==='chat').length;await finish(f,{config:{route:'M0'},stage:'extract',question_ids:['F02-Q1']});assert.equal(f.runtime.calls.filter(c=>c.kind==='chat').length,calls);
  for(const call of f.runtime.calls.filter(c=>c.kind==='chat'))for(const forbidden of ['"gold":','"required_claims":','"reference_answer":','"expected_state":','TEST-ONLY-582','합성차-882'])assert.ok(!JSON.stringify(call.messages).includes(forbidden));
  const ds=await f.engine.dataset();const review=buildReview(a,f.store,ds,'extraction');assert.ok(review.targets.some(t=>t.method==='summary'&&t.sources.length&&t.units[0].object===SUMMARY));
 }finally{f.store.db.close();}
});
test('raw/structured frozen artifacts cannot enter summary search or answers',async()=>{
 const f=fixture(true);try{const a=await finish(f,{config:{route:'R0'},question_ids:['F02-Q1']});const raw=a.results[0].stages.retrieval.artifact_id;const blocked=await finish(f,{config:{route:'M0'},stage:'answer',artifacts:[raw],question_ids:['F02-Q1']});assert.equal(blocked.results[0].status,'ERROR');assert.match(blocked.results[0].error,/서로 재사용/);
  const summarized=await finish(f,{config:{route:'M0'},question_ids:['F02-Q1']}),r=summarized.results[0].stages.retrieval,source=(await f.engine.dataset()).d.sources.records.find(s=>s.id===r.source_refs[0].source_id);const forged=structuredClone(r);forged.evidence[0].text=SENTINEL;assert.throws(()=>f.engine.summary.assertRetrieval(forged,[source]),/요약 이외/);
  const scope=structuredClone(source);scope.metadata.owner_id='other';assert.throws(()=>f.engine.summary.assertRetrieval(r,[scope]),/소유자/);const changed=structuredClone(source);changed.text+=' new content';assert.throws(()=>f.engine.summary.assertRetrieval(r,[changed]),/버전/);
 }finally{f.store.db.close();}
});
test('HTTP summary mutations require a token and same origin; GETs never start models',async()=>{
 const f=fixture(),api=createApi(f.dir,{store:f.store,runtime:f.runtime}),server=http.createServer((req,res)=>api.handle(req,res,new URL(req.url,'http://'+req.headers.host)));await new Promise(r=>server.listen(0,'127.0.0.1',r));const base='http://127.0.0.1:'+server.address().port+'/api/baseline';
 try{assert.equal((await fetch(base+'/summary-memory')).status,200);assert.equal(f.runtime.calls.length,0);const {token}=await(await fetch(base+'/bootstrap')).json();const post=(headers,body)=>fetch(base+'/summary-memory/save',{method:'POST',headers:{'Content-Type':'application/json',...headers},body:JSON.stringify(body)});
  assert.equal((await post({},{})).status,403);assert.equal((await post({'X-Memory-Lab-Token':token,Origin:'https://example.invalid'},{})).status,403);assert.equal((await post({'X-Memory-Lab-Token':token},{text:SENTINEL})).status,200);assert.equal((await(await fetch(base+'/summary-memory')).json()).memories.length,1);
 }finally{await new Promise(r=>server.close(r));await api.close();}
});
test('demo intent is proxied with same-origin authentication and does not store a memory',async()=>{
 const f=fixture(),api=createApi(f.dir,{store:f.store,runtime:f.runtime}),backend=http.createServer((req,res)=>api.handle(req,res,new URL(req.url,'http://'+req.headers.host)));
 await new Promise(r=>backend.listen(0,'127.0.0.1',r));
 const demo=createDemoServer(backend.address().port);await new Promise(r=>demo.listen(0,'127.0.0.1',r));
 const origin='http://127.0.0.1:'+demo.address().port,base=origin+'/api/baseline';
 try{
  const {token}=await(await fetch(base+'/bootstrap')).json();
  const post=(headers,text)=>fetch(base+'/summary-memory/intent',{method:'POST',headers:{'Content-Type':'application/json',Origin:origin,...headers},body:JSON.stringify({text})});
  assert.equal((await post({},'민수')).status,403);
  assert.equal((await post({'X-Memory-Lab-Token':token,Origin:'https://example.invalid'},'민수')).status,403);
  const headers={'X-Memory-Lab-Token':token};
  for(const [intent,input] of [['diary','어제 도서관에 갔다.'],['question','어제 어디 갔었지'],['unclear','민수']]){
   f.runtime.intent=intent;
   const response=await post(headers,input);
   assert.equal(response.status,200);
   assert.equal((await response.json()).intent,intent);
   const chat=f.runtime.calls.at(-1);
   assert.deepEqual(JSON.parse(chat.messages[1].content),{text:input});
  }
  f.runtime.intent='schedule';
  f.runtime.title='캡스톤 회의';
  const scheduled=await(await post(headers,'내일 모레 오후 3시 캡스톤 회의 등록해 줘')).json();
  assert.equal(scheduled.intent,'schedule');
  assert.equal(scheduled.title,'캡스톤 회의');
  assert.equal((await(await fetch(base+'/summary-memory')).json()).memories.length,0);
  assert.ok(f.runtime.calls.filter(c=>c.kind==='ensure').every(c=>c.role==='generation'));
  const progress=await fetch(base+'/summary-memory/progress?id='+require('node:crypto').randomUUID());
  assert.equal(progress.status,200);
  assert.deepEqual(await progress.json(),{stage:null});
  for(const asset of ['/diary-dates.js','/constellation.js'])assert.equal((await fetch(origin+asset)).status,200);
 }finally{await new Promise(r=>demo.close(r));await new Promise(r=>backend.close(r));await api.close();}
});

