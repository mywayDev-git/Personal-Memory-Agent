'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const {analyze,review,groundedIssues,arithmetic}=require('../ui/latest-turn.cjs');
const maps=require('../ui/plant-thought/dialogue-map.js'),context=require('../ui/plant-thought/conversation-context.js');
function wrongModel(){return {chat:async()=>({parsed:{intent:'emotion',operation:'reply',source:'conversation',speech:'statement',recordable:true,correction:false,needs_context:false,goal:'과거 감정 이야기 계속'}})};}
test('explicit write commands override a contradictory LLM intent, including spaced Korean commands',async()=>{
 for(const text of ['저장해줘','기록 해줘','메모 해줘']){const r=await analyze(wrongModel(),text,[],[]);assert.equal(r.intent,'experience');assert.equal(r.operation,'draft');assert.equal(r.recordable,false);assert.deepEqual(r.expected.expected_intents,['experience']);}
});
test('a calculation is isolated from earlier emotional context and checked with computed values',async()=>{
 const r=await analyze(wrongModel(),'7더하기 5는?',[],[]);assert.equal(r.intent,'general');assert.equal(r.source,'none');assert.equal(r.recordable,false);assert.equal(r.needs_context,false);assert.equal(r.calculation.result,12);
 assert.equal(arithmetic('8 나누기 2는?').result,4);assert.equal(arithmetic('12 곱하기 3은?').result,36);assert.equal(arithmetic('3 나누기 0은?'),null);assert.equal(arithmetic('지난번 7개 샀어'),null);
 const input={question:'7더하기 5는?',conversation_context:{latest_request:r,user_statements:[],corrections:[]}};
 assert.match(groundedIssues(input,{answer:'112입니다.'}),/계산/);assert.equal(groundedIssues(input,{answer:'12입니다.'}),null);
});
test('explicit emotional correction is a recordable user statement despite question punctuation',async()=>{
 const r=await analyze(wrongModel(),'아니 기분 좋다니까?',[],[]);assert.equal(r.correction,true);assert.equal(r.speech,'correction');assert.equal(r.recordable,true);assert.equal(r.operation,'reply');
});
test('unsupported emotion is blocked independently even when an LLM reviewer would approve',async()=>{
 let calls=0;const runtime={chat:async()=>{calls++;throw Error('must not rely on a self-approving reviewer');}};
 const input={question:'오늘 밥 먹었어',conversation_context:{latest_request:{recordable:true},user_statements:['오늘 밥 먹었어'],corrections:[]}};
 const r=await review(runtime,input,{answer:'절망감이 무겁고 고통스러우셨겠어요.'});assert.equal(r.passed,false);assert.equal(calls,0);
});
test('positive correction invalidates earlier sadness without rewriting original user evidence',()=>{
 const facts=['슬퍼','아니 기분 좋다니까?'];const original=JSON.stringify(facts);
 const input={question:facts[1],conversation_context:{latest_request:{recordable:true},user_statements:facts,corrections:[{text:facts[1]}]}};
 assert.match(groundedIssues(input,{answer:'슬픔을 기쁨이 덮어주었군요.'}),/원문에 없는/);assert.equal(JSON.stringify(facts),original);
});
test('unsupported save completion and HTML are blocked before semantic review',()=>{
 const input={question:'오늘 기록해줘',conversation_context:{latest_request:{recordable:false},user_statements:[],corrections:[]}};
 assert.match(groundedIssues(input,{answer:'저장했습니다.'}),/실제 쓰기/);assert.match(groundedIssues(input,{answer:'<p>초안입니다.</p>'}),/HTML/);assert.equal(groundedIssues(input,{answer:'초안이에요. 아직 저장하지 않았어요.'}),null);
});
test('correction provenance and recording source IDs survive normalized snapshots',()=>{
 const m=maps.empty('t');m.turn_labels=[{turn_id:'u-a',recordable:true,correction:true}];m.corrections=[{turn_id:'u-a',text:'기분 좋아',part_ids:[],invalidated_assistant_ids:['a-before']}];
 assert.deepEqual(maps.normalize(m,'t',context),m);
 const r=context.recording({status:'draft',date:'2026-11-18',statements:['기분 좋아'],sources:[{turn_id:'u-a',text:'기분 좋아'}],reason:'사용자 원문'});assert.equal(r.sources[0].turn_id,'u-a');
});
