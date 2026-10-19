import assert from 'node:assert/strict';
import {correctionView} from '../pma/static/search-explanation.js';

class Element {
  constructor(tag,text,cls){this.tag=tag;this.text=text || '';this.className=cls;this.children=[];}
  append(...children){this.children.push(...children);}
  get textContent(){return this.text+this.children.map(child=>child.textContent).join('');}
}
const node=(...args)=>new Element(...args);
const applied={status:'applied',original_query:'회의 내욜',query:'회의 내용',searched:true,
  edits:[{before:'내욜',after:'내용',kind:'spelling'}]};
const retry=node('button','원문으로만 다시 검색');
const evidence=[{search_explanation:{corrected_retrieval:{query:'회의 내용',contributed:true}}}];
const view=correctionView(node,applied,{evidence,retry});
assert.equal(view.tag,'details');
assert.equal(view.children[0].tag,'summary');
assert.match(view.children[0].textContent,/내욜 → 내용/);
for(const expected of ['검색 원문: 회의 내욜','보정 표현: 회의 내용','철자 보정',
  '의미·키워드 검색을 함께','1건의 검색 순위','같은 날짜·인물','중복해서 더하지',
  '질문과 저장된 기록은 수정하지'])assert.ok(view.textContent.includes(expected),expected);
assert.ok(view.children.includes(retry));

const unchanged=correctionView(node,applied,{evidence:[{search_explanation:{
  corrected_retrieval:{query:'회의 내용',contributed:false}}}]});
assert.match(unchanged.textContent,/검색 순위는 원문 검색 결과를 유지/);
const empty=correctionView(node,{...applied,searched:false});
assert.match(empty.textContent,/기록이 없어 보정 표현으로 검색하지 않았/);
assert.ok(!empty.textContent.includes('검색을 함께 했습니다'));
const unsupported=correctionView(node,{...applied,searched:false,reason:'unsupported_intent'});
assert.match(unsupported.textContent,/집계는 지원하지 않아 검색을 실행하지 않았/);
assert.ok(!unsupported.textContent.includes('기록이 없어'));
assert.match(correctionView(node,applied).textContent,/최종 근거에서의 반영 내역은 없습니다/);

for(const [reason,expected] of [['protected_entity','인물이나 장소 이름'],
  ['changed_constraints','검색 조건이 달라질'],['embedding_failed','원문으로 검색했습니다'],
  ['future_reason','원문 검색을 유지']]){
  const rejected=correctionView(node,{status:'rejected',reason,query:'원래 질문'});
  assert.match(rejected.children[0].textContent,/보정 미적용/);
  assert.ok(rejected.textContent.includes(expected));
}
assert.match(correctionView(node,{status:'none',reason:'disabled',query:'원문'}).textContent,/원문으로만 검색하도록 선택/);
assert.match(correctionView(node,{status:'none',query:'원문'}).textContent,/보정할 오타가 확인되지 않아/);
assert.equal(correctionView(node,null),null);
const legacy=correctionView(node,{...applied,searched:undefined});
assert.match(legacy.textContent,/실행 여부는 기록되어 있지 않습니다/);
const malicious=correctionView(node,{...applied,query:'<script>alert(1)</script>'});
assert.ok(malicious.textContent.includes('<script>alert(1)</script>'));
assert.ok(!malicious.children.some(child=>child.tag==='script'));
console.log('Correction UI checks passed: changes, execution, result impact, opt-out, rejection, empty and legacy results, literal text.');
