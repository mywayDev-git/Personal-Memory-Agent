'use strict';

const protectedParts = /(```[\s\S]*?```|`[^`\n]*`|https?:\/\/\S+|“[^”]*”|"[^"]*")/g;
const splitProse = text => text.split(protectedParts);
function fragments(text, source, request) {
  if (/번역|영어로|중국어로|일본어로|외국어로|영문으로/.test(request)) return [];
  // Preserve source text, technical names, quoted material, URLs and code.
  const prose = splitProse(text).filter((_,i)=>i%2===0).join(' ');
  const words = prose.match(/[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}]+|\b[a-z]{2,}\b/gu) || [];
  return [...new Set(words.filter(w=>!source.includes(w) && (!/^[a-z]+$/.test(w) ||
    /^(?:because|reason|maybe|please|instead|other|something|really|very|probably|perhaps|suddenly|however|feeling|sorry)$/.test(w))))];
}

function bodyOnly(text) {
  // Remove a conversational question sentence; keep quoted and code examples intact.
  return text.replace(/(```[\s\S]*?```|`[^`\n]*`|“[^”]*”|"[^"]*")|([^.!?。！？\n]*[?？])/g,(match,quoted)=>quoted || '').trim();
}

async function prepare(reply,{turns,evidence,outcomes,call}) {
  const request=turns.at(-1).text;
  const appQuestion=outcomes.find(s=>s.status==='needs_input' && s.question)?.question;
  let question=(appQuestion || (reply.outcome==='needs_input'?reply.question:'')).trim();
  if (/^(?:없음|없습니다|none|null|n\/a)[.!]?$/i.test(question)) question='';
  if(question) question=question.split(/(?<=[?？])\s*/u)[0];
  let answer=question || reply.question ? bodyOnly(reply.answer) : reply.answer.trim();
  if(question && !appQuestion && /(?:필요하신|필요하신가|더 궁금|도와드릴까요|추가 설명)/.test(question)) question='';
  if(!question && !/예문|예시|번역|질문.*(?:작성|만들)|코드/.test(request)) {
    answer=answer.replace(/(?:^|(?<=[.!。！])\s+|\n+)[^.!?\n]*(?:필요하신가요|있으신가요|도와드릴까요|원하시나요)[?？]\s*$/u,'').trim();
  }
  if(question) answer=answer.replace(/(?:^|(?<=[.!?])\s+|\n+)[^.!?\n]*(?:알려\s*주시면|알려\s*주세요)[^.!?\n]*[.!]?\s*$/u,'').trim();
  const source=[...turns.filter(t=>t.role==='user').map(t=>t.text),...evidence.map(e=>e.quote)].join('\n');
  const suspect=fragments(answer+'\n'+question,source,request);
  const tokens=splitProse(answer+'\n'+question).filter((_,i)=>i%2===0).join(' ').match(/[\p{L}]+/gu)||[];
  const words=[...new Set(tokens.filter(token=>suspect.some(w=>token.includes(w))))];
  if(words.length) {
    const schema={type:'object',properties:{replacements:{type:'array',minItems:words.length,maxItems:words.length,items:{type:'string',maxLength:80}}},required:['replacements'],additionalProperties:false};
    const correction=await call('language_repair',[{role:'system',content:'한국어 문장의 words 외국어 조각만 한국어 조사·앞뒤 표현까지 포함한 자연스러운 어절로 교정한다. 예: 다른什么原因인지 → 다른 이유인지, 다른reason인지 → 다른 이유인지. 순서대로 대체 문자열을 제공한다. 불필요하면 빈 문자열이다. 질문이나 사실을 추가하지 않는다.'},{role:'user',content:JSON.stringify({answer,question,words})}],schema);
    const pairs=new Map(words.map((w,i)=>[w,correction.replacements[i]]));
    if(correction.replacements.length!==words.length || correction.replacements.some(x=>!/^([가-힣 ㄱ-ㅎㅏ-ㅣ]*)$/u.test(x))) throw Error('한국어 교정 결과를 확인하지 못했습니다.');
    const repair=text=>splitProse(text).map((part,i)=>i%2?part:part.replace(/[\p{L}]+/gu,w=>pairs.get(w)??w)).join('');
    answer=repair(answer);question=repair(question);
    if(fragments(answer+'\n'+question,source,request).length) throw Error('답변의 언어 교정을 완료하지 못했습니다.');
  }
  return {...reply,outcome:!question && reply.outcome==='needs_input'?'answered':reply.outcome,answer:answer || question,question};
}
module.exports={prepare,fragments};
