'use strict';
// An execution receipt: explicit inputs, declared output fields, and checks. No hidden reasoning.
const VERSION='chat-inspection-v1';
const CHECKS=['conversation_context','schema','write_policy','intent_action','request_intent','conversation_context','citation_references','required_citations'];
const STAGES=['context','scope','context','retrieval','connection','model','validation','complete'];
function invalid(){throw Object.assign(Error('요청·응답 정보의 형식이 올바르지 않습니다.'),{status:400});}
function string(v,max=40000){if(typeof v!=='string'||v.length>max)invalid();return v;}
function number(v,min=0){if(!Number.isSafeInteger(v)||v<min)invalid();return v;}
function schemaCopy(value,depth=0){
 if(depth>12||!value||typeof value!=='object'||Array.isArray(value))invalid();const out={};
 if(value.type!=null)out.type=string(value.type,32);
 if(value.additionalProperties!=null){if(typeof value.additionalProperties!=='boolean')invalid();out.additionalProperties=value.additionalProperties;}
 if(value.required!=null){if(!Array.isArray(value.required)||value.required.length>64)invalid();out.required=value.required.map(v=>string(v,100));}
 if(value.enum!=null){if(!Array.isArray(value.enum)||value.enum.length>100)invalid();out.enum=value.enum.map(v=>string(v,200));}
 if(value.properties!=null){if(!value.properties||typeof value.properties!=='object'||Array.isArray(value.properties)||Object.keys(value.properties).length>64)invalid();out.properties=Object.fromEntries(Object.entries(value.properties).map(([k,v])=>[string(k,100),schemaCopy(v,depth+1)]));}
 for(const k of ['minItems','maxItems','minimum'])if(value[k]!=null)out[k]=number(value[k]);
 if(value.items!=null)out.items=schemaCopy(value.items,depth+1);return out;
}
function normalizeInspection(value){
 if(!value||value.version!==VERSION||!STAGES.includes(value.stage)||!Number.isFinite(Date.parse(value.captured_at)))invalid();
 const body=value.request_body;if(!body||!Array.isArray(body.messages)||body.messages.length<1||body.messages.length>2)invalid();
 const messages=body.messages.map((m,index)=>{if(!m||m.role!==(index===0?'system':'user'))invalid();return {role:m.role,content:string(m.content,200000)};});
 const format=body.response_format;if(format?.type!=='json_schema'||format.json_schema?.strict!==true)invalid();
 if(body.temperature!==0||body.stream!==false||body.chat_template_kwargs?.enable_thinking!==false)invalid();
 const out={version:VERSION,captured_at:string(value.captured_at,64),stage:value.stage,context_tokens:number(value.context_tokens,1),input_prepared:value.input_prepared===true,model_response_received:value.model_response_received===true,
 request_body:{messages,temperature:0,seed:number(body.seed),max_tokens:number(body.max_tokens,1),stream:false,chat_template_kwargs:{enable_thinking:false},response_format:{type:'json_schema',json_schema:{name:string(format.json_schema.name,100),strict:true,schema:schemaCopy(format.json_schema.schema)}}},checks:{}};
 for(const key of CHECKS){const state=value.checks?.[key]??(['intent_action','request_intent','conversation_context'].includes(key)?'not_run':undefined);if(!['not_run','passed','failed','not_required'].includes(state))invalid();out.checks[key]=state;}
 if(value.output!=null){const p=value.output;if(!p||!Array.isArray(p.citations)||p.citations.length>100)invalid();out.output={intent:string(p.intent,80),action:string(p.action,80),answer:string(p.answer,200000),citations:p.citations.map(c=>({evidence_id:string(c.evidence_id,160),sentence_id:string(c.sentence_id,160)}))};}
 if(Buffer.byteLength(JSON.stringify(out))>1000000)invalid();return out;
}
function createInspection(requestBody,contextTokens){return {version:VERSION,captured_at:new Date().toISOString(),stage:'scope',context_tokens:contextTokens,input_prepared:false,model_response_received:false,request_body:structuredClone(requestBody),checks:Object.fromEntries(CHECKS.map(k=>[k,'not_run']))};}
module.exports={VERSION,CHECKS,createInspection,normalizeInspection};
