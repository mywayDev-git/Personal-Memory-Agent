'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const editor=require('../ui/plant-thought/markdown-editor.js'),markdown=require('../ui/plant-thought/chat-markdown.js');
test('only the selected line exposes source; heading and emphasis on other lines keep formatting',()=>{
 const text='# 제목\n**기존 번호**: 206\n**새 번호**: 207',start=text.indexOf('**새 번호**'),ranges=editor.previewRanges(text,start+3);
 assert.ok(ranges.some(r=>r.class.includes('md-heading-1')));assert.ok(ranges.some(r=>r.class==='md-render-strong'&&r.from<start));
 assert.deepEqual(ranges.filter(r=>r.from>=start).map(r=>r.class),['md-active-source']);
 assert.equal(editor.previewState(text,start).update({selection:{anchor:0}}).state.doc.toString(),text);
});
test('a multi-line selection reveals every selected line and blur restores their Markdown',()=>{
 const text='# 제목\n**첫 줄**\n*둘째 줄*\n끝',from=text.indexOf('**'),to=text.indexOf('\n끝'),ranges=editor.previewRanges(text,from,to);
 assert.equal(ranges.filter(r=>r.class==='md-active-source').length,2);assert.ok(!ranges.some(r=>r.class==='md-render-strong'||r.class==='md-render-em'));
 const blurred=editor.previewRanges(text,from,to,false);assert.ok(blurred.some(r=>r.class==='md-render-strong'));assert.ok(blurred.some(r=>r.class==='md-render-em'));assert.ok(!blurred.some(r=>r.class==='md-active-source'));
});
test('table rows and code fences render without changing the stored Markdown source',()=>{
 const text='| 항목 | 값 |\n| --- | --- |\n| 번호 | 207 |\n\n```text\n206 -> 207\n```',line=text.indexOf('| 번호'),ranges=editor.previewRanges(text,line+2);
 assert.ok(ranges.some(r=>r.from===0&&r.replacement));assert.ok(!ranges.some(r=>r.from===line&&r.replacement));assert.ok(ranges.some(r=>r.class.includes('md-render-code-line')));
 const original=editor.previewState(text),changed=original.update({changes:{from:line+2,to:line+4,insert:'보관함'}}).state;assert.equal(original.doc.toString(),text);assert.ok(changed.doc.toString().includes('보관함'));
});
test('draft preview renders Markdown while raw HTML and unsafe URLs stay inert',()=>{
 const html=markdown.render('# 제목\n\n**번호**: `207`\n\n<img src=x onerror=alert(1)>\n\n[링크](javascript:alert(1))');
 assert.match(html,/<h1>제목<\/h1>/);assert.match(html,/<strong>번호<\/strong>/);assert.match(html,/<code>207<\/code>/);assert.ok(!html.includes('<img'));assert.ok(!html.includes('href="javascript:'));
});
test('task-list preview uses disabled checkboxes while escaped markers remain literal',()=>{
 const html=markdown.render('- [x] 완료\n- [ ] 다음 할 일\n- \\[x] 원문 표시');
 assert.equal((html.match(/type="checkbox"/g)||[]).length,2);assert.equal((html.match(/ disabled/g)||[]).length,2);assert.match(html,/disabled checked/);assert.match(html,/\[x\] 원문 표시/);
});
