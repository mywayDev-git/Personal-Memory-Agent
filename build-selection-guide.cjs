const fs=require('node:fs'),path=require('node:path');
const root=__dirname,catalog=JSON.parse(fs.readFileSync(path.join(root,'selection-catalog.json'),'utf8'));
const jsFile=path.join(root,'baseline.js'),htmlFile=path.join(root,'baseline.html'),cssFile=path.join(root,'baseline.css');
let js=fs.readFileSync(jsFile,'utf8');
const marker='// SELECTION GUIDE START';const suffix=js.includes('// PROGRESS SEARCH UI')?js.slice(js.indexOf('// PROGRESS SEARCH UI')):'';if(js.includes(marker))js=js.slice(0,js.indexOf(marker));
js+='\n'+marker+'\nconst selectionCatalog='+JSON.stringify(catalog)+';\n'+`
function renderSelectionGuide(){
 const panel=document.querySelector('#selection-guide');if(!panel)return;
 panel.querySelector('.guide-cards').innerHTML=selectionCatalog.groups.map(group=>{const item=group.items.find(item=>item.id===document.getElementById(group.key).value);return '<article class="guide-card"><small>'+esc(group.label)+' · '+esc(group.question)+'</small><strong>'+esc(item?.name||'선택 대기')+'</strong><p>'+esc(item?.summary||'선택 후 설명을 확인하세요.')+'</p><span>'+esc(item?.change||'')+'</span></article>';}).join('');
 panel.querySelector('.guide-common').textContent=selectionCatalog.common;
 panel.querySelector('.guide-context-note').textContent=document.querySelector('#stage').value==='answer'?'답변만 실행하면 선택한 저장 검색 산출물을 사용합니다. 현재 검색 구성 선택이 그 산출물을 다시 검색하거나 변경하지 않습니다.':document.querySelector('#stage').value==='retrieve'&&!['R0','R0-Full'].includes(document.querySelector('#route').value)?'검색만 실행하면 선택한 저장 추출 산출물을 사용합니다. 현재 구조화 방식·버전으로 다시 추출하지 않습니다.':'';
}
function initializeSelectionGuide(){
 const panel=document.querySelector('#selection-guide');if(!panel)return;
 panel.querySelector('.guide-reference').innerHTML=selectionCatalog.groups.map(group=>'<div class="guide-group"><h3>'+esc(group.label)+' <small>'+esc(group.question)+'</small></h3>'+group.items.map(item=>'<article class="guide-reference-item"><strong>'+esc(item.name)+'</strong><p>'+esc(item.detail)+'</p><p class="guide-change">차이: '+esc(item.change)+'</p><p>예: '+esc(item.example)+'</p><p class="guide-limit">확인: '+esc(item.limit)+'</p></article>').join('')+'</div>').join('');
 for(const id of ['dataset','method','structure-version','route','stage','frozen-run'])document.getElementById(id).addEventListener('change',renderSelectionGuide);
 renderSelectionGuide();
}
initializeSelectionGuide();
// After async bootstrap/dataset loading, refresh descriptions alongside existing help.
const originalGuideStageHelp=renderStageHelp;
renderStageHelp=function(){originalGuideStageHelp();renderSelectionGuide();};
// SELECTION GUIDE END
`;
fs.writeFileSync(jsFile,js+suffix);
let html=fs.readFileSync(htmlFile,'utf8');if(!html.includes('id="selection-guide"')){const at='<details id="prompt-controls">';if(!html.includes(at))throw Error('Controls insertion point missing');html=html.replace(at,'<section id="selection-guide" class="selection-guide" aria-label="선택 항목 설명"><div class="guide-heading"><strong>선택 항목 한눈에 보기</strong><span>선택을 바꾸면 설명도 바뀝니다.</span></div><div class="guide-cards" aria-live="polite"></div><p class="guide-context-note"></p><details><summary>모든 방식·버전 차이와 예시 보기</summary><p class="guide-common"></p><div class="guide-reference"></div></details></section>'+at);}
fs.writeFileSync(htmlFile,html);
let css=fs.readFileSync(cssFile,'utf8');const cssSuffix=css.includes('/* Progress and searchable evidence lists */')?css.slice(css.indexOf('/* Progress and searchable evidence lists */')):'';if(css.includes('/* SELECTION GUIDE */'))css=css.slice(0,css.indexOf('/* SELECTION GUIDE */'));
css+=`\n/* SELECTION GUIDE */
.selection-guide{margin-top:18px;padding:16px;background:#f8faf5;border:1px solid #e2eadc;border-radius:8px}.guide-heading{display:flex;gap:12px;align-items:center;margin-bottom:12px;font-size:11px}.guide-heading span{font-size:10px;color:#85917c}.guide-cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.guide-card{background:white;border:1px solid #e5ecdf;border-radius:7px;padding:12px;min-width:0}.guide-card small{display:block;color:#849179;font-size:9px}.guide-card strong{display:block;font-size:11px;margin:6px 0}.guide-card p{font-size:11px;line-height:1.8;color:#4e6b47}.guide-card>span{display:block;font-size:10px;color:#829073;margin-top:6px}.guide-common,.guide-context-note{font-size:10px;color:#79866e;line-height:1.8}.guide-context-note:empty{display:none}.guide-context-note:not(:empty){margin-top:12px;color:#977c3c}.guide-reference{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:16px}.guide-group h3{font-size:12px}.guide-group h3 small{font-size:10px;color:#849179;font-weight:400;margin-left:8px}.guide-reference-item{padding:13px 0;border-bottom:1px solid #e1e8da;font-size:11px}.guide-reference-item strong{font-size:11px}.guide-reference-item p{font-size:10px;line-height:1.9}.guide-change{color:#3e7755}.guide-limit{color:#9a814e}@media(max-width:1000px){.guide-cards{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:560px){.guide-cards,.guide-reference{grid-template-columns:minmax(0,1fr)}.guide-heading{align-items:flex-start;flex-direction:column;gap:3px}}
`;
fs.writeFileSync(cssFile,css+cssSuffix);
const lines=['# Baseline 선택 항목·버전 안내','',`설명 버전: ${catalog.revision} · ${catalog.updated_on}`,'','이 문서는 현재 구현의 차이를 기록한다. v2 또는 H1이 더 우수하다고 판정한 성능 보고서가 아니다.',''];
for(const g of catalog.groups){lines.push('## '+g.label+' — '+g.question,'');for(const i of g.items)lines.push('### '+i.name+' (`'+i.id+'`)','',i.summary,'',i.detail,'','- 변경·차이: '+i.change,'- 표현 예시: '+i.example,'- 주의·한계: '+i.limit,'');}
lines.push('## 공통 조건','',catalog.common,'','추출 프롬프트와 방식 버전은 별도 설정이며 함께 적용된다. 같은 방식의 v1/v2는 현재 JSON 스키마가 같다. 프롬프트 본문을 직접 수정하면 저장되는 본문 해시가 달라진다.','','고정 산출물을 재사용할 때는 해당 산출물의 저장 당시 방식·버전·검색 설정이 실제 입력을 결정한다. 현재 선택값으로 과거 산출물이 변하지 않는다.','','기존 실행 기록의 설정·해시는 유지하며, 이 안내 추가로 모델 평가를 실행하지 않는다.');
fs.writeFileSync(path.join(root,'SELECTION_GUIDE.md'),lines.join('\n')+'\n');
console.log('Selection guide generated: 4 groups, '+catalog.groups.reduce((n,g)=>n+g.items.length,0)+' options.');
