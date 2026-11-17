const {contextualQuery}=require('./summary-dialogue.cjs');
const eventGraph=require('./event-graph.cjs');
const multiAnchor=require('./multi-anchor.cjs');
const {cosine,rrf}=require('./core.cjs'),{dateValue,normalized,VERSION}=require('./structured-memory.cjs'),usage=require('./token-usage.cjs');
function queryTime(text){const iso=[...text.matchAll(/\b(\d{4}-\d{2}-\d{2})\b/g)].map(m=>m[1]),korean=[...text.matchAll(/(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일/g)].map(m=>`${m[1]}-${m[2].padStart(2,'0')}-${m[3].padStart(2,'0')}`),dates=[...new Set([...iso,...korean])];if(dates.length!==1)return null;try{dateValue(dates[0]);return dates[0];}catch{return null;}}
function predicateHints(query){return ['담당','소속','선호','거주','재직','근무','유효'].filter(s=>query.includes(s));}
function activeOn(relation,day){const start=relation.valid_time.from,end=relation.valid_time.to,point=dateValue(day);return (!start||dateValue(start)<=point)&&(!end||dateValue(end)+(end.length===10?86400000-1:0)>=point);}
function temporalEligibility(unit,query,day){
 const hints=predicateHints(query);
 if(!day||!hints.length)return {eligible:true,status:'NOT_FILTERED'};
 const relevant=unit.relations.filter(r=>hints.some(h=>r.predicate.includes(h)));
 if(!relevant.length||relevant.some(r=>(!r.valid_time.from&&!r.valid_time.to)||[r.valid_time.from,r.valid_time.to].some(t=>t&&t.length>10)))return {eligible:true,status:'UNKNOWN_RETAINED'};
 return {eligible:relevant.some(r=>activeOn(r,day)),status:'EXPLICIT_VALID_TIME'};
}
async function retrieve(engine,run,ds,q,context,sources,extraction,signal,persist=true){
 const original=q.compound_original??q.text;
 const queryUsed=q.text+contextualQuery(original,context).slice(original.length),started=performance.now(),c=run.config;
 const vectorOnly=c.excerpt_only===true;
 const eventMode=c.route===eventGraph.ROUTE,allEvents=eventMode&&c.all_candidates===true;
 const canonical=engine.summary.units(extraction,sources);
 if(vectorOnly&&extraction.records.some(record=>!record.excerpt_selection))throw Error('발췌문 산출물을 선택하세요.');
 const indexes=vectorOnly?[]:engine.structured.indexes(extraction,sources);
 const day=vectorOnly||c.all_candidates?null:queryTime(q.text),exclusions=[];
 const metadataUnits=indexes.flatMap(index=>index.units).filter(unit=>{
  const result=temporalEligibility(unit,q.text,day);
  if(!result.eligible)exclusions.push({id:unit.id,source_id:unit.source_id,reason:result.status});
  return result.eligible;
 });
 const multiMode=c.route===multiAnchor.ROUTE;
 const metadataById=new Map(metadataUnits.map(unit=>[unit.id,unit]));
 const excludedIds=new Set(exclusions.map(item=>item.id));
 const units=multiMode?canonical.filter(unit=>!excludedIds.has(unit.id)).map(unit=>metadataById.get(unit.id)||{...unit,entities:[],relations:[]}):vectorOnly?canonical:metadataUnits;
 let queryVector,eventSearch,multiSearch;
 if(eventMode){
  engine.update(run,q.id+' · 사건 그래프 설명 검색',{stage:'retrieval'});
  if(units.length)queryVector=(await engine.vector(queryUsed,true,signal)).vector;
  eventSearch=await eventGraph.search(engine,indexes,extraction.event_graph_index,
   new Set(units.map(unit=>unit.id)),queryVector,q.text,signal,allEvents?null:eventGraph.GRAPH_K,c,sources);
 }
 engine.update(run,q.id+(vectorOnly?' 발췌문 의미 검색':' 요약 검색어·개체·관계·유효기간 검색'),{stage:vectorOnly?'query_embedding':'lexical',unit_total:units.length});
 const lexical=vectorOnly?[]:engine.structured.lexical(units,indexes,queryUsed,c.candidate_k);
 const vectors=[],query=normalized(queryUsed),entities=[],relations=[];
 const bySimilarity=(a,b)=>b.cosine-a.cosine||a.id.localeCompare(b.id);
 if(units.length){
  const qv=queryVector??(await engine.vector(queryUsed,true,signal)).vector;queryVector=qv;
  for(const u of units){
   signal.throwIfAborted();
   const {vector}=await engine.vector(u.text,false,signal);
   vectors.push({id:u.id,cosine:cosine(qv,vector)});
  }
 }
 vectors.sort(bySimilarity);
 for(const u of metadataUnits){const matched=u.entities.filter(e=>[e.name,...e.aliases].some(label=>query.includes(normalized(label))));if(matched.length)entities.push({id:u.id,score:matched.length,entity_ids:matched.map(e=>e.entity_id)});const hits=u.relations.filter(r=>query.includes(normalized(r.subject))||query.includes(normalized(r.object))||query.includes(normalized(r.predicate)));if(hits.length)relations.push({id:u.id,score:hits.length,relation_ids:hits.map(r=>r.relation_id)});}
 entities.sort((a,b)=>b.score-a.score||a.id.localeCompare(b.id));relations.sort((a,b)=>b.score-a.score||a.id.localeCompare(b.id));
 // Entity IDs are scoped to owner and source; matching names do not merge different people/documents.
 const anchors=new Set(entities.slice(0,c.candidate_k).flatMap(e=>e.entity_ids)),graph=[];
 for(const u of metadataUnits){const edges=u.relations.filter(r=>anchors.has(r.subject_id)||anchors.has(r.object_id));if(edges.length)graph.push({id:u.id,relation_ids:edges.map(r=>r.relation_id)});}
 // Every eligible summary unit already has a vector score.
 const vectorCandidates=c.all_candidates?vectors:vectors.slice(0,c.candidate_k);
 const channels=vectorOnly?[vectorCandidates]:[lexical,vectorCandidates,entities.slice(0,c.candidate_k),relations.slice(0,c.candidate_k),graph.slice(0,c.candidate_k)];
 const baseRanking=rrf(channels);
 let ranking=baseRanking;
 let fallback;
 if(eventSearch){
  const inside=eventSearch.unitIds;
  const linked=units.filter(unit=>inside.has(unit.id));
  const linkedChannels=[
   vectors.filter(hit=>inside.has(hit.id)),
   engine.structured.lexical(linked,indexes,queryUsed,c.candidate_k),
   entities.filter(hit=>inside.has(hit.id)),
   relations.filter(hit=>inside.has(hit.id))
  ];
  if(eventSearch.claimHits){
   const claimUnits=[...new Set(eventSearch.claimHits.filter(hit=>inside.has(hit.unit_id)).map(hit=>hit.unit_id))];
   linkedChannels.push(claimUnits.map(id=>({id})));
  }
  if(allEvents){
   const vectorRanks=new Map(vectors.map((hit,rank)=>[hit.id,rank]));
   linkedChannels.push(eventSearch.selected.flatMap(graph=>graph.members.map(member=>({id:member.unit_id}))
    .sort((a,b)=>vectorRanks.get(a.id)-vectorRanks.get(b.id))));
  }
  ranking=rrf(linkedChannels);
  // Keep one independent direct hit when the graph shortlist omitted it.
  const direct=baseRanking[0];
  if(direct&&!inside.has(direct.id)){
   const owner=eventSearch.ranked.find(item=>item.members.some(member=>member.unit_id===direct.id));
   if(owner){
    fallback={graph_id:owner.id,unit_id:direct.id,reason:'DIRECT_TOP_HIT_OUTSIDE_GRAPH_SHORTLIST'};
    ranking.push(direct);
   }
  }
 }
 if(multiMode){
  engine.update(run,q.id+' · 다중 대상·독립 사실 검색',{stage:'retrieval',unit_total:units.length});
  const result=await multiAnchor.rank(engine,{indexes,sources,units,query:queryUsed,queryVector,baseChannels:[['lexical',lexical],['vector',vectorCandidates]],config:c,signal});
  ranking=result.ranking;multiSearch=result.trace;
 }
 const canonicalById=new Map(canonical.map(unit=>[unit.id,unit]));
 const fused=ranking.map((hit,i)=>({...canonicalById.get(hit.id),fusion_score:hit.fusion_score,rank:i+1}));
 const ranked=[],hitsBySource=new Map();
 for(const hit of fused){
  if(!hitsBySource.has(hit.source_id)){
   ranked.push({source_id:hit.source_id,revision:hit.revision,rank:ranked.length+1,first_unit_rank:hit.rank});
   hitsBySource.set(hit.source_id,[]);
  }
  hitsBySource.get(hit.source_id).push(hit);
 }
 const selected=c.all_candidates?ranked:ranked.slice(0,c.top_k),evidence=[];let chars=0;
 // The complete pool is budgeted during candidate judgment, before the final answer.
 for(const source of selected){
  const hits=hitsBySource.get(source.source_id);
  for(const hit of c.all_candidates?hits:hits.slice(0,4)){
   if(!c.all_candidates&&chars+hit.text.length>c.evidence_char_budget)continue;
   chars+=hit.text.length;
   evidence.push({evidence_id:'E'+(evidence.length+1),source_id:hit.source_id,revision:hit.revision,start:hit.start,end:hit.end,text:hit.text,origin:'summary',unit_id:hit.id,summary_id:hit.summary_id});
  }
 }
 const metrics=engine.retrievalMetrics(ds.d,q,ranked,evidence);metrics.span_groups_fully_covered=null;metrics.scope='요약 출처만 측정. 메타정보 의미 정확도는 사람 검토 필요.';
 const data={kind:require('./summary.cjs').VERSION,...(vectorOnly?{}:{structured_version:VERSION,structured_indexes:extraction.structured_indexes}),context_id:context.id,question_id:q.id,dataset_fingerprint:ds.fingerprint,config:c,source_refs:sources.map(s=>({source_id:s.id,revision:s.revision})),source_snapshots:[],summary_records:extraction.records,extraction_artifact_id:extraction.artifact_id||null,query_original:q.text,query_used:queryUsed,index_units:canonical,lexical_candidates:lexical,vector_candidates:vectorCandidates,fused_candidates:fused,ranked_sources:ranked,selected_sources:selected,evidence,cache_hits:0,elapsed_ms:performance.now()-started,metrics,token_usage:usage.report({stage:'retrieval',question_id:q.id}),structured_trace:{ranking_mode:vectorOnly?'excerpt-embedding-only':'structured-hybrid',entity_candidates:entities.slice(0,c.candidate_k),relation_candidates:relations.slice(0,c.candidate_k),graph_candidates:graph.slice(0,c.candidate_k),time_filter:{day,excluded:exclusions,rule:vectorOnly?'발췌문 의미 유사도만 사용':'명시된 단일 날짜와 담당·소속 등 상태 관계에만 유효기간 적용. 알 수 없는 기간은 유지.'},scoped_index_ids:indexes.map(a=>a.index_id)},warning:vectorOnly?'발췌문 의미 유사도로 검색했습니다.':'동명 개체는 출처별로 구분합니다. 관계 근거는 요약문에서 확인합니다.'};
 if(eventSearch){
  data.event_graph_index=eventSearch.reference;
  data.event_graph_search={scope:allEvents?'all-accessible':'top-k',graph_limit:allEvents?null:eventGraph.GRAPH_K,
   eligible_graph_count:eventSearch.ranked.length,ranked_graphs:allEvents?eventSearch.ranked:eventSearch.ranked.slice(0,c.candidate_k),
   selected_graph_ids:eventSearch.selected.map(graph=>graph.id),fallback:fallback||null,
   returned_source_count:selected.length,returned_unit_ids:evidence.map(item=>item.unit_id)};
  if(eventSearch.linking){
   const returned=new Set(evidence.map(item=>item.unit_id));
   data.event_graph_search.linking={
    candidate_pairs:eventSearch.linking.candidate_pairs,linked_count:eventSearch.linking.linked_count,
    multi_excerpt_graph_count:eventSearch.ranked.filter(graph=>graph.members.length>1).length,
    different:eventSearch.linking.different
   };
   data.event_graph_search.unit_graph_ids=Object.fromEntries(eventSearch.ranked.flatMap(graph=>
    graph.members.filter(member=>returned.has(member.unit_id)).map(member=>[member.unit_id,graph.id])
   ));
  }
  data.structured_trace.ranking_mode='event-graph-description';
  data.warning=allEvents?'접근 가능한 모든 사건 그래프와 발췌문을 후보로 포함했습니다.':'사건 그래프 설명으로 검색 범위를 고르고 연결된 발췌문에서 답변 근거를 찾았습니다.';
  if(eventSearch.claimHits){
   data.structured_trace.ranking_mode='event-graph-claims';
   const returned=new Set(evidence.map(item=>item.unit_id));
   data.event_graph_search.claim_search={
    matched_count:eventSearch.claimHits.length,
    matches:eventSearch.claimHits.slice(0,c.candidate_k),
    returned_claim_ids:eventSearch.claimHits.filter(hit=>returned.has(hit.unit_id)).map(hit=>hit.id)
   };
   data.warning='사건 설명과 Claim을 검색해 발췌 순위를 정했습니다. 답변에는 발췌문을 근거로 전달합니다.';
  }
 }
 if(multiSearch){
  data.multi_anchor_search={...multiSearch,returned_unit_ids:evidence.map(item=>item.unit_id),returned_source_count:selected.length};
  data.structured_trace.ranking_mode=multiAnchor.VERSION;
  data.warning='G2 · 인물·프로젝트·대상·독립 Claim·사건 설명을 함께 검색했습니다. 사건 후보로 다른 경로의 근거를 제한하지 않습니다. 이름 일치는 동일인 확정이 아닙니다.';
 }
 if(c.all_candidates)data.structured_trace.time_filter.rule='전체 조회에서 날짜는 후보를 제외하는 조건으로 사용하지 않습니다.';
 engine.summary.assertRetrieval(data,sources);
 return persist?{...data,artifact_id:engine.store.artifact('retrieval',data)}:data;
}
module.exports={retrieve,queryTime,temporalEligibility,activeOn};
