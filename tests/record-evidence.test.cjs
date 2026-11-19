'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),path=require('node:path');
const {ranges,segments}=require(path.join(process.env.PMA_APP_ROOT||path.resolve(__dirname,'..'),'ui/plant-thought/record-evidence.js'));
const body='민수는 🌿 문서를 전달했다.\n지연은 내일 검토한다.\n<img src=x onerror=alert(1)>',record={id:'record-a',revision:2,body};
const cite=(quote,extra={})=>({source_id:record.id,revision:record.revision,start:body.indexOf(quote),end:body.indexOf(quote)+quote.length,quote,...extra});
test('multiple Korean and emoji reference spans preserve the complete original and exact offsets',()=>{
 const citations=[cite('🌿 문서'),cite('지연은 내일')],parts=segments(record,citations);
 assert.equal(parts.map(p=>p.text).join(''),body);assert.deepEqual(parts.filter(p=>p.highlighted).map(p=>p.text),['🌿 문서','지연은 내일']);assert.deepEqual(ranges(record,citations),citations.map(({start,end})=>({start,end})));
});
test('duplicate, overlapping and touching citations merge without duplicating original text',()=>{
 const citations=[cite('민수는 🌿'),cite('🌿 문서를'),cite('민수는 🌿'),cite(' 전달했다.')];
 const result=ranges(record,citations);assert.equal(result.length,1);assert.equal(result[0].start,0);assert.equal(body.slice(result[0].start,result[0].end),'민수는 🌿 문서를 전달했다.');assert.equal(segments(record,citations).map(p=>p.text).join(''),body);
});
test('wrong records, stale versions, fabricated quotes and invalid boundaries never highlight',()=>{
 const bad=[cite('민수',{source_id:'another'}),cite('민수',{revision:1}),cite('민수',{quote:'위조'}),cite('민수',{start:-1}),cite('민수',{end:9999}),cite('민수',{start:.5}),cite('민수',{end:0}),null];
 assert.deepEqual(ranges(record,bad),[]);assert.deepEqual(segments(record,bad),[{text:body,highlighted:false}]);
});
test('repeated text highlights only the cited occurrence and markup remains literal text',()=>{
 const r={id:'repeat',revision:1,body:'같은 말\n같은 말\n<script>alert(1)</script>'},quote='같은 말',start=r.body.indexOf(quote,1);
 const parts=segments(r,[{source_id:r.id,revision:1,start,end:start+quote.length,quote}]);assert.equal(parts[0].text,'같은 말\n');assert.deepEqual(parts[1],{text:quote,highlighted:true});assert.equal(parts.map(p=>p.text).join(''),r.body);assert.ok(parts.at(-1).text.includes('<script>'));
});
