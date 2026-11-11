'use strict';
const {sentences}=require('./core.cjs');

// Deliberately narrow: only complete affirmative clauses with a single object.
// Quoted, compound, negative and ambiguous clauses stay with semantic review.
const SELF='사용자';
const datePrefix=/^(?:(?:\d{4}\s*년\s*)?\d{1,2}\s*월\s*\d{1,2}\s*일|\d{4}-\d{2}-\d{2})(?:에는|은|에)?\s*/u;
const person='[가-힣A-Za-z][가-힣A-Za-z0-9]{0,15}';
const object='[가-힣A-Za-z0-9]{1,20}';
const verb='받(?:았(?:다|어요|어|습니다)|음)|(?:줬|주었)(?:다|어요|어|습니다)|줌';
const transfer=new RegExp('^(?:(나|저|작성자|사용자)(?:는|가|이|은)\\s+)?('+person+')(에게서|한테서|로부터|에게|한테)\\s+('+object+')(?:을|를)\\s+('+verb+')[.!。！]?$', 'u');
function simpleTransfer(text){
 const body=text.trim().replace(datePrefix,'').replace(/^(?:내가|난|제가|전)\s+/u,'사용자는 ');
 const match=body.match(transfer);
 if(!match)return null;
 const [, ,peer,particle,item,action]=match;
 if(/^(?:나|저|사용자|작성자|우리|그|누구|누군가|어떤사람)$/u.test(peer))return null;
 const receiving=action.startsWith('받');
 if(!receiving&&['에게서','한테서','로부터'].includes(particle))return null;
 return {giver:receiving?peer:SELF,receiver:receiving?SELF:peer,object:item};
}
function sourceTransfers(plan){
 return [...plan.byId].flatMap(([sentence_id,span])=>{
  const fact=simpleTransfer(span.quote);
  return fact?[{sentence_id,...fact}]:[];
 });
}
function transferIssue(text,sentenceIds,facts){
 const selected=facts.filter(f=>sentenceIds.includes(f.sentence_id));
 if(!selected.length)return null;
 for(const sentence of sentences(text)){
  const result=simpleTransfer(sentence.text);
  if(!result)continue;
  const comparable=selected.filter(f=>f.object===result.object);
  if(comparable.length&&!comparable.some(f=>f.giver===result.giver&&f.receiver===result.receiver))return '선택한 근거와 책·물건을 준 사람 또는 받은 사람의 방향이 다름';
 }
 return null;
}
function asksReason(text){return /왜|이유|원인|사유/u.test(text);}
function hasReasonSignal(text){
 // Absence of a signal means we cannot safely assert a causal explanation.
 return /때문|이유|원인|사유|덕분|탓|위해서|하려고|하느라|(?:[가-힣]{2,})(?:아서|어서|여서|라서|차서)/u.test(text);
}
module.exports={sourceTransfers,transferIssue,asksReason,hasReasonSignal};
