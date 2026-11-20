'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),http=require('node:http'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const state=require('../ui/plant-thought/chat-state.js'),{Library,createLibraryApi,makeBackup,readBackup}=require('../ui/library.cjs');
function fixture(){
 const prior={kind:'assistant',status:'success',submission:{request_id:'prior',thread_id:'thread',text:'보관함 기록을 도와줘',collection_id:'personal'},result:{answer:'기록 초안을 생성할까요?',action:'clarify'}};
 const proposal={id:'proposal',operation:'create',status:'pending',after:{title:'보관함 변경',body:'임시 보관함 번호 207로 바뀌었어\n기록하자',date:'2026-11-19'}};
 const created={kind:'assistant',status:'success',submission:{request_id:'created',thread_id:'thread',text:'생성해줘',collection_id:'personal'},result:{request_id:'created',answer:'초안을 준비했습니다.',action:'abstain',proposals:[proposal]}};
 const review={kind:'assistant',status:'success',submission:{request_id:'review',thread_id:'thread',text:'준비 된 초안 보여줘',collection_id:'personal'},result:{request_id:'review',answer:'제목: 바뀐 번호\n내용: 206에서 207로 변경되었습니다.',action:'abstain',proposals:[]}};
 return {thread:{id:'thread',title:'보관함',messages:[prior,created,review]},created,review,proposal};
}
test('generation follow-up and draft review reconnect the same prepared draft without rewriting its body',()=>{
 const {thread,created,review,proposal}=fixture();assert.equal(state.recordActionProposals(created.result,created,thread).length,1);
 assert.deepEqual(state.recordDraftProposals(thread,review),[proposal]);const a=state.ensureRecordDraft(thread,created,created.result,proposal),b=state.ensureRecordDraft(thread,review,review.result,proposal);assert.equal(a,b);assert.equal(b.body,proposal.after.body);assert.equal(thread.recordDrafts.length,1);
 b.body+='\n수정한 내용';assert.equal(state.ensureRecordDraft(thread,review,review.result,proposal).body,b.body);
});
test('ordinary lookup, another scope, cancelled batches and later turns cannot revive unrelated drafts',()=>{
 const f=fixture();f.review.submission.text='민수에 대해';assert.deepEqual(state.recordDraftProposals(f.thread,f.review),[]);
 f.review.submission.text='초안 보여줘';f.review.submission.collection_id='samples';assert.deepEqual(state.recordDraftProposals(f.thread,f.review),[]);
 f.review.submission.collection_id='personal';f.proposal.status='cancelled';assert.deepEqual(state.recordDraftProposals(f.thread,f.review),[]);
 f.proposal.status='pending';assert.deepEqual(state.recordDraftProposals(f.thread,f.thread.messages[0]),[]);
});
async function client(t){
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'pma-draft-test-')),library=new Library(dir),api=createLibraryApi(dir,{library});
 const draft={id:'proposal-p',title:'초안 제목',body:'207로 변경되었다.',date:'2026-11-19',status:'draft',dismissed:false};library.save(0,()=>({threads:[{id:'thread',title:'보관함',draft:'다음 질문',messages:[],recordDrafts:[draft]}],records:[]}));
 const server=http.createServer((req,res)=>api.handle(req,res,new URL(req.url,'http://127.0.0.1')));await new Promise(r=>server.listen(0,'127.0.0.1',r));
 t.after(async()=>{await new Promise(r=>server.close(r));library.close();if(path.dirname(dir)===os.tmpdir()&&path.basename(dir).startsWith('pma-draft-test-'))fs.rmSync(dir,{recursive:true,force:true});});
 const url='http://127.0.0.1:'+server.address().port,{token}=await(await fetch(url+'/api/library/state')).json();return {library,draft,post:async body=>{const r=await fetch(url+'/api/library/record',{method:'POST',headers:{'Content-Type':'application/json','X-Library-Token':token},body:JSON.stringify(body)});return {status:r.status,data:await r.json()};}};
}
test('edited draft saves atomically once, tolerates acknowledgement loss, and retains backup receipts',async t=>{
 const c=await client(t),body={revision:1,draftSource:{thread_id:'thread',draft_id:c.draft.id},record:{title:'수정한 제목',body:'임시 보관함 번호가 207로 변경되었다. 확인 완료.',date:'2026-11-18',search_enabled:true}};
 const responses=await Promise.all([c.post(body),c.post(body)]);assert.ok(responses.every(r=>r.status===200));assert.equal(new Set(responses.map(r=>r.data.record_id)).size,1);assert.equal(c.library.read().records.length,1);
 const saved=c.library.read(),draft=saved.threads[0].recordDrafts[0];assert.equal(draft.status,'saved');assert.equal(draft.recordId,saved.records[0].id);assert.equal(saved.records[0].body,body.record.body);assert.equal(saved.records[0].date,'2026-11-18');assert.equal(saved.threads[0].draft,'다음 질문');
 const backup=readBackup(makeBackup(saved));assert.deepEqual(backup.threads[0].recordDrafts,[draft]);assert.deepEqual(backup.records[0].chat_draft,body.draftSource);
 const changed=await c.post({...body,record:{...body.record,body:'재시도 중 다른 편집'}});assert.equal(changed.status,409);assert.equal(c.library.read().records.length,1);
});
test('failed validation and stale revisions preserve the draft; arbitrary source IDs cannot create records',async t=>{
 const c=await client(t),base={revision:1,draftSource:{thread_id:'thread',draft_id:c.draft.id},record:{title:'제목',body:'',date:'2026-11-19'}};
 assert.equal((await c.post(base)).status,400);assert.equal((await c.post({...base,revision:0,record:{...base.record,body:'수정한 내용'}})).status,409);
 assert.equal((await c.post({...base,draftSource:{thread_id:'thread',draft_id:'missing'},record:{...base.record,body:'내용'}})).status,409);
 assert.equal(c.library.read().records.length,0);assert.equal(c.library.read().threads[0].recordDrafts[0].status,'draft');assert.equal(c.library.read().threads[0].recordDrafts[0].body,c.draft.body);
});
