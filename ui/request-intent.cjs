'use strict';
// High-confidence commands constrain a response independently of the model's own intent label.
// Unrecognized wording remains unclassified; this is not a complete Korean intent classifier.
const VERSION='request-intent-v1';
const CAPTURE_CLARIFICATION='이 채팅에서는 앞으로의 대화를 자동으로 기록하는 설정을 켤 수 없어요. 지금 기록할 내용을 알려주시겠어요?';
const ACTIONS=Object.freeze({
 memory_query:['answer','partial_answer','abstain','clarify','report_conflict','deny'],
 emotion:['empathy','clarify'],advice:['advice','clarify'],
 experience:['draft','clarify'],edit:['draft','clarify'],delete:['draft','clarify'],general:['answer','clarify'],
});
const polite='(?:줘|주세요|주십시오|주실래요|주실래|줄래요|줄래|주시겠어요|주겠어요|주겠니|주라|줄\\s*수\\s*있어(?:요)?|줄\\s*수\\s*있겠어(?:요)?)';
const ending='(?:\\s*(?:부탁해(?:요)?|부탁드립니다|고마워(?:요)?))?\\s*$';
const write=new RegExp('(?:기록|저장|기억|메모)(?:해\\s*(?:두|놓)?(?:어)?\\s*'+polite+'|해\\s*둬|해\\s*놔|해\\s*두세요|해\\s*놓으세요|하자|하세요|해라|\\s*부탁해(?:요)?)'+ending);
const change=new RegExp('(?:(?:수정|정정|변경)해\\s*'+polite+'|(?:고쳐|바꿔)\\s*'+polite+')'+ending);
const remove=new RegExp('(?:(?:삭제|제거)해\\s*'+polite+'|지워\\s*(?:'+polite+')?|잊어\\s*'+polite+')'+ending);
const memoryTarget=/(?:기억|기록|원문|메모|일기|대화|메시지|저장한|저장된|저장했던)/;
const noStore=new RegExp('(?:기록|저장|기억|메모)(?:하지\\s*(?:마(?:세요|십시오|라|요)?|말아\\s*'+polite+')|해\\s*주지\\s*마(?:세요|요)?|할\\s*필요\\s*없(?:어|어요|습니다)|하지\\s*않아도\\s*(?:돼|돼요|됩니다))'+ending);
const withoutStoring=/(?:기록|저장|기억|메모)(?:하지\s*말고|해\s*주지\s*말고)/;
const lookup=new RegExp('(?:(?:찾아|알려|보여)\\s*'+polite+'|(?:조회|검색|확인)해\\s*'+polite+')'+ending);
const advice=new RegExp('(?:조언해\\s*'+polite+'|(?:방법|행동|선택지).{0,40}제안해\\s*'+polite+')'+ending);
const emotion=new RegExp('(?:위로해|공감해|이야기\\s*들어|얘기\\s*들어)\\s*'+polite+ending);
function commandText(text){
 return String(text).normalize('NFKC')
  .replace(/```[\s\S]*?(?:```|$)|~~~[\s\S]*?(?:~~~|$)/g,' ')
  .replace(/^\s*>.*$/gm,' ')
  .replace(/`[^`\n]*`|"(?:\\.|[^"\\])*"|'[^'\n]*'|“[^”]*”|‘[^’]*’|「[^」]*」|『[^』]*』/g,' ')
  .trim();
}
function contract(kind,intents,actions,retrieval){return {version:VERSION,kind,expected_intents:intents,allowed_actions:actions,retrieval};}
function classifyRequest(text){
 const active=commandText(text).replace(/(기록|저장|기억|메모)\s+(?=해)/g,'$1'),clauses=active.split(/[.!?。！？\n]+/u).map(s=>s.trim()).filter(Boolean);
 const intents=new Set();let query=false,negative=false;
 for(const clause of clauses){
  if(noStore.test(clause)||withoutStoring.test(clause))negative=true;
  if(write.test(clause))intents.add('experience');
  if(remove.test(clause))intents.add('delete');
  if(memoryTarget.test(clause)&&change.test(clause))intents.add('edit');
  if(memoryTarget.test(clause)&&lookup.test(clause)&&!/(?:방법|하는\s*법|사용법|뜻|의미|번역|예시|예문)/.test(clause))query=true;
  if(advice.test(clause))intents.add('advice');
  if(emotion.test(clause))intents.add('emotion');
  // Explicit parallel commands need clarification because the response has one intent/action pair.
  if(memoryTarget.test(clause)&&/(?:수정|정정|변경|삭제|제거)해?\s*주고|(?:기록|기억|메모)(?:을|를)?\s*(?:수정|정정|변경|삭제|제거)하고/.test(clause)){
   if(/(?:수정|정정|변경)/.test(clause))intents.add('edit');
   if(/(?:삭제|제거)/.test(clause))intents.add('delete');
  }
  if(/(?:알려|찾아|보여)\s*주고/.test(clause))query=true;
 }
 if(intents.size>1||(query&&intents.size)||(negative&&intents.has('experience'))){
  return contract('mixed_request',[...new Set([...intents,...(query?['memory_query']:[]),...(negative?['general']:[])])],['clarify'],'skip');
 }
 if(negative){
  if(query)return contract('query_without_storage',['memory_query'],ACTIONS.memory_query,'allow');
  return contract('do_not_store',['general','emotion','advice'],['answer','clarify','empathy','advice'],'skip');
 }
 if(intents.has('experience')){
  const future=/(?:앞으로|이제부터|지금부터)(?:는|도)?\s*(?:(?:내가|제가|우리(?:가)?|내|제|너와)\s*)?(?:(?:하는|할|나누는|보내는|입력하는|작성하는|말하는)\s*)?(?:말|대화|메시지|입력|이야기|모든\s*내용)/.test(active)
   ||/(?:자동(?:으로)?\s*(?:기록|저장|기억|메모)|(?:내가|제가)\s*하는\s*말.{0,30}(?:다|모두|전부))/.test(active);
  const result=contract(future?'automatic_capture_request':'record_content',['experience'],future?['clarify']:ACTIONS.experience,'skip');
  // This is an unavailable app setting, so use an app-defined clarification rather than promise capture.
  if(future)result.clarification=CAPTURE_CLARIFICATION;
  return result;
 }
 if(intents.size){const [intent]=intents;return contract(intent+'_request',[intent],ACTIONS[intent],['edit','delete'].includes(intent)?'allow':'skip');}
 if(query)return contract('explicit_memory_query',['memory_query'],ACTIONS.memory_query,'allow');
 return null;
}
function responseIssues(expected,output){
 const issues=[];
 if(!ACTIONS[output.intent]?.includes(output.action))issues.push('intent_action');
 if(expected&&(!expected.expected_intents.includes(output.intent)||!expected.allowed_actions.includes(output.action)||(expected.clarification&&output.answer!==expected.clarification)))issues.push('request_intent');
 return issues;
}
function constrainSchema(schema,expected){
 if(!expected)return schema;
 return {...schema,properties:{...schema.properties,intent:{type:'string',enum:expected.expected_intents},action:{type:'string',enum:expected.allowed_actions},...(expected.clarification?{answer:{type:'string',enum:[expected.clarification]}}:{})}};
}
module.exports={VERSION,ACTIONS,classifyRequest,responseIssues,constrainSchema};
