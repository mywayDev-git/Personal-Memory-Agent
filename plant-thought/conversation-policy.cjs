'use strict';
function isQuestion(text){
 return /[?？]|(?:어디|누구|무엇|뭐|언제|어떻게|얼마|왜|어느|몇|동일인|같은\s*사람|기억나|알려\s*(?:줘|주세요)|찾아\s*(?:줘|주세요)|(?:했|갔|봤|였|었)(?:었)?지)(?:[가-힣\s?？.!]|$)/u.test(text);
}
function isExperience(text){return !isQuestion(text)&&/(?:[가-힣]*(?:았|었|였|했|갔|왔|봤))(?:어|다|어요|습니다|음)[.!。\s]*$/u.test(text);}
function isIdentityQuestion(text){return /(?:같은|동일한|다른)\s*(?:사람|인물)|동일인/u.test(text);}
function mentionsName(text,name){
 const escaped=name.replace(/[\[\]\\^$.*+?(){}|]/g,'\\$&');
 return new RegExp('(?<![가-힣A-Za-z0-9])'+escaped+'(?=$|[\\s.,?!？]|와|과|랑|이랑|은|는|이|가|을|를|의|도)','u').test(text);
}
function describedPeople(text,items){
 const groups=new Map();
 for(const item of items)for(const name of item.names||[]){
  if(!mentionsName(text,name))continue;
  const pos=item.body.indexOf(name);if(pos<0)continue;
  const start=Math.max(item.body.lastIndexOf('.',pos-1),item.body.lastIndexOf('\n',pos-1),item.body.lastIndexOf('!',pos-1))+1;
  let prefix=item.body.slice(start,pos).trim();
  prefix=prefix.replace(/^(?:(?:\d{2,4}\s*년\s*)?\d{1,2}\s*월\s*\d{1,2}\s*일(?:에|에는)?|\d{4}-\d{2}-\d{2})\s*/u,'');
  prefix=prefix.replace(/^(?:(?:나는|내가|작성자는|작성자가|오늘|어제|그제|당시)(?:은|는|에)?\s*)+/u,'').trim();
  if(!prefix||prefix.length>30)continue;
  const label=prefix+' '+name,key=name+'\n'+label;
  if(!groups.has(key))groups.set(key,{name,label,rows:[]});
  const group=groups.get(key);if(!group.rows.some(r=>r.memory_key===item.row.memory_key))group.rows.push(item.row);
 }
 return [...groups.values()];
}
function matchContext(text,groups){
 const ignored=new Set(['어디','누구','사람','같은','기록','이야기','여행','갔었지','갔어','알려줘']);
 const query=(text.match(/[가-힣A-Za-z0-9]+/gu)||[]).map(t=>t.replace(/(?:에서|에게|이랑|랑|와|과|은|는|의|를|을|는지|인지)$/u,'')).filter(t=>t.length>=2&&!ignored.has(t));
 const scores=groups.map(g=>({group:g,score:query.filter(t=>t!==g.name&&g.label.includes(t)).reduce((n,t)=>n+t.length,0)}));
 const best=Math.max(0,...scores.map(s=>s.score)),matches=scores.filter(s=>s.score===best&&best>0);
 return matches.length===1?matches[0].group:null;
}
function cleanUnbackedIds(answer,query,citations=[]){
 const grounded=[query,...citations.map(c=>c.quote||'')].join('\n');
 return answer.replace(/\bR[1-9]\d*\b(?:\s*의)?/gu,(id)=>new RegExp('\\b'+id.trim().replace(/\s*의$/u,'')+'\\b','u').test(grounded)?id:'').replace(/ {2,}/g,' ');
}
module.exports={isQuestion,isExperience,isIdentityQuestion,describedPeople,matchContext,cleanUnbackedIds};
