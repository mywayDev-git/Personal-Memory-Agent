import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
export const hash=value=>crypto.createHash('sha256').update(value).digest('hex');
export function loadDataset(dir){const read=n=>JSON.parse(fs.readFileSync(path.join(dir,n),'utf8'));return Object.fromEntries(['manifest','sources','contexts','questions','coverage','cases','connections'].map(n=>[n,read(n+'.json')]));}
export function materialize(context,sources){
 if(context.setup.steps.length)throw Error('고정 기억 묶음에 상태 변경 단계를 넣을 수 없습니다.');
 const byId=new Map(sources.map(s=>[s.id,s]));
 const active=context.setup.initial_sources.map(r=>{const s=byId.get(r.source_id);if(!s||s.revision!==r.revision)throw Error('원문 버전이 일치하지 않습니다.');return s;});
 return {active,accessible:active.filter(s=>s.metadata.owner_id===context.actor_id),trace:[]};
}
export function validate(d,dir,{checkHashes=true}={}){
 const errors=[];let checks=0;const ok=(condition,message)=>{checks++;if(!condition)errors.push(message);};
 try{
  const ss=d.sources.records,qq=d.questions.questions,cc=d.contexts.contexts,cs=d.cases.cases;
  const sm=new Map(ss.map(s=>[s.id,s])),qm=new Map(qq.map(q=>[q.id,q])),cm=new Map(cc.map(c=>[c.id,c]));
  const facts=new Map(ss.flatMap(s=>s.gold.facts.map(f=>[f.id,{...f,source:s}])));
  ok(d.manifest.dataset_version==='pma-memory-v2.0.0','dataset version');
  ok(ss.length===288&&qq.length===360&&cs.length===36,'288 originals, 288 base questions, 72 variants, 36 histories');
  ok(ss.filter(s=>s.split==='development').length===192&&ss.filter(s=>s.split==='final').length===96,'source split');
  ok(qq.filter(q=>!q.variant).length===288&&qq.filter(q=>q.profile==='controlled').length===72,'question composition');
  for(const [name,rows] of Object.entries({sources:ss,questions:qq,contexts:cc,cases:cs,connections:d.connections.relations}))ok(new Set(rows.map(x=>x.id)).size===rows.length,name+' unique IDs');
  const span=(e,label)=>{const s=sm.get(e.source_id);ok(s?.revision===e.revision&&Number.isInteger(e.start)&&Number.isInteger(e.end)&&e.start>=0&&e.end>e.start&&s.text.slice(e.start,e.end)===e.quote,label+' exact UTF16 span');};
  const uniqueTexts=new Set();
  for(const s of ss){
   ok(!uniqueTexts.has(s.text),s.id+' unique original');uniqueTexts.add(s.text);
   const sentences=s.text.split(/(?<=[。.!?])\s+(?=[가-힣A-Z])/u).map(s=>s.trim()).filter(Boolean);
   ok(new Set(sentences).size===sentences.length,s.id+' no repeated sentence inside original');
   ok(s.text.length>=25&&s.text.length<=260,s.id+' authored concise original, no padding');
   ok(/^MIS-[a-f0-9]{16}$/.test(s.id)&&/^fixture-[a-f0-9]{16}$/.test(s.metadata.owner_id),s.id+' opaque model IDs');
   ok(!Object.keys(s.metadata).some(k=>/gold|question|profile|family|case|expected|answer|split/.test(k)),s.id+' no oracle metadata');
   ok(s.gold.review_status==='AUTHOR_DRAFT'&&s.provenance.model_tokens===null,s.id+' honest review/token boundary');
   for(const f of s.gold.facts)for(const e of f.evidence){span(e,f.id);ok(e.source_id===s.id,f.id+' local evidence');}
   for(const h of s.gold.highlights)span({...h,source_id:s.id,revision:s.revision},s.id+' highlight');
  }
  for(const c of cc){
   const state=materialize(c,ss),refs=c.expected_state.accessible_sources;
   ok(state.accessible.length===refs.length&&state.active.length===refs.length,c.id+' owner scope');
   ok(new Set(state.active.map(s=>s.id)).size===state.active.length,c.id+' no duplicated original');
   ok(state.active.every(s=>s.split===c.split&&s.family_id===c.family_id),c.id+' no cross-partition/history leakage');
   ok(JSON.stringify(c.setup.initial_sources)===JSON.stringify(refs),c.id+' explicit input order');
   ok(state.active.every(s=>Date.parse(s.metadata.created_at)<=Date.parse(c.now)),c.id+' import before question');
  }
  for(const q of qq){
   const c=cm.get(q.context_id);ok(!!c,q.id+' context exists');if(!c)continue;
   const scope=new Set(c.expected_state.accessible_sources.map(r=>r.source_id));
   ok(q.split===c.split&&q.family_id===c.family_id,q.id+' context binding');
   ok(q.gold.reference_answer.trim()&&q.gold.required_claims.length&&q.gold.review_status==='AUTHOR_DRAFT',q.id+' reference draft');
   ok(['answer','deny','partial_answer','clarify','abstain','report_conflict'].includes(q.gold.expected_action),q.id+' action');
   ok(q.gold.evidence_groups.length>0,q.id+' annotated support');
   for(const g of q.gold.evidence_groups){ok(g.any_of_fact_ids.length>0,q.id+' nonempty evidence group');for(const f of g.any_of_fact_ids)ok(scope.has(facts.get(f)?.source.id),q.id+' gold accessible');}
   if(q.variant){const parent=qm.get(q.variant.paired_question_id);ok(parent&&parent.text===q.text&&parent.gold.reference_answer===q.gold.reference_answer,q.id+' invariant target');ok(scope.size===q.variant.source_count,q.id+' counted full memory');ok(q.split==='development'&&q.profile==='controlled',q.id+' controls do not consume final');}
  }
  for(const c of cs){
   ok(c.source_refs.length===8&&c.question_ids.length===8,c.id+' eight originals/eight base questions');
   ok(c.question_ids.every(id=>qm.get(id)?.family_id===c.id&&!qm.get(id)?.variant),c.id+' base bindings');
   ok(c.characters===c.source_refs.reduce((n,r)=>n+Array.from(sm.get(r.source_id).text).length,0),c.id+' measured chars');
  }
  for(const e of d.connections.relations){const c=cm.get(e.context_id);ok(facts.has(e.from_fact_id)&&facts.has(e.to_fact_id)&&c,e.id+' relationship bindings');for(const ev of e.evidence){span(ev,e.id);ok(c?.expected_state.accessible_sources.some(r=>r.source_id===ev.source_id),e.id+' relationship visible');}}
  for(const [id,count] of Object.entries(d.manifest.profiles))ok(qq.filter(q=>q.profile===id).length===count,'profile count '+id);
  ok(d.coverage.variables.length===489&&d.coverage.variables.every(v=>['PARTIAL','NOT_COVERED','SEPARATE_FUNCTIONAL_TEST'].includes(v.status)),'489 variables without fabricated full coverage');
  for(const split of ['development','final'])ok(JSON.stringify(d.manifest.partition[split])===JSON.stringify(qq.filter(q=>q.split===split).map(q=>q.id)),'partition '+split);
  ok(d.manifest.model_execution===false&&d.manifest.independent_gold===false,'no model or independent review claim');
  if(checkHashes){for(const file of d.manifest.integrity){ok(/^[a-zA-Z_]+\.(json|mjs|md|py)$/.test(file.file),'safe integrity filename');ok(hash(fs.readFileSync(path.join(dir,file.file)))===file.sha256,'hash '+file.file);}ok(hash(fs.readFileSync(path.join(dir,'definition.json')))===d.manifest.provenance.definition_sha256,'own definition hash');}
 }catch(e){errors.push('validation exception: '+e.message);}
 return {ok:errors.length===0,checks,errors};
}
