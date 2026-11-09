import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
export {materialize} from '../pma-dev-v0.1.0/lib.mjs';
export const hash=value=>crypto.createHash('sha256').update(value).digest('hex');
const same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
export function loadDataset(dir){const read=name=>JSON.parse(fs.readFileSync(path.join(dir,name),'utf8'));return {
 manifest:read('manifest.json'),sources:read('sources.json'),contexts:read('contexts.json'),questions:read('questions.json'),
 coverage:read('coverage.json'),cases:read('cases.json'),connections:read('connections.json'),import_plans:read('import_plans.json')};}
export function validate(d,dir,{checkHashes=true}={}){
 const errors=[];let checks=0;const ok=(value,message)=>{checks++;if(!value)errors.push(message);};
 try{
  const read=name=>JSON.parse(fs.readFileSync(path.join(dir,name),'utf8'));
  const inputs=read('inputs.json'),annotations=read('annotations.json'),inventory=read('sentence_inventory.json').records;
  const ss=d.sources.records,qq=d.questions.questions,cc=d.contexts.contexts,cases=d.cases.cases,edges=d.connections.relations;
  const sm=new Map(ss.map(s=>[s.id,s])),qm=new Map(qq.map(q=>[q.id,q])),cm=new Map(cc.map(c=>[c.id,c]));
  const facts=new Map(ss.flatMap(s=>s.gold.facts.map(f=>[f.id,{...f,source:s}])));
  for(const [name,items] of Object.entries({sources:ss,questions:qq,contexts:cc,cases,inputs,annotations,connections:edges}))ok(new Set(items.map(x=>x.id)).size===items.length,name+' unique IDs');
  ok(d.manifest.dataset_version==='pma-long-v2.0.0','dataset version');
  ok(d.manifest.execution_input_path==='raw_original_v1'&&d.manifest.model_execution===false&&d.manifest.independent_gold===false,'execution and review boundaries');
  ok(ss.length===84&&cc.length===80&&qq.length===140&&inputs.length===84&&annotations.length===80,'composition counts');
  ok(cases.length===12&&cases.filter(c=>c.domain==='work').length===6&&cases.filter(c=>c.domain==='life').length===6,'12 narratives; work/life 6 each');
  ok(cases.filter(c=>c.profile==='natural_single').length===8&&cases.filter(c=>c.profile==='natural_multi').length===4,'single/multiple source cases');
  ok(d.manifest.partition.final.length===0&&d.coverage.variables.length===0,'development only, no fabricated official mapping');
  const spanCheck=(e,label)=>{const s=sm.get(e.source_id);ok(s&&s.revision===e.revision&&Number.isInteger(e.start)&&Number.isInteger(e.end)&&e.start>=0&&e.end>e.start&&s.text.slice(e.start,e.end)===e.quote,label+' exact span');};
  for(const s of ss){
   const input=inputs.find(i=>i.id===s.provenance.upstream_case_id);
   ok(input?.text===s.text,s.id+' raw input binding');
   ok(s.gold.review_status==='AUTHOR_DRAFT',s.id+' draft gold');
   for(const f of s.gold.facts){ok(typeof f.statement==='string'&&!!f.statement.trim()&&f.evidence.length>0,f.id+' meaning/evidence');for(const e of f.evidence)spanCheck(e,f.id);}
   if(s.provenance.case_id){
    ok(/^NIS-[a-f0-9]{16}$/.test(s.id)&&/^fixture-[a-f0-9]{16}$/.test(s.metadata.owner_id),s.id+' opaque model-facing IDs');
    ok(s.metadata.synthetic_timestamp===true&&Number.isFinite(Date.parse(s.metadata.created_at)),s.id+' explicit fixture timestamp');
    ok(!Object.keys(s.metadata).some(k=>/gold|question|profile|family|pair|case|expected|answer/.test(k)),s.id+' no gold labels in model metadata');
    ok(s.provenance.model_tokens===null,s.id+' token count not invented');
    for(const f of s.gold.facts)ok(f.evidence.every(e=>e.source_id===s.id),f.id+' source extraction uses only its own input');
   }
  }
  for(const c of cc){
   const refs=c.expected_state.accessible_sources,keys=refs.map(r=>r.source_id+':'+r.revision);
   ok(c.setup.steps.length===0&&same(c.setup.initial_sources,refs)&&same(c.expected_state.active_sources,refs),c.id+' fixed scope');
   ok(keys.length>0&&new Set(keys).size===keys.length,c.id+' unique nonempty scope');
   for(const r of refs)ok(sm.get(r.source_id)?.revision===r.revision&&sm.get(r.source_id)?.metadata.owner_id===c.actor_id,c.id+' owner/revision');
   ok(ss.filter(s=>s.metadata.owner_id===c.actor_id).length===refs.length,c.id+' no outside-case/control leakage');
  }
  for(const q of qq){
   const c=cm.get(q.context_id),scope=new Set(c?.expected_state.accessible_sources.map(r=>r.source_id));
   ok(!!c,q.id+' context');ok(Array.isArray(q.gold.required_claims)&&q.gold.required_claims.length>0,q.id+' required meanings');
   for(const g of q.gold.evidence_groups){ok(g.any_of_fact_ids.length>0,q.id+' nonempty evidence group');for(const id of g.any_of_fact_ids){const f=facts.get(id);ok(f&&scope.has(f.source.id)&&f.evidence.every(e=>scope.has(e.source_id)),q.id+' evidence accessible '+id);}}
   if(q.profile.startsWith('natural_')){
    ok(typeof q.gold.reference_answer==='string'&&q.gold.reference_answer.trim().length>0,q.id+' authored reference');
    ok(['answer','partial_answer','abstain','clarify','report_conflict','deny'].includes(q.gold.expected_action),q.id+' response action');
    ok(q.gold.review_status==='AUTHOR_DRAFT'&&q.gold.annotation_status.reference_answer==='AUTHOR_DRAFT',q.id+' not independently verified');
   }
   if(q.profile==='natural_control'){
    const parent=qm.get(q.variant?.paired_question_id);
    ok(parent&&parent.pair_group===q.pair_group&&parent.context_id!==q.context_id,q.id+' separate paired context');
    for(const k of ['reference_answer','expected_action','required_claims','forbidden_claims','structured_expectations'])ok(same(parent?.gold[k],q.gold[k]),q.id+' target gold preserved '+k);
    ok(parent?.text===q.text,q.id+' paired question unchanged');
   }
  }
  for(const c of cases){
   const q=c.question_ids.map(id=>qm.get(id));ok(q.length===6&&q.every(x=>x?.family_id===c.id&&x.context_id===c.context_id),c.id+' six questions one context');
   ok(c.source_refs.length===(c.profile==='natural_single'?1:2),c.id+' original count');
   ok(c.characters===c.source_refs.reduce((n,r)=>n+Array.from(sm.get(r.source_id).text).length,0),c.id+' measured characters');
   const first=q[0],evidence=first.gold.evidence_groups.flatMap(g=>g.any_of_fact_ids.map(id=>facts.get(id)));
   ok(evidence.length>=2,c.id+' first question connects multiple meaning bundles');
   if(c.profile==='natural_multi')ok(new Set(evidence.map(f=>f.source.id)).size===2,c.id+' first question requires both originals');
   ok(qm.get(c.id+'-CONTROL-Q1')?.variant.paired_question_id===first.id,c.id+' paired counterpart present');
  }
  const naturalSources=ss.filter(s=>s.provenance.profile==='natural_single'||s.provenance.profile==='natural_multi');
  const allSentences=new Set();
  for(const s of naturalSources){
   const rows=inventory.filter(r=>r.source_id===s.id);ok(rows.length>0,s.id+' complete authored line inventory');
   const paragraphs=new Map();for(const row of rows){spanCheck(row.evidence,s.id+' inventory');const paragraph=paragraphs.get(row.paragraph)||[];paragraph.push(row.evidence.quote);paragraphs.set(row.paragraph,paragraph);ok(!allSentences.has(row.evidence.quote),s.id+' no repeated full sentence filler');allSentences.add(row.evidence.quote);ok(row.fact_ids.length>0&&row.fact_ids.every(id=>facts.get(id)?.source.id===s.id),s.id+' line meaning binding');}
   ok([...paragraphs.values()].map(p=>p.join(' ')).join('\n\n')===s.text,s.id+' every authored sentence represented');
   ok(!/정리 메모 \d+:|제본 견본의 가장자리를 살피고 색상표의 명도/.test(s.text),s.id+' no v1 padding');
  }
  for(const edge of edges){const from=facts.get(edge.from_fact_id),to=facts.get(edge.to_fact_id),context=cm.get(edge.context_id);ok(from&&to&&from.source.family_id===edge.case_id&&to.source.family_id===edge.case_id,edge.id+' case-local connection');ok(edge.review_status==='AUTHOR_DRAFT'&&!!edge.statement,edge.id+' draft meaning');for(const e of edge.evidence){spanCheck(e,edge.id);ok(context.expected_state.accessible_sources.some(r=>r.source_id===e.source_id),edge.id+' source in scope');}}
  for(const [key,count] of Object.entries(d.manifest.profiles))ok(qq.filter(q=>q.profile===key).length===count,'profile count '+key);
  ok(d.manifest.counts.source_facts===facts.size&&d.manifest.counts.new_sentence_meaning_bundles===inventory.length&&d.manifest.counts.source_relations===edges.length,'annotation counts');
  // Old controls must remain exactly the same objects; their prior scores are not rewritten.
  const pinned=path.join(dir,'..','pma-long-v1.0.1'),oldread=name=>JSON.parse(fs.readFileSync(path.join(pinned,name),'utf8'));
  ok(hash(fs.readFileSync(path.join(pinned,'manifest.json')))===d.manifest.provenance.pinned_manifest_sha256,'pinned v1 manifest');
  for(const [file,items,key] of [['sources.json',ss,'records'],['contexts.json',cc,'contexts'],['questions.json',qq,'questions']])for(const old of oldread(file)[key])ok(same(items.find(x=>x.id===old.id),old),'v1 preserved '+old.id);
  for(const old of oldread('inputs.json'))ok(same(inputs.find(x=>x.id===old.id),old),'v1 input preserved '+old.id);
  if(checkHashes){for(const file of d.manifest.integrity){ok(/^[a-z_]+\.(json|mjs|md)$|^README\.md$/.test(file.file),'allowed integrity file');if(!file.file.includes('/')&&!file.file.includes('\\'))ok(hash(fs.readFileSync(path.join(dir,file.file)))===file.sha256,'hash '+file.file);}
   for(const [name,key] of [['natural_cases.py','authoring_sha256'],['build-natural-dataset.py','builder_sha256']])ok(hash(fs.readFileSync(path.join(dir,'..','..','tools',name)))===d.manifest.provenance[key],'authoring/build code '+name);
  }
 }catch(e){errors.push('dataset validation exception: '+e.message);}
 return {ok:errors.length===0,errors,checks};
}
