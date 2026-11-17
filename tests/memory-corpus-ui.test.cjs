const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=process.env.PMA_APP_ROOT||path.resolve(__dirname,'..');
const script=process.env.PMA_UI_SCRIPT||path.join(root,'baseline.js');
const ids=['pma-dev-v0.1.0','pma-dev-v0.2.0','pma-long-v1.0.1','pma-long-v2.0.0','pma-context-v1.0.0','pma-memory-v2.0.0'];
function fixture(id){const d={fingerprint:id};for(const key of ['manifest','sources','contexts','questions','coverage'])d[key]=JSON.parse(fs.readFileSync(path.join(root,'datasets',id,key+'.json'),'utf8'));return d;}
function harness(){
 const elements=new Map(),listeners={},requests=[],saved=new Map(),deferred=new Map();
 class Element{
  constructor(){this.value='';this.textContent='';this.html='';this.options=[];this.dataset={};this.classList={toggle(){},add(){},remove(){}};}
  set innerHTML(s){this.html=s;const matches=[...s.matchAll(/<option value="([^"]*)"/g)];if(matches.length){this.options=matches.map(m=>({value:m[1]}));this.value=this.options[0].value;}}
  get innerHTML(){return this.html;}
  setAttribute(){} removeAttribute(){} addEventListener(){} scrollIntoView(){}
 }
 const el=s=>{if(!elements.has(s))elements.set(s,new Element());return elements.get(s);};
 const ctx=vm.createContext({console,setTimeout,clearTimeout,AbortSignal,Map,Set,URL,
  document:{querySelector:el,querySelectorAll:()=>[],body:{classList:{toggle(){}}},addEventListener:(event,fn)=>(listeners[event]??=[]).push(fn)},
  localStorage:{setItem:(k,v)=>saved.set(k,v),getItem:k=>saved.get(k)},
  MemoryTiming:{format:()=>'',elapsed:()=>0,isActive:()=>false},
  fetch:async(url,opts)=>{requests.push({url,opts});assert.ok(!opts?.method,'Selecting or browsing must never start or modify a run');const id=new URL(url,'http://local').searchParams.get('id');if(deferred.has(id))return deferred.get(id);assert.ok(ids.includes(id));return {ok:true,json:async()=>fixture(id)};}
 });
 vm.runInContext(fs.readFileSync(script,'utf8').replace('\ninitialize();','\n').replace('\ninitializeSelectionGuide();','\n'),ctx);
 vm.runInContext(`boot={datasets:${JSON.stringify(ids)}};renderWorkspace=()=>{};renderStageHelp=()=>{};dsRenderDetail=()=>{};`,ctx);
 const run=s=>vm.runInContext(s,ctx);
 const click=async dataset=>{const button={dataset},event={target:{closest:s=>s.includes('[data-ds-')?button:null}};for(const fn of listeners.click||[])await fn(event);};
 return {el,run,click,requests,saved,deferred};
}
const count=(html,attr)=>(html.match(new RegExp(attr+'=','g'))||[]).length;


test('new dataset exposes every execution item in both lists and all 288 originals',async()=>{
 const h=harness();await h.run("loadDataset('pma-memory-v2.0.0')");await h.run('openDatasetBrowser()');
 assert.equal(count(h.el('#question-list').innerHTML,'data-question'),360);assert.equal(count(h.el('#ds-list').innerHTML,'data-ds-item'),360);
 assert.equal(h.el('#question-count').textContent,'전체 360개 · 현재 조건 360개');assert.ok(h.el('#long-dataset-info').innerHTML.includes('기본 질문 288개 + 통제 입력 변형 72개'));
 await h.click({dsView:'sources'});assert.equal(count(h.el('#ds-list').innerHTML,'data-ds-item'),288);
 assert.equal(h.requests.length,1);assert.equal(h.el('#dataset').value,'pma-memory-v2.0.0');
});
test('new profiles filter independently and controlled source view reuses the 64 authored originals',async()=>{
 const h=harness();await h.run("loadDataset('pma-memory-v2.0.0')");await h.run('openDatasetBrowser()');
 for(const profile of ['development_a','development_b','final']){h.el('#dataset-profile').value=profile;await h.el('#dataset-profile').onchange();assert.equal(count(h.el('#question-list').innerHTML,'data-question'),96);}
 h.el('#ds-profile').value='controlled';h.el('#ds-profile').onchange({target:h.el('#ds-profile')});assert.equal(count(h.el('#ds-list').innerHTML,'data-ds-item'),72);
 await h.click({dsView:'sources'});assert.equal(count(h.el('#ds-list').innerHTML,'data-ds-item'),64);
 h.el('#ds-profile').value='final';h.el('#ds-profile').onchange({target:h.el('#ds-profile')});assert.equal(count(h.el('#ds-list').innerHTML,'data-ds-item'),96);
});
test('all-items selection exposes every question without loading a model',async()=>{
 const h=harness();await h.run("loadDataset('pma-memory-v2.0.0')");h.el('#scope').value='all';assert.equal(h.run('chosenIds().length'),360);assert.equal(h.requests.length,1);
});
