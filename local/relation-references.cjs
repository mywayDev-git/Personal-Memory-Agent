const FIELDS=['subject','predicate','object'];
const INSTRUCTION='후보 ID 사용 구분: search_terms에는 K로 시작하는 후보 ID를 쓴다. relations.subject·predicate·object에는 K31 같은 후보 ID 대신 해당 요약 절의 실제 문구를 쓴다. 관계 주체와 대상은 relation_clause_id로 선택한 동일한 절에서 확인되어야 한다. 다른 절의 대상을 연결하거나 불명확한 대상을 추측하지 않는다. 확인할 수 없는 관계는 출력하지 않는다. 담당하기로 했다는 계획을 배포나 작업의 완료로 표시하지 않는다.';

function normalizeRelationReferences(draft,input){
 const candidates=new Map((input?.search_candidates||[]).map(c=>[c.term_id,c])),adjustments=[],relations=[];
 for(const [i,original]of draft.relations.entries()){
  const relation={...original},resolved=[],rejected=[];
  for(const field of FIELDS){
   const from=relation[field];
   // A literal identifier in the source is data, even when it resembles K1.
   if(typeof from!=='string'||relation.quote.includes(from))continue;
   if(!/^K[1-9]\d*$/u.test(from.trim())){if(/(?:^|[^A-Za-z0-9_])K[1-9]\d*(?=$|[^A-Za-z0-9_])/u.test(from))rejected.push({field,value:from,reason:'MIXED_CANDIDATE_REFERENCE'});continue;}
   const candidate=candidates.get(from.trim());
   if(!candidate){rejected.push({field,value:from,reason:'UNKNOWN_CANDIDATE_ID'});continue;}
   if(!relation.quote.includes(candidate.text)){rejected.push({field,value:from,resolved_value:candidate.text,reason:'OUTSIDE_RELATION_CLAUSE'});continue;}
   relation[field]=candidate.text;resolved.push({path:'relations['+i+'].'+field,action:'resolved',from,to:candidate.text,reason:'SUMMARY_CANDIDATE_REFERENCE',quote:relation.quote,message:'후보 ID를 선택한 요약 절의 실제 구절로 복원했습니다.'});
  }
  if(rejected.length){adjustments.push({path:'relations['+i+']',action:'omitted',reason:'UNCONFIRMED_ID_RELATION',fields:rejected,quote:relation.quote,message:'후보 ID를 같은 근거 절에서 확인할 수 없어 해당 관계만 색인에서 제외했습니다. 요약 본문은 유지됩니다.'});continue;}
  if(resolved.length&&relation.status==='completed'&&/(하기로|맡기로|할\s*예정)/u.test(relation.predicate)&&!/(결정|수락|승인)/u.test(relation.predicate)){
   adjustments.push({path:'relations['+i+'].status',action:'corrected',from:'completed',to:'planned',reason:'EXPLICIT_PLAN',quote:relation.quote,message:'관계 구절에 명시된 계획을 완료 상태와 구분했습니다.'});relation.status='planned';
  }
  adjustments.push(...resolved);relations.push(relation);
 }
 return {draft:{...draft,relations},adjustments};
}
module.exports={normalizeRelationReferences,INSTRUCTION};
