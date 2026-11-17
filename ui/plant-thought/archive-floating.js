'use strict';
// Floating inspector for the existing synthetic-source UI. No backend connection.
(()=>{
  const dock=document.getElementById('archiveFloatingDock'),body=document.getElementById('archiveFloatingBody'),launcher=document.getElementById('archiveDockToggle');
  if(!dock||!body||!launcher)return;
  const visiblePages=new Set(['home','chat','archive']);
  const host=document.createElement('div');host.id='archiveInspectorHost';host.className='archive-inspector-host';
  host.append(dock,launcher);document.body.appendChild(host);
  function syncVisibility(){
    const page=document.querySelector('.page.active')?.id||'home';host.dataset.page=page;host.hidden=!visiblePages.has(page)||(window.PlantTestMode&&!window.PlantTestMode.enabled);
  }
  const navigate=go;
  go=function(id){navigate(id);syncVisibility();};
  syncVisibility();
  const storageKey='plant-thought-floating-inspector-v1';
  const groups=['info','examples'];
  let activeTab='info',isOpen=false,saved;
  try{saved=JSON.parse(sessionStorage.getItem(storageKey)||'null');}catch{}
  if(groups.includes(saved?.tab))activeTab=saved.tab;
  isOpen=saved?.open===true;
  const panels={info:document.getElementById('archiveDataInfo'),examples:document.getElementById('archiveExamples')};
  const tabs=[...document.querySelectorAll('[data-dock-tab]')];
  for(const [name,panel]of Object.entries(panels)){panel.setAttribute('role','tabpanel');panel.setAttribute('aria-labelledby',tabs.find(tab=>tab.dataset.dockTab===name).id);}
  function save(){try{sessionStorage.setItem(storageKey,JSON.stringify({tab:activeTab,open:isOpen}));}catch{}}
  function syncSummary(){
    const count=document.getElementById('archiveRecordTotal')?.textContent||'—',examples=document.getElementById('archiveQuestionTotal')?.textContent||'—';
    document.getElementById('archiveDockSummary').textContent='원문 '+count+'개 · 질문·답변 '+examples+'개';
    document.getElementById('archiveDockExampleCount').textContent=examples;
  }
  function setTab(name,{focus=false}={}){
    if(!groups.includes(name))return;activeTab=name;
    for(const tab of tabs){const selected=tab.dataset.dockTab===name;tab.setAttribute('aria-selected',String(selected));tab.tabIndex=selected?0:-1;}
    for(const [key,panel]of Object.entries(panels))panel.hidden=key!==name;
    body.scrollTop=0;if(focus)tabs.find(tab=>tab.dataset.dockTab===name).focus({preventScroll:true});save();
  }
  function open(name=activeTab,{focus=false}={}){isOpen=true;dock.hidden=false;launcher.setAttribute('aria-expanded','true');launcher.setAttribute('aria-label','데이터 정보 패널 접기');setTab(name,{focus});syncSummary();save();}
  function close({focus=false}={}){isOpen=false;dock.hidden=true;launcher.setAttribute('aria-expanded','false');launcher.setAttribute('aria-label','데이터 정보 패널 열기');save();if(focus)launcher.focus({preventScroll:true});}
  document.addEventListener('plant:test-mode-changed',()=>{if(!window.PlantTestMode.enabled)close();syncVisibility();});
  launcher.addEventListener('click',()=>isOpen?close():open(activeTab,{focus:true}));
  document.getElementById('archiveDockClose').addEventListener('click',()=>close({focus:true}));
  for(const [index,tab]of tabs.entries()){
    tab.addEventListener('click',()=>setTab(tab.dataset.dockTab));
    tab.addEventListener('keydown',event=>{
      let next;if(event.key==='ArrowRight')next=(index+1)%tabs.length;else if(event.key==='ArrowLeft')next=(index+tabs.length-1)%tabs.length;else if(event.key==='Home')next=0;else if(event.key==='End')next=tabs.length-1;else return;
      event.preventDefault();setTab(tabs[next].dataset.dockTab,{focus:true});
    });
  }
  document.addEventListener('keydown',event=>{if(event.key==='Escape'&&isOpen&&!host.hidden){event.preventDefault();close({focus:true});}});
  // Date selection keeps using the existing panel next to the calendar.
  const drawSelected=renderSelected;
  renderSelected=function(){drawSelected();syncSummary();};
  document.addEventListener('click',event=>{
    if(event.target.closest('.archive-evidence-link,.archive-question-text,.archive-focus-question'))close();
  },true);
  const jump=document.getElementById('archiveJumpExamples');
  jump.addEventListener('click',event=>{event.preventDefault();event.stopImmediatePropagation();open('examples');document.getElementById('archiveExampleQuery').focus({preventScroll:true});},true);
  syncSummary();setTab(activeTab);if(isOpen)open(activeTab);else close();
})();
