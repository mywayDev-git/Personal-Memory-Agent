import assert from 'node:assert/strict';
import {summaryRevision,shouldPoll} from '../pma/static/evaluation-refresh.js';

for(const status of ['completed','failed','cancelled',''])assert(!shouldPoll({status}));
assert(shouldPoll({status:'running'}));
assert(!shouldPoll({status:'running',hidden:true}));
const original={status:'running',case_counts:{total:2,recorded:1},metrics:{},progress:{case_id:'a',stage:'execution',updated_at:'old'}};
assert.equal(summaryRevision(original),summaryRevision({...original,progress:{...original.progress,updated_at:'new'}}));
assert.notEqual(summaryRevision(original),summaryRevision({...original,case_counts:{total:2,recorded:2}}));

class Element{
  children=[];dataset={};value='';hidden=false;disabled=false;checked=false;_text='';
  classList={add(){},remove(){},toggle(){}};
  constructor(tag='div'){this.tagName=tag;}
  set textContent(value){this._text=String(value??'');this.children=[];}
  get textContent(){return this._text+this.children.map(c=>c.textContent).join('');}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this._text='';this.children=children;}
  setAttribute(){} removeAttribute(){} querySelectorAll(){return [];} focus(){} scrollIntoView(){}
}
const nodes=new Map(),calls=[],handlers={},polls=[];
globalThis.document={hidden:false,getElementById(id){if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id);},createElement:tag=>new Element(tag),querySelectorAll:()=>[]};
globalThis.location={pathname:'/evaluation/cases',search:'?run_id=chosen&case_id=case-a&q=sample&offset=20&dataset_id=fixture&verdict=fail'};
let savedUrl='';
globalThis.history={replaceState(state,title,url){savedUrl=url;}};
globalThis.window={addEventListener:(name,handler)=>handlers[name]=handler};
globalThis.setInterval=callback=>{polls.push(callback);};
let summary={...original,status:'completed'};
globalThis.fetch=async path=>{
  calls.push(path);let value;
  if(path.endsWith('/display'))value={show_originals:true};
  else if(path.endsWith('/datasets'))value={items:[{id:'fixture',name:'합성',version:'3'}]};
  else if(path.includes('/runs?'))value={items:[{id:'chosen',status:'completed',variant:'baseline'}],total:1};
  else if(path.endsWith('/summary'))value=structuredClone(summary);
  else if(path.endsWith('/failures'))value={items:[]};
  else if(path.includes('/cases?'))value={items:[],total:0};
  else if(path.endsWith('/cases/case-a'))value={case_id:'case-a',question:'질문',actual_answer:'실제 답변',expected_answer:'예상 답변',verdict:'pass'};
  else throw Error('unexpected endpoint: '+path);
  return {ok:true,json:async()=>value};
};
await import('../pma/static/evaluation.js');
assert.equal(nodes.get('q').value,'sample');assert.equal(nodes.get('verdict').value,'fail');
assert.equal(nodes.get('dataset').value,'fixture');
assert.equal(new URL(savedUrl,'http://local').searchParams.get('offset'),'20');
assert.equal(new URL(savedUrl,'http://local').searchParams.get('case_id'),'case-a');
const before=calls.length,answer=nodes.get('answer-detail').children[0];
await polls[0]();assert.equal(calls.length,before,'completed run must not poll or redraw');
summary={...original};await nodes.get('refresh').onclick();
const opened=nodes.get('answer-detail').children[0],rows=nodes.get('cases').children;
await polls[0]();assert.strictEqual(nodes.get('answer-detail').children[0],opened,'unchanged poll must preserve open details');
summary={...original,case_counts:{total:2,recorded:2}};await polls[0]();
assert.strictEqual(nodes.get('answer-detail').children[0],opened,'progress updates must not rebuild the inspector');
assert.strictEqual(nodes.get('cases').children,rows,'reading a case must not reset the selected row');
assert(answer);assert(calls.every(path=>!path.includes('/execution')));
console.log('completed polls, progress-only changes and open detail preservation passed');
