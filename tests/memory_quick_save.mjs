import assert from 'node:assert/strict';
import {setupMemory} from '../pma/static/memory.js';
class Element {
  constructor(tag,text){this.tag=tag;this.textContent=text;this.children=[];this.listeners={};this.value='';}
  append(...nodes){this.children.push(...nodes);}
  prepend(...nodes){this.children.unshift(...nodes);}
  replaceChildren(...nodes){this.children=nodes;}
  setAttribute(){}
  addEventListener(name,fn){this.listeners[name]=fn;}
  showModal(){}
  close(){this.closed=true;}
  focus(){}
  remove(){}
}
const node=(tag,text)=>new Element(tag,text);
const action=(text,fn)=>Object.assign(node('button',text),{click:fn});
const walk=el=>[el,...el.children.flatMap(walk)];
for(const relation of [null,'contradiction','semantic_duplicate']) {
  const body=node('body'),toolbar=node('div'),calls=[];
  globalThis.document={body,activeElement:null,getElementById:()=>toolbar};
  const api=async(path,method,data)=>{
    calls.push({path,data});
    if(path.endsWith('/review'))return {status:'complete',review_id:'r',comparisons:relation?[{relation,memory_id:'old',content:'existing'}]:[]};
    if(path.endsWith('/commit'))return {memory_id:'saved'};
    throw Error(path);
  };
  const memory=setupMemory({api,node,action,notice:()=>{}});
  memory.preview({candidate_id:'c',candidate_version:1,content:'hello',message_ids:['m'],memory_type:'plan',epistemic_status:'user_reported'});
  const dialog=body.children[0];
  const save=walk(dialog).find(el=>el.tag==='button'&&el.textContent==='저장');
  await save.click();
  assert.equal(calls[0].path,'/memory/candidates/c/review');
  if(!relation){assert.equal(calls.length,2);assert.equal(dialog.closed,true);assert.equal(calls[1].data.approved,true);}
  else {assert.equal(calls.length,1);assert.ok(!dialog.closed);}
  if(relation==='contradiction') {
    const resolution=walk(dialog).find(el=>el.tag==='select'&&el.children.some(opt=>opt.value==='add_confirmed'));
    resolution.value='add_confirmed';await save.click();
    assert.equal(calls.length,2);assert.equal(dialog.closed,true);
  }
}
console.log('3 quick-save flows passed: save, conflict confirmation, duplicate guard');
