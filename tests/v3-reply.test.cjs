'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const {prepare}=require('../ui/v3-reply.cjs');
const context={turns:[{role:'user',text:'위치가 필요하면 물어봐.'}],evidence:[],outcomes:[]};
test('repairs only suspect prose, retaining technical terms, numbers and a single clarification',async()=>{
  for(const word of ['什么原因','reason']){
    let calls=0;
    const result=await prepare({answer:'Qwen API 7분, 다른'+word+'인지 확인합니다. 어디에 계신가요?',question:'현재 위치가 어디인가요?',outcome:'needs_input',support:[{ref_id:'R1'}]},
      {...context,call:async(phase,messages)=>{calls++;assert.equal(phase,'language_repair');assert.deepEqual(JSON.parse(messages[1].content).words,['다른'+word+'인지']);return {replacements:['다른 이유인지']}}});
    assert.equal(calls,1);assert.equal(result.answer,'Qwen API 7분, 다른 이유인지 확인합니다.');assert.equal(result.question,'현재 위치가 어디인가요?');assert.deepEqual(result.support,[{ref_id:'R1'}]);
  }
});
test('retains technical terms and requested foreign-language examples without an extra call',async()=>{
  for(const [request,answer] of [['Qwen API 설명','Qwen API는 JSON을 사용합니다.'],['중국어로 번역해줘','你好。']]){
    const r=await prepare({answer,outcome:'answered',question:''},{...context,turns:[{role:'user',text:request}],call:assert.fail});assert.equal(r.answer,answer);
  }
});
test('prioritizes application clarification and refuses a bad repair',async()=>{
 const r=await prepare({answer:'대상 확인이 필요합니다. 뭘 바꿀까요?',question:'어느 기록인가요?',outcome:'needs_input'},{...context,outcomes:[{status:'needs_input',question:'수정할 기록의 제목은 무엇인가요?'}],call:assert.fail});
 assert.equal(r.answer,'대상 확인이 필요합니다.');assert.equal(r.question,'수정할 기록의 제목은 무엇인가요?');
 await assert.rejects(()=>prepare({answer:'다른什么原因인지',question:'',outcome:'answered'},{...context,call:async()=>({replacements:['什么原因']})}),/교정/);
});
