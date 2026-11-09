const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=process.env.PMA_APP_ROOT||path.resolve(__dirname,'..');
const script=process.env.PMA_UI_SCRIPT||path.join(root,'baseline.js');
const ids=['pma-dev-v0.1.0','pma-dev-v0.2.0','pma-long-v1.0.1','pma-long-v2.0.0','pma-context-v1.0.0'];
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

test('both lists initially expose all 84 questions, including multi-source and short controls',async()=>{
 const h=harness();await h.run("loadDataset('pma-context-v1.0.0')");await h.run('openDatasetBrowser()');
 assert.equal(h.el('#question-count').textContent,'전체 84개 · 현재 조건 84개');
 assert.equal(h.el('#ds-list-count').textContent,h.el('#question-count').textContent);
 assert.equal(count(h.el('#question-list').innerHTML,'data-question'),84);
 assert.equal(count(h.el('#ds-list').innerHTML,'data-ds-item'),84);
 assert.ok(h.el('#ds-list').innerHTML.includes('NC-12-Q6'));
 assert.ok(h.el('#ds-list').innerHTML.includes('NC-12-CONTROL-Q1'));
 assert.equal(h.requests.length,1,'Browser reuses the selected workbench data');
});

test('the visible 24-question filter can be cleared and never survives browser reentry',async()=>{
 const h=harness();await h.run("loadDataset('pma-context-v1.0.0')");await h.run('openDatasetBrowser()');
 h.el('#ds-profile').value='natural_multi';h.el('#ds-profile').onchange({target:h.el('#ds-profile')});
 assert.equal(h.el('#ds-list-count').textContent,'전체 84개 · 현재 조건 24개');
 assert.equal(count(h.el('#ds-list').innerHTML,'data-ds-item'),24);
 await h.click({dsAction:'all-questions'});
 assert.equal(count(h.el('#ds-list').innerHTML,'data-ds-item'),84);
 h.run("datasetBrowser.profile='natural_multi';datasetBrowser.family='NC-09';datasetBrowser.query='하린';datasetBrowser.length='medium';dsRenderList()");
 await h.run('openDatasetBrowser()');
 assert.equal(h.el('#ds-profile').value,'');assert.equal(h.el('#ds-family').value,'');assert.equal(h.el('#ds-length').value,'');
 assert.equal(count(h.el('#ds-list').innerHTML,'data-ds-item'),84);
});

test('changing datasets in either screen updates the other selector, both lists and saved selection',async()=>{
 const h=harness();await h.run("loadDataset('pma-context-v1.0.0')");h.run("page='datasets'");await h.run('openDatasetBrowser()');
 await h.el('#ds-dataset').onchange({target:{value:'pma-dev-v0.2.0'}});
 assert.equal(h.el('#dataset').value,'pma-dev-v0.2.0');assert.equal(h.el('#ds-dataset').value,h.el('#dataset').value);
 assert.equal(h.el('#question-count').textContent,'전체 117개 · 현재 조건 117개');assert.equal(h.el('#ds-list-count').textContent,h.el('#question-count').textContent);
 assert.equal(count(h.el('#ds-list').innerHTML,'data-ds-item'),117);
 assert.equal(JSON.parse([...h.saved.values()][0]).dataset,'pma-dev-v0.2.0');
 await h.run("loadDataset('pma-context-v1.0.0')");
 assert.equal(h.el('#ds-dataset').value,'pma-context-v1.0.0');assert.equal(h.el('#ds-list-count').textContent,'전체 84개 · 현재 조건 84개');
});

test('workbench filters show total plus current count and the all-questions action clears every question filter',async()=>{
 const h=harness();await h.run("loadDataset('pma-context-v1.0.0')");
 h.run("datasetProfile='natural_multi';renderQuestions()");assert.equal(h.el('#question-count').textContent,'전체 84개 · 현재 조건 24개');
 h.el('#family').value='NC-09';h.el('#question-search').value='하린';h.run('renderQuestions()');
 await h.run('showAllQuestions()');assert.equal(h.el('#question-count').textContent,'전체 84개 · 현재 조건 84개');
 assert.equal(h.el('#family').value,'');assert.equal(h.el('#question-search').value,'');
});

test('opening a linked question in the workbench selects it without narrowing the whole list to 24',async()=>{
 const h=harness();await h.run("loadDataset('pma-context-v1.0.0')");await h.run('openDatasetBrowser()');
 await h.click({dsWorkbench:'NC-09-Q1'});
 assert.equal(h.run('questionId'),'NC-09-Q1');assert.equal(h.run('page'),'workspace');
 assert.equal(h.el('#question-count').textContent,'전체 84개 · 현재 조건 84개');
 assert.equal(count(h.el('#question-list').innerHTML,'data-question'),84);
});

test('a late response cannot overwrite the most recently selected dataset',async()=>{
 const h=harness();await h.run("loadDataset('pma-context-v1.0.0')");
 let resolve;h.deferred.set('pma-long-v1.0.1',new Promise(r=>resolve=r));
 const old=h.run("loadDataset('pma-long-v1.0.1')");await h.run("loadDataset('pma-dev-v0.2.0')");
 resolve({ok:true,json:async()=>fixture('pma-long-v1.0.1')});await old;
 assert.equal(h.el('#dataset').value,'pma-dev-v0.2.0');assert.equal(h.run('datasetBrowser.id'),'pma-dev-v0.2.0');
 assert.equal(h.el('#question-count').textContent,'전체 117개 · 현재 조건 117개');
});

test('failed selection retains the previous dataset and consistent selectors',async()=>{
 const h=harness();await h.run("loadDataset('pma-context-v1.0.0')");h.run("page='datasets'");await h.run('openDatasetBrowser()');
 h.deferred.set('pma-dev-v0.2.0',Promise.resolve({ok:false,json:async()=>({error:'조회 실패'})}));
 await h.el('#ds-dataset').onchange({target:{value:'pma-dev-v0.2.0'}});
 assert.equal(h.el('#dataset').value,'pma-context-v1.0.0');assert.equal(h.el('#ds-dataset').value,'pma-context-v1.0.0');
 assert.equal(h.el('#ds-list-count').textContent,'전체 84개 · 현재 조건 84개');assert.equal(h.el('#toast').textContent,'조회 실패');
});
