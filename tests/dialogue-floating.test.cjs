'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const {layout,bounds,fit,resize}=require('../ui/plant-thought/floating-workspace.js'),{selectMap}=require('../ui/plant-thought/dialogue-floating.js');
test('three desktop floatings fit side by side below the header without overlapping',()=>{
 for(const width of [900,1024,1280,1864]){
  const panes=layout(width,883,148,[420,520,460]);assert.equal(panes.length,3);
  for(let i=0;i<panes.length;i++){const p=panes[i];assert(p.width>=240);assert(width-p.right-p.width>=23);assert(883-p.bottom-p.height>=148);if(i)assert(p.right>=panes[i-1].right+panes[i-1].width+11);}
 }
});
test('a single map keeps the requested right edge and its readable preferred width',()=>{
 assert.deepEqual(layout(1280,883,148,[420]),[{right:24,bottom:98,width:420,height:623}]);assert.deepEqual(layout(1280,883,148,[]),[]);
});
test('mobile panels remain open with in-viewport cascading positions and a separate switching area',()=>{
 const panes=layout(390,844,180,[420,520,460]);assert.equal(panes.length,3);assert.equal(new Set(panes.map(p=>p.bottom)).size,3);
 for(const p of panes){assert(p.right>=12);assert(p.width<=366);assert(844-p.bottom-p.height>=180);assert(p.bottom>=134);}
});
const message=(id,trace=true)=>({kind:'assistant',status:'success',submission:{request_id:id,text:id},result:trace?{dialogue_trace:{parts:[{id:'P1'}]}}:{answer:'V1'}});
test('map follows the latest existing V2 trace while a new response is pending',()=>{
 const a=message('a'),b=message('b'),thread={messages:[a,message('v1',false),b,{kind:'assistant',status:'pending',submission:{request_id:'c'}}]};assert.equal(selectMap(thread).message,b);assert.equal(selectMap(thread).messages.length,2);
});
test('pinned maps remain pinned and changing conversations cannot show a different thread map',()=>{
 const a=message('a'),thread={messages:[a,message('b')]};const selected=selectMap(thread,'a');thread.messages.push(message('c'));assert.equal(selectMap(thread,selected.selection).message,a);assert.equal(selectMap({messages:[message('other')]},selected.selection).selection,'latest');assert.equal(selectMap({...thread,deletedAt:1}).message,null);assert.equal(selectMap(null).message,null);
});
test('viewing a map never changes the existing response or triggers a new analysis',()=>{
 const row=Object.freeze(message('a')),thread=Object.freeze({messages:Object.freeze([row])});assert.equal(selectMap(thread,'a').message,row);assert.equal(selectMap(thread,'missing').selection,'latest');
});
test('drag bounds keep the whole panel and title reachable while reserving the launcher row',()=>{
 const area=bounds(1280,900),rect={x:300,y:200,width:400,height:300};
 assert.deepEqual(fit({...rect,x:-900,y:-900},area),{x:8,y:8,width:400,height:300});
 assert.deepEqual(fit({...rect,x:9000,y:9000},area),{x:872,y:514,width:400,height:300});
});
test('resizing the left and top edges preserves the opposite anchor',()=>{
 const area=bounds(1280,900),rect={x:300,y:200,width:400,height:300};
 assert.deepEqual(resize(rect,'w',50,0,area),{x:350,y:200,width:350,height:300});
 assert.deepEqual(resize(rect,'n',0,40,area),{x:300,y:240,width:400,height:260});
 assert.deepEqual(resize(rect,'nw',50,40,area),{x:350,y:240,width:350,height:260});
});
test('all corner and edge resize operations remain within limits for extreme pointer motion',()=>{
 const area=bounds(1280,900),rect={x:300,y:200,width:400,height:300};
 for(const edge of ['n','s','e','w','nw','ne','sw','se'])for(const dx of [-10000,10000])for(const dy of [-10000,10000]){
  const r=resize(rect,edge,dx,dy,area);assert(r.x>=area.left);assert(r.y>=area.top);assert(r.width>=area.minWidth);assert(r.height>=area.minHeight);assert(r.x+r.width<=area.right);assert(r.y+r.height<=area.bottom);
 }
});
test('shrinking from left or top cannot flip a panel or move its fixed opposite edge',()=>{
 const area=bounds(1280,900),rect={x:300,y:200,width:400,height:300};
 const r=resize(rect,'nw',10000,10000,area);assert.equal(r.width,240);assert.equal(r.height,220);assert.equal(r.x+r.width,700);assert.equal(r.y+r.height,500);
});
test('adapting to a narrow viewport never overwrites the saved desktop geometry',()=>{
 const saved=Object.freeze({x:800,y:350,width:420,height:400}),narrow=fit(saved,bounds(390,844,134));assert.equal(narrow.width,374);assert.equal(narrow.x,8);assert(narrow.y+narrow.height<=710);
 assert.deepEqual(fit(saved,bounds(1280,900)),saved);
});
test('very small viewports remain mathematically valid instead of producing negative sizes',()=>{
 const area=bounds(180,240,134),r=fit({x:800,y:900,width:500,height:800},area);assert(r.width>0);assert(r.height>0);assert(r.x+r.width<=172);assert(r.y+r.height<=106);
});
