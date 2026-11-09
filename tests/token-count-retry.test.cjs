const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {Runtime}=require('../local/runtime.cjs'),{Store}=require('../local/store.cjs'),usage=require('../local/token-usage.cjs');
function fixture(){const root=fs.mkdtempSync(path.join(os.tmpdir(),'pma-count-retry-')),runtime=Object.create(Runtime.prototype);runtime.logDir=path.join(root,'runtime');runtime.states={generation:{status:'ready',port:18491},embedding:{status:'ready',port:18492}};runtime.keys={generation:'PRIVATE-KEY',embedding:'PRIVATE-KEY'};runtime.children={};return {root,runtime,cleanup(){fs.rmSync(root,{recursive:true,force:true});}};}
function transport(code='ECONNRESET'){return new TypeError('fetch failed',{cause:Object.assign(Error('connection failed'),{code})});}
const response=value=>({status:200,ok:true,text:async()=>JSON.stringify(value)});
async function withFetch(fetcher,fn){const old=global.fetch;global.fetch=fetcher;try{return await fn();}finally{global.fetch=old;}}

test('both token counters recover on the third attempt with the same input and fresh retry connections',async()=>{
 for(const endpoint of ['/tokenize','/v1/chat/completions/input_tokens']){
  const f=fixture(),requests=[],body={input:'PRIVATE-SOURCE'};try{await withFetch(async(url,options)=>{requests.push({url,body:options.body,headers:options.headers});if(requests.length<3)throw transport();return response({input_tokens:23});},async()=>assert.deepEqual(await f.runtime.request('generation',endpoint,body),{input_tokens:23}));assert.equal(requests.length,3);assert.ok(requests.every(r=>r.body===JSON.stringify(body)));assert.equal(requests[0].headers.Connection,undefined);assert.equal(requests[1].headers.Connection,'close');assert.equal(requests[2].headers.Connection,'close');const log=fs.readFileSync(path.join(f.runtime.logDir,'request-errors.jsonl'),'utf8');assert.ok(!log.includes('PRIVATE-SOURCE'));assert.ok(!log.includes('PRIVATE-KEY'));const events=log.trim().split('\n').map(JSON.parse);assert.deepEqual(events.map(e=>[e.retry_attempt,e.max_attempts]),[[1,3],[2,3]]);}finally{f.cleanup();}
 }
});

test('persistent counter transport failure stops at three attempts with the final diagnosis',async()=>{
 const f=fixture();let calls=0;try{await withFetch(async()=>{calls++;throw transport('UND_ERR_SOCKET');},()=>assert.rejects(()=>f.runtime.countChatTokens([],{}, {output_tokens:12}),e=>{assert.equal(e.error_details.cause_code,'UND_ERR_SOCKET');assert.equal(e.error_details.retry_attempt,3);assert.equal(e.error_details.max_attempts,3);return true;}));assert.equal(calls,3);}finally{f.cleanup();}
});

test('generation and embedding are never automatically replayed',async()=>{
 const f=fixture();try{for(const [role,endpoint]of [['generation','/v1/chat/completions'],['embedding','/v1/embeddings']]){let calls=0;await withFetch(async()=>{calls++;throw transport();},()=>assert.rejects(()=>f.runtime.request(role,endpoint,{})));assert.equal(calls,1);}}finally{f.cleanup();}
});

test('HTTP failures, invalid responses and non-transient timeout errors are not retried',async()=>{
 const f=fixture();try{for(const fetcher of [async()=>({status:503,ok:false,text:async()=>'unavailable'}),async()=>({status:200,ok:true,text:async()=>'invalid json'}),async()=>{throw transport('UND_ERR_HEADERS_TIMEOUT');}]){let calls=0;await withFetch(async(...args)=>{calls++;return fetcher(...args);},()=>assert.rejects(()=>f.runtime.request('generation','/tokenize',{})));assert.equal(calls,1);}}finally{f.cleanup();}
});

