const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const {retrieve}=require('../local/structured-retrieve.cjs'),{Engine}=require('../local/engine.cjs');

function fixture(){
 const units=[
  {id:'S1:U1',source_id:'A',revision:1,start:0,end:10,text:'민수와 발표 준비',summary_id:'S1',entities:[{name:'민수',aliases:[],entity_id:'E1'}],relations:[{relation_id:'R1',subject:'민수',object:'발표',predicate:'준비',subject_id:'E1',object_id:'E2'}]},
  {id:'S2:U1',source_id:'B',revision:1,start:0,end:7,text:'지연과 산책',summary_id:'S2',entities:[{name:'지연',aliases:[],entity_id:'E3'}],relations:[{relation_id:'R2',subject:'지연',object:'산책',predicate:'참여',subject_id:'E3',object_id:'E4'}]}
 ];
 let embeddings=0,lexical=0;
 const engine={summary:{units:()=>units,assertRetrieval:()=>{}},structured:{indexes:()=>[{index_id:'I1',units}],lexical:()=>{lexical++;return [{id:units[1].id}];}},vector:async()=>{embeddings++;return {vector:[1,0]};},update:()=>{},retrievalMetrics:()=>({}),store:{artifact:()=> 'retrieval-test'}};
 return {engine,counts:()=>({embeddings,lexical}),run:async(route,query)=>retrieve(engine,{config:{route,candidate_k:20,top_k:3,evidence_char_budget:6000}},{fingerprint:'test'},{id:'Q',text:query},{conversation:[]},[{id:'A',revision:1},{id:'B',revision:1}],{records:[],structured_indexes:[]},new AbortController().signal)};
}

test('M1 returns graph trace with hybrid results instead of a variable reference error',async()=>{
 const f=fixture(),result=await f.run('M1','민수는 무엇을 준비했어?');
 assert.equal(result.structured_trace.ranking_mode,'structured-hybrid');
 assert.deepEqual(result.structured_trace.graph_candidates.map(hit=>hit.id),['S1:U1']);
 assert.equal(result.evidence.length,2);
 assert.deepEqual(f.counts(),{embeddings:3,lexical:1});
});

test('G1 retrieves connected relations without embedding or lexical fallback',async()=>{
 const f=fixture(),result=await f.run('G1','민수는 무엇을 준비했어?');
 assert.equal(result.structured_trace.ranking_mode,'event-graph');
 assert.deepEqual(result.selected_sources.map(hit=>hit.source_id),['A']);
 assert.deepEqual(f.counts(),{embeddings:0,lexical:0});
 const missing=await f.run('G1','지원은 무엇을 했어?');
 assert.deepEqual(missing.evidence,[]);
 assert.deepEqual(f.counts(),{embeddings:0,lexical:0});
});

test('backend and demo prefer installed default 4B even when 9B is active',async()=>{
 const models=require('../local/model-registry.cjs');
 assert.deepEqual(models.filter(model=>model.role==='generation'&&model.default).map(model=>model.id),['qwen35-4b-q4']);
 assert.equal(Engine.prototype.config.call({root:process.cwd(),code_hash:'test'}).model,'qwen35-4b-q4');
 const source=fs.readFileSync(require.resolve('../demo-frontend/demo.js'),'utf8');
 const picker={value:'',add(){}},context={modelPicker:picker,updateDemoControls(){},demoJson:async()=>({runtime:{models:models.map(model=>({...model,present:true})),states:{generation:{status:'ready',model_id:'qwen35-9b-q8'}}}}),Option:function(){},showChatPrompt(){},homeStatus:{},chatStatus:{},saveStatus:{}};
 vm.runInNewContext(source.slice(source.indexOf('async function loadDemoModels()'),source.indexOf('async function withDemoRequest(')),context);
 await context.loadDemoModels();
 assert.equal(picker.value,'qwen35-4b-q4');
});
