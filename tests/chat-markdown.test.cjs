'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),path=require('node:path');
const root=process.env.PMA_APP_ROOT||path.resolve(__dirname,'..');
const markdown=require(path.join(root,'ui/plant-thought/chat-markdown.js'));
test('renders Korean headings, nested lists, emphasis, quotes, tables and safe links',()=>{
  const html=markdown.render('## 확인한 내용\n\n**중요**한 *메모*입니다.\n\n1. 첫 항목\n   - 하위 항목\n2. 다음 항목\n\n> 인용\n\n| 항목 | 상태 |\n| --- | --- |\n| 예약 | 확인 |\n\n[문서](https://example.com/?x=1&y=2)');
  for(const value of ['<h2>확인한 내용</h2>','<strong>중요</strong>','<em>메모</em>','<ol>','<ul>','<blockquote>','<th>항목</th>','<td>확인</td>','role="region"','target="_blank"','rel="noopener noreferrer"'])assert(html.includes(value),value);
});
test('preserves plain response line breaks and renders inline/fenced code literally',()=>{
  const html=markdown.render('첫 줄\n다음 줄\n\n`a < b`\n\n```html\n<script>alert("x")</script>\n**코드**\n```');
  assert(html.includes('첫 줄<br>\n다음 줄'));assert(html.includes('<code>a &lt; b</code>'));
  assert(html.includes('&lt;script&gt;'));assert(html.includes('**코드**'));assert(!html.includes('<strong>코드</strong>'));assert(!html.includes('<script>'));assert(html.includes('aria-label="코드 블록"'));
});
test('HTML, image requests and encoded executable links cannot become active content',()=>{
  const hostile=['<script>alert(1)</script>','<img src=x onerror=alert(1)>','<svg/onload=alert(1)>','<iframe src="https://example.com"></iframe>','![외부 이미지](https://example.com/tracker.png)','[실행](javascript:alert%281%29)','[인코딩](jav&#x61;script:alert%281%29)','[데이터](data:text/html;base64,PHNjcmlwdD4=)','[파일](file:///C:/private.txt)','[앱](plant:delete)','[상대](//example.com)','[속성](https://example.com/\"onmouseover=\"alert%281%29)'];
  for(const input of hostile){const html=markdown.render(input);assert(!/<(?:script|img|svg|iframe|object|embed)\b/i.test(html),input);assert(!/href="(?:javascript|data|file|plant):/i.test(html),input);assert(!/\s(?:onerror|onload|onmouseover)="/i.test(html),input);}
});
test('literal angle brackets, long code lines, mail links and malformed markdown survive',()=>{
  assert(markdown.render('**미완성').includes('**미완성'));
  assert(markdown.render('비용 < 5000 & 예약 > 2').includes('비용 &lt; 5000 &amp; 예약 &gt; 2'));
  assert(markdown.render('[메일](mailto:test@example.com)').includes('href="mailto:test@example.com"'));
  const long='x'.repeat(1000);assert(markdown.render('```\n'+long+'\n```').includes(long));
});
