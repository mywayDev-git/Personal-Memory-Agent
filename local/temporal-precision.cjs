const {groundedDate}=require('./metadata-grounding.cjs');

// The accepted v2 index format stays unchanged: only rejected temporal values
// are reduced to the precision supported by their own summary clause.
const INSTRUCTION='시각의 정밀도: "오후", "아침", "저녁", "쯤" 등의 표현만 보고 15:00 같은 시간을 정하지 않는다. 날짜만 확인되면 YYYY-MM-DD로 쓴다. 날짜도 확인되지 않으면 time_mentions의 해당 항목을 생략한다. time_mentions.value에는 null이나 빈 문자열을 넣지 않는다. 관계의 event_time·valid_from·valid_to는 날짜만 확인되면 날짜로, 날짜도 확인되지 않으면 null로 둔다. reference_time의 시각을 사건 시각으로 복사하지 않는다. 불명확한 시간 표현 자체는 요약의 근거 구절에 보존한다.';

function normalizeTemporalPrecision(draft,record){
 const adjustments=[];
 function reduce(value,quote,path){
  if(value===null)return null;
  try{groundedDate(value,quote,record.timestamp);return value;}catch{}
  const day=typeof value==='string'&&/^\d{4}-\d{2}-\d{2}(?:T|$)/u.test(value)?value.slice(0,10):null;
  if(day){try{groundedDate(day,quote,record.timestamp);adjustments.push({path,from:value,to:day,reason:'DATE_ONLY',message:'시각을 확정할 근거가 없어 확인되는 날짜만 저장했습니다.',quote});return day;}catch{}}
  adjustments.push({path,from:value,to:null,reason:'UNCONFIRMED_DATE',message:'날짜와 시각의 근거를 확인할 수 없어 시간 항목을 비웠습니다.',quote});return null;
 }
 const time_mentions=(draft.time_mentions||[]).flatMap((t,i)=>{const value=reduce(t.value,t.quote,'time_mentions['+i+'].value');return value===null?[]:[{...t,value}];});
 const relations=draft.relations.map((r,i)=>{
  const validQuote=r.valid_time_quote??r.time_quote??'',eventQuote=r.event_time_quote??r.time_quote??'',valid_from=reduce(r.valid_from,validQuote,'relations['+i+'].valid_from'),valid_to=reduce(r.valid_to,validQuote,'relations['+i+'].valid_to'),event_time=reduce(r.event_time,eventQuote,'relations['+i+'].event_time');
  return {...r,valid_from,valid_to,event_time,...(!valid_from&&!valid_to?{valid_time_quote:'',valid_time_occurrence:1}:{}),...(!event_time?{event_time_quote:'',event_time_occurrence:1}:{})};
 });
 return {draft:{...draft,time_mentions,relations},adjustments};
}
module.exports={normalizeTemporalPrecision,INSTRUCTION};
