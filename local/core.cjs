const crypto=require('node:crypto');
const hash=x=>crypto.createHash('sha256').update(typeof x==='string'?x:JSON.stringify(x)).digest('hex');
function schemaIssues(value,schema,at='$'){
 const errors=[],type=Array.isArray(value)?'array':value===null?'null':typeof value;
 const validType=Array.isArray(schema.type)?schema.type.includes(type):schema.type==='integer'?Number.isInteger(value):schema.type===type;
 if(schema.type&&!validType)return [at+': expected '+schema.type];
 if(schema.enum&&!schema.enum.includes(value))errors.push(at+': enum mismatch');
 if(schema.minimum!==undefined&&value<schema.minimum)errors.push(at+': below minimum');
 if(type==='array'&&schema.minItems!==undefined&&value.length<schema.minItems)errors.push(at+': too few items');
 if(type==='array'&&schema.maxItems!==undefined&&value.length>schema.maxItems)errors.push(at+': too many items');
 if(type==='array')value.forEach((v,i)=>errors.push(...schemaIssues(v,schema.items,at+'['+i+']')));
 if(type==='object'){
  for(const key of schema.required||[])if(!Object.hasOwn(value,key))errors.push(at+'.'+key+': required');
  for(const key of Object.keys(value)){if(schema.properties?.[key])errors.push(...schemaIssues(value[key],schema.properties[key],at+'.'+key));else if(schema.additionalProperties===false)errors.push(at+'.'+key+': unexpected property');}
 }
 return errors;
}
function sentences(text){
 const out=[];const re=/.*?(?:[.!?。！？](?=\s|$)|\n|$)/gs;
 for(const m of text.matchAll(re)){const raw=m[0];if(!raw.trim())continue;const leading=raw.length-raw.trimStart().length,start=m.index+leading,value=raw.trim();out.push({id:'S'+(out.length+1),start,end:start+value.length,text:value});}
 return out;
}
function locate(text,quote,occurrence=1){if(!quote||!Number.isInteger(occurrence)||occurrence<1)return null;let at=-1;for(let i=0;i<occurrence;i++){at=text.indexOf(quote,at+1);if(at<0)return null;}return {start:at,end:at+quote.length,quote};}
function validateNative(method,native,source){
 if(!native||typeof native!=='object'||Array.isArray(native))throw Error('구조화 출력은 JSON 객체여야 합니다.');
 const ss=sentences(source.text),byId=new Map(ss.map(s=>[s.id,s]));const units=[],errors=[];let rows;
 if(method==='triples'){if(!Array.isArray(native.facts))throw Error('facts 배열 누락');rows=native.facts.map((f,i)=>({...f,id:'F'+(i+1),label:[f.subject,f.relation,f.object].filter(Boolean).join(' · ')}));}
 else if(method==='events'){if(!Array.isArray(native.events))throw Error('events 배열 누락');rows=native.events.map((e,i)=>({...e,id:'EV'+(i+1),subject:e.actor,relation:e.action,label:[e.actor,e.action,e.object].filter(Boolean).join(' · ')}));}
 else if(method==='entities'){
  if(!Array.isArray(native.entities)||!Array.isArray(native.relationships))throw Error('entities/relationships 배열 누락');rows=[];
  native.entities.forEach((e,i)=>{if(!Array.isArray(e.attributes))throw Error('개체 attributes 배열 누락');e.attributes.forEach((a,j)=>rows.push({...a,id:`EN${i+1}-A${j+1}`,subject:e.name,object:a.value,label:[e.name,a.relation,a.value].filter(Boolean).join(' · ')}));});
  native.relationships.forEach((r,i)=>rows.push({...r,id:'REL'+(i+1),label:[r.subject,r.relation,r.object].filter(Boolean).join(' · ')}));
 }else throw Error('Unknown method');
 if(rows.length>100)throw Error('원문당 의미 단위가 100개를 초과했습니다.');
 for(const row of rows){
  const evidence=[],highlights=[];const localErrors=[];
  for(const key of ['subject','relation','object','polarity','status','modality','time','event_time','speech_time','valid_from','valid_to','condition'])if(typeof row[key]!=='string')localErrors.push(key+' 문자열 누락');
  if(!['positive','negative','unknown'].includes(row.polarity))localErrors.push('polarity 값 오류');
  if(!['planned','in_progress','completed','cancelled','failed','unknown','not_applicable'].includes(row.status))localErrors.push('status 값 오류');
  if(!['asserted','reported','hypothesis','opinion','question','unknown'].includes(row.modality))localErrors.push('modality 값 오류');
  if(!Array.isArray(row.evidence)||!row.evidence.length)localErrors.push('원문 근거 누락');
  for(const e of row.evidence||[]){const s=byId.get(e.sentence_id),pos=s&&locate(s.text,e.quote,e.occurrence);if(!pos)localErrors.push('근거 문구/문장 불일치: '+(e.sentence_id||'?'));else evidence.push({source_id:source.id,revision:source.revision,sentence_id:s.id,start:s.start+pos.start,end:s.start+pos.end,quote:e.quote});}
  if(!Array.isArray(row.mentions))localErrors.push('mentions 배열 누락');
  for(const m of row.mentions||[]){const s=byId.get(m.sentence_id),pos=s&&locate(s.text,m.text,m.occurrence);if(!pos)localErrors.push('하이라이트 문구 불일치');else highlights.push({role:m.role,start:s.start+pos.start,end:s.start+pos.end,quote:m.text});}
  const unit={...row,source_id:source.id,revision:source.revision,evidence,highlights,validation_errors:localErrors};units.push(unit);errors.push(...localErrors.map(e=>row.id+': '+e));
 }
 return {source_id:source.id,revision:source.revision,text:source.text,sentences:ss,native,units,errors,valid:!errors.length,warnings:units.length?[]:['의미 단위가 비어 있습니다. 의미 누락 여부는 사람 검토가 필요합니다.']};
}
function chunks(source,max=700,overlap=100){
 // UTF-16 text spans, sentence boundaries preferred. Budget is also checked with runtime tokenization before generation.
 const ss=sentences(source.text),out=[];let start=0;
 while(start<source.text.length){let end=Math.min(start+max,source.text.length);const boundary=ss.filter(s=>s.end>start&&s.end<=end).at(-1);if(boundary&&boundary.end>start+max/3)end=boundary.end;out.push({id:`${source.id}:C${out.length+1}`,source_id:source.id,revision:source.revision,start,end,text:source.text.slice(start,end)});if(end===source.text.length)break;start=Math.max(start+1,end-overlap);}
 return out;
}
function unitText(u){return JSON.stringify({subject:u.subject,relation:u.relation,object:u.object,participants:u.participants||[],polarity:u.polarity,status:u.status,modality:u.modality,time:u.time,event_time:u.event_time||'',speech_time:u.speech_time||'',valid_from:u.valid_from||'',valid_to:u.valid_to||'',condition:u.condition});}
function cosine(a,b){if(a.length!==b.length||!a.length)throw Error('임베딩 차원 불일치');let dot=0,aa=0,bb=0;for(let i=0;i<a.length;i++){if(!Number.isFinite(a[i])||!Number.isFinite(b[i]))throw Error('비정상 임베딩 값');dot+=a[i]*b[i];aa+=a[i]*a[i];bb+=b[i]*b[i];}if(!aa||!bb)throw Error('영벡터 임베딩');return dot/Math.sqrt(aa*bb);}
function rrf(lists,k=60){const scores=new Map();for(const list of lists)list.forEach((x,i)=>{const old=scores.get(x.id)||{...x,fusion_score:0};old.fusion_score+=1/(k+i+1);scores.set(x.id,old);});return [...scores.values()].sort((a,b)=>b.fusion_score-a.fusion_score||a.id.localeCompare(b.id));}
function queryText(q,c,preset){return preset==='query-original-v1'?q.text:q.text+'\n대화 맥락: '+JSON.stringify(c.conversation.slice(-4));}
function safeConversation(context,accessible){const ids=new Set(accessible.map(s=>s.id));return context.conversation.filter(t=>!(t.source_refs||[]).some(r=>!ids.has(r.source_id))).map(t=>({...t,...(t.items?{items:t.items.filter(i=>ids.has(i.source_id))}:{})}));}
function validateCitations(answer,evidence,policy={}){
 const errors=[],citations=[];if(!answer||typeof answer.answer!=='string'||!['answer','partial_answer','abstain','clarify','report_conflict','deny'].includes(answer.action)||!Array.isArray(answer.citations))throw Error('답변 스키마 오류');
 for(const c of answer.citations){const e=evidence.find(e=>e.evidence_id===c.evidence_id),p=e&&locate(e.text,c.quote,c.occurrence);if(!p)errors.push('인용 근거 또는 원문 구간이 유효하지 않음: '+c.evidence_id);else citations.push({...c,source_id:e.source_id,revision:e.revision,start:e.start+p.start,end:e.start+p.end});}
 if((policy.require_citation??(answer.action==='answer'))&&!citations.length)errors.push('개인 기록 사실 답변에 유효한 인용이 없음');
 return {citations,errors};
}
module.exports={hash,schemaIssues,sentences,locate,validateNative,chunks,unitText,cosine,rrf,queryText,safeConversation,validateCitations};
