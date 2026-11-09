const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=process.env.PMA_APP_ROOT||path.resolve(__dirname,'..');
const script=process.env.PMA_UI_SCRIPT||path.join(root,'baseline.js');
const ids=['pma-dev-v0.1.0','pma-dev-v0.2.0','pma-long-v1.0.1','pma-long-v2.0.0','pma-context-v1.0.0','pma-memory-v3.0.0'];
function fixture(id){const d={fingerprint:id};for(const key of ['manifest','sources','contexts','questions','coverage','connections','token_measurements','cases'])d[key]=JSON.parse(fs.readFileSync(path.join(root,'datasets',id,key+'.json'),'utf8'));return d;}
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
 vm.runInContext(`boot={datasets:${JSON.stringify(ids)}};renderWorkspace=()=>{};renderStageHelp=()=>{};globalThis.savedDatasetDetail=dsRenderDetail;dsRenderDetail=()=>{};`,ctx);
 const run=s=>vm.runInContext(s,ctx);
 const click=async dataset=>{const button={dataset},event={target:{closest:s=>s.includes('[data-ds-')?button:null}};for(const fn of listeners.click||[])await fn(event);};
 return {el,run,click,requests,saved,deferred};
}
const count=(html,attr)=>(html.match(new RegExp(attr+'=','g'))||[]).length;


test('v3 browsing shows all 671 execution items and 551 source rows without starting a test',async()=>{const h=harness();await h.run("loadDataset('pma-memory-v3.0.0')");await h.run('openDatasetBrowser()');assert.equal(count(h.el('#question-list').innerHTML,'data-question'),671);assert.equal(count(h.el('#ds-list').innerHTML,'data-ds-item'),671);assert.ok(h.el('#long-dataset-info').innerHTML.includes('작성 원문 443개'));assert.ok(h.el('#long-dataset-info').innerHTML.includes('기본 질문 431개'));await h.click({dsView:'sources'});assert.equal(count(h.el('#ds-list').innerHTML,'data-ds-item'),551);assert.equal(h.requests.length,1);});
test('final long and token profiles are selectable with real source rows and token budget detail',async()=>{const h=harness();await h.run("loadDataset('pma-memory-v3.0.0')");await h.run('openDatasetBrowser()');h.el('#dataset-profile').value='single_final';await h.el('#dataset-profile').onchange();assert.equal(count(h.el('#question-list').innerHTML,'data-question'),36);assert.ok(h.el('#long-dataset-info').innerHTML.includes('토큰'));h.el('#ds-profile').value='tokens_final';h.el('#ds-profile').onchange({target:h.el('#ds-profile')});assert.equal(count(h.el('#ds-list').innerHTML,'data-ds-item'),16);await h.click({dsView:'sources'});assert.ok(count(h.el('#ds-list').innerHTML,'data-ds-item')>0);});
test('selecting a last dialogue turn expands its prerequisites and keeps their execution order',async()=>{const h=harness();await h.run("loadDataset('pma-memory-v3.0.0')");h.run("datasetProfile='dialogue_final';questionId='CHAT-final-T5'");h.el('#scope').value='one';assert.equal(JSON.stringify(h.run('chosenIds()')),JSON.stringify([1,2,3,4,5].map(n=>'CHAT-final-T'+n)));assert.equal(h.requests.length,1);});

test('natural reading is selected inside the same v3 dataset and profiles expose 24 questions each',async()=>{const h=harness();await h.run("loadDataset('pma-memory-v3.0.0')");const id=h.el('#dataset').value;for(const profile of ['natural_reading_development','natural_reading_final']){h.el('#dataset-profile').value=profile;await h.el('#dataset-profile').onchange();assert.equal(count(h.el('#question-list').innerHTML,'data-question'),24);assert.equal(h.el('#dataset').value,id);}assert.ok(h.el('#long-dataset-info').innerHTML.includes('natural-reading-r1'));assert.equal(h.requests.length,1);});
test('explorer shows the connected natural body, format and paragraph evidence with no model request',async()=>{const h=harness();await h.run("loadDataset('pma-memory-v3.0.0')");await h.run('openDatasetBrowser()');h.run("dsRenderDetail=savedDatasetDetail;datasetBrowser.selected='NR-D-01-Q1';dsRenderDetail()");const html=h.el('#ds-detail').innerHTML;assert.ok(html.includes('서술형 회고'));assert.ok(html.includes('문을 열자'));assert.ok(html.includes('문단 사이 정보 결합'));assert.ok(count(html,'data-ds-evidence')>=2);assert.ok(html.includes('3문단과 4문단'));assert.equal(h.requests.length,1);});
