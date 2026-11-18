'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const {recordActionProposals}=require('../ui/plant-thought/chat-state.js');
const proposal=(operation='create')=>({id:'proposal-a',operation,status:'pending'});
const result=(extra={})=>({action:'answer',intent:'contextual',proposals:[proposal()],...extra});
const message=text=>({kind:'assistant',submission:{text}});
test('ordinary lookup cannot expose an unrelated model-created draft',()=>{
 const r=result({action_trace:{steps:[{tool:'create',proposal_id:'proposal-a'}]}}),m=message('민수에 대해');assert.deepEqual(recordActionProposals(r,m),[]);assert.equal(r.proposals.length,1);
});
test('explicit save and mixed search-plus-save keep confirmation cards',()=>{
 for(const text of ['오늘 이야기를 기록해줘','오늘 내 기분을 기록하고 싶어','지금까지 대화를 저장해 주세요','기록에서 담당자를 알려주고 이번 일정도 저장해줘','save this conversation'])assert.equal(recordActionProposals(result(),message(text)).length,1,text);
});
test('queries about saved content, quotations and negative requests do not count as writes',()=>{
 for(const text of ['저장한 기록을 알려줘','기록하는 방법을 설명해줘','저장하지 말고 알려줘','“기록해줘”라는 문장이 무슨 뜻이야?','How do I save a record?'])assert.equal(recordActionProposals(result(),message(text)).length,0,text);
});
test('record edits, deletion and restore retain their corresponding confirmations',()=>{
 for(const [operation,text]of [['update','내 기록을 수정해줘'],['delete','이 기록을 삭제해줘'],['restore','삭제한 기록을 복원해줘']])assert.equal(recordActionProposals(result({proposals:[proposal(operation)]}),message(text)).length,1);
});
test('only the linked earlier record task can authorize a follow-up card',()=>{
 const first={...message('이 기록을 수정해줘'),result:{task_id:'task-write',action:'clarify'}},current=message('회사 하린이야'),r=result({action_trace:{plan:{task_id:'task-write'}}}),thread={messages:[first,current]};assert.equal(recordActionProposals(r,current,thread).length,1);assert.equal(recordActionProposals(result({action_trace:{plan:{task_id:'other-task'}}}),current,thread).length,0);
 const earlier=message('민수에 대해'),later={...message('저장해줘'),result:{task_id:'task-write'}};assert.equal(recordActionProposals(r,earlier,{messages:[earlier,later]}).length,0);
});
test('completed operations and legacy recording drafts stay readable',()=>{
 assert.equal(recordActionProposals(result({executions:[{proposal_id:'proposal-a',status:'succeeded'}]}),message('민수에 대해')).length,1);
 assert.equal(recordActionProposals(result({action:'draft',intent:'experience'}),message('오늘은 산책했어')).length,1);
 assert.equal(recordActionProposals(result({recording:{status:'draft'}}),message('오늘은 산책했어')).length,1);
 assert.equal(recordActionProposals(result({proposals:[proposal('search')]}),message('저장해줘')).length,0);
});
