import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
export {materialize} from '../pma-dev-v0.1.0/lib.mjs';

export const hash = value => crypto.createHash('sha256').update(value).digest('hex');
export const utf16Offset = (text, offset) => Array.from(text).slice(0, offset).join('').length;
export function loadDataset(dir) {
 const read = name => JSON.parse(fs.readFileSync(path.join(dir, name), 'utf8'));
 return {manifest:read('manifest.json'),sources:read('sources.json'),contexts:read('contexts.json'),
  questions:read('questions.json'),coverage:read('coverage.json'),import_plans:read('import_plans.json')};
}

// This adapter deliberately permits unannotated actions/answers and missing
// author timestamps. It must not weaken the older dataset's separate validator.
export function validate(d, dir, {checkHashes=true}={}) {
 const errors=[];
 const check=(ok, message)=>{if(!ok) errors.push(message);};
 try {
  const read=name=>JSON.parse(fs.readFileSync(path.join(dir,name),'utf8'));
  const inputs=read('inputs.json'), annotations=read('annotations.json');
  const original=read('upstream/inputs.json'), oldAnnotations=read('upstream/annotations.json');
  const plans=read('import_plans.json');
  check(d.manifest.dataset_version==='pma-long-v1.0.1','dataset version');
  check(d.manifest.execution_input_path==='raw_original_v1','execution path must be explicit');
  check(d.manifest.model_execution===false && d.manifest.independent_gold===false,'no model/independent gold claims');
  check(d.manifest.partition.final.length===0,'development only');
  check(d.coverage.variables.length===0,'unmapped official variables');
  for(const [name,records] of Object.entries({inputs,annotations,sources:d.sources.records,contexts:d.contexts.contexts,questions:d.questions.questions})) {
   check(records.length===56 && new Set(records.map(r=>r.id)).size===56,name+' count/unique IDs');
  }
  const sources=d.sources.records, questions=d.questions.questions, contexts=d.contexts.contexts;
  const profileCounts={};let evidenceCount=0;
  for(let i=0;i<inputs.length;i++) {
   const x=inputs[i],a=annotations[i],up=original[i],upA=oldAnnotations[i];
   const s=sources.find(s=>s.provenance.upstream_case_id===x.id);
   const q=questions.find(q=>q.display_case_id===x.id),c=contexts.find(c=>c.id===q?.context_id);
   check(x.id===a.id && x.id===up.id && x.id===upA.id,x.id+' identity');
   check(JSON.stringify(a.input)===JSON.stringify({text:x.text,reference_time:x.reference_time,entry_mode:x.entry_mode}),x.id+' input/annotation match');
   check(a.metadata.characters===Array.from(x.text).length && a.metadata.utf8_bytes===Buffer.byteLength(x.text) && a.metadata.sha256===hash(x.text),x.id+' metadata');
   const changed=x.id==='LI-import-4001';
   check(changed?Array.from(x.text).length===4001:x.text===up.text,x.id+' upstream text preservation');
   check(x.reference_time===up.reference_time && x.entry_mode===up.entry_mode,x.id+' unchanged input metadata');
   check(JSON.stringify({...a,gold:{...a.gold,evidence:upA.gold.evidence},input:upA.input,metadata:upA.metadata})===JSON.stringify(upA),x.id+' unchanged semantic gold');
   check(s && q && c,x.id+' linked source/question/context');
   if(!s||!q||!c)continue;
   profileCounts[a.profile]=(profileCounts[a.profile]||0)+1;
   check(s.text===x.text && c.now===x.reference_time && s.metadata.document_reference_time===x.reference_time,x.id+' text/reference time');
   check(s.metadata.created_at===null && s.metadata.owner_is_author===false,x.id+' no invented author/time');
   check(/^LIS-[a-f0-9]{16}$/.test(s.id) && /^fixture-[a-f0-9]{16}$/.test(s.metadata.owner_id),x.id+' opaque model-facing IDs');
   check(!Object.keys(s.metadata).some(k=>/gold|profile|family|position|case|question|pair/.test(k)),x.id+' no labels in metadata');
   const expected=[{source_id:s.id,revision:1}];
   check(c.actor_id===s.metadata.owner_id && JSON.stringify(c.setup.initial_sources)===JSON.stringify(expected) && c.setup.steps.length===0,x.id+' scope isolation');
   check(JSON.stringify(c.expected_state.accessible_sources)===JSON.stringify(expected) && JSON.stringify(c.expected_state.active_sources)===JSON.stringify(expected),x.id+' expected scope');
   check(sources.filter(z=>z.metadata.owner_id===c.actor_id).length===1,x.id+' distinct fixture owner');
   check(q.text===a.gold.question && q.profile===a.profile && q.pair_group===a.pair_group && q.position===a.position,x.id+' question conditions');
   check(q.gold.reference_answer===null && q.gold.expected_action===null && q.gold.review_status==='AUTHOR_DRAFT',x.id+' no invented answer/action');
   for(const [key,originalKey] of [['required_claims','required_meanings'],['forbidden_claims','forbidden_inferences'],['structured_expectations','structured_expectations']])
    check(JSON.stringify(q.gold[key])===JSON.stringify(a.gold[originalKey]),x.id+' gold '+key);
   check(JSON.stringify(s.gold.structured_expectations)===JSON.stringify(a.gold.structured_expectations),x.id+' source gold');
   check(s.gold.facts.length===a.gold.evidence.length && q.gold.evidence_groups.length===a.gold.evidence.length,x.id+' evidence count');
   for(const [j,e] of a.gold.evidence.entries()) {
    const cp=Array.from(x.text),f=s.gold.facts[j],span=f?.evidence?.[0];evidenceCount++;
    check(cp.slice(e.start,e.end).join('')===e.quote,x.id+' codepoint evidence');
    check(span && span.start===utf16Offset(x.text,e.start) && span.end===utf16Offset(x.text,e.end) && x.text.slice(span.start,span.end)===e.quote && span.quote===e.quote && span.source_id===s.id && span.revision===s.revision,x.id+' UTF16 evidence');
    check(f.kind==='annotated_target_evidence_region' && f.statement===e.quote,x.id+' evidence is not full fact annotation');
    check(JSON.stringify(q.gold.evidence_groups[j].any_of_fact_ids)===JSON.stringify([f.id]),x.id+' required evidence link');
   }
   const plan=plans.cases.find(p=>p.case_id===x.id);
   check(plan?.status==='PLAN_ONLY_NOT_EXECUTED',x.id+' import plan only');
   if(plan) {
    let pos=0;const cp=Array.from(x.text);
    for(const r of plan.regions) {
     check(r.start===pos && r.end>r.start && r.end-r.start<=4000,x.id+' plan continuity');
     check(r.utf16_start===utf16Offset(x.text,r.start) && r.utf16_end===utf16Offset(x.text,r.end) && r.sha256===hash(cp.slice(r.start,r.end).join('')),x.id+' plan span/hash');pos=r.end;
    }
    check(pos===cp.length,x.id+' plan complete text');
    if(a.profile==='boundary') {
     check(cp.length===Number(x.id.split('-').at(-1)),x.id+' exact boundary length');
     if(cp.length>4000)check(a.gold.evidence.some(e=>e.start<plan.regions[0].end && e.end>plan.regions[0].end),x.id+' evidence crosses first cut');
    }
    if(a.profile==='dependency')check(a.gold.evidence.length===2 && !plan.regions.some(r=>a.gold.evidence.every(e=>r.start<=e.start && r.end>=e.end)),x.id+' distant evidence');
   }
  }
  check(evidenceCount===60 && d.manifest.counts.target_evidence_regions===60 && d.manifest.counts.source_facts===60,'60 evidence regions');
  for(const [key,count] of Object.entries(d.manifest.profiles))check(profileCounts[key]===count,'profile '+key);
  check(JSON.stringify(Object.keys(profileCounts).sort())===JSON.stringify(Object.keys(d.manifest.profiles).sort()),'all profiles registered');
  if(checkHashes)for(const f of d.manifest.integrity)check(hash(fs.readFileSync(path.join(dir,f.file)))===f.sha256,'hash '+f.file);
 } catch(e) {errors.push('dataset parsing: '+e.message);}
 return {ok:errors.length===0,errors};
}
