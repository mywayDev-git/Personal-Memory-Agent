const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {resolve} = require('node:path');

(async()=>{
  const browser=await chromium.launch({headless:true,channel:'chrome'});
  try{
    const page=await browser.newPage({viewport:{width:1000,height:850}});
    await page.route('http://127.0.0.1:8882/**',async route=>{
      const path=new URL(route.request().url()).pathname;
      if(path==='/')return route.fulfill({contentType:'text/html',body:'<!doctype html><html lang="ko"><meta charset="utf-8"><link rel="stylesheet" href="/static/style.css"><body><main id="result"></main></body></html>'});
      if(!/^\/static\/(search-explanation\.js|style\.css)$/.test(path))return route.fulfill({status:404,body:''});
      return route.fulfill({body:readFileSync(resolve(__dirname,'..','pma'+path),'utf8'),contentType:path.endsWith('.js')?'text/javascript':'text/css'});
    });
    await page.goto('http://127.0.0.1:8882/');
    await page.evaluate(async()=>{
      const {explanation,expansionView}=await import('/static/search-explanation.js');
      const node=(tag,text,cls)=>{const el=document.createElement(tag);if(text)el.textContent=text;if(cls)el.className=cls;return el;};
      const host=document.getElementById('result');
      host.append(node('h1','한영·발음 검색 설명'));
      const expansion={status:'applied',searched:true,edits:[{before:'쿠버네티스',after:'Kubernetes',kind:'transliteration'}],retrieval:[{
        query:'kubernetes 공부',kind:'transliteration',weight:0.8,contributed:true,
        keyword_matches:[{field:'source_text',start:2,end:12,quote:'Kubernetes'}]}]};
      const summary=expansionView(node,expansion);summary.open=true;host.append(summary);
      host.append(explanation(node,{source_text:'😀 Kubernetes 공부',search_explanation:{methods:['expansion'],query_expansion:expansion}}));
      host.append(explanation(node,{source_text:'😀 Ｐｙｔｈｏｎ 공부',search_explanation:{methods:['keyword'],keyword_matches:[{
        field:'source_text',start:2,end:8,quote:'Ｐｙｔｈｏｎ',term:'python',kind:'normalized',match_type:'alias'}]}}));
      const rejected=expansionView(node,{status:'rejected',reason:'embedding_failed',rejected:[{before:'Java',reason:'ambiguous_expression'}]});rejected.open=true;host.append(rejected);
      const literal=expansionView(node,{status:'applied',searched:false,edits:[{before:'원문',after:'<script>bad()</script>',kind:'translation'}]});literal.open=true;host.append(literal);
    });
    await page.locator('.search-explanation details > summary').click();
    const text=await page.locator('#result').innerText();
    for(const label of ['발음 표기','등록 별칭','원문으로 검색','여러 의미','<script>bad()</script>'])assert.ok(text.includes(label),label);
    assert.deepEqual(await page.locator('.keyword-highlight').allTextContents(),['Kubernetes','Ｐｙｔｈｏｎ']);
    assert.equal(await page.locator('#result script').count(),0);
    await page.screenshot({path:'.local/multilingual-search-ui.png',fullPage:true});
    console.log('Multilingual browser checks passed: pronunciation, alias labels, Unicode highlights, fallback, ambiguous terms, literal HTML.');
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
