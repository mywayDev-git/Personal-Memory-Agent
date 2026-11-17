'use strict';
const {hash,rrf}=require('./core.cjs');
const {normalized}=require('./metadata-grounding.cjs');
const eventGraph=require('./event-graph.cjs');
const claimGraph=require('./claim-graph.cjs');
const ROUTE='G2',VERSION='multi-anchor-grounded-v1';
const LABELS={person:'인물',project:'프로젝트',organization:'조직',place:'장소',event:'사건',other:'대상·문서·주제'};
function compatibleExtraction(config,artifact){
 const previous=artifact.config;
 return config.route===ROUTE&&artifact.kind==='summary-only-v1'&&['M1','G1',ROUTE].includes(previous?.route)&&
  previous.summary_mode==='extractive-v1'&&!previous.excerpt_only&&
  artifact.structured_version===require('./metadata-schema.cjs').VERSION&&Array.isArray(artifact.structured_indexes)&&
  !!config.summary_settings_hash&&previous.summary_settings_hash===config.summary_settings_hash&&
  !!config.metadata_settings_hash&&previous.metadata_settings_hash===config.metadata_settings_hash;
}

// Mention identities remain source-scoped; a matching label is never an identity merge.
function catalog(indexes,sources,eligible){
 const allowed=new Map(sources.map(s=>[s.id,s])),entities=[],units=[];
 for(const index of indexes){
  const source=allowed.get(index.source_id);
  if(!source||source.revision!==index.revision||source.metadata.owner_id!==index.owner_id)throw Error('G2 색인의 접근 범위·소유자·버전이 현재 기록과 다릅니다.');
  for(const unit of index.units){
   if(!eligible.has(unit.id))continue;
   if(unit.source_id!==source.id||unit.source_revision!==source.revision||unit.owner_id!==index.owner_id)throw Error('G2 검색 단위의 출처가 색인과 다릅니다.');
   units.push(unit);
   for(const entity of unit.entities||[])entities.push({
    id:'MA-'+hash({source:source.id,revision:source.revision,unit:unit.id,mention:entity.entity_id}).slice(0,24),
    entity_id:entity.entity_id,unit_id:unit.id,source_id:source.id,revision:source.revision,
    name:entity.name,aliases:entity.aliases||[],type:entity.type,label:LABELS[entity.type]||LABELS.other,
    evidence:entity.evidence
   });
  }
 }
 // Claims are built over every eligible unit, including units without an event.
 const buckets=units.map(unit=>({id:'U-'+hash(unit.id).slice(0,24),members:[{unit_id:unit.id}]}));
 const claims=claimGraph.attachClaims(buckets,indexes,sources).flatMap(bucket=>bucket.claims.map(({event_id,...claim})=>({...claim,anchor_unit_id:claim.evidence.unit_id})));
 return {entities,claims,units};
}
function labelMatches(label,query){const value=normalized(label);return value.length>=2&&query.includes(value);}
function unitHits(items){const seen=new Set();return items.filter(item=>!seen.has(item.unit_id)&&seen.add(item.unit_id)).map(item=>({id:item.unit_id}));}
async function rank(engine,{indexes,sources,units,query,queryVector,baseChannels,config,signal}){
 signal.throwIfAborted();
 const eligible=new Set(units.map(u=>u.id)),data=catalog(indexes,sources,eligible),norm=normalized(query),channels=[];
 const limit=config.all_candidates?units.length:config.candidate_k;
 const add=(name,label,hits)=>{const selected=hits.slice(0,limit);if(selected.length)channels.push({name,label,hits:selected});};
 for(const [name,hits]of baseChannels)add(name,name==='lexical'?'발췌 키워드':'발췌 의미',hits);
 const matched=data.entities.map(entity=>({...entity,matched_labels:[entity.name,...entity.aliases].filter(label=>labelMatches(label,norm))})).filter(entity=>entity.matched_labels.length);
 for(const [type,label]of Object.entries(LABELS)){
  const hits=matched.filter(e=>e.type===type).sort((a,b)=>b.matched_labels.length-a.matched_labels.length||a.id.localeCompare(b.id));
  add(type,label,unitHits(hits));
 }
 const claimById=new Map(data.claims.map(claim=>[claim.id,claim]));
 const claimMatches=engine.lexical(data.claims.map(claim=>({id:claim.id,text:[claim.subject,claim.predicate,claim.object,claim.evidence.quote].join('\n')})),query)
  .map(hit=>({...hit,unit_id:claimById.get(hit.id).evidence.unit_id}));
 add('claims','독립 사실·관계',unitHits(claimMatches));
 // Event descriptions provide another ranking vote, never a gate on other lanes.
 const eventSearch=await eventGraph.search(engine,indexes,null,eligible,queryVector,query,signal,config.all_candidates?null:eventGraph.GRAPH_K,{},sources);
 const events=eventSearch.selected.flatMap(event=>event.members.map(member=>({unit_id:member.unit_id})));
 add('event_description','사건 설명',unitHits(events));
 const ranking=rrf(channels.map(channel=>channel.hits));
 const byUnit=new Map();for(const channel of channels)for(const hit of channel.hits){if(!byUnit.has(hit.id))byUnit.set(hit.id,[]);byUnit.get(hit.id).push(channel.name);}
 return {ranking,trace:{version:VERSION,status:'COMPLETED',scope:config.all_candidates?'all-accessible':'top-k',
  event_gate:false,identity_merging:false,query,channels:channels.map(channel=>({name:channel.name,label:channel.label,candidates:channel.hits})),
  matched_entities:matched,claim_matches:claimMatches.slice(0,config.candidate_k).map(hit=>({...hit,claim:claimById.get(hit.id)})),
  eligible_unit_count:units.length,eligible_claim_count:data.claims.length,
  event_candidate_ids:eventSearch.selected.map(event=>event.id),
  ranked_units:ranking.map(hit=>({unit_id:hit.id,channels:byUnit.get(hit.id),fusion_score:hit.fusion_score})),
  provenance_policy:'현재 접근 가능한 출처·버전의 발췌만 반환. 이름·별칭 일치는 후보이며 동일인 확정이 아님.'}};
}
function fuse(branches,evidence){
 if(!branches.some(branch=>branch.result.multi_anchor_search))return undefined;
 return {version:VERSION,status:'COMPLETED',event_gate:false,identity_merging:false,
  branches:branches.map(branch=>({id:branch.id,focus:branch.focus,...branch.result.multi_anchor_search})),
  returned_unit_ids:evidence.map(item=>item.unit_id),returned_source_count:new Set(evidence.map(item=>item.source_id)).size};
}
module.exports={ROUTE,VERSION,LABELS,catalog,rank,fuse,compatibleExtraction};
