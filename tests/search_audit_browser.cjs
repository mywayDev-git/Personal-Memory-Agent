// Render the disposable fixture through intercepted requests; no network or personal data.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {resolve} = require('node:path');

(async () => {
  const browser = await chromium.launch({headless:true, channel:'chrome'});
  try {
    const page = await browser.newPage();
    await page.route('http://127.0.0.1:8880/**', async route => {
      const path=new URL(route.request().url()).pathname;
      const file=path==='/'?'pma/static/index.html':path==='/fixture.js'?'evaluation/chat_ui_fixture.js':`pma${path}`;
      if(path!=='/' && path!=='/fixture.js' && !/^\/static\/[a-z-]+\.(js|css)$/.test(path))return route.fulfill({status:404,body:''});
      let body=readFileSync(resolve(__dirname,'..',file),'utf8');
      if(path==='/')body=body.replace('/static/app.js','/fixture.js');
      await route.fulfill({body,contentType:path==='/'?'text/html':path.endsWith('.css')?'text/css':'text/javascript'});
    });
    await page.goto('http://127.0.0.1:8880/');
    await page.getByRole('button',{name:'검색 사유',exact:true}).click();
    // Prepare the nested render fixture; production conversation tests cover folding.
    await page.locator('.chat-search-info').evaluate(el=>{el.open=true;});
    await page.locator('.search-audit > summary').click();
    await page.locator('.search-audit, .search-audit details').evaluateAll(nodes=>nodes.forEach(el=>{el.open=true;}));
    const info = await page.locator('.chat-search-info').innerText();
    for(const text of ['답변 전체 검증 실패','개별 기록이 틀렸다는 뜻은 아닙니다','초안 검증: 실패','재작성 검증: 실패','조건 검사: 조건 통과','근거 선택: 선택됨','답변 사용: 미사용','요청 조건: 2026-01-01 ~ 2026-12-31','사건 날짜 확인 불가','근거 선택: 미실행'])assert.ok(info.includes(text),text);
    // Exercise production rendering and record lookup with deterministic responses.
    await page.evaluate(async () => {
      const {auditView,answerAuditView} = await import('/static/search-explanation.js');
      const node=(tag,text,cls)=>{const el=document.createElement(tag);if(text)el.textContent=text;if(cls)el.className=cls;return el;};
      const action=(text,fn)=>{const el=node('button',text);el.onclick=fn;return el;};
      const cases=[['unused','draft_not_cited'],['removed','citation_removed'],['legacy',null],['changed',null],['deleted',null]];
      const host=node('div');host.id='audit-test';
      host.style.cssText='position:fixed;inset:0;z-index:10000;overflow:auto;background:white;padding:20px';
      document.body.append(host);
      const retry=answerAuditView(node,{status:'model_checked',attempts:[
        {generation:1,status:'rejected',reasons:['invalid_review_citation']},
        {generation:1,status:'passed',reasons:[]}
      ]});retry.id='review-retry';host.append(retry);
      for(const [id,reason] of cases){
        const candidate={id,record_id:id,version:1,status:'selected',reason:'combined_rank'};
        if(reason)candidate.stages={conditions:{status:'passed'},selection:{status:'selected'},answer:{status:'not_run'}};
        const view=auditView({node,action,api:async()=>{if(id==='deleted')throw Error();return {version:id==='changed'?2:1,text:'원문 값: 지연'};}},{candidates:[candidate]},new Set(),[],reason?{usage:[{id,status:'unused',reason}],attempts:[]}:null);
        view.id=id;view.open=true;host.append(view);
        view.querySelectorAll('details').forEach(el=>{el.open=true;});
      }
    });
    assert.match(await page.locator('#unused').innerText(),/최종 초안에서 인용하지 않음/);
    assert.match(await page.locator('#removed').innerText(),/답변 검증에서 인용 제거/);
    assert.match(await page.locator('#legacy').innerText(),/세부 사유가 기록되지 않음/);
    assert.match(await page.locator('#review-retry').innerText(),/같은 답변 검증 재시도: 통과/);
    assert.ok(!(await page.locator('#review-retry').innerText()).includes('재작성'));
    for(const id of ['unused','changed','deleted'])await page.locator(`#${id} button`).click();
    assert.match(await page.locator('#unused').innerText(),/원문 값: 지연/);
    assert.match(await page.locator('#changed').innerText(),/검색 당시와 다른 버전/);
    assert.match(await page.locator('#deleted').innerText(),/현재 이 기록을 열 수 없습니다/);
    assert.ok(!(await page.locator('#changed').innerText()).includes('원문 값:'));
    await page.locator('#audit-test').evaluate(el=>el.remove());
    await page.screenshot({path:'.local/search-audit-browser.png',fullPage:true});
    console.log('Search audit browser checks passed: stages, attempts, limits, legacy, deleted and changed sources.');
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
