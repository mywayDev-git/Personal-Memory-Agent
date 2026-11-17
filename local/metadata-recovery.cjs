// Optional search hints may be omitted; the summary itself is never discarded.
function recoverMetadata(raw,process,input){
 if(!raw||!['entities','relations','time_mentions','search_terms'].every(k=>Array.isArray(raw[k]))){const search_terms=input.search_candidates.slice(0,8).map(c=>c.term_id);return {...process({search_terms,entities:[],relations:[],time_mentions:[]}),metadata_origin:'deterministic_summary_fallback',metadata_omissions:[{path:'$',reason:'MODEL_OUTPUT_UNUSABLE',message:'두 차례 생성한 메타정보를 사용할 수 없어 해당 출력을 폐기하고 요약의 실제 구절로만 기본 색인을 만들었습니다.'}]};}
 const base={...raw,entities:[],relations:[],time_mentions:[]};process(base);
 const kept={entities:[],time_mentions:[],relations:[]},omissions=[];
 for(const key of ['entities','time_mentions','relations'])for(const [index,item]of raw[key].entries()){
  try{process({...base,entities:kept.entities,time_mentions:kept.time_mentions,relations:kept.relations,[key]:[...kept[key],item]});kept[key].push(item);}
  catch(error){omissions.push({path:key+'['+index+']',reason:'UNVERIFIED_OPTIONAL_METADATA',message:'두 차례 보완 후에도 요약 근거를 확인하지 못해 검색용 항목만 제외했습니다. 요약 본문은 유지됩니다.',issues:error.validation_issues||[{message:error.message}],draft:item});}
 }
 return {...process({...base,...kept}),metadata_omissions:omissions};
}
module.exports={recoverMetadata};
