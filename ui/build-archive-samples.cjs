'use strict';
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const {pathToFileURL}=require('node:url');
const hash=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
async function buildArchiveSamples(root){
  const dir=path.join(root,'datasets','pma-generalization-v1.0.0');
  const read=name=>JSON.parse(fs.readFileSync(path.join(dir,name+'.json'),'utf8'));
  const manifest=read('manifest'),sources=read('sources').records,questions=read('questions').questions,contexts=read('contexts').contexts;
  const {materialize}=await import(pathToFileURL(path.join(dir,'lib.mjs')).href);
  const bySource=new Map(sources.map(s=>[s.id,s])),byContext=new Map(contexts.map(c=>[c.id,c]));
  const byFact=new Map(sources.flatMap(s=>(s.gold?.facts||[]).map(f=>[f.id,{...f,source:s}])));
  const dateFormatter=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit'});
  const date=value=>{if(!value||!Number.isFinite(Date.parse(value)))return null;const parts=Object.fromEntries(dateFormatter.formatToParts(new Date(value)).map(p=>[p.type,p.value]));return parts.year+'-'+parts.month+'-'+parts.day;};
  const records=sources.map(s=>({id:s.id,revision:s.revision,profile:s.split,title:s.metadata.title||s.family_id||'제목 없는 가상 기록',body:s.text,date:date(s.metadata.created_at),created_at:s.metadata.created_at||null,imported_at:s.metadata.imported_at||null,family:s.family_id,synthetic:s.provenance?.synthetic_only===true}));
  const examples=questions.map(q=>{
    const context=byContext.get(q.context_id);assert.ok(context,q.id+' context');
    const state=materialize(context,sources),accessible=new Set(state.accessible.map(s=>s.id)),evidence=[];
    for(const group of q.gold.evidence_groups||[])for(const factId of group.any_of_fact_ids||[]){
      const fact=byFact.get(factId);assert.ok(fact,q.id+' fact '+factId);
      for(const span of fact.evidence||[]){const source=bySource.get(span.source_id);assert.ok(source);assert.equal(source.revision,span.revision);assert.equal(source.text.slice(span.start,span.end),span.quote);assert.ok(accessible.has(source.id),q.id+' inaccessible support');
        if(!evidence.some(e=>e.source_id===span.source_id&&e.start===span.start&&e.end===span.end))evidence.push({source_id:span.source_id,revision:span.revision,start:span.start,end:span.end,quote:span.quote,group:group.id});
      }
    }
    return {id:q.id,profile:q.profile,family:q.family_id,variant:q.variant?.kind||null,question:q.text,answer:q.gold.reference_answer||'',answer_status:q.gold.annotation_status?.reference_answer||q.gold.review_status||'AUTHOR_DRAFT',expected_action:q.gold.expected_action,
      evidence,record_ids:[...new Set(evidence.map(e=>e.source_id))],accessible_ids:[...accessible],context_id:context.id,reference_time:context.now,
      dialogue:context.dialogue||null,conversation:context.conversation||[],setup_actions:(context.setup.steps||[]).map(step=>({action:step.action,source_id:step.source_id||null,old_source:step.old_source||null,new_source:step.new_source||null}))};
  });
  const profiles=['development','confirmation'].map(id=>({id,label:id==='development'?'개발용':'확인용',record_count:records.filter(r=>r.profile===id).length,question_count:examples.filter(q=>q.profile===id).length}));
  assert.equal(records.length,manifest.counts.sources);assert.equal(examples.length,manifest.counts.questions);
  return {version:1,dataset:manifest.dataset_version,title:'일반화 최소 기준점',subtitle:manifest.title,synthetic:true,time_zone:'Asia/Seoul',default_profile:'development',profiles,record_count:records.length,question_count:examples.length,
    provenance:{kind:'read-only-ui-examples',model_execution:false,independent_gold:manifest.independent_gold,files:Object.fromEntries(['manifest','sources','questions','contexts'].map(name=>[name+'.json',hash(fs.readFileSync(path.join(dir,name+'.json')))]))},records,examples};
}
async function writeSamples(root,output=path.join(root,'ui/plant-thought/archive-data.js')){
  const data=await buildArchiveSamples(root);fs.mkdirSync(path.dirname(output),{recursive:true});
  fs.writeFileSync(output,'// Read-only synthetic UI examples. Reference answers are author drafts, not model outputs.\nwindow.PlantArchiveSamples = '+JSON.stringify(data).replaceAll('<','\\u003c')+';\n');
  return {output,records:data.records.length,questions:data.examples.length,profiles:data.profiles};
}
if(require.main===module)writeSamples(path.resolve(__dirname,'..')).then(value=>console.log(JSON.stringify(value))).catch(error=>{console.error(error);process.exitCode=1;});
module.exports={buildArchiveSamples,writeSamples};
