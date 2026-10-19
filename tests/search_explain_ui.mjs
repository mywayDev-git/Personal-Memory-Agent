export async function runSearchExplanationUI(tab) {
 const p=tab.playwright, checks=[];
 const check=(ok,name)=>{if(!ok)throw Error(name);checks.push(name);};
 await p.getByRole('button',{name:'부분 근거',exact:true}).click();await tab.getAXState({emit:false});
 check((await p.locator('.chat-search-info').innerText()).includes('검색 질문: 민수 부산 여행'),'rewritten question');
 await p.locator('.search-audit > summary').click();await tab.getAXState({emit:false});
 check((await p.locator('.search-audit').innerText()).includes('사건 날짜 확인 불가'),'unknown date reason');
 check((await p.locator('.search-audit').innerText()).includes('답변에 인용됨'),'cited distinction');
 await p.locator('.search-audit .search-explanation details > summary').click();await tab.getAXState({emit:false});
 check((await p.locator('.search-audit .keyword-highlight').innerText())==='민수','exact keyword highlight');
 await p.locator('.search-audit > summary').click();await p.locator('.chat-evidence > summary').click();await tab.getAXState({emit:false});
 check((await p.locator('.chat-evidence').innerText()).includes('인물: 민수 · 조건 통과'),'condition value');
 await p.locator('.chat-evidence .search-explanation details > summary').click();await tab.getAXState({emit:false});
 const keyword=await p.locator('.chat-evidence .keyword-highlight').evaluate(el=>getComputedStyle(el).backgroundColor);
 const evidence=await p.locator('.chat-evidence .evidence-highlight').first().evaluate(el=>getComputedStyle(el).backgroundColor);
 check(keyword!==evidence,'distinct keyword and evidence colors');
 return {passed:checks.length,checks};
}
