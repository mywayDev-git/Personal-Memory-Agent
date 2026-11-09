const {contextualQuery,arithmeticTask}=require('./summary-dialogue.cjs');
const {MODE,planQuestion}=require('./scoped-answer.cjs');
const {cosine,rrf}=require('./core.cjs'),{dateValue,normalized,VERSION}=require('./structured-memory.cjs'),usage=require('./token-usage.cjs');
function queryTime(text){const iso=[...text.matchAll(/\b(\d{4}-\d{2}-\d{2})\b/g)].map(m=>m[1]),korean=[...text.matchAll(/(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일/g)].map(m=>`${m[1]}-${m[2].padStart(2,'0')}-${m[3].padStart(2,'0')}`),dates=[...new Set([...iso,...korean])];if(dates.length!==1)return null;try{dateValue(dates[0]);return dates[0];}catch{return null;}}
function predicateHints(query){return ['담당','소속','선호','거주','재직','근무','유효'].filter(s=>query.includes(s));}
function activeOn(relation,day){const start=relation.valid_time.from,end=relation.valid_time.to,point=dateValue(day);return (!start||dateValue(start)<=point)&&(!end||dateValue(end)+(end.length===10?86400000-1:0)>=point);}
function temporalEligibility(unit,query,day,plan){
 const hints=predicateHints(query);
 if(!day||!hints.length)return {eligible:true,status:'NOT_FILTERED'};
 const relevant=unit.relations.filter(r=>hints.some(h=>r.predicate.includes(h)));
 if(plan&&(plan.ambiguous||!plan.target||!relevant.every(r=>[r.subject,r.object].some(label=>normalized(label)===normalized(plan.target)))))
  return {eligible:true,status:'TARGET_NOT_CONFIRMED'};
 if(!relevant.length||relevant.some(r=>(!r.valid_time.from&&!r.valid_time.to)||[r.valid_time.from,r.valid_time.to].some(t=>t&&t.length>10)))return {eligible:true,status:'UNKNOWN_RETAINED'};
 return {eligible:relevant.some(r=>activeOn(r,day)),status:'EXPLICIT_VALID_TIME'};
}
async function retrieve(engine,run,ds,q,context,sources,extraction,signal){
 const queryUsed=contextualQuery(q.text,context),started=performance.now(),c=run.config;
 const vectorOnly=c.excerpt_only===true;
 const canonical=engine.summary.units(extraction,sources);
 if(vectorOnly&&extraction.records.some(record=>!record.excerpt_selection))throw Error('발췌문 산출물을 선택하세요.');
 const indexes=vectorOnly?[]:engine.structured.indexes(extraction,sources);
 let plan;
 if(c.answer_pipeline===MODE&&!arithmeticTask(q.text)){
  engine.update(run,q.id+' · 질문과 검색 범위 분석',{stage:'query_plan'});
  plan=await planQuestion(engine.runtime,q,context,c,signal);
 }
 const day=vectorOnly?null:queryTime(q.text),exclusions=[];
 const metadataUnits=indexes.flatMap(index=>index.units).filter(unit=>{
  const result=temporalEligibility(unit,q.text,day,plan);
  if(!result.eligible)exclusions.push({id:unit.id,source_id:unit.source_id,reason:result.status});
  return result.eligible;
 });
 const units=vectorOnly?canonical:metadataUnits;
 engine.update(run,q.id+(vectorOnly?' 발췌문 의미 검색':' 요약 검색어·개체·관계·유효기간 검색'),{stage:vectorOnly?'query_embedding':'lexical',unit_total:units.length});
 const lexical=vectorOnly?[]:engine.structured.lexical(units,indexes,queryUsed,c.candidate_k);
 const vectors=[],query=normalized(queryUsed),entities=[],relations=[],documentVectors=[];
 const bySimilarity=(a,b)=>b.cosine-a.cosine||a.id.localeCompare(b.id);
 if(units.length){
  const qv=await engine.vector(queryUsed,true,signal);
  for(const u of units){
   signal.throwIfAborted();
   const {vector}=await engine.vector(u.text,false,signal);
   vectors.push({id:u.id,cosine:cosine(qv.vector,vector)});
   if(plan?.queries.length>1)documentVectors.push({id:u.id,vector});
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
 const branchRankings=[];
 if(documentVectors.length)for(const searchText of plan.queries.slice(1)){
  const {vector}=await engine.vector(searchText,true,signal);
  const ranking=documentVectors.map(doc=>({id:doc.id,cosine:cosine(vector,doc.vector)})).sort(bySimilarity);
  branchRankings.push(ranking.slice(0,c.candidate_k));
 }
 // Merge supplementary searches as one channel so the original ranking keeps its weight.
 const baseRanking=rrf(channels);
 const ranking=branchRankings.length?rrf([baseRanking,rrf(branchRankings)]):baseRanking;
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
 if(plan){
  data.scoped_query=plan;
  data.scoped_search={eligible_units:units.length,original_ranked_ids:baseRanking.map(hit=>hit.id),
   supplementary_rankings:branchRankings.map((branch,i)=>({query:plan.queries[i+1],candidates:branch}))};
 }
 engine.summary.assertRetrieval(data,sources);return {...data,artifact_id:engine.store.artifact('retrieval',data)};
}
module.exports={retrieve,queryTime,temporalEligibility,activeOn};
