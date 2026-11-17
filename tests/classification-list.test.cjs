const test=require('node:test'),assert=require('node:assert/strict'),path=require('node:path');
const root=process.env.PMA_APP_ROOT||path.resolve(__dirname,'..');
const {classificationOptions}=require(path.join(root,'ui/plant-thought/response-inspector.js'));
const {schema}=require(path.join(root,'ui/chat-api.cjs'));
test('full intent and action catalogs match the assigned schema and mark the chosen output',()=>{
 const message={result:{intent:'memory_query',action:'partial_answer',inspection:{version:'chat-inspection-v1',request_body:{response_format:{json_schema:{schema}}}}}};
 const groups=classificationOptions(message);assert.equal(groups.intent.recorded,true);assert.deepEqual(groups.intent.items.map(i=>i.code),schema.properties.intent.enum);assert.deepEqual(groups.action.items.map(i=>i.code),schema.properties.action.enum);assert.deepEqual(groups.intent.items.filter(i=>i.selected).map(i=>i.code),['memory_query']);assert.deepEqual(groups.action.items.filter(i=>i.selected).map(i=>i.code),['partial_answer']);
});
test('historic schemas retain their own choices; missing snapshots explicitly use the current catalog',()=>{
 const recorded={inspection:{version:'chat-inspection-v1',request_body:{response_format:{json_schema:{schema:{properties:{intent:{enum:['legacy_intent']},action:{enum:['legacy_action']}}}}}},output:{intent:'legacy_intent',action:'legacy_action'}}};
 const groups=classificationOptions(recorded);assert.equal(groups.intent.items.length,1);assert.equal(groups.intent.items[0].selected,true);assert.equal(groups.intent.items[0].code,'legacy_intent');const legacy=classificationOptions({result:{intent:'emotion',action:'empathy'}});assert.equal(legacy.intent.recorded,false);assert.equal(legacy.intent.items.length,7);assert.equal(legacy.action.items.length,9);
});
test('every supported classification explains when it applies and has an illustrative user example',()=>{
 const groups=classificationOptions({});
 for(const key of ['intent','action'])for(const item of groups[key].items){assert.ok(item.guide?.when,item.code+' selection criteria');assert.ok(item.guide?.user,item.code+' user example');if(key==='action'){assert.ok(item.guide.context,item.code+' evidence or situation');assert.ok(item.guide.response,item.code+' response example');}}
 const unknown=classificationOptions({inspection:{version:'chat-inspection-v1',request_body:{response_format:{json_schema:{schema:{properties:{intent:{enum:['unknown_intent']},action:{enum:['unknown_action']}}}}}}}});assert.equal(unknown.intent.items[0].guide,null);assert.equal(unknown.action.items[0].guide,null);
});
