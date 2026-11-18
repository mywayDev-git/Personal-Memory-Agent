'use strict';
// These rules describe conversation settings and user statements, never archive writes.
function plain(text){return String(text).normalize('NFKC').replace(/```[\s\S]*?(?:```|$)|~~~[\s\S]*?(?:~~~|$)|`[^`\n]*`|"[^"\n]*"|“[^”]*”|‘[^’]*’|「[^」]*」|『[^』]*』/g,' ').replace(/^\s*>.*$/gm,' ').trim();}
const recordingWord=/(?:기록|저장|기억|메모)/;
const localOnly=/(?:이번(?:만|에는|\s*(?:이야기|내용|질문|답변))|이\s*(?:이야기|내용|질문|답변)(?:만|은|는)|잠깐)/;
const future=/(?:앞으로|이제부터|지금부터|계속|매번|항상|이\s*대화에서는)/;
const stopping=/(?:그만|중단|멈춰|꺼\s*줘|하지\s*마|하지\s*말|안\s*해도|필요\s*없)/;
const emotion=/(?:바보(?:\s*같|야|예요|다)|멍청|한심|자책|내가\s*싫|힘들|속상|지쳤|지쳐|슬퍼|슬프|외로|걱정|불안|기뻐|기쁘|우울|답답|뿌듯|괜찮아|괜찮아요|후련|서운|짜증|화가\s*나|행복|기분.{0,12}(?:안\s*좋|좋|나쁘))/;
const narrative=/(?:오늘|어제|방금|아까|나는|내가|저는|제가|나\s|내\s).{0,200}(?:공부|까먹|잊|느껴|느꼈|생각|다녀|만났|만난|샀|배웠|들었|들은|먹었|했어|했다|했는데|있었|보냈|마셨어|걸었|산책)/;
function analyze(text,base,mode,now){
 const active=plain(text),change=[],local=localOnly.test(active),continuing=future.test(active),recordCommand=recordingWord.test(active)&&/(?:해|하고\s*싶|남겨|부탁|하자|그만|중단|멈춰|하지|안\s*해도)/.test(active);
 const stop=recordCommand&&stopping.test(active),oneOffSkip=stop&&local;
 if(recordCommand&&!local&&(stop||continuing))change.push({type:'record',value:stop?'disabled':'enabled'});
 const styleTarget=/(?:답변|답해|대답|설명|말해)/.test(active),brief=styleTarget&&/(?:짧게|간단히|간결하게)/.test(active),normal=styleTarget&&/(?:원래대로|보통으로|자세히|길게)/.test(active);
 if((brief||normal)&&!local&&(continuing||/원래대로/.test(active)))change.push({type:'style',value:brief?'brief':'normal'});
 const selected=type=>[...base.directives].reverse().find(d=>d.scope===mode&&d.type===type)?.value;
 const record=change.find(d=>d.type==='record')?.value||selected('record')||'disabled';
 const style=local&&(brief||normal)?(brief?'brief':'normal'):change.find(d=>d.type==='style')?.value||selected('style')||'normal';
 const content=change.length?active.split(/[.!?。！？\n]+/).map(s=>s.trim()).filter(s=>s&&!((recordingWord.test(s)&&(future.test(s)||stopping.test(s)))||(/(?:답변|답해|설명|대답)/.test(s)&&/(?:짧게|간단히|간결하게|원래대로|자세히|길게)/.test(s)))).join('. '):active;
 const commandOnly=change.length>0&&!content;
 const explicitRecord=recordCommand&&!change.length&&!stop;
 const feeling=emotion.test(content),personal=!commandOnly&&!stop&&!/[?？]|(?:누가|얼마|언제|어디).{0,30}(?:야|지|까|요|줘)/.test(content)&&(feeling||narrative.test(content));
 const summary=!explicitRecord&&/(?:기분|감정|이야기|내용).{0,15}(?:정리|요약)해/.test(active);
 const recordSummary=summary||explicitRecord&&/(?:기분|감정|이야기|내용|방금|아까|오늘\s*일)/.test(active);
 return {active,content,summary,change,commandOnly,record,style,oneOffSkip,excludeStory:oneOffSkip&&/(?:이야기|내용)/.test(active),skip:stop,explicitRecord,recordSummary,feeling,personal,now,date:new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(now))};
}
function statements(plan,text){
 const list=[...(plan.topic?.utterances||[])];
 if(plan.discourse.personal&&!plan.discourse.explicitRecord)list.push(plan.discourse.content.slice(0,600));
 return [...new Set(list)].slice(-8);
}
function draft(date,items){return '기록 초안 · '+date+'\n\n사용자 표현\n\n'+items.map(s=>'> '+s.replaceAll('\n','\n> ')).join('\n\n')+'\n\n사용자가 표현한 경험과 느낌을 모은 초안이에요. 보관소에는 아직 저장하지 않았어요.';}
function acknowledgement(d){
 const texts=[];
 for(const change of d.change){
  if(change.type==='record')texts.push(change.value==='enabled'?'이 대화에서는 앞으로 말씀하신 경험과 감정을 기록 초안으로 이어서 정리할게요. 계산이나 단순 질문은 별도 요청으로 처리해요. 보관소에 자동 저장하지 않으며, 초안과 저장 여부를 구분해서 알려드릴게요.':'앞으로의 기록 초안 준비를 중단했어요. 기존 초안과 보관소 기록은 그대로입니다.');
  else texts.push(change.value==='brief'?'이 대화에서는 앞으로 답변을 짧게 할게요.':'이 대화의 답변 길이를 기본으로 되돌렸어요.');
 }
 return {intent:'general',action:'answer',answer:texts.join('\n\n'),citations:[]};
}
function response(plan,data){
 const d=plan.discourse;
 if(!d)return null;
 if(d.commandOnly)return acknowledgement(d);
 if(d.skip)return {intent:'general',action:'answer',answer:'이번 내용은 기록 초안에서 제외할게요. 앞으로의 기록 지시는 유지합니다.',citations:[]};
 if(d.recordSummary){
  const items=statements(plan,data.text);
  if(d.summary)return items.length?{intent:'general',action:'answer',answer:'말씀하신 경험과 느낌을 모았어요.\n\n'+items.map(s=>'> '+s.replaceAll('\n','\n> ')).join('\n\n'),citations:[]}:{intent:'general',action:'clarify',answer:'어느 이야기의 기분을 정리할까요?',citations:[]};
  return items.length?{intent:'experience',action:'draft',answer:draft(d.date,items),citations:[]}:{intent:'experience',action:'clarify',answer:'오늘 어떤 기분이었는지 말씀해 주세요. 말씀하신 느낌을 바탕으로 기록 초안을 만들게요.',citations:[]};
 }
 // Self-criticism is a reported feeling, not a claim about the person's ability.
 if(d.feeling&&/(?:바보|멍청|한심|자책)/.test(d.active)){
  const study=statements(plan,data.text).some(s=>/공부|까먹|잊/.test(s));
  return {intent:'emotion',action:'empathy',answer:study?'공부했는데 기억이 잘 나지 않아 속상하고, 스스로를 탓하게 된 것 같아요. 지금 느끼는 마음을 더 들려주셔도 괜찮아요.':'스스로 바보 같다는 생각이 들어 마음이 힘들었겠어요. 어떤 일이 있었는지 들려주실래요?',citations:[]};
 }
 if(d.personal&&plan.topic?.category==='story'&&/(?:공부|까먹|잊)/.test(d.active)&&/바보|자책|한심|멍청/.test(plan.topic.utterances.join(' ')))return {intent:'emotion',action:'empathy',answer:'오늘 공부한 내용이 잘 기억나지 않아서 그런 마음이 들었군요. 말씀하신 상황과 스스로를 탓하는 마음을 함께 이해했어요.',citations:[]};
 return null;
}
function apply(plan,data,result,topic){
 const d=plan.discourse,base=plan.base;
 if(!d)return;
 for(const change of d.change){base.directives=base.directives.filter(old=>old.type!==change.type||old.scope!==plan.mode);base.directives.push({...change,id:'directive-'+data.request_id+'-'+change.type,scope:plan.mode,request_id:data.request_id,text:data.text.slice(0,600),turn:base.revision+1});}
 base.directives=base.directives.slice(-12);
 if(d.excludeStory&&base.story)base.exclusions=[...base.exclusions.filter(e=>e.topic_id!==base.story||e.scope!==plan.mode),{topic_id:base.story,scope:plan.mode}].slice(-8);
 if(!topic||d.commandOnly||d.skip||plan.cancelled.length||plan.correction||plan.returnOnly)return;
 if(topic.category==='story'&&d.personal&&!d.explicitRecord)topic.utterances=[...new Set([...topic.utterances,d.content.slice(0,600)])].slice(-8);
 if(topic.category==='story')base.story=topic.id;
 const capture=d.record==='enabled'&&d.personal&&!d.explicitRecord&&!d.oneOffSkip&&!base.exclusions.some(e=>e.topic_id===topic.id&&e.scope===plan.mode);
 if(capture){
  const previous=base.pending.find(p=>p.scope===plan.mode&&p.topic_id===topic.id&&p.origin==='ongoing_recording'&&p.status==='awaiting_confirmation');
  const recording={status:'draft',date:d.date,statements:plan.recordingSources?plan.recordingSources.map(s=>s.text):[...new Set([...(previous?.recording?.statements||[]),d.content.slice(0,600)])].slice(-8),reason:'지속 기록 지시에 따라 사용자 표현을 이어서 정리했어요.',...(plan.recordingSources?{sources:plan.recordingSources}:{})};
  result.recording=recording;
  const row={id:previous?.id||'pending-'+data.request_id,request_id:data.request_id,topic_id:topic.id,intent:'experience',proposal:draft(recording.date,recording.statements).slice(0,2000),targets:[],status:'awaiting_confirmation',scope:plan.mode,origin:'ongoing_recording',save_target:'personal_facts',source_turn_ids:plan.recordingSources?.map(s=>s.turn_id)||[],recording};
  base.pending=base.pending.filter(p=>p.id!==row.id);base.pending.push(row);
 }
 if(d.explicitRecord&&result.action==='draft'&&topic.category==='story'){
  base.exclusions=base.exclusions.filter(e=>e.topic_id!==topic.id||e.scope!==plan.mode);
  const recording={status:'draft',date:d.date,statements:[...topic.utterances],reason:'현재 이야기의 사용자 표현을 모은 기록 초안이에요.',...(plan.recordingSources?{sources:plan.recordingSources}:{})};
  if(recording.statements.length){result.recording=recording;const current=base.pending.find(p=>p.request_id===data.request_id);if(current){current.recording=recording;current.origin='ongoing_recording';base.pending=base.pending.filter(p=>p.id===current.id||p.topic_id!==topic.id||p.origin!=='ongoing_recording'||p.status!=='awaiting_confirmation');}}
 }
}
module.exports={plain,analyze,statements,draft,response,apply,acknowledgement};
