const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),{pathToFileURL}=require('node:url');
const root=path.resolve(__dirname,'..'),dir=path.join(root,'datasets/pma-memory-v3.0.0'),libPromise=import(pathToFileURL(path.join(dir,'lib.mjs')).href);
const canonical=x=>Array.isArray(x)?x.map(canonical):x&&typeof x==='object'?Object.fromEntries(Object.keys(x).sort().map(k=>[k,canonical(x[k])])):x;
test('natural readings extend the existing ID with four original formats in both partitions',async()=>{
 const lib=await libPromise,d=lib.loadDataset(dir);assert.equal(d.manifest.dataset_version,'pma-memory-v3.0.0');assert.equal(d.manifest.content_revision,'natural-reading-r1');assert.deepEqual(lib.validate(d,dir).errors,[]);
 const docs=d.sources.records.filter(s=>s.provenance.natural_reading);assert.equal(docs.length,8);
 for(const split of ['development','final'])for(const form of ['narrative','transcript','email','mixed'])assert.equal(docs.filter(s=>s.split===split&&s.provenance.text_format===form).length,1);
 for(const s of docs){assert.ok(s.text.length>=1700);assert.ok(s.text.length<2000);assert.equal(s.provenance.contributors,undefined);assert.ok(s.gold.facts.length>=8);assert.ok(s.text.includes('\n\n'));assert.ok(!s.text.includes(' / 저장 2026-'));}
});
test('all previous 543 sources, 623 questions and other case objects survive byte-equivalent canonical JSON',async()=>{
 const lib=await libPromise,d=lib.loadDataset(dir),maps={sources:d.sources.records,questions:d.questions.questions,contexts:d.contexts.contexts,cases:d.cases.cases,relations:d.connections.relations};
 for(const [name,hashes]of Object.entries(d.editorial_review.natural_reading_revision.preserved_item_sha256)){
  const current=new Map(maps[name].map(x=>[x.id,x]));for(const [id,hash]of Object.entries(hashes)){assert.ok(current.has(id));assert.equal(crypto.createHash('sha256').update(JSON.stringify(canonical(current.get(id)))).digest('hex'),hash,id);}
 }
});
test('paragraph support spans bind all 48 questions while allowing both connected and direct checks',async()=>{
 const lib=await libPromise,d=lib.loadDataset(dir),questions=d.questions.questions.filter(q=>q.question_type==='natural_long_reading'),facts=new Map(d.sources.records.flatMap(s=>s.gold.facts.map(f=>[f.id,{s,f}])));
 assert.equal(questions.length,48);assert.ok(questions.filter(q=>q.gold.evidence_groups.length>1).length>=28);assert.ok(questions.some(q=>q.gold.evidence_groups.length===1));
 for(const q of questions){const c=d.contexts.contexts.find(c=>c.id===q.context_id);assert.equal(c.scope_kind,'natural_reading');assert.equal(c.expected_state.accessible_sources.length,1);for(const group of q.gold.evidence_groups)for(const id of group.any_of_fact_ids){const {s,f}=facts.get(id);for(const span of f.evidence)assert.equal(s.text.slice(span.start,span.end),span.quote);assert.equal(s.id,c.expected_state.accessible_sources[0].source_id);}}
});
test('reading annotations are review-only and never reach the model input',async()=>{
 const lib=await libPromise,d=lib.loadDataset(dir),{answerMessages}=require('../local/prompts.cjs'),{fullEvidence}=require('../local/raw-full.cjs');
 const q=d.questions.questions.find(q=>q.id==='NR-D-01-Q1'),c=d.contexts.contexts.find(c=>c.id===q.context_id),sources=lib.materialize(c,d.sources.records).accessible,p=JSON.parse(answerMessages({answer_prompt:'answer-grounded-v1'},q,c,fullEvidence(sources))[1].content);
 assert.equal(p.evidence[0].text,sources[0].text);assert.equal(p.question,q.text);for(const key of ['reading_skills','reference_answer','any_of_fact_ids','NR-D-01'])assert.equal(JSON.stringify(p).includes(key),false);
});
test('new profiles have complete offline vocabulary measurements and no inference claim',async()=>{
 const lib=await libPromise,d=lib.loadDataset(dir);for(const split of ['development','final']){const p='natural_reading_'+split;assert.equal(d.manifest.profiles[p],24);const rows=d.token_measurements.questions.filter(r=>r.profile===p);assert.equal(rows.length,24);assert.ok(rows.every(r=>r.full_eligible_offline));}
 assert.equal(d.manifest.model_execution,false);assert.equal(d.token_measurements.measurement.model_inference,false);
});
