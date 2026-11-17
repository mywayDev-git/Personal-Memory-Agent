const {dateValue}=require('./metadata-grounding.cjs');

const MODE='chronological-v1';
const dayInSeoul=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit'});

function recordTime(value){
 if(!value)return {timestamp:null,day:null,instant:null};
 try{
  const instant=dateValue(value);
  return value.length===10?{timestamp:value,day:value,instant:null}:
   {timestamp:value,day:dayInSeoul.format(instant),instant};
 }catch{
  return {timestamp:null,day:null,instant:null};
 }
}

function chronologicalEvidence(evidence,sources){
 const times=new Map(sources.map(source=>[source.id,recordTime(source.metadata.created_at)]));
 const entries=evidence.map(item=>({item,time:times.get(item.source_id)}));
 entries.sort((a,b)=>{
  if(!a.time.day&&b.time.day)return 1;
  if(a.time.day&&!b.time.day)return -1;
  if(a.time.day!==b.time.day)return a.time.day.localeCompare(b.time.day);
  const time=(a.time.instant??Infinity)-(b.time.instant??Infinity);
  return time||a.item.source_id.localeCompare(b.item.source_id)||a.item.start-b.item.start;
 });
 const input=entries.map(({item,time})=>({
  evidence_id:item.evidence_id,source_id:item.source_id,recorded_at:time.timestamp,
  precision:time.instant!==null?'datetime':time.day?'date':'unknown',text:item.text
 }));
 return {ordered:entries.map(({item})=>item),input};
}

module.exports={MODE,chronologicalEvidence};
