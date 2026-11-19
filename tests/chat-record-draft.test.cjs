'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const {recordDraft,mergeRecordDraft}=require('../ui/plant-thought/chat-state.js');
test('draft contains only the selected exchange, preserves attribution and leaves chat untouched',()=>{
 const selected={kind:'assistant',status:'success',submission:{text:'오늘 발표 시연을 마쳤어.'},result:{action:'answer',answer:'7분 동안 진행한 시연을 마친 기분은 어땠나요?'}};
 const thread={title:'발표 준비',draft:'아직 보내지 않은 말',messages:[selected,{kind:'user',text:'다른 주제의 나중 대화'}]},before=JSON.stringify(thread);
 const draft=recordDraft(thread,selected,selected.result,'2026-11-19');
 assert.equal(draft.title,'오늘 발표 시연을 마쳤어.');assert.equal(draft.date,'2026-11-19');
 assert.equal(draft.body,'나의 이야기\n오늘 발표 시연을 마쳤어.\n\nAI와 나눈 내용\n7분 동안 진행한 시연을 마친 기분은 어땠나요?');assert.equal(JSON.stringify(thread),before);
});
test('explicit create draft keeps the proposed content and valid record date',()=>{
 const result={action:'draft',answer:'초안입니다.',proposals:[{id:'p',operation:'create',status:'pending',after:{title:'발표를 마친 날',body:'나는 오늘 시연을 마쳤다.',date:'2026-11-18'}}]},message={submission:{text:'어제 발표한 내용을 기록해줘'},result};
 assert.deepEqual(recordDraft({messages:[message]},message,result,'2026-11-19'),{title:'발표를 마친 날',body:'나는 오늘 시연을 마쳤다.',date:'2026-11-18'});
 result.proposals[0].after.date='2026-02-30';assert.equal(recordDraft({messages:[message]},message,result,'2026-11-19').date,'2026-11-19');
});
test('editor handoff preserves an existing draft and avoids duplicate append; replacement is explicit',()=>{
 const current={title:'작성 중',body:'기존 본문',date:'2026-11-18'},draft={title:'새 기록',body:'대화 내용',date:'2026-11-19'};
 const merged=mergeRecordDraft(current,draft);assert.deepEqual(merged,{title:'작성 중',body:'기존 본문\n\n대화 내용',date:'2026-11-18'});
 assert.deepEqual(mergeRecordDraft(merged,draft),merged);assert.deepEqual(mergeRecordDraft(current,draft,false),draft);assert.equal(current.body,'기존 본문');
 assert.deepEqual(mergeRecordDraft({title:'',body:'',date:'2026-01-01'},draft),draft);
});
