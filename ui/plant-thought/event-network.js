'use strict';
(()=>{
 const el=id=>document.getElementById(id),svg=el('egCanvas'),info=el('egInfo'),scope=el('egScope'),query=el('egQuery');
 const colors={event:'#c3a4ef',excerpt:'#98c7a9',source:'#e5b97c'},names={event:'사건',excerpt:'발췌',source:'출처'};
 let data,loading=false,nodes=[],edges=[],selected,hover,layer,frame,drag,scale=1,tx=0,ty=0;
 const tag=(name,attrs,parent)=>{const item=document.createElementNS('http://www.w3.org/2000/svg',name);for(const [k,v] of Object.entries(attrs))item.setAttribute(k,v);parent.append(item);return item};
 const line=(name,text)=>{const e=document.createElement(name);e.textContent=text;info.append(e);return e};
 const shorten=(s,n=19)=>s.length>n?s.slice(0,n)+'…':s;
 function detail(node){
   selected=node;info.replaceChildren();if(!node){line('p','조건에 맞는 사건이 없습니다.');return}
   line('small',names[node.kind]);line('h2',node.label);if(node.text)line('p',node.text);
   const related=edges.filter(e=>e.a===node||e.b===node);
   if(related.length)line('h3','직접 연결');
   for(const edge of related){const other=edge.a===node?edge.b:edge.a;
     const button=line('button',other.label+' · '+({member:'사건에 속한 발췌',source:'발췌의 출처',proof:'같은 사건으로 판정'})[edge.kind]);button.onclick=()=>detail(other);}
   const proofs=node.group?.links||related.filter(e=>e.proof).map(e=>e.proof);
   if(proofs.length)line('h3','연결 판정 근거');
   for(const proof of proofs){line('small',({explicit_reference:'명시적 참조',same_identifier:'같은 식별자'})[proof.reason]||proof.reason);for(const p of proof.proof||[])line('blockquote',p.quote);}
   highlight();
 }
 function highlight(){const focus=hover||selected,near=new Set([focus]);for(const e of edges){const active=e.a===focus||e.b===focus;if(active){near.add(e.a);near.add(e.b)}e.shape.style.opacity=!focus||active?'1':'.34'}
   for(const n of nodes){n.shape.style.opacity=!hover||near.has(n)?'1':'.28';n.shape.setAttribute('aria-pressed',String(n===selected));n.caption.style.display=n.kind==='event'||n===focus?'':'none'}}
 function camera(){layer?.setAttribute('transform','translate('+tx+' '+ty+') scale('+scale+')')}
 function zoom(f,x=400,y=270){const next=Math.max(.22,Math.min(5,scale*f));tx=x-(x-tx)*next/scale;ty=y-(y-ty)*next/scale;scale=next;camera()}
 function point(e){return new DOMPoint(e.clientX,e.clientY).matrixTransform(svg.getScreenCTM().inverse())}
 function fit(){if(!nodes.length)return;const xs=nodes.map(n=>n.x),ys=nodes.map(n=>n.y),x=Math.min(...xs),y=Math.min(...ys),w=Math.max(...xs)-x,h=Math.max(...ys)-y;scale=Math.min(1.5,700/(w+80),435/(h+52));tx=400-(x+w/2)*scale;ty=255-(y+h/2)*scale;camera()}
 function render(){
   cancelAnimationFrame(frame);drag=null;hover=null;selected=null;svg.replaceChildren();layer=tag('g',{},svg);nodes=[];edges=[];const byId=new Map(),view=data?.views[Number(scope.value)||0];
   const term=query.value.trim().toLocaleLowerCase();const graphs=(view?.graphs||[]).filter(g=>!term||[g.label,g.description,...g.members.map(m=>m.text)].join(' ').toLocaleLowerCase().includes(term));
   function node(id,kind,label,text,x,y,group){if(!byId.has(id)){const n={id,kind,label,text,x,y,vx:0,vy:0,group};byId.set(id,n);nodes.push(n)}return byId.get(id)}
   function edge(a,b,kind,proof){if(a&&b)edges.push({a,b,kind,proof})}
   for(const [i,g] of graphs.entries()){
     const angle=i*2.4,r=Math.sqrt(i)*55,x=400+Math.cos(angle)*r,y=255+Math.sin(angle)*r;
     const hub=node(g.id,'event',g.label||'사건',g.description,x,y,g);
     for(const [j,m] of g.members.entries()){const a=j*2.4+i,ex=node(m.id,'excerpt',shorten(m.text||m.id),m.text,x+Math.cos(a)*48,y+Math.sin(a)*48);
       edge(hub,ex,'member');edge(ex,node('src:'+m.source,'source',m.source,'같은 출처의 발췌를 함께 표시합니다.',ex.x+26,ex.y+22),'source');}
     for(const link of g.links)edge(byId.get(link.from),byId.get(link.to),'proof',link);
   }
   for(const e of edges)e.shape=tag('line',{class:'eg-edge '+e.kind},layer);
   for(const n of nodes){const degree=edges.filter(e=>e.a===n||e.b===n).length;
     n.shape=tag('g',{class:'eg-node',tabindex:0,role:'button','aria-label':names[n.kind]+' '+n.label},layer);
     tag('circle',{r:(n.kind==='event'?7:4)+Math.min(6,Math.sqrt(degree)),fill:colors[n.kind]},n.shape);
     n.caption=tag('text',{x:12,y:4},n.shape);n.caption.textContent=shorten(n.label);
     n.shape.onpointerenter=()=>{hover=n;highlight()};n.shape.onpointerleave=()=>{hover=null;highlight()};
     n.shape.onkeydown=e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();detail(n)}};
     n.shape.onpointerdown=e=>begin(e,n);
   }
   const draw=()=>{for(const n of nodes)n.shape.setAttribute('transform','translate('+n.x+' '+n.y+')');for(const e of edges)for(const [key,v]of Object.entries({x1:e.a.x,y1:e.a.y,x2:e.b.x,y2:e.b.y}))e.shape.setAttribute(key,v)};
   let tick=0;
   function settle(){for(let i=0;i<nodes.length;i++){const a=nodes[i];for(let j=i+1;j<nodes.length;j++){const b=nodes[j],dx=a.x-b.x||.1,dy=a.y-b.y||.1,d=Math.max(10,Math.hypot(dx,dy));if(d>140)continue;const f=80/(d*d);a.vx+=dx*f/d;a.vy+=dy*f/d;b.vx-=dx*f/d;b.vy-=dy*f/d}}
     for(const {a,b} of edges){const dx=b.x-a.x,dy=b.y-a.y,d=Math.hypot(dx,dy)||1,f=(d-58)*.016/d;a.vx+=dx*f;a.vy+=dy*f;b.vx-=dx*f;b.vy-=dy*f}
     for(const n of nodes){n.x+=n.vx*=.8;n.y+=n.vy*=.8}}
   draw();fit();detail(nodes.find(n=>n.group?.links.length)||nodes[0]);
   el('egStatus').textContent=data?.views.length?data.dataset+' · 사건 '+graphs.length+'개 · 발췌 간 판정 연결 '+edges.filter(e=>e.kind==='proof').length+'개':'저장된 사건 연결 색인이 없습니다.';
   if(nodes.length<450){if(matchMedia('(prefers-reduced-motion: reduce)').matches){for(let i=0;i<35;i++)settle();draw();fit()}else{const animate=()=>{settle();draw();if(++tick<95)frame=requestAnimationFrame(animate)};frame=requestAnimationFrame(animate)}}
 }
 function begin(e,node){if(e.button!==0)return;e.stopPropagation();cancelAnimationFrame(frame);const p=point(e);drag={node,start:p,last:p};svg.setPointerCapture(e.pointerId)}
 svg.onpointerdown=e=>begin(e,null);
 svg.onpointermove=e=>{if(!drag)return;const p=point(e),dx=p.x-drag.last.x,dy=p.y-drag.last.y,n=drag.node;drag.last=p;
 if(n){n.x+=dx/scale;n.y+=dy/scale;n.shape.setAttribute('transform','translate('+n.x+' '+n.y+')');for(const edge of edges){const side=edge.a===n?'1':edge.b===n?'2':null;if(side){edge.shape.setAttribute('x'+side,n.x);edge.shape.setAttribute('y'+side,n.y)}}}
 else{tx+=dx;ty+=dy;camera()}};
 svg.onpointerup=e=>{if(drag?.node&&Math.hypot(drag.last.x-drag.start.x,drag.last.y-drag.start.y)<5)detail(drag.node);drag=null};svg.onpointercancel=()=>{drag=null};
 svg.addEventListener('wheel',e=>{e.preventDefault();const p=point(e);zoom(e.deltaY<0?1.14:1/1.14,p.x,p.y)},{passive:false});
 el('egPlus').onclick=()=>zoom(1.3);el('egMinus').onclick=()=>zoom(1/1.3);el('egReset').onclick=fit;query.oninput=render;scope.onchange=render;
 async function load(){if(loading)return;loading=true;el('egStatus').textContent='저장된 사건 연결을 읽고 있습니다…';try{
 const r=await fetch('/api/event-network',{cache:'no-store'});if(!r.ok)throw Error();data=await r.json();scope.replaceChildren(...data.views.map((v,i)=>new Option(v.context+' · 사건 '+v.graphs.length+'개',i)));render()
 }catch{el('egStatus').textContent='사건 그래프를 불러오지 못했습니다. AI 연결 화면에서 다시 시도하세요.'}finally{loading=false}}
 el('egRefresh').onclick=load;const page=el('eventGraph');const enter=()=>{if(page.classList.contains('active')&&!data)load()};new MutationObserver(enter).observe(page,{attributes:true,attributeFilter:['class']});enter();
})();
