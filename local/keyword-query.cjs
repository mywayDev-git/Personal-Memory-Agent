const {normalize,identifiers}=require('./chunk-keywords.cjs');
const {keywordMatcher}=require('./extractive.cjs');
const {queryTime}=require('./structured-retrieve.cjs');

const VERSION='corpus-keyword-expansion-v1';
const expressions=[
 ['왜','이유','사유','까닭','때문'],
 ['어디','장소','위치','공간'],
 ['얼마','금액','비용','가격'],
 ['변경','전환','교체'],
 ['담당','담당자'],
 ['결과','측정결과','관측결과']
];
const generic=new Set(expressions.flat().map(normalize));
const stop=new Set(['알려줘','대해','대한','무엇','어떤','있다','했다','한다','그리고','그럼','그러면','지금','확인','하나']);

function vocabulary(units){
 const words=new Map();
 for(const unit of units)for(const keyword of unit.keywords){
  let entry=words.get(keyword.normalized);
  if(!entry){entry={text:keyword.text,normalized:keyword.normalized,unit_ids:new Set()};words.set(keyword.normalized,entry);}
  entry.unit_ids.add(unit.id);
 }
 return words;
}

function planQuestion(question,units,mode='filtered'){
 const words=vocabulary(units),matcher=keywordMatcher(question),compact=normalize(question);
 const direct=[...words.values()].filter(word=>word.normalized.length>=2&&matcher([word])>0);
 const anchors=direct.filter(word=>!generic.has(word.normalized)&&!stop.has(word.normalized))
  .sort((a,b)=>Math.log(1+units.length/b.unit_ids.size)*b.normalized.length-
   Math.log(1+units.length/a.unit_ids.size)*a.normalized.length||a.text.localeCompare(b.text)).slice(0,4);
 const queries=[{id:'Q0',text:question,kind:'original',keywords:direct.slice(0,24).map(word=>word.text)}];
 const groups=[];
 if(mode!=='original')for(const terms of expressions){
  if(!terms.some(term=>compact.includes(normalize(term))))continue;
  const selected=terms.map(term=>words.get(normalize(term))).filter(Boolean);
  if(!selected.length)continue;
  const added=selected.filter(word=>!direct.some(hit=>hit.normalized===word.normalized));
  if(!added.length)continue;
  const keywords=selected.map(word=>word.text);
  const text=[question,...anchors.map(word=>word.text),...keywords].join(' ');
  if(queries.some(query=>query.text===text))continue;
  const group={id:'Q'+queries.length,text,kind:'keyword_expansion',keywords,
   additions:added.map(word=>({text:word.text,reason:'INDEXED_SEARCH_EXPRESSION',candidate_units:word.unit_ids.size}))};
  queries.push(group);groups.push(group);
  if(queries.length===4)break;
 }
 const excluded=[];
 for(const word of direct.filter(word=>{
  const at=compact.indexOf(word.normalized);
  return at>=0&&/^(?:을|를|은|는|이|가|의|대신)?(?:말고|제외|빼고)/u.test(compact.slice(at+word.normalized.length));
 }).sort((a,b)=>b.normalized.length-a.normalized.length)){
  if(excluded.some(value=>normalize(value).includes(word.normalized)))continue;
  excluded.push(word.text);
  if(excluded.length===4)break;
 }
 return {version:VERSION,mode,original:question,queries,anchors:anchors.map(word=>word.text),
  identifiers:identifiers(question),excluded_keywords:excluded,
  recorded_day:/(작성|저장|기록한|기록된)/u.test(question)?queryTime(question):null,
  vocabulary_size:words.size,generation_calls:0,groups};
}

function filterChunk(unit,source,plan){
 const expected=new Map();
 for(const id of plan.identifiers){const namespace=id.split(/[-_]/u)[0];if(!expected.has(namespace))expected.set(namespace,new Set());expected.get(namespace).add(id);}
 const found=unit.identifiers.length?unit.identifiers:identifiers(source.metadata.title||'');
 for(const [namespace,allowed]of expected){
  const scoped=found.filter(id=>id.split(/[-_]/u)[0]===namespace);
  if(scoped.length&&!scoped.some(id=>allowed.has(id)))return {keep:false,reason:'DIFFERENT_EXPLICIT_IDENTIFIER',found:scoped};
 }
 if(plan.recorded_day){
  const stamp=source.metadata.created_at;
  if(/^\d{4}-\d{2}-\d{2}(?:T.*(?:Z|[+-]\d{2}:\d{2}))?$/u.test(stamp||'')&&stamp.slice(0,10)!==plan.recorded_day)
   return {keep:false,reason:'DIFFERENT_EXPLICIT_RECORD_DATE',found:stamp};
 }
 const compact=normalize(unit.text);
 const excluded=plan.excluded_keywords.filter(word=>compact.includes(normalize(word)));
 const positive=plan.anchors.filter(word=>!plan.excluded_keywords.some(ex=>normalize(ex).includes(normalize(word))));
 if(excluded.length&&positive.length&&!positive.some(word=>compact.includes(normalize(word))))
  return {keep:false,reason:'EXPLICITLY_EXCLUDED_TARGET_ONLY',found:excluded};
 return {keep:true,reason:found.length?'SCOPE_RETAINED':'UNKNOWN_SCOPE_RETAINED'};
}

module.exports={VERSION,planQuestion,filterChunk};