test('cancellation during retry backoff stops before the next request',async()=>{
 const f=fixture(),cancel=new AbortController();let calls=0;try{await withFetch(async()=>{calls++;setTimeout(()=>cancel.abort(),20);throw transport();},()=>assert.rejects(()=>f.runtime.request('generation','/tokenize',{},cancel.signal),{name:'AbortError'}));assert.equal(calls,1);}finally{f.cleanup();}
});

test('a stopped server or user cancellation never triggers a retry',async()=>{
 const f=fixture();try{for(const stopped of [true,false]){const cancel=new AbortController();let calls=0;f.runtime.states.generation.status='ready';await withFetch(async()=>{calls++;if(stopped)f.runtime.states.generation.status='error';else cancel.abort();throw transport();},()=>assert.rejects(()=>f.runtime.request('generation','/tokenize',{},cancel.signal)));assert.equal(calls,1);}}finally{f.cleanup();}
});

test('exhausted token-count retries record one failed logical call, zero blocked calls and no unsent inference',async()=>{
 const f=fixture(),store=new Store(f.root),run={id:'RETRY-ERROR',created_at:new Date().toISOString(),transient:true};usage.attach(f.runtime);try{await withFetch(async()=>{throw transport();},()=>usage.track({store},run,()=>usage.withStage('summary',()=>assert.rejects(()=>f.runtime.chat([],{}, {model:'local'})))));const row=run.token_usage.stages.summary;assert.equal(row.failed_calls,1);assert.equal(row.blocked_calls,0);assert.equal(row.generation.calls,0);assert.equal(row.generation.input_tokens,0);assert.equal(row.generation.output_tokens,0);const events=store.db.prepare('SELECT payload FROM token_usage_events').all().map(v=>JSON.parse(v.payload));assert.equal(events.length,1);assert.equal(events[0].status,'ERROR');assert.equal(events[0].skipped,true);}finally{store.db.close();f.cleanup();}
});

test('recovered token calculation records only the single generation that was actually sent',async()=>{
 const f=fixture(),store=new Store(f.root),run={id:'RETRY-OK',created_at:new Date().toISOString(),transient:true};usage.attach(f.runtime);let counts=0,generations=0;try{await withFetch(async url=>{if(url.endsWith('/input_tokens')){if(++counts===1)throw transport();return response({input_tokens:21});}generations++;return response({choices:[{finish_reason:'stop',message:{content:'{}'}}],usage:{prompt_tokens:21,completion_tokens:2}});},()=>usage.track({store},run,()=>usage.withStage('summary',()=>f.runtime.chat([],{type:'object'}, {model:'local',output_tokens:16}))));assert.equal(counts,2);assert.equal(generations,1);const row=run.token_usage.stages.summary;assert.equal(row.generation.calls,1);assert.equal(row.generation.input_tokens,21);assert.equal(row.generation.output_tokens,2);assert.equal(row.blocked_calls,0);}finally{store.db.close();f.cleanup();}
});

test('cancellation before counting or during backoff records no unsent generation tokens',async()=>{
 for(const before of [true,false]){
  const f=fixture(),store=new Store(f.root),cancel=new AbortController(),run={id:'CANCEL',created_at:new Date().toISOString(),transient:true};usage.attach(f.runtime);let calls=0;if(before)cancel.abort();
  try{await withFetch(async()=>{calls++;setTimeout(()=>cancel.abort(),20);throw transport();},()=>usage.track({store},run,()=>usage.withStage('summary',()=>assert.rejects(()=>f.runtime.chat([],{}, {model:'local'},cancel.signal)))));assert.equal(calls,before?0:1);const row=run.token_usage.stages.summary;assert.equal(row.generation.calls,0);assert.equal(row.failed_calls,1);assert.equal(row.blocked_calls,0);}finally{store.db.close();f.cleanup();}
 }
});
