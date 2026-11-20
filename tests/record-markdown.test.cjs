'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),md=require('../ui/plant-thought/chat-markdown.js'),{locate,normalized}=require('../ui/plant-thought/record-markdown.js');
test('record source maps preserve original CRLF offsets without changing ordinary Markdown output',()=>{
 const text='# 제목\r\n\r\n**현재 번호**: 207\r\n\r\n```text\r\n206 -> 207\r\n```';
 const html=md.render(text,{sourceMap:true}),start=text.indexOf('**'),end=text.indexOf('\r\n\r\n```')+2;
 assert.ok(html.includes('data-record-from="'+start+'"'));assert.ok(html.includes('data-record-to="'+end+'"'));assert.ok(html.includes('data-record-from="'+text.indexOf('```')+'"'));
 assert.match(html,/<strong>현재 번호<\/strong>/);assert.ok(!md.render(text).includes('data-record-from'));
});
test('the second cited occurrence remains the second visible occurrence',()=>{
 const raw='담당자는 민수다. 담당자는 민수다.',quote='담당자는 민수다.',offset=raw.lastIndexOf(quote);
 assert.deepEqual(locate(raw,offset,quote,raw,quote),{start:offset,end:offset+quote.length});
});
test('ambiguous Markdown projections fall back to their source block instead of marking a different match',()=>{
 assert.equal(locate('**207** / 207',0,'**207**','207 / 207','207'),null);
 assert.equal(locate('[207](https://example.com/207)',1,'207','207','207'),null);
 assert.equal(normalized('  현재\n\t번호  207  '),'현재 번호 207');
});
test('HTML and unsafe links stay escaped when source metadata is enabled',()=>{
 const html=md.render('<img src=x onerror=alert(1)>\n\n[실행](javascript:alert(1))',{sourceMap:true});assert.ok(!html.includes('<img'));assert.ok(!html.includes('href="javascript:'));assert.match(html,/data-record-from="0"/);
});
