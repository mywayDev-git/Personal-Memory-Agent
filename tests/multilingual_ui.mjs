import assert from 'node:assert/strict';
import {explanation, expansionView} from '../pma/static/search-explanation.js';

class Element {
  constructor(tag,text,cls){this.tag=tag;this.text=text || '';this.className=cls;this.children=[];}
  append(...children){this.children.push(...children);}
  get textContent(){return this.text+this.children.map(child=>child.textContent).join('');}
}
const node=(...args)=>new Element(...args);
globalThis.document={createTextNode:text=>node('#text',text)};
assert.equal(expansionView(node,null),null);
const text='😀 Ｐｙｔｈｏｎ 공부';
const expansion={status:'applied',searched:true,edits:[
  {before:'쿠버네티스',after:'Kubernetes',kind:'transliteration'},
  {before:'학습',after:'공부',kind:'similar'}],retrieval:[
  {query:'python 공부',kind:'translation',weight:0.8,contributed:true,
   keyword_matches:[{field:'source_text',start:2,end:8,quote:'Ｐｙｔｈｏｎ'}]}]};
const view=expansionView(node,expansion);
assert.match(view.textContent,/발음 표기/);
assert.match(view.textContent,/유사어/);
assert.match(view.textContent,/실행/);
const result=explanation(node,{source_text:text,search_explanation:{query_expansion:expansion,
  methods:['expansion'],keyword_matches:[{term:'python',kind:'normalized',match_type:'alias',
  field:'source_text',start:2,end:8,quote:'Ｐｙｔｈｏｎ'}]}});
for(const label of ['등록 별칭','번역 표현 일치','가중치 0.8','통합 순위에 반영','Ｐｙｔｈｏｎ'])assert.ok(result.textContent.includes(label),label);
const rejected=expansionView(node,{status:'rejected',searched:false,reason:'embedding_failed',
  rejected:[{before:'Java',reason:'ambiguous_expression'}]});
assert.match(rejected.textContent,/원문으로 검색/);
assert.match(rejected.textContent,/여러 의미/);
assert.ok(explanation(node,{search_explanation:{methods:['keyword']}}));
console.log('Multilingual explanation checks passed: aliases, translations, pronunciation, similar terms, original offsets, fallback, legacy results');
