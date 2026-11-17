'use strict';
const state=require('./plant-thought/conversation-context.js');
const {classifyRequest,ACTIONS}=require('./request-intent.cjs');
const conversation=require('./conversation-policy.cjs');
const words=text=>String(text).normalize('NFKC').toLowerCase().match(/[\p{L}\p{N}]{2,}/gu)||[];
const stop=new Set(['그사람','그것','그건','그게','사람은','누가','누구','어디','언제','뭐였지','알려줘','기록','기억','내용','이야기','아까','앞서','다시','돌아가자','대해서']);
function terms(text){return words(text).filter(w=>!stop.has(w)).flatMap(w=>[w,...Array.from({length:Math.max(0,w.length-1)},(_,i)=>w.slice(i,i+2))]);}
function overlap(text,topic){const hay=[topic.label,...topic.questions].join(' ').toLowerCase();return [...new Set(terms(text))].reduce((n,t)=>n+(hay.includes(t)?t.length:0),0);}
function sourceMap(scope){return new Map(scope.sources.map(s=>[s.id,s]));}
function validReference(r,sources){const s=sources.get(r.source_id);return !!s&&s.revision===r.revision&&s.text.slice(r.start,r.end)===r.quote;}
function hydrate(value,threadId,scope,mode){
 const context=state.normalize(value,threadId),sources=sourceMap(scope);
 for(const t of context.topics){const had=t.references.length;t.references=t.scope===mode?t.references.filter(r=>validReference(r,sources)):[];t.unavailable=had>0&&!t.references.length;t.needs_target=t.needs_target||t.unavailable;if(t.unavailable&&!t.correction)t.focus='';if(t.references.length)t.label=sources.get(t.references[0].source_id).metadata.title.slice(0,200);}
 return context;
}
function plain(text){return String(text).replace(/```[\s\S]*?```|`[^`]*`|"[^"\n]*"|“[^”]*”|‘[^’]*’|「[^」]*」/g,' ');}
function isGeneral(text){return /(?:\d|[일이삼사오육칠팔구십]).{0,18}(?:더하면|더해|곱하면|빼면|나누면|계산|\+|\*|\d\s*[-/])/.test(text);}
function requestContract(intent){return {version:'request-intent-v1',kind:'context_'+intent,expected_intents:[intent],allowed_actions:ACTIONS[intent],retrieval:['general','emotion','advice','experience'].includes(intent)?'skip':'allow'};}
function resolve(data,scope,now=new Date().toISOString()){
 const mode=data.collection_id||'samples',base=hydrate(data.context,data.thread_id,scope,mode),text=data.text,active=base.topics.find(t=>t.id===base.active&&t.scope===mode);
 const discourse=conversation.analyze(text,base,mode,now);
 const story=base.topics.find(t=>t.id===base.story&&t.scope===mode&&t.category==='story');
 const available=base.topics.filter(t=>t.scope===mode&&(t.kind==='memory_query'||t.category==='story'));
 let expected=classifyRequest(text);const unquoted=plain(text);
 if(discourse.commandOnly||discourse.skip)expected=requestContract('general');
 else if(discourse.summary)expected=requestContract('general');
 else if(discourse.explicitRecord)expected=requestContract('experience');
 else if(discourse.feeling)expected=requestContract('emotion');
 else if(discourse.personal)expected=requestContract('experience');
 if(!expected){if(/(?:힘들어(?:요)?|속상해(?:요)?|지쳤어(?:요)?|슬퍼(?:요)?|외로워(?:요)?|걱정돼(?:요)?|기뻐(?:요)?)[.!…\s]*$/.test(unquoted))expected=requestContract('emotion');else if(/어떻게.{0,45}(?:좋을까|해야\s*할까|하면\s*될까)/.test(unquoted))expected=requestContract('advice');else if(/(?:오늘|어제|방금|내가|나는|저는).{0,160}(?:만났어|다녀왔어|샀어|배웠어|들었어|먹었어|했어)[.!…\s]*$/.test(unquoted))expected=requestContract('experience');}
 if(expected?.expected_intents[0]==='experience'&&!discourse.recordSummary&&expected.kind!=='automatic_capture_request'&&/(?:오늘|어제|방금|내가|나는|저는).{0,180}(?:들었|들은|다녀왔|다녀온|만났|만난|배웠|배운|샀|산(?=\s)|먹었|먹은|했어|했다)/.test(text)){
  const supplied=discourse.content.replace(/\s*(?:(?:이|그|위)\s*(?:내용|사실|경험|일)(?:을|를)?|이걸|그걸)?\s*(?:기록|저장|기억|메모)(?:해|하여|\s*부탁)[\s\S]{0,60}$/,'').trim().replace(/(?:을|를)$/,'');
  if(supplied)expected={...expected,allowed_actions:['draft'],draft_text:supplied};
 }
 const returning=/(?:아까|앞서|이전|전에|다시).{0,45}(?:돌아|이야기|얘기|업무|기록|계속)|(?:이야기|얘기).{0,20}돌아/.test(unquoted);
 const referent=/(?:그\s*(?:사람|분|기록|작업|내용|일|서버|숙소|예약|장소|물건|책|상자|금액|일정|프로젝트)|그건|그게|그거|그때|이어서|그쪽|해당\s*(?:사람|기록))/.test(unquoted)||/^(?:언제|어디|얼마|완료|끝났|끝나|맡은|(?:배포|검토|수리|작업|행사)(?:가|는|이|은)?\s*(?:끝났|완료|끝나))/.test(unquoted.trim());
 let topic=null,relation='new_topic',clarification=null,choices=[];
 const selection=data.context_selection;
 if(selection){topic=base.topics.find(t=>t.id===selection&&t.scope===mode);if(!topic&&!base.pending.some(p=>p.id===selection&&p.scope===mode&&p.status==='awaiting_confirmation'))throw Object.assign(Error('선택한 대화 대상이 현재 맥락에 없습니다.'),{status:409,stage:'context'});relation='return';}
 else if(returning){
  const ranked=available.map(t=>({t,score:overlap(text,t)})).sort((a,b)=>b.score-a.score||b.t.turn-a.t.turn);
  if(ranked.length===1||ranked[0]?.score>0&&ranked[0].score>ranked[1]?.score){topic=ranked[0].t;relation='return';}
  else{clarification='어느 이야기로 돌아갈까요? 이어갈 주제를 선택해 주세요.';choices=available.map(t=>({id:t.id,label:t.label}));}
 }else if(referent){
  topic=active?.kind==='memory_query'?active:available.length===1?available[0]:null;relation='continue';
  if(!topic){clarification='어떤 사람이나 기록을 가리키는지 확인할 수 없어요. 대상이나 주제를 알려주시겠어요?';choices=available.map(t=>({id:t.id,label:t.label}));}
 }else if(active&&overlap(text,active)>=8&&!isGeneral(text)){topic=active;relation='related';}
 if(!selection&&!returning&&(discourse.personal||discourse.recordSummary)&&story&&((active?.id===story.id&&(discourse.feeling||/(?:그래서|그러니까|그런데|왜냐하면|그게|해서|어서|는데|거든)/.test(unquoted)))||discourse.recordSummary||overlap(text,story)>=4||(/(?:그래서|그러니까|그런데|왜냐하면|그게|아까)/.test(unquoted)))){topic=story;relation='continue';clarification=null;}
 if(discourse.commandOnly||discourse.skip){topic=null;relation='new_topic';clarification=null;choices=[];}
 const pending=base.pending.filter(p=>p.status==='awaiting_confirmation'&&p.scope===mode);
 const cancel=/(?:취소해\s*(?:줘|주세요)|취소할게|취소합니다|^취소$)/.test(unquoted.trim());
 let cancelled=[];
 if(cancel){
  const requested=(data.pending_target||selection)?pending.filter(p=>p.id===(data.pending_target||selection)):returning&&topic?pending.filter(p=>p.topic_id===topic.id):pending;
  if(requested.length===1){cancelled=requested.map(p=>p.id);clarification=null;choices=[];relation='cancel';topic=base.topics.find(t=>t.id===requested[0].topic_id)||topic;}
  else{clarification=requested.length?'어느 확인 대기 작업을 취소할까요? 작업을 선택해 주세요.':'현재 취소할 확인 대기 작업이 없어요. 어떤 작업을 말씀하시는지 알려주시겠어요?';choices=requested.map(p=>({id:p.id,label:p.proposal.slice(0,80),pending:true}));}
 }
 const correction=unquoted.match(/([가-힣]{2,8}?)(?:이|가)?\s*(?:아니라|말고)\s*([가-힣]{2,8}?)(?:이야|야|예요|이에요|입니다)[.!?]?$/);
 const correctOnly=!!correction&&!['edit','delete','experience'].some(i=>expected?.expected_intents.includes(i));
 if(correctOnly){topic=topic||active;relation='correction';if(!topic)clarification='어느 대화의 대상을 정정할까요? 주제나 기록을 알려주세요.';else clarification=null;}
 const general=isGeneral(unquoted)&&!returning;
 if(general){topic=null;relation='new_topic';clarification=null;}
 let resolvedQuestion=null;
 if(base.awaiting?.scope===mode&&base.awaiting.intent==='memory_query'&&!expected&&!returning&&!cancel&&!correctOnly&&!general&&unquoted.length<=30&&!/[?？]|어디|언제|누가|무엇|어떻게|사람은|뭐였|얼마|어느|끝났|알려|찾아|보여|오늘|어제|내가|나는|저는/.test(unquoted)&&/^[가-힣A-Za-z0-9 ·_-]{1,30}$/.test(unquoted.trim())){
  topic=base.topics.find(t=>t.id===(selection||base.awaiting.topic_id)&&t.scope===mode)||topic;
  if(!topic&&available.length===1)topic=available[0];
  resolvedQuestion=base.awaiting.question;relation='continue';clarification=null;
 }
 const kind=general?'general':expected?.expected_intents.length===1?expected.expected_intents[0]:'memory_query';
 const fixed=general?requestContract('general'):expected||(resolvedQuestion?requestContract(base.awaiting.intent==='experience'?'experience':'memory_query'):null);
 // Explicit new subjects never inherit an earlier person's identity or quote context.
 const connected=!!topic&&(['continue','return','correction'].includes(relation)||topic.category==='story'&&relation==='related');
 if(connected&&topic.needs_target&&!correctOnly&&!cancel){clarification='이전 대상을 연결하던 원문의 현재 버전을 확인할 수 없어요. 이어갈 사람이나 기록을 다시 알려주시겠어요?';choices=[];}
 if(pending.length&&/^(?:응|네|좋아|확인|기록하기|기록해|저장해|반영해|수정\s*반영|삭제\s*확인)[.!?\s]*(?:줘|주세요)?[.!?\s]*$/.test(unquoted.trim())){clarification='확인한 초안이 있어도 채팅에서는 원문 변경을 직접 실행할 수 없어요. 기록을 새로 작성하려면 감정 갈무리에서 내용을 확인하고 저장해 주세요.';choices=[];}
 if(connected&&!resolvedQuestion&&!topic.focus&&/(?:그\s*사람|그분)/.test(unquoted)&&actorNames(topic.references).length>1){clarification='앞선 기록에 여러 사람이 나와요. 어느 사람인지 이름이나 소속을 알려주시겠어요?';choices=[];}
 const history=connected?topic.questions:[];
 const references=connected?topic.references:[];
 const statusLookup=/(?:끝났|끝나|완료|마쳤|마무리)/.test(resolvedQuestion||text)?'완료 보고 실패 대기 진행 상태':'';
 const lookup=[resolvedQuestion||text,...(resolvedQuestion?[text]:[]),...(connected?[topic.focus,topic.correction,statusLookup,...(!topic.focus?[topic.label,...history.slice(0,1)]:[])]:[])].join(' ');
 return {base,mode,topic,relation,kind,discourse,text,returnOnly:!!topic&&returning&&/(?:돌아가자|돌아갈게|돌아가줘|계속하자|이어가자)[.!?\s]*$/.test(unquoted),expected:fixed,history,references,lookup,clarification,choices,cancelled,resolvedQuestion,correction:correctOnly&&topic?{from:correction[1],to:correction[2]}:null,
  modelContext:{relation,resolved_question:resolvedQuestion,user_selection:resolvedQuestion?text:null,topic:topic?.label||null,selected_target:connected?topic.focus||null:null,user_correction:connected?topic.correction||null:null,verified_references:references,reference_time:scope.now,current_time:now,ongoing_instructions:{record:discourse.record,response_style:discourse.style,scope:'this_conversation'},user_statements:connected?topic.utterances:[],notice:'user_statements는 사용자가 말한 경험과 느낌이며 객관적 사실이나 성격으로 확정하지 않는다. 보관소의 개인 사실은 이번 evidence로만 답한다.'}};
}
function actorNames(citations){
 const found=new Set();
 for(const c of citations)for(const m of c.quote.matchAll(/(?:^|\s)(?:(회사|도서관|출판사|연구실|독서\s*모임|[가-힣]{2,8}팀|[가-힣]{2,8}동호회)\s+)?([가-힣]{2,4}?)(?:은|는|이|가|에게)\s/g)){
  if(!['기록','서버','배포','검토','사람','작업','보고서','보고','담당','결과','시각','예약','금액','확인','이름','소속','시간','일정','선택','입력','질문','검사','기능','설정','알림','진동','운영','완료','내용','인계','재검사','반영','범위','내가','나는','그녀','우리','현재','공방'].includes(m[2]))found.add((m[1]?m[1]+' ':'')+m[2]);
 }
 return [...found];
}
function focusFrom(answer,citations){
 const clean=String(answer).replace(/[*_`]/g,''),all=actorNames(citations);
 const qualified=all.filter(n=>n.includes(' ')&&clean.includes(n));if(qualified.length===1)return qualified[0];
 const matching=all.filter(n=>clean.includes(n)||(!n.includes(' ')&&clean.includes(n)));
 return matching.length===1?matching[0]:all.length===1&&clean.includes(all[0].split(' ').at(-1))?all[0]:'';
}
function update(plan,data,result){
 const base=plan.base,scope=plan.mode;let topic=plan.topic&&base.topics.find(t=>t.id===plan.topic.id);
 if(plan.cancelled.length){for(const p of base.pending)if(plan.cancelled.includes(p.id))p.status='cancelled';}
 if(plan.correction){const t=base.topics.find(t=>t.id===plan.topic.id);t.focus=plan.correction.to;t.correction='사용자가 대화 대상을 '+plan.correction.from+'에서 '+plan.correction.to+'로 정정함. 원문 변경이 아님.';t.references=[];base.active=t.id;}
 else if(!plan.clarification&&!plan.cancelled.length&&!plan.discourse?.commandOnly&&!plan.discourse?.skip){
  const refs=(result.citations||[]).filter(c=>c.quote.length<=1000).slice(0,4).map(({source_id,revision,start,end,quote})=>({source_id,revision,start,end,quote}));
  if(!topic){const id='topic-'+data.request_id;topic={id,label:((result.citations||[])[0]?.title||data.text.replace(/\s+/g,' ').slice(0,70)),scope,kind:result.intent,category:plan.discourse?.personal||plan.discourse?.recordSummary?'story':'request',utterances:[],questions:[],references:[],focus:'',correction:'',turn:base.revision};base.topics.push(topic);}
  topic.kind=refs.length||topic.kind==='memory_query'?'memory_query':result.intent;topic.turn=base.revision+1;if(!plan.returnOnly)topic.questions=[...topic.questions,(plan.resolvedQuestion||data.text).slice(0,600)].slice(-3);if(refs.length){topic.references=refs;topic.label=result.citations[0].title.slice(0,200);topic.needs_target=false;}
  if(result.intent==='memory_query'){topic.focus=focusFrom(result.answer,result.citations||[])||(['continue','return'].includes(plan.relation)?topic.focus:'');}
  base.active=topic.id;
  if(['experience','edit','delete'].includes(result.intent)&&result.action==='draft'){
   const id='pending-'+data.request_id,pending={id,request_id:data.request_id,topic_id:topic.id,intent:result.intent,proposal:result.answer.slice(0,2000),targets:[...new Set((result.citations||[]).map(c=>c.source_id))].slice(0,12),status:'awaiting_confirmation',scope};
   base.pending=base.pending.filter(p=>p.id!==id);base.pending.push(pending);
  }
 }
 conversation.apply(plan,data,result,topic);
 base.task={request_id:data.request_id,intent:result.intent,status:result.action==='clarify'||result.action==='draft'?'waiting':'completed',topic_id:topic?.id||null};
 if(result.action==='clarify'&&!plan.cancelled.length)base.awaiting={question:plan.resolvedQuestion||data.text,topic_id:plan.topic?.id||base.active,intent:result.intent,scope};else base.awaiting=null;
 const pinned=base.topics.find(t=>t.id===base.story);base.topics=base.topics.filter(t=>t.id!==pinned?.id).sort((a,b)=>a.turn-b.turn).slice(-(pinned?5:6));if(pinned)base.topics.push(pinned);base.pending=base.pending.slice(-8);base.revision=data.context.revision+1;base.last_request=data.parent_request_id||data.request_id;
 return state.normalize(base,data.thread_id);
}
function splitTasks(text){
 if(classifyRequest(text)?.kind!=='mixed_request')return [text];
 // Protect quoted content when splitting explicit top-level commands.
 const tokens=[];let protectedText=text.replace(/```[\s\S]*?```|`[^`]*`|"[^"\n]*"|“[^”]*”|‘[^’]*’/g,s=>{tokens.push(s);return '\uE000'+(tokens.length-1)+'\uE001';});
 protectedText=protectedText.replace(/(알려|찾아|보여|수정해|삭제해|저장해|기록해)\s*주고\s*/g,'$1줘.\n');
 const parts=protectedText.split(/[.!?。！？]\s+|\n+|\s+그리고\s+/).map(s=>s.trim().replace(/\uE000(\d+)\uE001/g,(_,n)=>tokens[Number(n)])).filter(Boolean);
 if(parts.length<2||parts.length>3)return [text];
 const contracts=parts.map(classifyRequest);if(contracts.some((c,i)=>(!c&&!/(?:알려|찾아|보여)\s*(?:줘|주세요|줄래)/.test(parts[i]))||c?.kind==='mixed_request'||c?.kind==='do_not_store'))return [text];
 return parts;
}
function policy(plan){
 if(plan.clarification)return {intent:plan.expected?.expected_intents[0]||'memory_query',action:'clarify',answer:plan.clarification,citations:[]};
 if(plan.returnOnly)return {intent:'general',action:'answer',answer:'앞서 이야기한 '+plan.topic.label+' 주제로 돌아왔어요. 이어서 어떤 내용을 확인할까요?',citations:[]};
 if(plan.cancelled.length)return {intent:'general',action:'cancelled',answer:'선택한 확인 대기 작업을 취소했어요. 다른 초안과 보관소 기록은 그대로입니다.',citations:[]};
 const response=conversation.response(plan,{text:plan.text});if(response)return response;
 if(plan.expected?.draft_text)return {intent:'experience',action:'draft',answer:'기록 초안\n\n> '+plan.expected.draft_text.replaceAll('\n','\n> ')+'\n\n아직 보관소에 저장하지 않았어요.',citations:[]};
 if(plan.correction)return {intent:'general',action:'answer',answer:'이 대화에서는 대상을 '+plan.correction.to+'으로 정정해서 이어갈게요. 저장된 원문은 바꾸지 않았어요.',citations:[]};
 return null;
}
function targetEvidence(plan,data,evidence){
 if(!plan?.topic||plan.topic.category==='story'||!['continue','return'].includes(plan.relation))return null;
 const text=plan.resolvedQuestion||data.text,person=/(?:그\s*사람|그분)/.test(text)&&!!plan.topic.focus;
 const ignored=new Set(['사람','맡은','맡았','끝났어','끝났','끝나','완료','상태','작업','기록','내용','언제','어디','누구','누가','배포','검토','수락','인계','아까','이야기','돌아가자','알려줘','현재','다시','서버배포']);
 const anchors=[...new Set(words(text).map(w=>w.replace(/(?:에게|에서|으로|은|는|이|가|을|를|의|로)$/,'')))].filter(w=>w.length>=2&&!ignored.has(w)&&!/^그/.test(w));
 const focus=plan.topic.focus,qualified=focus.includes(' '),name=focus.split(' ').at(-1);
 if(!person&&!anchors.length&&!focus)return null;
 const matchesName=s=>!!focus&&(s.includes(focus)||(!qualified&&s.includes(name)));
 const matchesWork=s=>anchors.some(w=>s.includes(w));
 const eligible=e=>{
  const text=e.text||e.quote||'',actors=actorNames([{quote:text}]);
  if(person&&actors.length&&!actors.some(n=>n===focus||(!qualified&&n.split(' ').at(-1)===name)))return false;
  return matchesName(text)||matchesWork(text);
 };
 const allowed=evidence.filter(eligible).map(e=>e.evidence_id);
 const quoteCompatible=quote=>{
  const actors=actorNames([{quote}]),same=actors.some(n=>n===focus||(!qualified&&n.split(' ').at(-1)===name));
  if(person&&actors.length&&!same)return false;
  if(!person&&actors.length&&focus&&!same&&(!anchors.length||!matchesWork(quote)))return false;
  return true;
 };
 return {person,focus,anchors,allowed,eligible,quoteCompatible};
}
function constrainEvidence(schema,target){
 if(!target?.allowed.length)return schema;
 const citations=schema.properties.citations,items=citations.items;
 return {...schema,properties:{...schema.properties,citations:{...citations,items:{...items,properties:{...items.properties,evidence_id:{type:'string',enum:target.allowed}}}}}};
}
function completionContract(plan,data,evidence,target){
 if(!target||!/(?:끝났|끝나|완료|마쳤|마무리)/.test(plan.resolvedQuestion||data.text))return null;
 const rows=evidence.filter(e=>target.allowed.includes(e.evidence_id));
 const completed=rows.some(e=>/(?:배포했다|배포를\s*마쳤|작업을\s*완료했다|검토를\s*마쳤|수리를\s*마쳤|행사를\s*마쳤|완료\s*보고.{0,6}받았다)/.test(e.text)&&!/(?:않|아직|없|대기)/.test(e.text));
 const missing=rows.filter(e=>/(?:완료|끝났|마쳤|배포).{0,12}(?:보고|연락|확인).{0,12}(?:없|못|대기)/.test(e.text));
 if(completed)return null;
 return {version:'request-intent-v1',kind:'completion_unconfirmed',expected_intents:['memory_query'],allowed_actions:['abstain'],retrieval:'allow',clarification:'현재 기록에서는 해당 작업의 완료를 확인할 수 없어요. 담당 인계나 다른 작업의 완료와 실제 완료 여부는 구분해야 합니다.',evidence_ids:(missing.length?missing:rows).map(e=>e.evidence_id),require_citation:missing.length>0};
}
module.exports={resolve,update,policy,splitTasks,validReference,requestContract,targetEvidence,constrainEvidence,completionContract};
