import assert from 'node:assert/strict';
import fs from 'node:fs';

class Element{
  children=[];dataset={};value='';hidden=false;_text='';
  constructor(tag){this.tagName=tag;}
  set textContent(value){this._text=String(value??'');this.children=[];}
  get textContent(){return this._text+this.children.map(c=>c.textContent).join('');}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this._text='';this.children=children;}
  setAttribute(){}focus(){}scrollIntoView(){}
}
const find=(root,predicate)=>predicate(root)?root:root.children.map(c=>find(c,predicate)).find(Boolean);
const cases=JSON.parse(fs.readFileSync('evaluation/main_suite/data/scenarios.json','utf8'));
const conditions=['IN-01.normal','IN-01.boundary'].map(id=>cases.find(c=>c.id===id));
assert(conditions.every(Boolean));
const host=new Element('section');host.dataset.mode='full';
globalThis.document={getElementById:()=>host,createElement:tag=>new Element(tag)};
globalThis.location={search:''};globalThis.history={replaceState(){}};globalThis.window={addEventListener(){}};
const calls=[];
globalThis.fetch=async(path,options)=>{
  calls.push({path,options});let value;
  if(path.includes('?')){
    assert.equal(new URL(path,'http://local').searchParams.get('view'),'questions');
    value={inventory_question_total:1,inventory_total:2,total:1,items:[{id:conditions[0].id,question:conditions[0].question,expected_answers:[conditions[0].expected_answer],variables:conditions[0].variables,priority:'P0',splits:['development'],condition_count:2}]};
  }else value={case:conditions[0],conditions};
  return {ok:true,json:async()=>value};
};
await import('../pma/static/evaluation-datasets.js');
const list=find(host,e=>e.className==='dataset-list');
assert.equal(list.children.length,1,'normal and boundary must be one visible question');
assert(list.textContent.includes('검사 조건 2개'));
const link=list.children[0].children[0];link.onclick({preventDefault(){}});
await new Promise(resolve=>setImmediate(resolve));
const detail=find(host,e=>e.className==='dataset-detail');
const selector=find(detail,e=>e.tagName==='select');
assert.equal(selector.children.length,2);
selector.value=conditions[1].id;selector.onchange();
assert(detail.textContent.includes('distractor'),'boundary input must remain available in the selector');
selector.value=conditions[0].id;selector.onchange();
assert(!detail.textContent.includes('distractor'),'normal input must not inherit boundary distractors');
assert(calls.every(c=>!c.options.method||c.options.method==='GET'));
console.log('one visible question with independent selectable conditions passed');
