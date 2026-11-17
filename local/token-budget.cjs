const BUDGET_VERSION='chat-request-budget-v2',FULL_POLICY='full-request-only-v2';
function chatRequest(messages,schema,config){
 const output=config.output_tokens??config.answer_output_tokens??2048;
 if(!Number.isInteger(output)||output<=0)throw Error('출력 토큰 한도 오류');
 return {messages,temperature:0,seed:config.seed,max_tokens:output,stream:false,chat_template_kwargs:{enable_thinking:false},response_format:{type:'json_schema',json_schema:{name:'baseline_output',strict:true,schema}}};
}
function budgetLimits(config,serverContext=8192){
 const context=config.context_tokens??8192,output=config.output_tokens??config.answer_output_tokens??2048,margin=512;
 if(!Number.isInteger(context)||context<=0||!Number.isInteger(output)||output<=0||context>serverContext||context<=output+margin)throw Error('실제 서버 문맥과 입력·출력 예산 설정이 맞지 않습니다.');
 return {context_limit:context,output_limit:output,template_margin:margin,input_limit:context-output-margin};
}
async function requestBudget(runtime,messages,schema,config,signal){
 const input=await runtime.countChatTokens(messages,schema,config,signal);
 if(!Number.isInteger(input)||input<0)throw Error('실제 요청 토큰 수를 확인할 수 없습니다.');
 const limits=budgetLimits(config,runtime.contextLimit?.()??8192);
 return {...limits,input_tokens:input,input_tokens_estimate:input,remaining_input_tokens:limits.input_limit-input,eligible:input<=limits.input_limit,measurement:'llama.cpp-chat-request-input-tokens-v1',budget_version:BUDGET_VERSION};
}
module.exports={BUDGET_VERSION,FULL_POLICY,chatRequest,budgetLimits,requestBudget};
