// Offline DOM/state-machine checks. All network responses are synthetic.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {webcrypto} from 'node:crypto';

const source=fs.readFileSync('pma/static/evaluation-execution.js','utf8');
const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;
class Element {
  children=[]; disabled=false; checked=false; textContent=''; value='';
  constructor(tag){this.tagName=tag;}
  append(...children){this.children.push(...children);}
  querySelectorAll(selector){
    const all=this.children.flatMap(child=>child instanceof Element?[child,...child.querySelectorAll('*')]:[]);
    return selector==='input:checked'?all.filter(n=>n.tagName==='input'&&n.checked):all;
  }
}
async function fixture({running=false,available=true}={}){
  const nodes=new Map();
  const document={hidden:false,getElementById(id){if(!nodes.has(id))nodes.set(id,new Element('div'));return nodes.get(id);},
    createElement:tag=>new Element(tag),createTextNode:text=>({textContent:text})};
  document.getElementById('execution-profile').value='core';
  const specs={core:{automated:40,review:749,repeats:1},compare:{automated:40,review:749,repeats:3},extended:{automated:53,review:842,repeats:1},final:{automated:14,review:278,repeats:5}};
  const options={profiles:specs,server_available:available,
    generation:[{id:'baseline',label:'기준 생성 모델',available},{id:'candidate',label:'비교 생성 모델',available}],
    embedding:[{id:'baseline',label:'검색 모델',available}]};
  let status=running?{id:'existing',status:'running',run_ids:['existing-result']}:{status:'idle',run_ids:[]};
  const calls=[],events=[];let poll;
  const fetch=async(url,request={})=>{
    calls.push({url,...request});
    if(url==='/api/v1/session')return {ok:true,json:async()=>({csrf:'unit-test-csrf'})};
    if(url==='/api/eval/execution/options')return {ok:true,json:async()=>options};
    if(request.method==='POST')status=url.endsWith('/cancel')?{...status,status:'cancelling'}:{id:'new-job',status:'running',run_ids:['new-result']};
    return {ok:true,json:async()=>status};
  };
  class Event {constructor(type,values){this.type=type;Object.assign(this,values);}}
  await new AsyncFunction('document','window','fetch','setInterval','crypto','CustomEvent',source)(
    document,{dispatchEvent:event=>events.push(event)},fetch,callback=>{poll=callback;},webcrypto,Event);
  return {nodes,calls,events,document,poll:()=>poll(),setStatus:value=>{status=value;}};
}
const ui=await fixture();
const el=id=>ui.nodes.get(id);
assert(ui.calls.every(c=>c.method!=='POST'),'opening dashboard must not execute');
assert.equal(el('execution-start').disabled,false);
assert.match(el('execution-scope').textContent,/자동 실행 40개/);
await el('execution-form').onsubmit({preventDefault(){}});
const start=ui.calls.find(c=>c.method==='POST');
assert.equal(start.url,'/api/eval/execution');
assert.equal(start.headers['X-CSRF-Token'],'unit-test-csrf');
assert.equal(JSON.parse(start.body).profile,'core');
assert.deepEqual(JSON.parse(start.body).generation,['baseline']);
assert.equal(el('execution-start').disabled,true);
assert.equal(el('execution-cancel').disabled,false);
assert.equal(el('execution-profile').disabled,true);
assert.equal(ui.events.at(-1).detail.runId,'new-result');
await el('execution-cancel').onclick();
assert.equal(ui.calls.filter(c=>c.method==='POST').length,2);
assert.equal(ui.calls.at(-1).url,'/api/eval/execution/new-job/cancel');
assert.equal(el('execution-cancel').disabled,true);
assert.match(el('execution-feedback').textContent,/현재 모델 처리가 끝나면/);
ui.setStatus({id:'new-job',status:'completed',run_ids:['new-result']});
await ui.poll();
assert.equal(el('execution-start').disabled,false);
assert.equal(ui.calls.filter(c=>c.method==='POST').length,2,'polling must never start a test');
el('execution-profile').value='final';el('execution-profile').onchange();
const inputs=el('execution-generation').querySelectorAll('*').filter(n=>n.tagName==='input');
inputs.find(n=>n.value==='baseline').checked=false;
inputs.find(n=>n.value==='candidate').checked=true;
inputs[0].onchange();
await el('execution-form').onsubmit({preventDefault(){}});
assert.deepEqual(JSON.parse(ui.calls.at(-1).body).generation,['candidate']);
const reloaded=await fixture({running:true});
assert(reloaded.calls.every(c=>c.method!=='POST'));
assert.equal(reloaded.nodes.get('execution-start').disabled,true);
assert.equal(reloaded.nodes.get('execution-cancel').disabled,false);
assert.equal(reloaded.events.length,0,'loading a running job must preserve the selected run');
const missing=await fixture({available:false});
assert.equal(missing.nodes.get('execution-start').disabled,true);
assert(missing.calls.every(c=>c.method!=='POST'));
console.log('dashboard controls: explicit start, CSRF, stop, polling, model selection, reload and missing-file checks passed');
