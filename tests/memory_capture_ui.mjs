// Run with a CUA tab after authenticating against evaluation.memory_ui_server.
// All browser operations use CUA's supported Playwright surface.
export async function runMemoryUI(tab) {
  const p=tab.playwright;
  const button=name=>p.getByRole('button',{name,exact:true});
  const checks=[];
  const assert=(value,name)=>{if(!value)throw new Error(name);checks.push(name);};
  for(const mode of ['general','memory','hybrid']) {
    await button(`${mode} 평가: 앞으로 한국어로 간결하게 설명해줘.`).click();
    await tab.getAXState({emit:false});
    await p.getByRole('heading',{name:`${mode} 평가: 앞으로 한국어로 간결하게 설명해줘.`,exact:true}).waitFor({state:'visible'});
    if(!await p.locator('.chat-user').getByRole('button',{name:'기억에 저장',exact:true}).isVisible()) await p.locator('.chat-user-actions > summary').click();
    await p.locator('.chat-user').getByRole('button',{name:'기억에 저장',exact:true}).click();
    await tab.getAXState({emit:false});
    assert(await button('저장').isEnabled(),mode+': single save action');
    await button('저장').click();
    await tab.getAXState({emit:false});
    if(await p.getByLabel('기존 기억 처리',{exact:true}).isVisible()) {
      await p.getByLabel('기존 기억 처리',{exact:true}).selectOption('add_confirmed');
      await button('저장').click();
    }
    if(!await button('기억 관리').isVisible()) await p.locator('#chat-menu > summary').click();
    await button('기억 관리').click();
    await p.getByRole('button',{name:/앞으로 한국어로 간결하게 설명해줘/}).last().click();
    await p.getByRole('heading',{name:'저장된 기억',exact:true}).waitFor({state:'visible'});
    assert(await p.getByRole('heading',{name:'저장된 기억',exact:true}).isVisible(),mode+': saved');
    await button('수정 이력').click();
    await tab.getAXState({emit:false});
    await p.locator('dialog').getByText(/버전 1/).waitFor({state:'visible'});
    assert((await p.locator('dialog').innerText()).includes('버전 1'),mode+': history');
    await button('기억 보관').click();
    await tab.getAXState({emit:false});
    await button('보관 해제').waitFor({state:'visible'});
    assert(await button('보관 해제').isVisible(),mode+': archived');
    await button('보관 해제').click();
    await tab.getAXState({emit:false});
    await button('기억 보관').waitFor({state:'visible'});
    assert(await button('기억 보관').isVisible(),mode+': unarchived');
    await button('닫기').click();
  }
  await p.locator('.chat-ai').getByRole('button',{name:'기억에 저장',exact:true}).click();
  await tab.getAXState({emit:false});
  const options=await p.getByLabel('기억 유형',{exact:true}).innerText();
  assert(!options.includes('사건'),'AI cannot become event');
  await button('저장 취소').click();
  await tab.getAXState({emit:false});
  if(!await button('기억 관리').isVisible()) await p.locator('#chat-menu > summary').click();
  await button('기억 관리').click();
  await tab.getAXState({emit:false});
  await p.getByLabel('저장 정책 · 자동 저장은 꺼져 있습니다',{exact:true}).selectOption('SUGGEST');
  await tab.getAXState({emit:false});
  await button('닫기').click();
  await tab.reload();
  await button('AI 대화').click();
  await button('hybrid 평가: 앞으로 한국어로 간결하게 설명해줘.').click();
  await p.getByRole('heading',{name:'hybrid 평가: 앞으로 한국어로 간결하게 설명해줘.',exact:true}).waitFor({state:'visible'});
  if(!await button('기억 관리').isVisible()) await p.locator('#chat-menu > summary').click();
  await button('기억 관리').click();
  await tab.getAXState({emit:false});
  assert((await p.getByLabel('저장 정책 · 자동 저장은 꺼져 있습니다',{exact:true}).evaluate(el=>el.value))=== 'SUGGEST','reload');
  return {passed:checks.length,checks};
}

export async function runMemoryEdges(tab) {
  const p=tab.playwright, checks=[];
  const button=name=>p.getByRole('button',{name,exact:true});
  const assert=(value,name)=>{if(!value)throw new Error(name);checks.push(name);};
  await button('닫기').click();
  await button('hybrid 평가: 앞으로 한국어로 간결하게 설명해줘.').click();
  await p.locator('.chat-user').getByRole('button',{name:'기억에 저장',exact:true}).click();
  await button('저장').click();
  await tab.getAXState({emit:false});
  assert((await p.locator('dialog').innerText()).includes('이미 저장된 내용'),'duplicate blocks commit');
  await p.getByLabel('저장할 내용',{exact:true}).fill('수정된 선호: 한국어로 짧게 설명해줘.');
  assert((await p.locator('dialog').innerText()).includes('변경한 내용을 자동으로 비교'),'edit invalidates review');
  await button('저장 취소').click();
  if(!await button('기억 관리').isVisible()) await p.locator('#chat-menu > summary').click();
  await button('기억 관리').click();
  await tab.getAXState({emit:false});
  await p.getByRole('button',{name:/인덱싱 재시도 평가 기억/}).click();
  await tab.getAXState({emit:false});
  assert(await button('검색 처리 재시도').isVisible(),'index failure displayed');
  await button('검색 처리 재시도').click();
  await tab.getAXState({emit:false});
  assert((await p.locator('dialog').innerText()).includes('검색 처리 대기'),'index retry queued');
  await p.getByLabel('정정할 내용',{exact:true}).fill('인덱싱 재시도 평가 기억을 정정했다.');
  await button('정정 미리보기').click();
  await button('저장').click();
  if(!await button('기억 관리').isVisible()) await p.locator('#chat-menu > summary').click();
  await button('기억 관리').click();
  await p.getByRole('button',{name:/인덱싱 재시도 평가 기억을 정정했다/}).click();
  await button('수정 이력').click();
  await tab.getAXState({emit:false});
  assert((await p.locator('dialog').innerText()).includes('버전 2'),'correction version 2');
  await p.getByRole('button',{name:'닫기',exact:true}).press('Escape');
  await tab.getAXState({emit:false});
  assert(await p.locator('dialog').count()===0,'escape closes dialog');
  return {passed:checks.length,checks};
}

