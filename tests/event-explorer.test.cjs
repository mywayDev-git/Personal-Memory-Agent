'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),http=require('node:http');
const {DatabaseSync}=require('node:sqlite'),{personal,api}=require('../ui/event-explorer.cjs');
const records=[
 ['a','11월 12일 민수와 A프로젝트 UI를 논의했다.'],
 ['b','11월 14일 12일 논의를 바탕으로 A프로젝트 첫 화면을 수정했다.'],
 ['c','11월 15일 민수와 B프로젝트 UI를 논의했다.'],
 ['d','조용한 카페를 선호한다.']
].map(([id,body])=>({id,title:id,revision:1,body,date:null}));
test('follow-up requires project and explicit reference, and each quote resolves to its source',()=>{
 const v=personal(records),links=v.edges.filter(e=>e.type==='후속 작업');
 assert.equal(links.length,1);assert.deepEqual(links[0].proof.map(p=>p.source),['a','b']);
 assert.equal(v.nodes.filter(n=>n.kind==='person'&&n.label==='민수').length,2);
 assert.ok(v.nodes.some(n=>n.kind==='claim'&&n.label.includes('선호')));
 for(const e of v.edges)for(const p of e.proof)assert.equal(v.sources[p.source].text.slice(p.start,p.end),p.quote);
});
test('review persists across rebuilding the graph and stale edits cannot replace it',async t=>{
 const db=new DatabaseSync(':memory:');t.after(()=>db.close());
 const library={db,read:()=>({records})};const handler=api(library,'');
 const server=http.createServer((req,res)=>handler(req,res,new URL(req.url,'http://localhost')));
 await new Promise(done=>server.listen(0,'127.0.0.1',done));t.after(()=>new Promise(done=>server.close(done)));
 const url='http://127.0.0.1:'+server.address().port+'/api/event-explorer';
 const state=()=>fetch(url).then(r=>r.json());const initial=await state(),edge=initial.view.edges.find(e=>e.type==='후속 작업');
 const post=(status,revision,label)=>fetch(url,{method:'POST',headers:{'X-Graph-Token':initial.token,'Content-Type':'application/json'},body:JSON.stringify({edge:edge.id,status,revision,label})});
 const one=await (await post('수정',0,'이전 논의 참조')).json();
 assert.equal((await post('거절',0,edge.type)).status,409);
 const two=await (await post('거절',one.history.at(-1).seq,'이전 논의 참조')).json();
 assert.equal((await state()).view.edges.find(e=>e.id===edge.id).history.at(-1).status,'거절');
 const undo=await (await post('undo',two.history.at(-1).seq,'')).json();assert.equal(undo.history.at(-1).label,'이전 논의 참조');assert.equal(undo.history.at(-1).status,'수정');
});
