// Production app bootstrap and navigation against a disposable, CSRF-enforcing API double.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const {readFileSync,mkdirSync,writeFileSync}=require('node:fs');
const {resolve}=require('node:path');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 const checks=[],errors=[],requests=[],records=[],sessions=new Map();
 sessions.set('s',{id:'s',title:'내 대화',mode:'auto',messages:[]});
 const out=resolve(process.env.PMA_TEST_OUTPUT||'.local/conversation-ui');mkdirSync(out,{recursive:true});
 const check=(value,label)=>{assert.ok(value,label);checks.push(label);};
 let releaseCommit,releaseMessage;
 try{
  const page=await browser.newPage({viewport:{width:1280,height:900}});
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('http://127.0.0.1:8884/**',async route=>{
   const request=route.request(),url=new URL(request.url()),path=url.pathname,method=request.method();
   const data=request.postDataJSON();
   const json=body=>route.fulfill({json:body});
   if(path.startsWith('/api/')){
    if(method!=='GET'&&request.headers()['x-csrf-token']!=='test-token')return route.fulfill({status:403,json:{error:{message:'CSRF missing'}}});
    requests.push({path,method,data});
    if(path==='/api/v1/session')return json({csrf:'test-token',evaluation_enabled:false});
    if(path==='/api/v1/health')return json({models:{generation:'ready',embedding:'ready'}});
    if(path==='/api/v1/processing')return json({remaining:0,queued:0,processing:0,completed:0,failed:0,total:0,recent:[],current:null});
    if(path==='/api/v1/records'){
     if(method==='POST'){const item={id:'r'+records.length,text:data.text,version:1,status:'queued',updated_at:new Date().toISOString()};records.push(item);return json({record_id:item.id,job_id:'job',status:'queued',version:1});}
     return json({items:records,next_cursor:null});
    }
    if(path==='/api/v1/chat/sessions'){
     if(method==='POST'){const s={id:'s'+sessions.size,title:'새 대화',mode:'auto',messages:[]};sessions.set(s.id,s);return json(s);}
     return json({items:[...sessions.values()]});
    }
    if(path.startsWith('/api/v1/chat/sessions/')){
     const parts=path.split('/'),s=sessions.get(parts[5]);
     if(parts[6]==='messages'){
      s.mode=data.mode;s.title=data.question;
      if(data.question==='중단점검'){
       const m={id:'cancel-m',request_id:data.request_id,state:'running',question:data.question,mode:data.mode,evidence:[]};s.messages.push(m);
       await new Promise(resolve=>{releaseMessage=resolve;});return json({message_id:m.id,memory_candidates:[]});
      }
      const m={id:'m'+s.messages.length,request_id:data.request_id,state:'completed',question:data.question,mode:data.mode,evidence:[],snapshot:{searches:[]},response:{status:'answered',conversation_type:'general',items:[{text:'확인한 일반 답변입니다.',citations:[]}]}};
      s.messages.push(m);return json({message_id:m.id,memory_candidates:[]});
     }
     if(parts[6]==='requests'){
      if(parts[8]==='cancel'){const m=s.messages.find(m=>m.request_id===parts[7]);m.state='failed';m.error_code='CANCELLED';if(releaseMessage)releaseMessage();return json({state:'cancelled'});}
      const m=s.messages.find(m=>m.request_id===parts[7]);return json({state:m?.state||'completed',error_code:m?.error_code});
     }
     return json(s);
    }
    if(path==='/api/v1/answers'){
     if(data.question==='오류점검')return route.fulfill({status:503,json:{error:{code:'MODEL_UNAVAILABLE',message:'합성 검색 서버 연결 실패'}}});
     return json({status:'insufficient_evidence',items:[],results:[],filters:data.filters||{},search_keywords:[],connections:[]});
    }
    if(path==='/api/v1/imports/preview')return json({import_id:'upload',filename:data.filename,chunks:[{text:data.text,start:0,end:Array.from(data.text).length}]});
    if(path==='/api/v1/imports/upload/commit'){
     await new Promise(resolve=>{releaseCommit=resolve;});return json({records:[{record_id:'imported'}]});
    }
    if(path==='/api/v1/imports/upload'&&method==='DELETE')return route.fulfill({status:204});
    return route.fulfill({status:404,json:{error:{message:'unsupported fixture route'}}});
   }
   let file=path==='/'?'pma/static/index.html':/^\/static\/[a-z-]+\.(js|css)$/.test(path)?'pma'+path:null;
   if(!file)return route.fulfill({status:404,body:''});
   return route.fulfill({body:readFileSync(resolve(file),'utf8'),contentType:path==='/'?'text/html':path.endsWith('.css')?'text/css':'text/javascript'});
  });
  await page.goto('http://127.0.0.1:8884/');
  const input=page.getByLabel('메시지',{exact:true});await input.waitFor();
  check(await page.locator('body').getAttribute('data-tab')==='chat','실제 앱 초기 대화 진입');
  await page.locator('#chat-mode').selectOption('general');await input.fill('첫 메시지');await page.getByRole('button',{name:'보내기',exact:true}).click();
  await page.getByText('확인한 일반 답변입니다.',{exact:true}).waitFor();
  const sent=requests.find(r=>r.method==='POST'&&r.path.endsWith('/messages'));
  check(sent.data.mode==='general','첫 전송의 기억 사용 안 함 모드 보존');
  check(sent.data.question==='첫 메시지','첫 메시지 생성·전송 연결');
  await input.fill('중단점검');await page.locator('#chat-send').click();await page.locator('#chat-cancel').waitFor({state:'visible'});
  check(await page.locator('#chat-send').isDisabled(),'실행 중 전송 중복 방지');
  await page.locator('#chat-cancel').click();await page.locator('#chat-cancel').waitFor({state:'hidden'});
  check(requests.some(r=>r.path.endsWith('/cancel')),'대화 중단 버튼은 현재 요청 취소 API 호출');
  await page.locator('.site-header [data-tab=records]').click();await page.getByLabel('기록 내용',{exact:true}).fill('합성 원문');
  await page.getByRole('button',{name:'기록 저장',exact:true}).click();await page.locator('#record-list .record').waitFor();
  check(records[0].text==='합성 원문','기록 저장 화면과 인증 API 연결');
  check((await page.locator('#record-list').innerText()).includes('기억 정리 대기'),'원문 저장 후 색인 대기 상태 표시');
  await page.locator('.chat-list-item').first().click();
  await page.locator('#chat:not([hidden])').waitFor();check(await input.isVisible(),'기록 화면에서 대화 선택 시 대화로 이동');
  await page.locator('.site-header [data-tab=records]').click();await page.locator('#chat-new').click();
  await page.locator('#chat:not([hidden])').waitFor();check(await input.isVisible(),'다른 화면에서 새 대화로 이동');
  await page.getByRole('button',{name:'기록 검색',exact:true}).click();await page.getByLabel('질문',{exact:true}).fill('합성 검색');
  await page.getByRole('button',{name:'기억 찾아보기',exact:true}).click();await page.locator('#answer:not([hidden])').waitFor();
  check(requests.some(r=>r.path==='/api/v1/answers'),'검색 도구와 기존 질문 API 연결');
  await page.getByLabel('질문',{exact:true}).fill('오류점검');await page.getByRole('button',{name:'기억 찾아보기',exact:true}).click();
  await page.getByText('합성 검색 서버 연결 실패',{exact:true}).waitFor();
  check(await page.getByRole('button',{name:'기억 찾아보기',exact:true}).isEnabled(),'검색 실패 뒤 다시 검색 가능');
  await page.locator('#date-from').evaluate(el=>el.closest('details').open=true);
  await page.locator('#date-from').fill('2026-10-01');await page.locator('#date-to').fill('2026-10-20');
  await page.getByLabel('질문',{exact:true}).fill('필터점검');await page.getByRole('button',{name:'기억 찾아보기',exact:true}).click();
  await page.locator('#answer:not([hidden])').waitFor();
  check(requests.some(r=>r.data?.question==='필터점검'&&r.data.filters.date_from==='2026-10-01'&&r.data.filters.date_to==='2026-10-20'),'변경한 기간 필터를 검색 API에 반영');
  await page.locator('.site-header [data-tab=chat]').click();
  await page.locator('#record-upload').setInputFiles({name:'literal.md',mimeType:'text/markdown',buffer:Buffer.from('<img src=x onerror=alert(1)>','utf8')});
  await page.getByRole('dialog').waitFor();check(await page.getByRole('dialog').locator('img').count()===0,'업로드 HTML을 텍스트로 표시');
  await page.getByRole('button',{name:'확인하고 저장',exact:true}).click();
  await page.getByText('원문을 저장하고 있습니다.',{exact:true}).waitFor();
  await page.keyboard.press('Escape');check(await page.getByRole('dialog').isVisible(),'저장 처리 중 Escape로 미확정 취소 방지');
  releaseCommit();await page.getByRole('dialog').waitFor({state:'hidden'});
  check(requests.filter(r=>r.path.endsWith('/imports/upload/commit')).length===1,'실제 업로드 API 중복 호출 없음');
  await page.setViewportSize({width:390,height:844});await page.locator('#app-menu-toggle').click();
  await page.locator('.site-header [data-tab=records]').click();
  check(await page.locator('body').getAttribute('data-tab')==='records','모바일 기록 탐색');
  check(!await page.locator('#main-content').evaluate(el=>el.inert),'모바일 탐색 후 본문 초점 복원');
  check(!errors.length,'실제 앱 실행 오류 없음');
  writeFileSync(resolve(out,'app-results.json'),JSON.stringify({passed:checks.length,checks,errors},null,2));
  console.log(JSON.stringify({passed:checks.length,checks}));
 }finally{if(releaseCommit)releaseCommit();if(releaseMessage)releaseMessage();await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
