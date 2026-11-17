'use strict';
const VERSION='summary-preservation-v1';
const AXES=['date','number','negation','condition'];

// Normalize representations, not facts. Never remove negation, tense, actors,
// date/time roles, units, or conditional connectives to make strings match.
function normalize(text){
 let s=String(text).normalize('NFKC').replace(/\r\n/g,'\n').replace(/(?<=\d),(?=\d)/g,'').replace(/[ \t\u00a0]+/g,'');
 const native={열다섯:15,열두:12,열한:11,스무:20,여섯:6,다섯:5,넷:4,네:4,셋:3,세:3,둘:2,두:2,하나:1,한:1,아홉:9,여덟:8,일곱:7,열:10,예순:60,육십:60};
 for(const [word,n]of Object.entries(native))s=s.replace(new RegExp(word+'(?=시|분|명|개|곡|장|만(?:원)?|원)','g'),String(n));
 const digit={일:1,이:2,삼:3,사:4,오:5,육:6,칠:7,팔:8,구:9},unit={십:10,백:100,천:1000};
 s=s.replace(/[일이삼사오육칠팔구십백천]+(?=분|초|개|명|원)/g,word=>{let total=0,n=0;for(const ch of word){if(digit[ch])n=digit[ch];else {total+=(n||1)*unit[ch];n=0;}}return String(total+n);});
 s=s.replace(/(\d+(?:\.\d+)?)만원/g,(_,n)=>String(Number(n)*10000)+'원');
 // Keep explicit 오전/오후 distinct from an unqualified hour.
 s=s.replace(/(오전|오후)(\d{1,2})시(?:(\d{1,2})분|(반))?/g,(_,ap,h,m,half)=>'T'+((Number(h)%12+(ap==='오후'?12:0))*60+Number(m||(half?30:0)))+';');
 s=s.replace(/\b(\d{1,2}):(\d{2})\b/g,(_,h,m)=>'T'+(Number(h)*60+Number(m))+';');
 s=s.replace(/(\d{1,2})시(?:(\d{1,2})분|(반))?/g,(_,h,m,half)=>Number(h)>12?'T'+(Number(h)*60+Number(m||(half?30:0)))+';':'H'+Number(h)+'m'+Number(m||(half?30:0))+';');
 return s;
}
const rx=source=>new RegExp(source,'iu');
function match(text,patterns,{skipDenied=false}={}){for(const pattern of patterns||[]){const re=new RegExp(pattern,'giu');for(const m of text.matchAll(re)){
 if(skipDenied&&/^(?:되었다|되었|했다|했|한|했다는|했다는뜻|되었다는뜻|라는뜻|라는말|다는뜻|다는말|다고|다|은|는|이|가|란|것|뜻|말|주장|이란|것은|뜻은|말은|주장은|완료|된것){0,5}(?:아니|아님|않|없)/u.test(text.slice(m.index+m[0].length)))continue;
 return {pattern,text:m[0],start:m.index,end:m.index+m[0].length,coordinate:'normalized-text'};
 }}return null;}
function outcome(status,code,evidence=null){return {status,code,...(evidence?{evidence}:{} )};}
function evaluateRule(rule,text){
 const normalized=normalize(text);
 const contradiction=match(normalized,rule.forbidden,{skipDenied:true});
 if(contradiction)return outcome('FAIL','CONTRADICTION',contradiction);
 const groups=rule.required||[];
 const evidence=groups.map(g=>({fact:g.fact,match:match(normalized,g.any_of)}));
 const missing=evidence.filter(x=>!x.match);
 if(!missing.length)return {...outcome('PASS','REQUIRED_FACTS_RECOGNIZED'),evidence};
 // An omission is asserted only by a declared, narrowly scoped absence rule.
 // Unrecognized new wording stays REVIEW and cannot silently pass a release.
 const omission=(rule.omissions||[]).find(o=>missing.some(m=>m.fact===o.fact)&&match(normalized,o.when)&&!match(normalized,o.unless));
 if(omission)return {...outcome('FAIL','REQUIRED_FACT_OMITTED'),missing:missing.map(x=>x.fact),reason:omission.reason,evidence};
 return {...outcome('REVIEW','UNRECOGNIZED_WORDING'),missing:missing.map(x=>x.fact),evidence};
}
function evaluateCase(c,summary){
 if(!c?.id||!Array.isArray(c.axes)||!c.axes.length||c.axes.some(a=>!AXES.includes(a))||!Array.isArray(c.rule?.required)||!c.rule.required.length||c.rule.required.some(g=>!g.fact||!Array.isArray(g.any_of)||!g.any_of.length))throw Error('Invalid regression criterion');
 if(typeof summary!=='string'||!summary.trim())return {case_id:c.id,status:'FAIL',axes:Object.fromEntries(AXES.map(a=>[a,c.axes.includes(a)?'FAIL':'NOT_APPLICABLE'])),checks:[outcome('FAIL','EMPTY_SUMMARY')]};
 const result=evaluateRule(c.rule,summary);
 return {case_id:c.id,source_id:c.source_id,status:result.status,axes:Object.fromEntries(AXES.map(a=>[a,c.axes.includes(a)?result.status:'NOT_APPLICABLE'])),checks:[result]};
}
function evaluateCandidates(fixture,rows){
 if(fixture.version!==VERSION)throw Error('Unsupported criteria version');
 if(!Array.isArray(rows))throw Error('Candidates must be an array');
 const byCase=new Map(),bySource=new Map(),knownCases=new Set(fixture.cases.map(c=>c.id)),knownSources=new Set(fixture.cases.map(c=>c.source_id));
 for(const row of rows){
  if(typeof row?.summary!=='string'||(!row.case_id&&!row.source_id))throw Error('Candidate requires case_id or source_id and summary');
  if(row.case_id&&row.source_id)throw Error('Use exactly one candidate identity');
  const map=row.case_id?byCase:bySource,key=row.case_id||row.source_id;
  if(!(row.case_id?knownCases:knownSources).has(key))throw Error('Unknown candidate '+key);
  if(map.has(key))throw Error('Duplicate candidate '+key);map.set(key,row.summary);
 }
 const results=fixture.cases.map(c=>{
  if(byCase.has(c.id)&&bySource.has(c.source_id))throw Error('Overlapping candidate '+c.id);
  const text=byCase.get(c.id)??bySource.get(c.source_id);
  return text===undefined?{case_id:c.id,source_id:c.source_id,status:'NOT_RUN',axes:Object.fromEntries(AXES.map(a=>[a,c.axes.includes(a)?'NOT_RUN':'NOT_APPLICABLE']))}:evaluateCase(c,text);
 });
 const counts=Object.fromEntries(['PASS','FAIL','REVIEW','NOT_RUN'].map(s=>[s,results.filter(r=>r.status===s).length]));
 const axes=Object.fromEntries(AXES.map(a=>[a,Object.fromEntries(['PASS','FAIL','REVIEW','NOT_RUN','NOT_APPLICABLE'].map(s=>[s,results.filter(r=>r.axes[a]===s).length]))]));
 return {version:VERSION,scope:'fixed-22-regression-criteria; not a general Korean semantic grader',status:counts.FAIL?'FAIL':counts.REVIEW||counts.NOT_RUN?'REVIEW':'PASS',complete:counts.NOT_RUN===0,counts,axes,results};
}
module.exports={VERSION,AXES,normalize,evaluateRule,evaluateCase,evaluateCandidates};
