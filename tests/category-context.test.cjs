'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {DatabaseSync} = require('node:sqlite');
const {respond} = require('../ui/goal-agent.cjs');
const {ActionService} = require('../ui/action-service.cjs');

test('V3 selects with the previous exchange, plans and answers with selected originals, and reuses its index', async t => {
  const db = new DatabaseSync(':memory:');
  t.after(()=>db.close());
  const service = new ActionService({db,isThreadPurged:()=>false,read:()=>({records:[]})});
  const history = [];
  function exchange(id, question, answer, scope='personal') {
    history.push({id:'u-'+id,role:'user',text:question,scope},{id:'a-'+id,role:'assistant',text:answer,scope});
  }
  exchange('presentation','발표 담당은 민수야','발표 확인');
  exchange('example','예시 자료함 전용','가상 답변','samples');
  exchange('travel','여행지는 제주야','여행 확인');
  let indexed = 0, selections = 0, decisions = 0;
  const runtime = {async chat(messages) {
    const last = messages.at(-1).content;
    if (last.startsWith('{')) {
      const input = JSON.parse(last);
      assert.doesNotMatch(last,/예시 자료함 전용/);
      if (input.exchange) {
        indexed++;
        const travel = input.exchange[0].id === 'u-travel';
        return {parsed:{id:travel?'C2':'C1',title:travel?'여행':'발표',summary:travel?'제주':'담당자 민수'}};
      }
      assert.equal(input.previous_exchange[0].id,selections===0?'u-travel':'u-q1');
      selections++;
      return {parsed:{ids:['C1']}};
    }
    const body = JSON.parse(messages.at(-2).content);
    const prompt = messages.map(m=>m.content).join('\n');
    assert.match(prompt,/발표 담당은 민수야/);
    assert.doesNotMatch(prompt,/여행지는 제주야|여행 확인|예시 자료함 전용/);
    decisions++;
    if (body.phase==='goal_plan') return {parsed:{goal:'발표 담당 확인',context_summary:'발표',related_turn_ids:['u-presentation'],task_id:'',reply_guidance:'간단히',steps:[]}};
    return {parsed:{answer:'민수',support:[],outcome:'answered',question:''}};
  }};
  async function ask(id, question) {
    return respond({data:{thread_id:'thread',request_id:id,text:question,collection_id:'personal',analysis_version:'v3',conversation_ids:history.filter(t=>t.scope==='personal').map(t=>t.id)},runtime,service,conversation:async()=>history,getScope:async()=>({id:'personal',sources:[]}),retrieve:()=>[]});
  }
  const first = await ask('q1','발표 담당은 누구였지?');
  assert.deepEqual(first.action_trace.context_turn_ids,['u-presentation','a-presentation']);
  assert.equal(indexed,3);
  exchange('q1','발표 담당은 누구였지?',first.answer);
  const second = await ask('q2','그 사람 이름 다시 알려줘');
  assert.equal(second.analysis_version,'v3');
  assert.equal(indexed,4);
  assert.equal(selections,2);
  assert.equal(decisions,4);
});
