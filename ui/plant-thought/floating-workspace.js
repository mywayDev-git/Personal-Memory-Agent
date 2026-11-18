'use strict';
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else api.mount(root);})(typeof window==='undefined'?null:window,function(){
 function layout(width,height,header,preferred){
  if(!preferred.length)return [];
  const margin=width<=600?12:24,gap=12,bottom=width<900&&preferred.length>1?134:98,available=Math.max(120,width-margin*2),room=Math.max(120,height-header-bottom-14),n=preferred.length;
  if(width>=900){const ratio=Math.min(1,(available-gap*(n-1))/preferred.reduce((a,b)=>a+b,0));let right=margin;return preferred.map(w=>{const rect={right,bottom,width:Math.min(w,w*ratio),height:Math.min(710,room)};right+=rect.width+gap;return rect;});}
  const step=n>1?34:0,h=Math.max(120,Math.min(660,room-step*(n-1)));return preferred.map((w,i)=>({right:margin,bottom:bottom+i*step,width:Math.min(w,available),height:h}));
 }
 const clamp=(v,min,max)=>Math.min(max,Math.max(min,v));
 function bounds(width,height,bottom=86){const left=8,top=8,right=Math.max(9,width-8),edge=Math.max(9,height-bottom);return {left,top,right,bottom:edge,minWidth:Math.min(240,right-left),minHeight:Math.min(220,edge-top)};}
 function fit(rect,area){
  const width=clamp(rect.width,area.minWidth,area.right-area.left),height=clamp(rect.height,area.minHeight,area.bottom-area.top);
  return {x:clamp(rect.x,area.left,area.right-width),y:clamp(rect.y,area.top,area.bottom-height),width,height};
 }
 function resize(rect,edge,dx,dy,area){
  const start=fit(rect,area);let left=start.x,right=left+start.width,top=start.y,bottom=top+start.height;
  if(edge.includes('w'))left=clamp(left+dx,area.left,right-area.minWidth);
  if(edge.includes('e'))right=clamp(right+dx,left+area.minWidth,area.right);
  if(edge.includes('n'))top=clamp(top+dy,area.top,bottom-area.minHeight);
  if(edge.includes('s'))bottom=clamp(bottom+dy,top+area.minHeight,area.bottom);
  return {x:left,y:top,width:right-left,height:bottom-top};
 }
 function validRect(v){return v&&['x','y','width','height'].every(k=>typeof v[k]==='number'&&Number.isFinite(v[k]))&&v.width>0&&v.height>0;}
 function mount(win){
  const doc=win.document,entries=[],storageKey='plant-thought-floating-placement-v1';let active=null,queued=false,gesture=null,saved={};
  try{const value=JSON.parse(win.localStorage.getItem(storageKey)||'null');if(value?.version===1&&value.panels&&typeof value.panels==='object')saved=value.panels;}catch{}
  function save(){try{win.localStorage.setItem(storageKey,JSON.stringify({version:1,panels:Object.fromEntries(entries.filter(e=>e.rect).map(e=>[e.id,e.rect]))}));}catch{}}
  function viewport(){return {width:Math.min(doc.documentElement.clientWidth||win.innerWidth,doc.documentElement.getBoundingClientRect().width||win.innerWidth),height:win.innerHeight};}
  const tabs=doc.createElement('div');tabs.className='floating-window-tabs';tabs.setAttribute('aria-label','열린 플로팅 선택');tabs.hidden=true;doc.body.append(tabs);
  const visible=e=>!e.host.hidden&&win.getComputedStyle(e.host).display!=='none'&&win.getComputedStyle(e.launcher).display!=='none';
  function area(){const v=viewport(),count=entries.filter(e=>visible(e)&&!e.panel.hidden).length;return bounds(v.width,v.height,v.width<900&&count>1?134:86);}
  function paint(entry,rect){Object.assign(entry.panel.style,{left:rect.x+'px',top:rect.y+'px',right:'auto',bottom:'auto',width:rect.width+'px',height:rect.height+'px',maxWidth:'none',maxHeight:'none'});entry.panel.classList.toggle('floating-compact',rect.width<420);entry.reset.disabled=!entry.rect;}
  function focus(id){active=id;for(const e of entries){e.panel.style.zIndex=e.id===id?'114':'110';e.panel.classList.toggle('floating-is-active',e.id===id);}schedule();}
  function redraw(){
   queued=false;const shown=entries.filter(visible),opened=shown.filter(e=>!e.panel.hidden).reverse(),width=Math.min(doc.documentElement.clientWidth||win.innerWidth,doc.documentElement.getBoundingClientRect().width||win.innerWidth);
   const margin=width<=600?12:24;shown.slice().reverse().forEach((e,i)=>{e.launcher.classList.add('floating-managed-launcher');e.launcher.style.right=(margin+i*74)+'px';e.launcher.style.width='62px';});
   const header=doc.querySelector('body>header')?.getBoundingClientRect().height||82,rects=layout(width,win.innerHeight,header,opened.map(e=>e.width));
   opened.forEach((e,i)=>{const rect=rects[i];paint(e,e.rect?fit(e.rect,area()):{x:width-rect.right-rect.width,y:win.innerHeight-rect.bottom-rect.height,width:rect.width,height:rect.height});});
   if(!opened.some(e=>e.id===active))active=opened[0]?.id||null;
   tabs.hidden=width>=900||opened.length<2;
   const signature=opened.map(e=>e.id).join('|');if(tabs.dataset.signature!==signature){tabs.replaceChildren();for(const e of opened){const button=doc.createElement('button');button.type='button';button.textContent=e.label;button.dataset.windowId=e.id;button.addEventListener('click',()=>{focus(e.id);e.closeButton?.focus({preventScroll:true});});tabs.append(button);}tabs.dataset.signature=signature;}
   for(const b of tabs.children)b.setAttribute('aria-pressed',String(b.dataset.windowId===active));
   for(const e of opened){e.panel.style.zIndex=e.id===active?'114':'110';e.panel.classList.toggle('floating-is-active',e.id===active);}
  }
  function schedule(){if(!queued){queued=true;win.requestAnimationFrame(redraw);}}
  function stopGesture(cancel=false){
   if(!gesture)return;const g=gesture;gesture=null;
   if(cancel){g.entry.rect=g.before;schedule();}else if(g.moved)save();
   doc.body.classList.remove('floating-interacting');g.entry.panel.classList.remove('floating-gesture');
   if(g.handle.hasPointerCapture(g.pointerId))g.handle.releasePointerCapture(g.pointerId);
  }
  function startGesture(event,entry,handle,edge){
   if(event.button!==0||gesture||event.isPrimary===false)return;
   if(!edge&&event.target.closest?.('button,a,input,select,textarea,summary'))return;
   const r=entry.panel.getBoundingClientRect();gesture={entry,handle,edge,pointerId:event.pointerId,originX:event.clientX,originY:event.clientY,start:{x:r.left,y:r.top,width:r.width,height:r.height},before:entry.rect?{...entry.rect}:null,moved:false};
   focus(entry.id);event.preventDefault();handle.focus({preventScroll:true});handle.setPointerCapture(event.pointerId);
  }
  function pointerMove(event){
   const g=gesture;if(!g||event.pointerId!==g.pointerId)return;
   const dx=event.clientX-g.originX,dy=event.clientY-g.originY;if(!g.moved&&Math.abs(dx)+Math.abs(dy)<3)return;
   g.moved=true;event.preventDefault();g.entry.rect=g.edge?resize(g.start,g.edge,dx,dy,area()):fit({...g.start,x:g.start.x+dx,y:g.start.y+dy},area());
   doc.body.classList.add('floating-interacting');g.entry.panel.classList.add('floating-gesture');paint(g.entry,g.entry.rect);
  }
  function keyboardAdjust(event,entry,edge){
   const directions={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]},direction=directions[event.key];if(!direction||event.altKey||event.ctrlKey||event.metaKey)return;
   event.preventDefault();event.stopPropagation();const r=entry.panel.getBoundingClientRect(),rect={x:r.left,y:r.top,width:r.width,height:r.height},step=event.shiftKey?1:10,dx=direction[0]*step,dy=direction[1]*step;
   entry.rect=edge?resize(rect,edge,dx,dy,area()):fit({...rect,x:rect.x+dx,y:rect.y+dy},area());focus(entry.id);paint(entry,entry.rect);save();
  }
  function attachHandle(handle,entry,edge){
   handle.addEventListener('pointerdown',event=>startGesture(event,entry,handle,edge));handle.addEventListener('pointermove',pointerMove);
   handle.addEventListener('pointerup',event=>{if(gesture?.pointerId===event.pointerId)stopGesture();});handle.addEventListener('pointercancel',()=>stopGesture(true));handle.addEventListener('lostpointercapture',()=>stopGesture(true));
   handle.addEventListener('keydown',event=>{if(event.target===handle)keyboardAdjust(event,entry,edge);});
  }
  function register({panel,launcher,host,width,label,closeButton}){
   if(!panel||!launcher||!host||entries.some(e=>e.id===panel.id))return;
   const entry={id:panel.id,panel,launcher,host,width,label,closeButton,rect:validRect(saved[panel.id])?{x:saved[panel.id].x,y:saved[panel.id].y,width:saved[panel.id].width,height:saved[panel.id].height}:null};entries.push(entry);panel.dataset.floatingWindow=panel.id;
   const header=panel.firstElementChild;header.classList.add('floating-draggable-header');header.tabIndex=0;header.setAttribute('aria-label',label+' 이동 영역');header.title='드래그하여 이동 · 방향키로 이동 (Shift: 1px)';
   const grip=doc.createElement('span');grip.className='floating-drag-grip';grip.textContent='⠿';grip.setAttribute('aria-hidden','true');header.prepend(grip);attachHandle(header,entry,null);
   const reset=doc.createElement('button');reset.type='button';reset.className='floating-placement-reset';reset.textContent='↺';reset.setAttribute('aria-label',label+' 위치·크기 초기화');reset.title='위치·크기 초기화';reset.disabled=!entry.rect;entry.reset=reset;header.insertBefore(reset,closeButton);
   reset.addEventListener('click',()=>{entry.rect=null;save();schedule();header.focus({preventScroll:true});});
   const names={n:'위',s:'아래',e:'오른쪽',w:'왼쪽',nw:'왼쪽 위',ne:'오른쪽 위',sw:'왼쪽 아래',se:'오른쪽 아래'};
   for(const [edge,name]of Object.entries(names)){const handle=doc.createElement('button');handle.type='button';handle.className='floating-resize-handle floating-resize-'+edge;handle.setAttribute('aria-label',label+' '+name+' 크기 조절');handle.title='드래그 또는 방향키로 크기 조절';panel.append(handle);attachHandle(handle,entry,edge);}
   launcher.title=label;panel.addEventListener('pointerdown',()=>focus(entry.id));panel.addEventListener('focusin',()=>{if(active!==entry.id)focus(entry.id);});
   let wasHidden=panel.hidden;const observer=new MutationObserver(()=>{if(!panel.hidden&&wasHidden)active=entry.id;wasHidden=panel.hidden;schedule();});observer.observe(panel,{attributes:true,attributeFilter:['hidden']});observer.observe(host,{attributes:true,attributeFilter:['hidden']});schedule();
  }
  win.PlantFloatingWindows={register,schedule,focus,isActive:panel=>active===panel.id};
  register({panel:doc.getElementById('archiveFloatingDock'),launcher:doc.getElementById('archiveDockToggle'),host:doc.getElementById('archiveInspectorHost'),width:460,label:'데이터 정보',closeButton:doc.getElementById('archiveDockClose')});
  register({panel:doc.getElementById('responseFloatingPanel'),launcher:doc.getElementById('responseInspectorToggle'),host:doc.getElementById('responseInspectorHost'),width:520,label:'요청·응답 정보',closeButton:doc.querySelector('.response-floating-close')});
  doc.addEventListener('keydown',event=>{if(event.key!=='Escape'||doc.querySelector('dialog[open]'))return;if(gesture){event.preventDefault();event.stopImmediatePropagation();stopGesture(true);return;}const entry=entries.find(e=>e.id===active&&!e.panel.hidden&&visible(e));if(!entry)return;event.preventDefault();event.stopImmediatePropagation();entry.closeButton?.click();},true);
  new MutationObserver(schedule).observe(doc.body,{attributes:true,attributeFilter:['class','data-test-mode','data-library-collection']});
  const header=doc.querySelector('body>header');if(header)new ResizeObserver(schedule).observe(header);win.addEventListener('resize',()=>{stopGesture(true);schedule();});win.addEventListener('blur',()=>stopGesture(true));schedule();
 }
 return {layout,bounds,fit,resize,mount};
});
