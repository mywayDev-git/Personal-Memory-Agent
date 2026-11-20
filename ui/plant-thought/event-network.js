'use strict';
(()=>{
 const $=id=>document.getElementById(id), svg=$('egCanvas'),info=$('egInfo'),page=$('eventGraph');
 const colors={event:'#c8aff3',claim:'#edce91',statement:'#98d1b0',person:'#94c8ed',project:'#ebb292',place:'#9ed5d0'};
 const names={event:'사건',claim:'상태·주장',statement:'원문 진술',person:'인물',project:'프로젝트',place:'장소'};
 let sourceVisit=0;
 let data,root,selection,request=0,zoom=1,x=0,y=0,layer,drag,shown=[],expanded=new Map(),pos=new Map(),byId=new Map(),busy=false;
 const add=(p,t,text)=>{const a=document.createElement(t);a.textContent=text;p.append(a);return a};
 const button=(p,t,fn)=>{const b=add(p,'button',t);b.type='button';b.onclick=fn;return b};
 function shape(p,t,attrs){const a=document.createElementNS('http://www.w3.org/2000/svg',t);for(const [k,v]of Object.entries(attrs))a.setAttribute(k,v);p.append(a);return a}
 const latest=e=>e.history?.at(-1),label=e=>latest(e)?.label||e.type;
 const href=()=>'/api/event-explorer?'+new URLSearchParams({mode:$('egMode').value,scope:$('egScope').value});
 function active(e){const last=latest(e);return (!e.candidate||last?.status==='확인'||$('egCandidates').checked)&&
 (last?.status!=='거절'||$('egRejected').checked)&&(!$('egRelation').value||label(e)===$('egRelation').value);}
 const around=id=>data.view.edges.filter(e=>(e.a===id||e.b===id)&&active(e));
 async function source(p){
   const s=data.view.sources[p.source],dialog=$('egSource');dialog.querySelector('h2').textContent=s?.title||p.source;
   const body=dialog.querySelector('p');body.replaceChildren();const exact=s?.revision===p.revision && s.text.slice(p.start,p.end)===p.quote;
   dialog.querySelector('small').textContent='v'+p.revision+' · '+(exact?(s.partial?'저장된 발췌':'원문')+' · '+p.start+'–'+p.end:'원문 버전 또는 구간이 달라졌습니다');
   if(exact){body.append(s.text.slice(0,p.start));add(body,'mark',p.quote);body.append(s.text.slice(p.end));}else add(body,'blockquote',p.quote);
   dialog.showModal();body.querySelector('mark')?.scrollIntoView({block:'nearest'});
   if($('egMode').value==='personal'){
     const ticket=String(++sourceVisit);dialog.dataset.visit=ticket;
     try{const response=await fetch(href(),{cache:'no-store'});if(!response.ok)throw Error();
       const current=(await response.json()).view.sources[p.source];
       if(dialog.open && dialog.dataset.visit===ticket && current?.revision!==p.revision)dialog.querySelector('small').textContent+=' · '+(current?'현재 v'+current.revision+'으로 수정됨':'현재 자료함에서 삭제됨');
     }catch{if(dialog.open&&dialog.dataset.visit===ticket)dialog.querySelector('small').textContent+=' · 최신 버전 확인 실패';}
   }
 }
 $('egClose').onclick=()=>$('egSource').close();
 function proofs(rows){for(const p of rows||[]){add(info,'blockquote',p.quote);button(info,'원문 열기 · v'+p.revision,()=>source(p))}}
 function detail(item){
   selection=item;info.replaceChildren();if(!item)return;
   if(item.a){add(info,'small','연결 상세');add(info,'h2',label(item));
     add(info,'p',byId.get(item.a).label+' → '+byId.get(item.b).label);
     add(info,'small',item.origin+' · '+(latest(item)?.status||'미검토')+(item.changed?' · 새 근거 재검토':''));
     add(info,'p',item.reason);proofs(item.proof);
     const actions=add(info,'div','');actions.className='eg-actions';
     for(const [title,status] of [['확인','확인'],['연결 거절','거절']])button(actions,title,()=>review(item,status,label(item)));
     if(item.history?.length)button(actions,'되돌리기',()=>review(item,'undo',item.type));
     const form=add(info,'details','');add(form,'summary','관계 유형 수정');const input=add(form,'input','');input.value=label(item);input.maxLength=60;input.setAttribute('aria-label','관계 이름');button(form,'수정 저장',()=>review(item,'수정',input.value));
     if(item.history?.length){const log=add(info,'details','');add(log,'summary','검토 이력 '+item.history.length+'건');for(const row of item.history.slice().reverse())add(log,'p',row.at.slice(0,10)+' · '+row.status+' · '+row.label);}
   }else{add(info,'small',names[item.kind]);add(info,'h2',item.label);if(item.description)add(info,'p',item.description);
     const incident=around(item.id),hidden=incident.filter(e=>!shown.includes(e.a)||!shown.includes(e.b)).length;
     if(hidden)button(info,'주변 펼치기 · 추가 연결 '+hidden+'개',()=>{expanded.set(item.id,(expanded.get(item.id)||0)+24);draw()});
     for(const e of incident){button(info,label(e)+' · '+byId.get(e.a===item.id?e.b:e.a).label,()=>detail(e))}
     if(item.proof?.length)add(info,'h3','원문 근거');proofs(item.proof);
   }
   svg.querySelectorAll('[data-id]').forEach(n=>n.setAttribute('aria-pressed',String(n.dataset.id===item.id)));
 }
 async function review(e,status,name){if(busy||!name.trim())return;busy=true;
   try{const response=await fetch(href(),{method:'POST',headers:{'Content-Type':'application/json','X-Graph-Token':data.token},body:JSON.stringify({edge:e.id,status,label:name,revision:latest(e)?.seq||0,storage_epoch:window.PlantLibraryPersistence?.epoch?.()})});
   const d=await response.json();if(!response.ok)throw Error(d.error);e.history=d.history;filters();draw();detail(e);
   }catch(err){$('egStatus').textContent=err.message}finally{busy=false}}
 function filters(){const sel=$('egRelation'),prev=sel.value;sel.replaceChildren(new Option('모든 관계',''),...Array.from(new Set(data.view.edges.map(label))).sort().map(t=>new Option(t,t)));sel.value=prev;if(sel.selectedIndex<0)sel.selectedIndex=0}
 function enter(id){root=id;expanded=new Map([[id,24]]);pos.clear();zoom=1;x=0;y=0;selection=byId.get(id);list(false);draw()}
 function list(recenter=true){
   const target=$('egResults');target.replaceChildren();const q=$('egQuery').value.trim().toLowerCase(),from=$('egFrom').value,to=$('egTo').value;
   const rows=data.view.nodes.filter(n=>['claim','event'].includes(n.kind)&&(!from||n.date>=from)&&(!to||n.date&&n.date<=to)&&[n.label,n.description,...(n.proof||[]).map(p=>p.quote)].join(' ').toLowerCase().includes(q)).sort((a,b)=>(b.date||'').localeCompare(a.date||''));
   for(const n of rows){const b=button(target,n.label,()=>enter(n.id));b.setAttribute('aria-current',String(root===n.id))}
   if(!rows.length)add(target,'p','조건에 맞는 기억이 없습니다.');
   if(recenter&&!rows.some(n=>n.id===root))enter(rows[0]?.id);
 }
 function camera(){layer?.setAttribute('transform','translate('+x+' '+y+') scale('+zoom+')')}
 function point(e){return new DOMPoint(e.clientX,e.clientY).matrixTransform(svg.getScreenCTM().inverse())}
 function magnify(f,p={x:400,y:270}){const z=Math.max(.3,Math.min(5,zoom*f));x=p.x-(p.x-x)*z/zoom;y=p.y-(p.y-y)*z/zoom;zoom=z;camera()}
 function draw(){
   svg.replaceChildren();layer=shape(svg,'g',{});camera();const visible=new Set(root?[root]:[]);
   for(const [id,limit]of expanded){if(!visible.has(id))continue;const links=around(id).sort((a,b)=>Number(byId.get(a.b)?.kind==='statement')-Number(byId.get(b.b)?.kind==='statement'));for(const e of links.slice(0,limit)){visible.add(e.a);visible.add(e.b)}}
   shown=[...visible];const edges=data.view.edges.filter(e=>active(e)&&visible.has(e.a)&&visible.has(e.b));
   if(root&&!pos.has(root))pos.set(root,{x:400,y:255});
   for(const [i,id]of shown.entries()){if(pos.has(id))continue;const angle=(i-1)*2.4-.6,r=100+18*Math.sqrt(i);pos.set(id,{x:400+Math.cos(angle)*r,y:255+Math.sin(angle)*r})}
   const redraw=[];for(const e of edges){
     const g=shape(layer,'g',{class:'eg-wire',role:'button',tabindex:0,'aria-label':label(e),'data-id':e.id});
     const stroke=shape(g,'line',{stroke:e.candidate?'#d8b187':'#a397bc','stroke-width':2,'stroke-dasharray':e.candidate?'5 4':'none'});
     const caption=shape(g,'text',{'font-size':10,fill:'#dad5e3','text-anchor':'middle','paint-order':'stroke',stroke:'#292a35','stroke-width':3});caption.textContent=(e.type==='후속 작업'?'→ ':'')+label(e);
     const hit=shape(g,'line',{stroke:'transparent','stroke-width':16});const title=shape(g,'title',{});title.textContent=label(e);
     redraw.push(()=>{const a=pos.get(e.a),b=pos.get(e.b);caption.setAttribute('x',(a.x+b.x)/2);caption.setAttribute('y',(a.y+b.y)/2-4);for(const l of [hit,stroke])for(const [k,v]of Object.entries({x1:a.x,y1:a.y,x2:b.x,y2:b.y}))l.setAttribute(k,v)});
     g.onpointerdown=ev=>ev.stopPropagation();g.onclick=()=>detail(e);g.onkeydown=ev=>{if(['Enter',' '].includes(ev.key)){ev.preventDefault();detail(e)}};
   }
   for(const id of shown){const n=byId.get(id),g=shape(layer,'g',{class:'eg-node',role:'button',tabindex:0,'data-id':id,'aria-label':names[n.kind]+' '+n.label});
     shape(g,'circle',{r:id===root?10:7,fill:colors[n.kind]});const t=shape(g,'text',{x:13,y:4});t.textContent=n.label.length>17?n.label.slice(0,16)+'…':n.label;
     shape(g,'title',{}).textContent=names[n.kind]+' · '+n.label;
     redraw.push(()=>g.setAttribute('transform','translate('+pos.get(id).x+' '+pos.get(id).y+')'));
     g.onpointerdown=ev=>{ev.stopPropagation();start(ev,id)};g.onkeydown=ev=>{if(['Enter',' '].includes(ev.key)){ev.preventDefault();detail(n)}};
   }
   update=()=>redraw.forEach(fn=>fn());update();
   const timeline=$('egTime');timeline.replaceChildren();add(timeline,'strong','시간순 기록');for(const n of shown.map(id=>byId.get(id)).filter(n=>['event','claim'].includes(n.kind)).sort((a,b)=>(a.date||'9999').localeCompare(b.date||'9999')))button(timeline,(n.date?n.date+' '+n.dateKind:'날짜 미확인')+' · '+n.label.slice(0,22),()=>detail(n));
   $('egStatus').textContent='표시 '+shown.length+'개 · 연결 '+edges.length+'개';detail(selection||byId.get(root));
 }
 let update=()=>{};
 function start(e,id){if(e.button!==0)return;const p=point(e);drag={id,p,start:p};svg.setPointerCapture(e.pointerId)}
 svg.onpointerdown=e=>start(e,null);svg.onpointermove=e=>{if(!drag)return;const p=point(e),dx=p.x-drag.p.x,dy=p.y-drag.p.y;drag.p=p;if(drag.id){const n=pos.get(drag.id);n.x+=dx/zoom;n.y+=dy/zoom;update()}else{x+=dx;y+=dy;camera()}};
 svg.onpointerup=()=>{if(drag?.id&&Math.hypot(drag.p.x-drag.start.x,drag.p.y-drag.start.y)<5)detail(byId.get(drag.id));drag=null};svg.onpointercancel=()=>drag=null;
 svg.addEventListener('wheel',e=>{e.preventDefault();magnify(e.deltaY<0?1.12:.89,point(e))},{passive:false});
 $('egPlus').onclick=()=>magnify(1.25);$('egMinus').onclick=()=>magnify(.8);$('egReset').onclick=()=>{zoom=1;x=0;y=0;camera()};
 async function load(reset=false){const id=++request;$('egStatus').textContent='기억을 읽는 중…';try{const response=await fetch(href(),{cache:'no-store'});if(!response.ok)throw Error();const result=await response.json();if(request!==id)return;
   data=result;byId=new Map(data.view.nodes.map(n=>[n.id,n]));const scope=$('egScope');scope.hidden=$('egMode').value!=='lab';scope.replaceChildren(...data.scopes.map(s=>new Option(s.label,s.id)));if(data.scope)scope.value=data.scope;
   filters();if(reset||!byId.has(root)){root=null;selection=null;expanded.clear();pos.clear()}else selection=byId.get(root);
   list();draw();
 }catch{if(request===id)$('egStatus').textContent='기억을 불러오지 못했습니다. 새로고침해 주세요.'}}
 for(const id of ['egQuery','egFrom','egTo'])$(id).oninput=()=>data&&list();
 for(const id of ['egRelation','egCandidates','egRejected'])$(id).onchange=()=>data&&draw();
 $('egMode').onchange=()=>{$('egScope').replaceChildren();load(true)};$('egScope').onchange=()=>load(true);$('egRefresh').onclick=()=>load();
 const check=()=>{if(page.classList.contains('active')&&!data)load(true)};new MutationObserver(check).observe(page,{attributes:true,attributeFilter:['class']});check();
})();
