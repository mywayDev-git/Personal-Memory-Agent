const {cosine,hash}=require('./core.cjs');
const {normalized}=require('./metadata-grounding.cjs');
const eventLinking=require('./event-linking.cjs');
const claimGraph=require('./claim-graph.cjs');

const ROUTE='G1';
const VERSION='source-scoped-event-graph-v1';
const GRAPH_K=3;

function build(indexes){
 const groups=new Map();
 for(const index of indexes){
  for(const unit of index.units){
   const names=type=>[...new Set(unit.entities.filter(entity=>entity.type===type).map(entity=>entity.name))];
   const events=names('event'),places=names('place');
   // Keep uncertain and multi-event excerpts separate. Names never join different sources.
   const labels=events.map(normalized);
   const anchor=labels.length===1&&labels[0]?{event:labels[0],places:places.map(normalized).sort()}:null;
   const id='G-'+hash({version:VERSION,index_id:index.index_id,anchor:anchor||unit.id}).slice(0,24);
   const group=groups.get(id)||{id,source_id:index.source_id,revision:index.revision,events,places,units:[]};
   group.units.push(unit);
   groups.set(id,group);
  }
 }
 return [...groups.values()].map(({units,...group})=>describe(group,units));
}

function describe(group,units){
  const terms=[...new Set(units.flatMap(unit=>unit.search_terms))].slice(0,10);
  const relations=[...new Set(units.flatMap(unit=>unit.relations.map(relation=>
   [relation.subject,relation.predicate,relation.object].join(' ')
  )))].slice(0,6);
  const description=[
   group.events.length&&'사건: '+group.events.join(', '),
   group.places.length&&'장소: '+group.places.join(', '),
   relations.length&&'관계: '+relations.join(' / '),
   terms.length&&'검색 표현: '+terms.join(', ')
  ].filter(Boolean).join('\n').slice(0,1200)||units[0].text.slice(0,300);
  return {...group,description,members:units.map(unit=>({unit_id:unit.id,entity_ids:unit.entity_ids,relation_ids:unit.relation_ids}))};
}

const mode=config=>config?.event_graph_mode===eventLinking.MODE?eventLinking.MODE:null;
const hasClaims=config=>config?.event_graph_mode===claimGraph.MODE;
const version=config=>hasClaims(config)?claimGraph.MODE:mode(config)||VERSION;
const settings=config=>mode(config)?{model:config.model,seed:config.seed}:null;

async function buildLinked(engine,indexes,sources,config,signal){
 const {groups,linked,different,candidate_pairs}=await eventLinking.link(engine,indexes,sources,config,signal);
 const graphs=groups.map(group=>{
  const units=group.map(entry=>entry.unit),first=group[0].index;
  const sourceRefs=[...new Map(group.map(({index})=>[index.source_id,{source_id:index.source_id,revision:index.revision}])).values()];
  const ids=new Set(units.map(unit=>unit.id));
  const names=type=>[...new Set(units.flatMap(unit=>unit.entities.filter(entity=>entity.type===type).map(entity=>entity.name)))];
  return describe({id:'G-'+hash({version:eventLinking.MODE,members:[...ids].sort()}).slice(0,24),
   source_id:first.source_id,revision:first.revision,source_refs:sourceRefs,events:names('event'),places:names('place'),
   links:linked.filter(link=>ids.has(link.from)&&ids.has(link.to))},units);
 });
 return {graphs,linking:{candidate_pairs,linked_count:linked.length,different}};
}

async function prepare(engine,indexes,signal,config,sources){
 const data=mode(config)?await buildLinked(engine,indexes,sources,config,signal):{graphs:build(indexes)};
 if(hasClaims(config))data.graphs=claimGraph.attachClaims(data.graphs,indexes,sources);
 const {graphs}=data;
 for(const graph of graphs){
  signal.throwIfAborted();
  await engine.vector(graph.description,false,signal);
 }
 const index_ids=indexes.map(index=>index.index_id);
 const value={version:version(config),index_ids,...data};
 if(mode(config))value.settings=settings(config);
 return {artifact_id:engine.store.artifact('event-graph-index',value),count:graphs.length};
}

async function search(engine,indexes,reference,eligible,queryVector,question,signal,limit=GRAPH_K,config,sources){
 let graphs,linking;
 if(reference){
  const saved=engine.store.readArtifact(reference.artifact_id);
  if(saved.type!=='event-graph-index'||
   JSON.stringify(saved.index_ids)!==JSON.stringify(indexes.map(index=>index.index_id)))
   throw Error('사건 그래프 색인의 출처 또는 버전이 현재 검색 범위와 다릅니다.');
  if(saved.version===version(config)&&JSON.stringify(saved.settings??null)===JSON.stringify(settings(config))){
   graphs=saved.graphs;
   linking=saved.linking;
  }
 }
 if(!graphs&&(mode(config)||hasClaims(config))){
  reference=await prepare(engine,indexes,signal,config,sources);
  const saved=engine.store.readArtifact(reference.artifact_id);
  ({graphs,linking}=saved);
 }
 if(!graphs){graphs=build(indexes);reference=undefined;}
 const claimHits=hasClaims(config)?claimGraph.rankClaims(engine,graphs,eligible,question):null;
 const claimRanks=new Map();
 for(const hit of claimHits||[])if(!claimRanks.has(hit.event_id))claimRanks.set(hit.event_id,hit.rank);
 const query=normalized(question),ranked=[];
 for(const graph of graphs){
  const members=graph.members.filter(member=>eligible.has(member.unit_id));
  if(!members.length)continue;
  signal.throwIfAborted();
  const {vector}=await engine.vector(graph.description,false,signal);
  const similarity=cosine(queryVector,vector);
  const matches=[...graph.events,...graph.places].filter(name=>{
   const label=normalized(name);
   return label.length>=2&&query.includes(label);
  });
  const claimRank=claimRanks.get(graph.id);
  const claimBonus=claimRank?0.04/Math.sqrt(claimRank):0;
  ranked.push({...graph,members,similarity,matched_labels:matches,
   ...(claimHits?{claims:graph.claims.filter(claim=>eligible.has(claim.evidence.unit_id)),
    claim_rank:claimRank??null,claim_bonus:claimBonus}:{}),
   score:similarity+0.08*Math.min(2,matches.length)+claimBonus});
 }
 ranked.sort((a,b)=>b.score-a.score||a.id.localeCompare(b.id));
 const selected=limit===null?ranked:ranked.slice(0,limit);
 return {ranked,selected,reference,linking,claimHits,unitIds:new Set(selected.flatMap(graph=>graph.members.map(member=>member.unit_id)))};
}

module.exports={ROUTE,VERSION,GRAPH_K,CLAIM_MODE:claimGraph.MODE,prepare,search};
