import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
export const sha256 = x => crypto.createHash('sha256').update(x).digest('hex');
export function loadDataset(dir) {
 const read=n=>JSON.parse(fs.readFileSync(path.join(dir,n),'utf8'));
 return {manifest:read('manifest.json'),sources:read('sources.json'),contexts:read('contexts.json'),questions:read('questions.json'),coverage:read('coverage.json')};
}
export function materialize(context,sources) {
 const byId=new Map(sources.map(s=>[s.id,s])), active=new Set(context.setup.initial_sources.map(s=>s.source_id)), deleted=new Set(), trace=[];
 for(const step of context.setup.steps){
  if(step.action==='replace'){
   if(!active.has(step.old_source))throw Error(context.id+': replace inactive source');
   active.delete(step.old_source);active.add(step.new_source);
  }else if(step.action==='delete'){
   if(!active.has(step.source_id))throw Error(context.id+': delete inactive source');
   active.delete(step.source_id);deleted.add(step.source_id);
  }else if(step.action==='restore'){
   if(!deleted.has(step.source_id))throw Error(context.id+': restore non-deleted source');
   deleted.delete(step.source_id);active.add(step.source_id);
  }else if(step.action==='chat_input'){
   const source=byId.get(step.source_id);
   // The fixture's explicit consent policy is a declared product contract, not a model answer.
   if(step.storage_policy!=='explicit_consent_only')throw Error('Unknown consent policy');
   if(source.text.includes('기억하지 마')){}else if(source.text.includes('기억해줘'))active.add(source.id);else throw Error('Unspecified consent input');
  }else if(!['new_session','query'].includes(step.action))throw Error('Unknown setup action '+step.action);
  trace.push({action:step.action,active_source_ids:[...active]});
 }
 const available=[...active].map(id=>{const s=byId.get(id);if(!s)throw Error('Unknown active source '+id);return s;});
 return {active:available,accessible:available.filter(s=>s.metadata.owner_id===context.actor_id),trace};
}
export function validate(d,dir,{checkHashes=true}={}) {
 const errors=[];let checks=0;
 const ok=(v,msg)=>{checks++;if(!v)errors.push(msg);};
 function unique(items,label){const ids=items.map(x=>x.id);ok(new Set(ids).size===ids.length,label+' duplicate IDs');}
 const ss=d.sources.records,cc=d.contexts.contexts,qq=d.questions.questions,ff=d.manifest.families;
 for(const [items,name] of [[ss,'source'],[cc,'context'],[qq,'question'],[ff,'family']])unique(items,name);
 const sm=new Map(ss.map(s=>[s.id,s])),cm=new Map(cc.map(c=>[c.id,c])),qm=new Map(qq.map(q=>[q.id,q])),fm=new Map(ff.map(f=>[f.id,f])),facts=new Map();
 const variableIds=new Set(d.coverage.variables.map(v=>v.variable_id));
 ok(variableIds.size===489,'expected original 489-variable registry');
 const span=(e,s,label)=>{ok(!!s,label+' source missing');if(!s)return;ok(e.revision===s.revision,label+' revision mismatch');ok(Number.isInteger(e.start)&&Number.isInteger(e.end)&&e.start>=0&&e.end>e.start&&e.end<=s.text.length,label+' offsets invalid');ok(s.text.slice(e.start,e.end)===e.quote,label+' quote mismatch');};
 for(const s of ss){
  ok(fm.has(s.family_id),s.id+' family missing');ok(s.split==='development',s.id+' unexpected partition');
  ok(s.text.trim().length>0,s.id+' empty source');ok(!Number.isNaN(Date.parse(s.metadata.created_at)),s.id+' invalid timestamp');
  if(s.provenance.kind==='existing_development_source')ok(s.provenance.upstream_split==='development',s.id+' upstream holdout leak');
  for(const f of s.gold.facts){ok(!facts.has(f.id),f.id+' duplicate fact');facts.set(f.id,{...f,source_id:s.id});ok(f.statement.trim().length>0,f.id+' empty proposition');ok(f.evidence.length>0,f.id+' missing evidence');for(const e of f.evidence){ok(e.source_id===s.id,f.id+' cross-source fact span');span(e,sm.get(e.source_id),f.id);}}
  unique(s.gold.highlights,s.id+' highlights');for(const h of s.gold.highlights)span({...h,revision:s.revision},s,h.id);
 }
 const states=new Map();
 for(const c of cc){
  ok(fm.has(c.family_id),c.id+' family missing');ok(c.split==='development',c.id+' partition mismatch');ok(!Number.isNaN(Date.parse(c.now)),c.id+' invalid now');
  for(const r of [...c.setup.initial_sources,...c.expected_state.active_sources,...c.expected_state.accessible_sources]){ok(sm.has(r.source_id),c.id+' unknown source');if(sm.has(r.source_id)){ok(sm.get(r.source_id).revision===r.revision,c.id+' wrong source revision');ok(sm.get(r.source_id).family_id===c.family_id,c.id+' cross-family contamination');}}
  for(const step of c.setup.steps){for(const key of ['source_id','old_source','new_source'])if(step[key])ok(sm.has(step[key]),c.id+' unknown step source');if(step.question_id)ok(qm.has(step.question_id),c.id+' unknown prerequisite question');}
  try{const state=materialize(c,ss);states.set(c.id,state);const ids=arr=>arr.map(x=>x.id||x.source_id).sort().join('|');ok(ids(state.active)===ids(c.expected_state.active_sources),c.id+' active state mismatch');ok(ids(state.accessible)===ids(c.expected_state.accessible_sources),c.id+' authorization state mismatch');}catch(e){ok(false,e.message);}
  for(const t of c.conversation){for(const r of t.source_refs||[])ok(sm.has(r.source_id),c.id+' conversation source missing');for(const r of t.items||[])ok(sm.has(r.source_id),c.id+' result source missing');if(t.selected_result_id)ok(c.conversation.some(h=>(h.items||[]).some(i=>i.result_id===t.selected_result_id)),c.id+' selection not in displayed results');}
 }
 const actions=new Set(['answer','partial_answer','abstain','clarify','report_conflict','deny']);
 for(const q of qq){
  const c=cm.get(q.context_id),state=states.get(q.context_id);ok(!!c,q.id+' context missing');if(!c)continue;
  ok(c.family_id===q.family_id,q.id+' wrong family');ok(q.text.trim().length>0&&q.gold.reference_answer.trim().length>0,q.id+' missing text or answer');ok(q.gold.required_claims.length>0,q.id+' no answer claims');ok(actions.has(q.gold.expected_action),q.id+' unknown action');
  for(const v of q.variables)ok(variableIds.has(v),q.id+' unknown variable '+v);
  if(q.variant){ok(q.variant.of!==q.id,q.id+' self variant');ok(qm.has(q.variant.of),q.id+' unknown baseline');if(qm.has(q.variant.of))ok(qm.get(q.variant.of).family_id===q.family_id,q.id+' cross-family variant');}
  for(const g of q.gold.evidence_groups){ok(g.any_of_fact_ids.length>0,q.id+' empty evidence group');for(const fid of g.any_of_fact_ids){const f=facts.get(fid);ok(!!f,q.id+' missing fact '+fid);if(f&&state)ok(state.accessible.some(s=>s.id===f.source_id),q.id+' inaccessible or stale gold '+fid);}}
  if(q.gold.expected_action==='answer')ok(q.gold.evidence_groups.length>0,q.id+' answer lacks source evidence');
 }
 for(const r of d.sources.relations){ok(sm.has(r.from_source_id)&&sm.has(r.to_source_id),r.id+' missing endpoint');if(sm.has(r.from_source_id)&&sm.has(r.to_source_id))ok(sm.get(r.from_source_id).family_id===sm.get(r.to_source_id).family_id,r.id+' cross-family relation');}
 for(const f of ff){ok(qq.some(q=>q.family_id===f.id),f.id+' no question');ok(cc.some(c=>c.family_id===f.id),f.id+' no context');}
 const counts=d.manifest.counts;
 for(const [key,value]of Object.entries({families:ff.length,sources:ss.length,contexts:cc.length,questions:qq.length,source_facts:facts.size,source_relations:d.sources.relations.length,upstream_variables:d.coverage.variables.length,draft_linked_variables:d.coverage.variables.filter(v=>v.family_ids.length).length}))ok(counts[key]===value,'manifest count mismatch '+key);
 for(const v of d.coverage.variables){ok(v.test_status==='NOT_RUN'&&v.full_variable_verified===false,v.variable_id+' unsupported verification claim');for(const id of v.family_ids)ok(fm.has(id),v.variable_id+' unknown family');for(const id of v.question_ids)ok(qm.has(id),v.variable_id+' unknown question');}
 ok(d.manifest.partition.final.length===0,'development package must not claim a final holdout');
 if(checkHashes)for(const entry of d.manifest.integrity){const file=path.join(dir,entry.file);ok(fs.existsSync(file)&&sha256(fs.readFileSync(file))===entry.sha256,'hash mismatch '+entry.file);}
 return {ok:errors.length===0,checks,errors,counts};
}
