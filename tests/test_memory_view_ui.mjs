import assert from 'node:assert/strict';
import {setupTestMemories,inputSourceView} from '../pma/static/test-memory-view.js';
class Element{
  children=[];value='';hidden=false;_text='';
  constructor(tag){this.tagName=tag;}
  set textContent(value){this._text=String(value??'');this.children=[];}
  get textContent(){return this._text+this.children.map(c=>c.textContent).join('');}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this._text='';this.children=children;}
  setAttribute(){}focus(){}scrollIntoView(){}
}
const find=(root,predicate)=>predicate(root)?root:root.children.map(c=>find(c,predicate)).find(Boolean);
globalThis.document={createElement:tag=>new Element(tag)};
const text='첫 줄\n<script>alert(1)</script>\n'+'긴 원문 '.repeat(200),calls=[];
globalThis.fetch=async(path,options)=>{calls.push({path,options});return {ok:true,json:async()=>path.includes('?')?
  {total:1,inventory_total:1,items:[{id:'test-one',preview:'첫 줄…',version:1,kinds:['기록 입력'],case_count:1}]}:
  {source:{id:'test-one',text,version:1,kinds:['기록 입력'],owner:'user-a',cases:[{case_id:'IN-01.normal',kind:'기록 입력',question:'질문'}]}}};};
const host=new Element('section'),reader=setupTestMemories(host);
assert.equal(calls.length,0,'opening the main app must not load or insert synthetic records');
await reader.ensureLoaded();await reader.ensureLoaded();assert.equal(calls.length,1,'switching back must preserve the current list');
const open=find(host,e=>e.className==='test-source-open');await open.onclick();
assert.equal(find(host,e=>e.tagName==='pre').textContent,text,'the full raw text and line breaks must survive');
assert.equal(find(host,e=>e.tagName==='script'),undefined,'never interpret source HTML');
assert(calls.every(c=>c.path.startsWith('/api/eval/plan/memories')&&!c.options.method));
const raw=inputSourceView([{id:'target',text:'현재 원문',initial_text:'이전 원문',version:2}]);
assert(raw.textContent.includes('현재 원문'));assert(raw.textContent.includes('이전 원문'));
console.log('lazy source browsing, full safe original text and read-only fetches passed');
