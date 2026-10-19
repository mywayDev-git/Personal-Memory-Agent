import assert from 'node:assert/strict';
import {highlight} from '../pma/static/search-explanation.js';
class Element {
  constructor(tag,text,cls){this.tag=tag;this.text=text || '';this.className=cls;this.children=[];}
  append(...children){this.children.push(...children);}
  get textContent(){return this.text+this.children.map(child=>child.textContent).join('');}
}
const node=(...args)=>new Element(...args);
globalThis.document={createTextNode:text=>node('#text',text)};
const text='😀 민수<script>와 제주';
const result=highlight(node,text,[
  {start:2,end:4,quote:'민수'},
  {start:2,end:12,quote:'민수<script>'},
  {start:-1,end:4,quote:'민수'},
  {start:13,end:15,quote:'잘못된 위치'}
]);
assert.equal(result.textContent,text);
assert.equal(result.children.filter(child=>child.tag==='mark').length,1);
assert.equal(result.children.find(child=>child.tag==='mark').textContent,'민수<script>');
assert.ok(result.children.every(child=>child.tag!=='script'));
console.log('Highlight checks passed: Unicode positions, overlapping spans, invalid spans, literal HTML');
