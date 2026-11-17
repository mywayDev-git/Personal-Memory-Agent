const {hash}=require('./core.cjs');

const MODE='claim-v1';

function claimType(relation){
 const predicate=relation.predicate;
 if(/가설|추정|예상/u.test(predicate))return 'hypothesis';
 if(/제안|추천/u.test(predicate))return 'proposal';
 if(/측정|관측|집계/u.test(predicate))return 'observation';
 if(relation.status==='planned')return 'plan';
 if(relation.status==='cancelled')return 'cancellation';
 if(['in_progress','completed'].includes(relation.status)&&relation.polarity==='positive')return 'execution';
 return 'assertion';
}

function attachClaims(graphs,indexes,sources){
 const sourceById=new Map(sources.map(source=>[source.id,source]));
 const units=new Map();
 for(const index of indexes){
  const ranges=new Map((index.excerpt_manifest?.excerpts||[]).map(range=>[range.unit_id,range]));
  const source=sourceById.get(index.source_id);
  for(const unit of index.units)units.set(unit.id,{unit,range:ranges.get(unit.id),source});
 }
 return graphs.map(graph=>{
  const claims=graph.members.flatMap(({unit_id})=>{
   const {unit,range,source}=units.get(unit_id);
   return unit.relations.map(relation=>{
    const {start,end,quote}=relation.evidence;
    if(start<unit.start||end>unit.end||unit.text.slice(start-unit.start,end-unit.start)!==quote)
     throw Error('Claim 근거의 발췌 위치가 기존 색인과 일치하지 않습니다.');
    const originalStart=range?.start+start-unit.start,originalEnd=range?.start+end-unit.start;
    const originalSpan=range&&source?.revision===unit.source_revision&&typeof source.text==='string'&&originalEnd<=range.end&&
     source.text.slice(originalStart,originalEnd)===quote?{start:originalStart,end:originalEnd}:null;
    const speaker=source?.metadata.speaker_id??source?.metadata.speaker;
    return {
     id:'C-'+hash({mode:MODE,relation:relation.relation_id}).slice(0,24),event_id:graph.id,
     relation_id:relation.relation_id,type:claimType(relation),
     subject:relation.subject,predicate:relation.predicate,object:relation.object,
     status:relation.status,polarity:relation.polarity,speaker:typeof speaker==='string'&&speaker.trim()?speaker:null,
     event_time:relation.event_time,recorded_at:unit.timestamp??null,valid_time:relation.valid_time,
     evidence:{unit_id,summary_id:unit.summary_id,source_id:unit.source_id,revision:unit.source_revision,
      excerpt_start:start,excerpt_end:end,original_span:originalSpan,quote}
    };
   });
  });
  return {...graph,claims};
 });
}

function rankClaims(engine,graphs,eligible,question){
 const items=graphs.flatMap(graph=>(graph.claims||[])
  .filter(claim=>eligible.has(claim.evidence.unit_id))
  .map(claim=>({
   id:claim.id,event_id:graph.id,unit_id:claim.evidence.unit_id,
   text:[claim.subject,claim.predicate,claim.object,claim.evidence.quote].join('\n')
  })));
 const byId=new Map(items.map(item=>[item.id,item]));
 const query=(question.match(/[\p{L}\p{N}_-]+/gu)||[]).join(' ');
 return engine.lexical(items,query).map((hit,i)=>{
  const {event_id,unit_id}=byId.get(hit.id);
  return {...hit,event_id,unit_id,rank:i+1};
 });
}

module.exports={MODE,attachClaims,rankClaims};
