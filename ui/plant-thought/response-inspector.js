'use strict';
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.PlantResponseInspector=api;})(typeof window==='undefined'?null:window,function(){
 function goalMode(message){return message.result?.action_trace?.version==='goal-actions-v1'||(!message.result&&['v2','v3'].includes(message.submission?.analysis_version));}
 function renderGoal(doc,message,answerElement){
  const result=message.result,trace=result?.action_trace,plan=trace?.plan;
  const node=(tag,text,cls)=>{const e=doc.createElement(tag);if(text!=null)e.textContent=text;if(cls)e.className=cls;return e;};
  const panel=node('details',null,'ai-response-inspection');panel.open=message.inspectionExpanded===true;panel.append(node('summary','목표·행동·실행 결과 · 테스트 전용'));const content=node('div',null,'ai-inspection-content');panel.append(content);
  function section(title){const s=node('section');s.append(node('h4',title));content.append(s);return s;}
  function row(dl,key,value){dl.append(node('dt',key),node('dd',value));}
  function raw(parent,title,value){const detail=node('details',null,'ai-inspection-raw');detail.append(node('summary',title));const pre=node('pre');pre.tabIndex=0;pre.textContent=typeof value==='string'?value:JSON.stringify(value,null,2);detail.append(pre);parent.append(detail);}
  const status={planned:'계획에 포함',completed:'조회 완료',awaiting_confirmation:'확인 대기 · 기록 미변경',committed:'반영 완료',cancelled:'취소 완료',needs_input:'사용자 구분 필요',failed:'단계 실패',skipped:'문맥 검토 · 준비하지 않음'};
  const tool={search:'기록 조회',create:'새 기록 초안',save_transcript:'대화 원문 보관 초안',update:'기록 수정 초안',delete:'기록 삭제 초안',restore:'기록 복원 초안',cancel:'확인 대기 초안 취소'};
  const goal=section('이번 요청에서 이해한 사용자 목표');goal.append(node('p',plan?.goal||(message.status==='pending'?'문맥에서 목표와 필요한 행동을 준비하고 있어요.':'아직 확인된 목표 계획이 없습니다.')));
  goal.append(node('p','입력을 하나의 의도 종류로 먼저 분류하지 않습니다. 목표에 필요한 여러 행동을 함께 계획합니다.','ai-inspection-note'));raw(goal,'제출한 입력 원문',message.submission?.text||'');
  if(plan){const context=section('이해에 사용한 대화 맥락');context.append(node('p',plan.context_summary||'별도 맥락 요약 없음'));const dl=node('dl');row(dl,'미완료 목표 연결',plan.task_id?'기존 대기 목표를 이어받음':'이번 요청의 목표');row(dl,'연결한 발언',String(plan.related_turn_ids?.length||0)+'개');row(dl,'답변 방향',plan.reply_guidance||'현재 목표에 맞춰 답변');context.append(dl);if(result.dialogue_trace?.references?.length)raw(context,'연결한 사용자·AI 발언 원문',result.dialogue_trace.references);}
  const work=section('모델이 계획한 행동과 실제 결과');
  if(plan?.steps?.length){const list=node('ol');for(const [index,step]of plan.steps.entries()){const observed=trace.steps?.find(s=>s.index===index),receipt=result.executions?.find(r=>r.proposal_id===observed?.proposal_id),state=receipt?(receipt.status==='succeeded'?'committed':'cancelled'):observed?.status||'planned';const item=node('li');item.append(node('strong',tool[step.tool]||step.tool),node('p',step.purpose),node('small',status[state]||state));if(observed?.accessible_count!=null)item.append(node('p',observed.accessible_count+'개 원문에서 '+observed.result_count+'개 구간 조회'));if(observed?.question)item.append(node('p',observed.question));if(observed?.error)item.append(node('p',observed.error,'ai-error-message'));list.append(item);}work.append(list);}
  else work.append(node('p',plan?'모델이 추가 도구 실행을 요청하지 않았습니다.':'아직 확정된 행동이 없습니다.'));
  const reads=trace?.observations?.filter(o=>o.origin?.startsWith('app_'))||[];if(reads.length){const prefetch=section('앱이 먼저 읽은 자료');for(const read of reads)prefetch.append(node('p',(read.scope==='personal'?'개인 자료함':'현재 가상 자료함')+' · 전체 '+read.accessible_count+'개 중 '+read.results.length+'개 구간을 제공했습니다.'));prefetch.append(node('p','이 읽기 전용 조회는 입력을 특정 의도로 분류했다는 뜻이 아닙니다.','ai-inspection-note'));}
  const actual=section('응답 결과와 기록 반영');const dl=node('dl');row(dl,'응답 상태',({answered:'답변',partial:'일부 처리',not_found:'필요한 정보 미확인',conflict:'원문 간 차이 확인',needs_input:'구분 질문'})[trace?.response?.status]||({pending:'준비 중',error:'처리 실패',cancelled:'수신 중단'}[message.status]||'과정 기록 없음'));
  row(dl,'확인할 초안',String(result?.proposals?.filter(p=>p.status==='pending').length||0)+'개');row(dl,'실제 반영',String(result?.executions?.filter(r=>r.status==='succeeded').length||0)+'건');row(dl,'실제 취소',String(result?.executions?.filter(r=>r.status==='cancelled').length||0)+'건');row(dl,'연결한 인용',String(result?.citations?.length||0)+'개 구간');actual.append(dl);actual.append(node('p','계획, 초안 준비, 실제 반영을 구분합니다. 기록 반영 완료는 서버의 실행 영수증으로 확인합니다.','ai-inspection-note'));
  if(trace?.reply_error)raw(actual,'답변 생성 단계 오류',trace.reply_error);if(message.error)raw(actual,'요청 처리 오류',message.error);if(result?.executions?.length)raw(actual,'서버의 실제 실행 결과',result.executions);if(result)raw(actual,'표시한 답변 원문',result.answer);
  if(plan?.recording_review){const review=section('기록 준비 전 문맥 검토');for(const item of plan.recording_review.reviews||[])review.append(node('p',(tool[plan.steps[item.index]?.tool]||'기록 작업')+' · '+(item.decision==='prepare'?'초안 준비':'준비하지 않음')+' — '+item.reason));if(plan.recording_review.error)review.append(node('p','검토 실패 · '+plan.recording_review.error.message));}
  if(trace?.model_calls?.length){const calls=section('이번 제출에서 실제 호출한 모델');const phase={goal_plan:'목표·행동 계획',recording_review:'문맥에서 기록 필요성과 동의 범위 확인',goal_response:'목표에 맞는 답변 작성',tool_arguments:'기록 대상 확인',record_arguments:'기록 내용 준비',transcript_arguments:'대화 보관 범위 준비',record_patch:'수정할 구간 준비'};for(const [i,call]of trace.model_calls.entries())raw(calls,(i+1)+'. '+(phase[call.phase]||call.phase)+' · 실제 입력·출력',call);}
  else if(trace)content.append(node('p','이번 응답에는 모델 호출 원문이 첨부되지 않았습니다. 실행한 계획과 실제 결과만 표시합니다.','ai-inspection-note'));
  if(trace)raw(content,'앱이 보관한 목표·행동 전체 기록',trace);
  return panel;
 }

 const intents={mixed:'복합 요청',memory_query:'개인 기억 조회',emotion:'감정 공유',advice:'조언 요청',experience:'새 경험 기록 요청',edit:'기록 수정 요청',delete:'기록 삭제 요청',general:'일반 대화·질문'};
 const actions={committed:'확인한 기록 변경 반영 완료',cancelled:'확인 대기 작업 취소',multi_result:'작업별 처리 결과',answer:'근거를 바탕으로 답변',partial_answer:'확인된 부분만 답변',abstain:'근거 부족으로 확인 불가',clarify:'추가 확인 질문',report_conflict:'기록 간 충돌 알림',deny:'기록에 근거해 질문의 전제 확인',draft:'기록 변경 초안 제시',empathy:'감정에 공감',advice:'조언 제시'};
 const intentGuides={
  memory_query:{when:'사용자가 저장된 자신의 과거 경험·선호·약속 등 개인 사실을 확인하려는 경우입니다.',user:'지난주에 내가 산 책 제목이 뭐였지?'},
  emotion:{when:'해결 방법이나 기록 변경을 요청하기보다 현재의 감정을 나누고 공감을 원하는 경우입니다.',user:'오늘은 좀 지치고 속상해.'},
  advice:{when:'현재 고민이나 목표에 대해 방법·선택지·다음 행동을 제안해 달라고 요청하는 경우입니다.',user:'퇴근 후 독서 습관을 만들려면 어떻게 시작하면 좋을까?'},
  experience:{when:'새로운 경험이나 사실을 기록으로 남겨 달라고 요청하는 경우입니다. 초안을 확인한 뒤 기록하기를 누르면 개인 자료함에 저장합니다.',user:'오늘 처음 도예 수업을 들었어. 이 경험을 기록해 줘.'},
  edit:{when:'이미 있는 기록의 내용이나 날짜 등 특정 정보를 고쳐 달라고 요청하는 경우입니다.',user:'어제 기록의 약속 시간을 오후 2시에서 3시로 고쳐 줘.'},
  delete:{when:'기존에 보관된 기록을 지워 달라고 요청하는 경우입니다.',user:'지난주 영화 감상 기록을 지워 줘.'},
  general:{when:'개인 기록 조회에 해당하지 않는 인사·일반 지식 질문·순수 계산 등의 경우입니다.',user:'광합성이 무엇인지 간단히 설명해 줘.'}
 };
 const actionGuides={
  answer:{when:'질문에 답할 정보가 충분한 경우입니다. 개인 기억 조회라면 사실을 직접 뒷받침하는 원문 근거가 필요합니다.',context:'저장된 기록에 화요일 도예 수업에 참석했다고 적혀 있습니다.',user:'내 도예 수업은 무슨 요일이었지?',response:'기록에 따르면 화요일이었어요.'},
  partial_answer:{when:'질문에 필요한 사실 중 일부만 근거로 확인할 수 있는 경우입니다. 확인된 내용과 모르는 내용을 나눠 답합니다.',context:'민수와 카페에서 만난 사실은 있지만 카페 이름은 기록에 없습니다.',user:'누구와 어느 카페에서 만났지?',response:'민수와 만난 것은 확인되지만, 카페 이름은 기록에 없어요.'},
  abstain:{when:'기록 조회가 정상적으로 끝났지만 필요한 사실을 확인할 근거가 없는 경우입니다. 연결이나 모델 실행 오류와 구분합니다.',context:'조회한 기록에 사물함 번호가 없습니다.',user:'내 사물함 번호가 뭐였지?',response:'현재 기록에서는 사물함 번호를 확인할 수 없어요.'},
  clarify:{when:'대상이나 조건이 실제로 모호해서 답변 또는 기록 변경 초안을 만들기 전에 구분 질문이 필요한 경우입니다.',context:'삭제할 수 있는 기록이 여러 개이고, 어느 기록인지 지정되지 않았습니다.',user:'그 기록 지워 줘.',response:'어느 기록을 삭제할까요? 제목이나 날짜를 알려주세요.'},
  report_conflict:{when:'같은 사실에 대해 서로 다른 기록이 있고, 시간·정정 관계 등으로 차이를 해소하지 못한 경우입니다.',context:'같은 독서 모임 장소가 한 기록에는 북카페, 다른 기록에는 도서관으로 적혀 있고 변경 여부가 불분명합니다.',user:'독서 모임 장소가 어디야?',response:'북카페와 도서관으로 적힌 기록이 함께 있어 장소를 확정할 수 없어요.'},
  deny:{when:'사용자의 질문에 담긴 전제와 명시적으로 반대되는 원문 근거가 있는 경우입니다.',context:'기록에는 도예 수업에 예정대로 참석했다고 적혀 있습니다.',user:'어제 도예 수업은 취소됐지?',response:'기록에는 취소가 아니라 예정대로 참석했다고 되어 있어요.'},
  draft:{when:'기록 추가·수정·삭제 요청에 대해 실제 변경을 실행하지 않고 검토할 초안을 제시하는 경우입니다.',context:'초안 확인 버튼으로 보관소 기록 변경을 실행할 수 있습니다.',user:'오늘 처음 도예 수업을 들은 걸 기록해 줘.',response:'기록 초안: 오늘 처음 도예 수업을 들었다. 아직 저장하지 않았어요.'},
  empathy:{when:'표현된 감정에 공감하며 응답하는 경우입니다. 기록에 없는 사건이나 개인 성격을 확정하지 않습니다.',context:'사용자가 지치고 속상한 마음을 나눴습니다.',user:'오늘은 좀 지치고 속상해.',response:'지친 하루였겠어요. 지금 느끼는 마음을 편하게 이야기해도 괜찮아요.'},
  advice:{when:'사용자가 요청한 고민이나 목표에 대해 실천할 수 있는 작은 방법을 제안하는 경우입니다.',context:'사용자가 독서를 시작할 방법을 물었습니다.',user:'독서 습관을 어떻게 시작할까?',response:'하루 10분처럼 작은 목표로 시작하고, 읽을 책을 미리 가까이 두는 방법을 시도해 보세요.'}
 };
 const stages={context:'대화 맥락 확인',scope:'기록 범위 확인',retrieval:'원문 검색',connection:'AI 연결',model:'모델 호출',validation:'답변 검증',complete:'처리 완료'};
 const checks={conversation_context:'대화 대상과 현재 원문 연결',schema:'응답 JSON 형식',write_policy:'기록 변경 응답 규칙',intent_action:'의도와 후속 행동의 일치',request_intent:'명시적 입력 요청과 응답 분류의 일치',latest_grounding:'최신 요청·정정·사용자 원문과 답변의 일치',citation_references:'인용 문장과 원문 연결',required_citations:'기억 답변의 필수 인용'};
 const checkStates={not_run:'확인 단계에 도달하지 않음',passed:'통과',failed:'실패',not_required:'이 응답에는 해당 없음'};
 const features=[['h1,h2,h3,h4,h5,h6','제목'],['p','문단'],['ul','글머리 목록'],['ol','번호 목록'],['table','표'],['pre','코드 블록'],['blockquote','인용문'],['strong,em','강조'],['a','링크']];
 function label(map,value){return value?(map[value]||'알 수 없는 분류')+' ('+value+')':'분류 결과 없음';}
 function classificationOptions(message){
  const snapshot=message.result?.inspection||message.inspection;
  const properties=snapshot?.version==='chat-inspection-v1'?snapshot.request_body?.response_format?.json_schema?.schema?.properties:null;
  const output=message.result||snapshot?.output;
  return Object.fromEntries([['intent',intents,intentGuides],['action',actions,actionGuides]].map(([key,map,guides])=>{const recorded=Array.isArray(properties?.[key]?.enum);const values=recorded?properties[key].enum:[];return [key,{recorded,items:values.map(code=>({code,description:map[code]||'현재 화면에 설명이 등록되지 않은 분류',selected:output?.[key]===code,guide:guides[code]?{...guides[code]}:null}))}];}));
 }
 function describe(message){
  if(goalMode(message))return {snapshot:null,input:null,intent:"단일 의도 분류 사용 안 함",action:message.result?.action||"",stage:message.status==='success'&&(message.result?.action_trace?.reply_error||message.result?.action_trace?.steps?.some(s=>s.status==='failed'))?"일부 단계 실패 · 준비된 작업 보존":({pending:"목표·행동 준비 중",success:"목표와 실행 결과 준비 완료",error:"처리 실패",cancelled:"수신 중단"})[message.status]||"확인 전",status:message.status,original:message.submission?.text||"",history:[]};
  const snapshot=message.result?.inspection||message.inspection;
  const valid=snapshot?.version==='chat-inspection-v1';
  const output=message.result||snapshot?.output;
  let input=null;try{const user=snapshot?.request_body?.messages.find(m=>m.role==='user');if(user)input=JSON.parse(user.content);}catch{}
  return {snapshot:valid?snapshot:null,input,intent:label(intents,output?.intent),action:label(actions,output?.action),stage:stages[snapshot?.stage||message.stage]||({pending:'응답 대기',success:'응답 완료',error:'처리 실패',cancelled:'수신 중단'}[message.status]||'확인할 수 없음'),status:message.status,original:message.submission?.text||'',history:input?.previous_user_questions||message.submission?.history||[]};
 }
 function render(doc,message,answerElement,enabled){
  if(enabled!==true)return null;if(goalMode(message))return renderGoal(doc,message,answerElement);
  const info=describe(message),s=info.snapshot;
  const node=(tag,text,cls)=>{const e=doc.createElement(tag);if(text!=null)e.textContent=text;if(cls)e.className=cls;return e;};
  const panel=node('details',null,'ai-response-inspection');panel.open=message.inspectionExpanded===true;
  const summary=node('summary','요청·응답 정보 · 테스트 전용');panel.append(summary);
  const content=node('div',null,'ai-inspection-content');panel.append(content);
  function section(title){const e=node('section');e.append(node('h4',title));content.append(e);return e;}
  function row(list,key,value){const wrap=node('div',null,'ai-inspection-row');wrap.append(node('dt',key),node('dd',String(value)));list.append(wrap);}
  function raw(parent,title,value){const detail=node('details',null,'ai-inspection-raw');detail.append(node('summary',title));const pre=node('pre'),code=node('code',typeof value==='string'?value:JSON.stringify(value,null,2));pre.tabIndex=0;pre.append(code);detail.append(pre);parent.append(detail);}
  const overview=section('이전 방식으로 남은 응답 기록'),overviewList=node('dl');overview.append(overviewList);
  row(overviewList,'기록에 남은 의도 값',info.intent);row(overviewList,'기록에 남은 처리 값',info.action);row(overviewList,'처리 상태',info.stage+(message.status==='error'?' · 실패':'')+(message.archived?' · 가져온 실행 기록':''));
  row(overviewList,'보관소 변경',message.result?.execution?message.result.execution.message:message.result?.proposal?'초안 준비 · 확인 전 변경 없음':'기록 변경 실행 없음');if(message.result?.action_trace){const tools=section('문맥에 따른 행동과 실제 실행');raw(tools,'행동 선택 · 도구 관찰',message.result.action_trace);if(message.result.proposal)raw(tools,'확인할 작업',message.result.proposal);if(message.result.execution)raw(tools,'실제 실행 결과',message.result.execution);}
  overview.append(node('p','이전 방식에서 저장된 값입니다. 현재의 목표·행동 계획을 소급해 추정하지 않습니다.','ai-inspection-note'));
  const options=classificationOptions(message);
  for(const [key,title]of [['intent','이전 실행의 의도'],['action','이전 실행의 응답 형식']]){
   const group=options[key];if(!group.recorded)continue;const details=node('details',null,'ai-classification-list');details.append(node('summary',title+' 전체 목록 · '+group.items.length+'개'));
   details.append(node('p',group.recorded?'이 요청에 지정한 전체 선택지입니다.':'현재 앱의 분류 목록입니다. 이 응답의 당시 선택지 기록은 없습니다.','ai-inspection-note'));
   details.append(node('p','선택 기준과 예시는 현재 앱 기준의 가상 안내입니다. 이번 응답의 실제 분류 이유를 설명하는 내용은 아닙니다.','ai-inspection-note'));
   const table=node('table'),head=node('thead'),header=node('tr');header.append(node('th','분류값'),node('th','의미'));head.append(header);const rows=node('tbody');
   for(const item of group.items){
    const row=node('tr',null,item.selected?'is-current':'');const code=node('td');code.append(node('code',item.code));const description=node('td',item.description);
    if(item.selected)description.append(node('span','이번 응답에서 선택','ai-classification-selected'));
    if(item.guide){
     const condition=node('p',null,'ai-classification-condition');condition.append(node('strong','선택되는 경우'),node('span',item.guide.when));description.append(condition);
     const example=node('details',null,'ai-classification-example');example.append(node('summary','예시 보기'));const items=node('dl');
     for(const [field,title]of [['context','상황'],['user','사용자 발화 예시'],['response','응답 예시']])if(item.guide[field])items.append(node('dt',title),node('dd',item.guide[field]));
     example.append(items);description.append(example);
    }
    row.append(code,description);rows.append(row);
   }
   table.append(head,rows);details.append(table);overview.append(details);
  }
  if(!s)content.append(node('p',message.status==='pending'?'요청 처리 중입니다. 응답을 받으면 실행 정보를 표시합니다.':'이 답변에는 당시 지침·입력·검증 결과의 실행 기록이 없습니다. 저장된 분류와 답변만 확인할 수 있습니다.','ai-inspection-note'));
  const request=section('받은 요청과 검색 범위');raw(request,'제출한 질문 원문',info.original);
  if(info.history.length)raw(request,'함께 전달한 이전 사용자 질문 '+info.history.length+'개',info.history);
  const requestList=node('dl');request.append(requestList);
  if(info.input){const evidence=info.input.evidence||[];row(requestList,'사용한 자료함',info.input.scope?.context_id==='personal'?'개인 자료함':'가상 예시 자료함');row(requestList,'검색 대상 원문',String(info.input.scope?.accessible_count??'확인 불가')+'개');row(requestList,'입력에 포함한 근거',evidence.length+'개 구간 · '+new Set(evidence.map(e=>e.source_id)).size+'개 원문');row(requestList,'검색 방식',info.input.scope?.retrieval||'확인 불가');}
  else row(requestList,'검색 범위','실행 정보 없음');
  if(info.input?.conversation_context){const c=info.input.conversation_context;row(requestList,'대화 연결',c.relation);row(requestList,'이야기 중인 주제',c.topic||'새 주제');row(requestList,'선택한 대상',c.selected_target||'확정된 대상 없음');row(requestList,'날짜 기준',c.reference_time);}
  if(info.input?.request_contract){const c=info.input.request_contract;row(requestList,'서버가 확인한 요청',c.kind);row(requestList,'허용 의도',c.expected_intents.map(v=>intents[v]||v).join(' / '));row(requestList,'허용 후속 행동',c.allowed_actions.map(v=>actions[v]||v).join(' / '));}
  else if(info.input)row(requestList,'명시적 요청 대조','서버 규칙에 해당하지 않는 표현 · 모델 분류 사용');
  if(s){
   const expected=section('우리가 지정한 답변 형식'),dl=node('dl');expected.append(dl);
   row(dl,'모델 응답 형식','JSON Schema · 필수 항목 '+(s.request_body.response_format.json_schema.schema.required||[]).join(' / '));row(dl,'답변 본문 형식','answer 문자열 안의 Markdown · 내용에 맞는 문단·강조·목록·표·코드 블록');row(dl,'문맥 / 출력 상한',s.context_tokens+' / '+s.request_body.max_tokens+' 토큰');
   row(dl,'생성 설정','temperature '+s.request_body.temperature+' · seed '+s.request_body.seed+' · 비스트리밍');
   raw(expected,'당시 지정한 전체 응답 지침',s.request_body.messages.find(m=>m.role==='system')?.content||'없음');raw(expected,'당시 지정한 JSON Schema',s.request_body.response_format.json_schema);
   raw(request,s.model_response_received?'모델 호출에 사용한 입력 JSON':'모델 호출을 위해 준비한 입력 JSON',info.input||'입력 준비 단계에 도달하지 못했습니다.');
  }
  const actual=section('실제 답변과 형식'),actualList=node('dl');actual.append(actualList);
  const formats=answerElement?features.filter(([selector])=>answerElement.querySelector(selector)).map(([,name])=>name):[];
  row(actualList,'현재 화면에 렌더링한 형식',answerElement?(formats.join(' · ')||'일반 텍스트'):'표시할 완료 답변 없음');
  const result=message.result;
  row(actualList,'검증 후 연결한 인용',result?result.citations.length+'개 문장 · '+new Set(result.citations.map(c=>c.source_id+'@'+c.revision)).size+'개 원문':'확인된 인용 없음');
  if(result)raw(actual,'실제 답변 Markdown 원문',result.answer);
  if(s?.output)raw(actual,'모델이 반환한 구조화 응답 JSON',s.output);
  if(s){const validation=section('확인된 검증 결과'),dl=node('dl');validation.append(dl);for(const [key,title]of Object.entries(checks))row(dl,title,checkStates[s.checks[key]]||'확인 불가');validation.append(node('p','명시적 요청은 서버 규칙과 대조하고, 의도별 허용 행동·응답 형식·인용 연결을 확인합니다. 모든 표현의 의도나 답변의 의미가 정확하다는 판정은 아닙니다.','ai-inspection-note'));}
  if(message.error)raw(actual,'처리 오류',message.error);
  return panel;
 }
 return {describe,render,classificationOptions};
});
