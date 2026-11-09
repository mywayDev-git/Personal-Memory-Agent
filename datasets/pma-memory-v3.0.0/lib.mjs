import fs from 'node:fs';import path from 'node:path';import crypto from 'node:crypto';
export const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
export function loadDataset(dir){return Object.fromEntries(['manifest','sources','contexts','questions','coverage','cases','connections','token_measurements','editorial_review'].map(n=>[n,JSON.parse(fs.readFileSync(path.join(dir,n+'.json'),'utf8'))]));}
export function materialize(c,sources){
 const byId=new Map(sources.map(s=>[s.id,s])),active=new Map(),deleted=new Map(),acl=new Map(),trace=[];
 const get=id=>{const s=byId.get(id);if(!s)throw Error('Unknown source '+id);return s;};
 for(const r of c.setup.initial_sources){const s=get(r.source_id);if(s.revision!==r.revision)throw Error('Wrong source revision');active.set(s.id,s);}
 for(const step of c.setup.steps){
  if(step.action==='replace'){if(!active.has(step.old_source))throw Error('Replace inactive source');active.delete(step.old_source);const s=get(step.new_source);active.set(s.id,s);}
  else if(step.action==='delete'){if(!active.has(step.source_id))throw Error('Delete inactive source');deleted.set(step.source_id,active.get(step.source_id));active.delete(step.source_id);}
  else if(step.action==='restore'){if(!deleted.has(step.source_id))throw Error('Restore non-deleted source');active.set(step.source_id,deleted.get(step.source_id));deleted.delete(step.source_id);}
  else if(step.action==='grant'||step.action==='revoke'){get(step.source_id);if(!acl.has(step.source_id))acl.set(step.source_id,new Set());if(step.action==='grant')acl.get(step.source_id).add(step.actor_id);else acl.get(step.source_id).delete(step.actor_id);}
  else if(step.action==='chat_input'){const s=get(step.source_id);if(step.store===true){if(s.text.includes('기억하지 마')||!s.text.includes('기억해줘'))throw Error('Consent mismatch');active.set(s.id,s);}else if(step.store!==false)throw Error('Explicit store policy required');}
  else if(step.action!=='new_session')throw Error('Unknown transition '+step.action);
  trace.push({...step,active_source_ids:[...active.keys()],scope:'synthetic fixture; personal DB and product cache not observed'});
 }
 const current=[...active.values()].filter(s=>Date.parse(s.metadata.imported_at)<=Date.parse(c.now));
 return {active:current,accessible:current.filter(s=>s.metadata.owner_id===c.actor_id||acl.get(s.id)?.has(c.actor_id)),trace};
}
export function validate(d,dir,{checkHashes=true}={}){
 const errors=[];let checks=0;const ok=(v,m)=>{checks++;if(!v)errors.push(m);};
 try{
  const ss=d.sources.records,qq=d.questions.questions,cc=d.contexts.contexts,sm=new Map(ss.map(s=>[s.id,s])),cm=new Map(cc.map(c=>[c.id,c])),qm=new Map(qq.map(q=>[q.id,q])),facts=new Map(ss.flatMap(s=>s.gold.facts.map(f=>[f.id,{...f,source:s}])));
  ok(d.manifest.dataset_version==='pma-memory-v3.0.0','version');
  for(const [name,rows]of Object.entries({sources:ss,questions:qq,contexts:cc,cases:d.cases.cases,relations:d.connections.relations}))ok(new Set(rows.map(x=>x.id)).size===rows.length,name+' unique IDs');
  const span=(e,m)=>{const s=sm.get(e.source_id);ok(s&&s.revision===e.revision&&e.start>=0&&e.end>e.start&&s.text.slice(e.start,e.end)===e.quote,m+' exact UTF16 span');};
  for(const s of ss){
   const sentences=s.text.split(/(?<=[.!?])\s+/u).map(t=>t.trim()).filter(Boolean);ok(new Set(sentences).size===sentences.length,s.id+' no repeated complete sentence');
   ok(s.text.trim()&&s.gold.review_status==='AUTHOR_DRAFT',s.id+' authored text and draft');
   ok(Date.parse(s.metadata.created_at)<=Date.parse(s.metadata.imported_at),s.id+' creation before import');
   ok(!Object.keys(s.metadata).some(k=>/gold|expected|question|profile|split|family|case/.test(k)),s.id+' no oracle metadata');
   for(const f of s.gold.facts)for(const e of f.evidence){span(e,f.id);ok(e.source_id===s.id,f.id+' local evidence');}
   for(const h of s.gold.highlights)span({...h,source_id:s.id,revision:s.revision},s.id+' lexical mark');
   if(s.provenance.kind==='derived_export'){
    ok(s.text.length===s.provenance.target_characters,s.id+' exact length without cutting');
    ok(s.provenance.body_characters+s.provenance.header_characters===s.text.length,s.id+' body/header length');
    for(const r of s.provenance.contributors)ok(sm.get(r.source_id)?.split===s.split&&sm.get(r.source_id)?.metadata.owner_id===s.metadata.owner_id,s.id+' no cross-user/partition export');
   }
  }
  for(const c of cc){const state=materialize(c,ss),refs=x=>x.map(s=>({source_id:s.id,revision:s.revision}));ok(JSON.stringify(refs(state.active))===JSON.stringify(c.expected_state.active_sources),c.id+' active state');ok(JSON.stringify(refs(state.accessible))===JSON.stringify(c.expected_state.accessible_sources),c.id+' access state');ok(state.active.every(s=>s.split===c.split),c.id+' partition isolation');
   ok(new Set(state.active.map(s=>s.id)).size===state.active.length,c.id+' no duplicate source');
   if(c.scope_kind==='cumulative'){const full=ss.filter(s=>s.provenance.kind==='authored_note'&&s.metadata.owner_id===c.actor_id&&Date.parse(s.metadata.imported_at)<=Date.parse(c.now)).map(s=>s.id).sort();ok(JSON.stringify(full)===JSON.stringify(state.accessible.map(s=>s.id).sort()),c.id+' all memories available at timestamp, no relevance prefilter');}
  }
  for(const q of qq){const c=cm.get(q.context_id);ok(c&&c.split===q.split,q.id+' context');if(!c)continue;const ids=new Set(c.expected_state.accessible_sources.map(r=>r.source_id));
   ok(!!q.gold.reference_answer&&q.gold.required_claims.length>0,q.id+' reference meaning');
   for(const g of q.gold.evidence_groups){ok(g.any_of_fact_ids.length>0,q.id+' nonempty evidence group');for(const f of g.any_of_fact_ids)ok(ids.has(facts.get(f)?.source.id),q.id+' accessible support');}
   if(/^같은 (기간|범위)/.test(q.text))ok(c.conversation.some(t=>/\d+월/.test(t.text)),q.id+' relative scope has antecedent');
   if(q.variant?.parent_question_id){const p=qm.get(q.variant.parent_question_id);ok(p&&p.text===q.text&&p.gold.reference_answer===q.gold.reference_answer,q.id+' invariant target');}
   if(q.snapshot?.kind==='cumulative_snapshot')ok(c.expected_state.accessible_sources.reduce((n,r)=>n+sm.get(r.source_id).text.length,0)>=q.snapshot.threshold_body_characters,q.id+' actual body length threshold');
   if(c.dialogue){for(const dep of c.dialogue.depends_on)ok(qm.has(dep)&&cm.get(qm.get(dep).context_id).dialogue.id===c.dialogue.id,q.id+' real dialogue dependency');}
  }
  const natural=ss.filter(s=>s.provenance.natural_reading),readingQuestions=qq.filter(q=>q.question_type==='natural_long_reading');
  if(d.manifest.content_revision==='natural-reading-r1'){
   ok(natural.length===8&&readingQuestions.length===48,'natural reading originals and questions');
   for(const split of ['development','final'])for(const format of ['narrative','transcript','email','mixed']){const docs=natural.filter(s=>s.split===split&&s.provenance.text_format===format);ok(docs.length===1,'one natural form per partition '+split+' '+format);}
   for(const s of natural){ok(s.text.length>=1600&&s.text.length<=2600,s.id+' natural length range, no exact-length padding');ok(s.gold.facts.length>=8,s.id+' authored paragraphs');ok(s.provenance.kind==='authored_note'&&!s.provenance.contributors,s.id+' independently written original, no exported notes');ok(!s.text.includes(' / 저장 2026-'),s.id+' no machine note envelopes');}
   ok(readingQuestions.filter(q=>q.gold.evidence_groups.length>1).length>=28,'connected and direct reading questions coexist');
  }
  const pos=qq.filter(q=>q.variant?.kind==='position');ok(pos.length===72,'72 position conditions');ok(new Set(pos.map(q=>JSON.stringify([q.text,cm.get(q.context_id).setup.initial_sources]))).size===72,'all 72 input orders distinct');
  for(const sp of ['development','final']){
   const long=qq.filter(q=>q.profile==='single_'+sp),sentence=qq.filter(q=>q.profile==='sentence_'+sp);ok(long.length===36&&sentence.length===6,sp+' all long stages and positions');
   ok(qq.some(q=>q.profile==='dialogue_'+sp)&&qq.some(q=>q.profile==='state_'+sp)&&qq.some(q=>q.profile==='distance_'+sp)&&qq.some(q=>q.profile==='tokens_'+sp),sp+' matched ability families');
   ok(qq.some(q=>q.split===sp&&q.gold.expected_action==='partial_answer'),sp+' partial answer');
   const g=qq.find(q=>q.id==='GROW-'+sp+'-24000');ok(g&&g.snapshot.actual_body_characters>=24000,sp+' full memory body at least 24000 characters');
  }
  for(const e of d.connections.relations){ok(facts.has(e.from_fact_id)&&facts.has(e.to_fact_id)&&cm.has(e.context_id),e.id+' relationship endpoints');for(const ev of e.evidence)span(ev,e.id);}
  for(const [id,n]of Object.entries(d.manifest.profiles)){ok(qq.filter(q=>q.profile===id).length===n,'profile count '+id);ok(n<=150,'profile within run limit '+id);}
  ok(d.coverage.variables.length===489&&d.coverage.variables.every(v=>v.full_variable_verified===false),'no fabricated official coverage');
  for(const v of d.coverage.variables)for(const id of v.question_ids)ok(qm.get(id)?.variables.includes(v.id),v.id+' question binding');
  const counts={sources:ss.length,authored_notes:ss.filter(s=>s.provenance.kind==='authored_note').length,fixture_sources:ss.filter(s=>s.provenance.kind==='fixture_note').length,derived_exports:ss.filter(s=>s.provenance.kind==='derived_export').length,questions:qq.length,base_questions:qq.filter(q=>!q.variant).length,controlled_variants:qq.filter(q=>q.variant).length,contexts:cc.length,families:d.cases.cases.length,source_facts:facts.size,source_relations:d.connections.relations.length};for(const [k,v]of Object.entries(counts))ok(d.manifest.counts[k]===v,'manifest '+k);
  ok(d.token_measurements.measurement.model_inference===false&&d.token_measurements.questions.length===qq.length,'offline token measurements');
  for(const s of ss)ok(d.token_measurements.source_text_sha256[s.id]===hash(s.text),s.id+' measured tokens bound to exact text');
  const measuredContexts=new Map();for(const c of cc){const e=c.expected_state.accessible_sources.map((r,i)=>{const s=sm.get(r.source_id);return {evidence_id:'E'+(i+1),source_id:s.id,revision:s.revision,start:0,end:s.text.length,text:s.text,metadata:s.metadata,origin:'raw_full',unit_id:s.id+':FULL'};});measuredContexts.set(c.id,hash(JSON.stringify(e)));}
  for(const row of d.token_measurements.questions){ok(row.evidence_json_sha256===measuredContexts.get(row.context_id),row.question_id+' measured evidence snapshot');const q=qm.get(row.question_id),c=cm.get(row.context_id);ok(row.question_seed_sha256===hash(JSON.stringify({question:q.text,now:c.now,actor_id:c.actor_id,conversation:c.conversation,evidence_json_sha256:row.evidence_json_sha256})),row.question_id+' measured question and conversation');}
  if(checkHashes){for(const x of d.manifest.integrity){ok(/^[a-zA-Z_]+\.(json|mjs|md|py)$/.test(x.file),'safe integrity file');ok(hash(fs.readFileSync(path.join(dir,x.file)))===x.sha256,'hash '+x.file);}ok(hash(fs.readFileSync(path.join(dir,'definition.json')))===d.manifest.provenance.definition_sha256,'definition hash');}
 }catch(e){errors.push('validation exception '+e.message);}
 return {ok:errors.length===0,checks,errors};
}
