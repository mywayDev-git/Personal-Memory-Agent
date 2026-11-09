const {sentences}=require('./core.cjs');
function citationPlan(evidence,baseSchema){
 const schema=JSON.parse(JSON.stringify(baseSchema)),byId=new Map(),payload=evidence.map(e=>({evidence_id:e.evidence_id,source_id:e.source_id,summary_id:e.summary_id,origin:'summary',sentences:sentences(e.text).map(s=>{const id=e.evidence_id+':'+s.id;let at=-1,occurrence=0;do{at=e.text.indexOf(s.text,at+1);occurrence++;}while(at>=0&&at<s.start);byId.set(id,{evidence_id:e.evidence_id,quote:s.text,occurrence});return {sentence_id:id,text:s.text};})}));
 if(!byId.size){schema.properties.citations.maxItems=0;return {schema,evidence:payload,byId};}
 const item=schema.properties.citations.items;item.properties.evidence_id={type:'string',enum:evidence.map(e=>e.evidence_id)};item.properties.sentence_id={type:'string',enum:[...byId.keys()]};item.properties.quote={type:'string',enum:['']};item.properties.occurrence={type:'integer',enum:[1]};item.required.push('sentence_id');schema.properties.citations.maxItems=8;return {schema,evidence:payload,byId};
}
function resolveCitations(parsed,plan){return {...parsed,citations:parsed.citations.map(c=>{const span=plan.byId.get(c.sentence_id);if(!span)throw Error('제공되지 않은 요약 인용 문장 ID');return {...span};})};}
module.exports={citationPlan,resolveCitations};
