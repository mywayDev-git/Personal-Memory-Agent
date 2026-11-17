'use strict';

window.EventGraphViewer=(()=>{
 const viewers=new WeakMap();
 const reasons={
  shared_identifier:'공통 식별번호',
  explicit_reference:'기록 간 명시적 참조',
  matching_event_scope:'같은 사건 범위로 판단'
 };
 const claimTypes={hypothesis:'가설·추정',proposal:'제안·추천',observation:'관측·측정',
  plan:'계획',execution:'실행·진행',cancellation:'취소',assertion:'기록의 주장'};
 const claimTitle=claim=>[claim.subject,claim.predicate,claim.object].join(' ');

 function panel(stage){
  const ref=stage?.event_graph_index,trace=stage?.event_graph_search;
  if(!stage?.artifact_id||!ref?.artifact_id&&!trace?.ranked_graphs)return '';
  const count=ref?.count??trace.ranked_graphs.length;
  return `<details class="event-graph-viewer" data-graph-index="${esc(ref?.artifact_id)}" data-graph-stage="${esc(stage.artifact_id)}">
   <summary>사건 그래프 보기 <span>${count}개${ref?.artifact_id?'':' · 검색 기록'}</span></summary>
   <div data-event-viewer-body><p class="hint">저장된 그래프를 불러오는 중입니다.</p></div>
  </details>`;
 }

 function graphName(graph){
  return graph.events?.join(' · ')||graph.description.split('\n')[0];
 }

 function sourceRecord(state,unitId){
  return state.sources.get(unitId.split(':')[0]);
 }

 async function getUnit(state,unitId){
  if(!state.units.has(unitId)){
   const ref=state.indexes.get(unitId.split(':')[0]);
   if(ref){
    const index=await artifact(ref);
    for(const unit of index.units)state.units.set(unit.id,unit);
   }
  }
  return state.units.get(unitId);
 }

 function draw(state,graph){
  const positions=graph.members.map((member,i)=>({id:member.unit_id,y:36+i*66,index:i+1}));
  const byId=new Map(positions.map(position=>[position.id,position]));
  const height=Math.max(124,positions.length*66+10),middle=height/2;
  const spokes=positions.map(p=>`<path class="graph-membership" d="M 195 ${middle} C 260 ${middle}, 290 ${p.y}, 366 ${p.y}"/>`).join('');
  const edges=(graph.links||[]).flatMap(link=>{
   const a=byId.get(link.from),b=byId.get(link.to);
   return a&&b?[`<path class="graph-proof-edge" d="M 366 ${a.y} C 275 ${a.y}, 275 ${b.y}, 366 ${b.y}"/>`]:[];
  }).join('');
  const nodes=positions.map(p=>{
   const label=sourceRecord(state,p.id)?.source_id||'발췌 출처';
   const short=label.length>27?label.slice(0,24)+'…':label;
   return `<g class="graph-excerpt-node" data-event-node="${esc(p.id)}" role="button" tabindex="0" aria-pressed="false" aria-label="발췌 ${p.index}, ${esc(label)}">
    <title>${esc(label)}</title><rect x="366" y="${p.y-24}" width="210" height="48" rx="8"/>
    <text x="380" y="${p.y-3}" class="graph-node-name">발췌 ${p.index}</text>
    <text x="380" y="${p.y+13}" class="graph-node-caption">${esc(short)}</text></g>`;
  }).join('');
  return `<div class="event-graph-canvas"><svg viewBox="0 0 602 ${height}" aria-label="사건과 발췌문 연결" role="group">
   ${spokes}${edges}<g class="graph-hub"><rect x="20" y="${middle-28}" width="175" height="56" rx="9"/>
   <text x="37" y="${middle-4}" class="graph-node-name">사건 그래프</text>
   <text x="37" y="${middle+15}" class="graph-node-caption">발췌문 ${positions.length}개</text></g>${nodes}
  </svg></div><p class="graph-legend"><span>실선 · 그래프에 포함된 발췌</span>${edges?'<span>점선 · 근거가 기록된 발췌 간 연결</span>':''}</p>`;
 }

 function drawClaims(graph){
  const claims=graph.claims,positions=new Map(graph.members.map((member,i)=>[member.unit_id,36+i*66]));
  const height=Math.max(124,claims.length*66+10,positions.size*66+10),middle=height/2;
  const attached=new Set(claims.map(claim=>claim.evidence.unit_id));
  const connection=(x,y,target,end)=>`<path class="graph-membership" d="M ${x} ${y} C ${x+20} ${y}, ${target-20} ${end}, ${target} ${end}"/>`;
  const nodes=claims.map((claim,i)=>{
   const y=36+i*66,title=claimTitle(claim);
   return connection(195,middle,252,y)+connection(482,y,552,positions.get(claim.evidence.unit_id))+
    `<g class="graph-excerpt-node" data-event-node="${esc(claim.evidence.unit_id)}" role="button" tabindex="0" aria-pressed="false" aria-label="${esc(title)}">
    <title>${esc(title)}</title><rect x="252" y="${y-24}" width="230" height="48" rx="8"/>
    <text x="266" y="${y-3}" class="graph-node-name">Claim ${i+1} · ${esc(claimTypes[claim.type])}</text>
    <text x="266" y="${y+13}" class="graph-node-caption">${esc(title.length>27?title.slice(0,26)+'…':title)}</text></g>`;
  }).join('');
  const excerpts=graph.members.map((member,i)=>{
   const id=member.unit_id,y=positions.get(id);
   return (attached.has(id)?'':connection(195,middle,552,y))+
    `<g class="graph-excerpt-node" data-event-node="${esc(id)}" role="button" tabindex="0" aria-pressed="false" aria-label="발췌 ${i+1}">
    <rect x="552" y="${y-24}" width="130" height="48" rx="8"/>
    <text x="568" y="${y+4}" class="graph-node-name">발췌 ${i+1}</text></g>`;
  }).join('');
  return `<div class="event-graph-canvas"><svg viewBox="0 0 706 ${height}" aria-label="사건에서 Claim을 거쳐 근거 발췌까지" role="group">
   <g class="graph-hub"><rect x="20" y="${middle-28}" width="175" height="56" rx="9"/>
   <text x="37" y="${middle-4}" class="graph-node-name">사건 그래프</text>
   <text x="37" y="${middle+15}" class="graph-node-caption">Claim ${claims.length}개</text></g>${nodes}${excerpts}</svg></div>`;
 }

 function claimsHTML(graph){
  if(!Array.isArray(graph.claims))return '';
  if(!graph.claims.length)return '<p class="hint">이 사건에서 검증된 관계 구절을 찾지 못했습니다. 연결된 발췌문을 조회할 수 있습니다.</p>';
  return `<details class="event-link-proofs" open><summary>Claim별 근거 <span>${graph.claims.length}건</span></summary>`+
   graph.claims.map(claim=>{
    const e=claim.evidence,p=e.original_span;
    const position=p?`원문 위치 [${p.start}, ${p.end})`:`발췌 색인 위치 [${e.excerpt_start}, ${e.excerpt_end})`;
    const details=[claim.speaker&&'발화자 '+claim.speaker,claim.event_time&&'사건 시각 '+claim.event_time,
     claim.recorded_at&&'기록 시각 '+claim.recorded_at,claim.valid_time&&(claim.valid_time.from||claim.valid_time.to)&&
      '유효기간 '+(claim.valid_time.from||'미상')+' ~ '+(claim.valid_time.to||'미상')].filter(Boolean).join(' · ');
    return `<article><strong>${esc(claimTitle(claim))}</strong> <span class="graph-link-reason">${esc(claimTypes[claim.type])}</span>
     ${details?'<p class="hint">'+esc(details)+'</p>':''}
     <blockquote><small>${esc(e.source_id+' · 버전 '+e.revision+' · '+position)}</small><br>${esc(e.quote)}</blockquote></article>`;
   }).join('')+'</details>';
 }

 function linksHTML(graph){
  const links=graph.links||[];
  if(!links.length)return '';
  const memberNumber=new Map(graph.members.map((member,i)=>[member.unit_id,i+1]));
  return `<details class="event-link-proofs" open><summary>발췌 간 연결 근거 <span>${links.length}건</span></summary>${links.map(link=>
   `<article><strong>발췌 ${memberNumber.get(link.from)} ↔ 발췌 ${memberNumber.get(link.to)}</strong>
    <span class="graph-link-reason">${esc(reasons[link.reason]||link.reason)}</span>
    ${(link.proof||[]).map(proof=>`<blockquote><small>발췌 ${memberNumber.get(proof.unit_id)} · ${esc(proof.sentence_id)}</small><br>${esc(proof.quote)}</blockquote>`).join('')}
   </article>`).join('')}</details>`;
 }

 async function showUnit(state,unitId){
  state.activeUnit=unitId;
  const detail=state.body.querySelector('[data-event-excerpt]');
  for(const node of state.body.querySelectorAll('[data-event-node]'))node.setAttribute('aria-pressed',String(node.dataset.eventNode===unitId));
  detail.innerHTML='<p class="hint">발췌문을 불러오는 중입니다.</p>';
  try{
   const unit=await getUnit(state,unitId);
   if(state.activeUnit!==unitId||!detail.isConnected)return;
   if(!unit){detail.textContent='저장된 발췌문을 찾을 수 없습니다.';return;}
   const record=sourceRecord(state,unitId),timestamp=unit.timestamp||record?.timestamp;
   detail.innerHTML=`<strong>원문 발췌</strong><p class="hint">출처 ${esc(unit.source_id||record?.source_id)} · 버전 ${esc(unit.revision??unit.source_revision??record?.revision)}${timestamp?' · '+esc(timestamp):''}</p>
    <blockquote>${esc(unit.text)}</blockquote>`;
  }catch(error){
   if(state.activeUnit===unitId&&detail.isConnected)detail.textContent=error.message;
  }
 }

 function showGraph(state,graph){
  state.activeGraph=graph.id;
  state.activeUnit=null;
  const view=state.body.querySelector('[data-event-graph-detail]');
  const rank=state.ranks.get(graph.id),selected=state.selected.has(graph.id);
  view.innerHTML=`<div class="event-graph-heading"><strong>${esc(graphName(graph))}</strong>
   <span>${rank?`검색 ${rank}위 · `:''}${selected?'검색에서 선택됨':state.fallback===graph.id?'직접 검색으로 보완':'저장된 그래프'}</span></div>
   <p class="event-graph-description">${esc(graph.description)}</p>${graph.claims?.length?drawClaims(graph):draw(state,graph)}
   <p class="hint">그래프에서 발췌 노드를 선택하면 해당 원문 구절을 볼 수 있습니다.</p>
   <section class="event-excerpt-detail" data-event-excerpt aria-live="polite"></section>${claimsHTML(graph)}${linksHTML(graph)}`;
  if(graph.members[0])showUnit(state,graph.members[0].unit_id);
 }

 function showList(state){
  const query=state.body.querySelector('[data-event-graph-query]').value.trim().toLocaleLowerCase();
  const onlyLinked=state.body.querySelector('[data-event-graph-linked]').checked;
  const matches=state.graphs.filter(graph=>(!onlyLinked||graph.members.length>1)&&
   (!query||[graph.description,graph.id,graph.source_id,...(graph.source_refs||[]).map(ref=>ref.source_id),...(graph.claims||[]).map(claimTitle)]
    .some(text=>text?.toLocaleLowerCase().includes(query))));
  const list=state.body.querySelector('[data-event-graph-list]');
  list.innerHTML=matches.map(graph=>{
   const rank=state.ranks.get(graph.id);
   const label=[rank?`${rank}위`:null,graphName(graph),`발췌 ${graph.members.length}개`,
    graph.claims&&'Claim '+graph.claims.length+'개'].filter(Boolean).join(' · ');
   return `<option value="${esc(graph.id)}">${esc(label)}</option>`;
  }).join('');
  state.body.querySelector('[data-event-graph-count]').textContent=`${matches.length}/${state.graphs.length}개 그래프`;
  const active=matches.find(graph=>graph.id===state.activeGraph)||matches[0];
  if(active){
   list.value=active.id;
   if(active.id!==state.activeGraph)showGraph(state,active);
  }else{
   state.activeGraph=null;state.activeUnit=null;
   state.body.querySelector('[data-event-graph-detail]').innerHTML='<p class="empty">조건에 맞는 사건 그래프가 없습니다.</p>';
  }
 }

 async function open(panelElement){
  if(viewers.has(panelElement))return;
  const body=panelElement.querySelector('[data-event-viewer-body]');
  const state={body};
  viewers.set(panelElement,state);
  try{
   const [index,stage]=await Promise.all([
    panelElement.dataset.graphIndex?artifact(panelElement.dataset.graphIndex):null,
    artifact(panelElement.dataset.graphStage)
   ]);
   const trace=stage.event_graph_search,ranked=trace?.ranked_graphs||[];
   state.ranks=new Map(ranked.map((graph,i)=>[graph.id,i+1]));
   state.selected=new Set(trace?.selected_graph_ids||[]);
   state.fallback=trace?.fallback?.graph_id;
   state.units=new Map((stage.index_units||[]).map(unit=>[unit.id,unit]));
   state.sources=new Map((stage.summary_records||stage.records||[]).map(record=>[record.summary_id,record]));
   state.indexes=new Map((stage.structured_indexes||[]).map(ref=>[ref.summary_id,ref.index_id]));
   state.graphs=[...(index?.graphs||ranked)].sort((a,b)=>
    (state.ranks.get(a.id)??Infinity)-(state.ranks.get(b.id)??Infinity)||a.id.localeCompare(b.id));
   const linked=state.graphs.some(graph=>graph.members.length>1)&&!state.graphs.some(graph=>Array.isArray(graph.claims));
   body.innerHTML=`<div class="event-graph-layout"><div class="event-graph-picker">
    <label>그래프 설명·출처 검색<input type="search" data-event-graph-query></label>
    <label class="inline"><input type="checkbox" data-event-graph-linked${linked?' checked':''}> 연결된 발췌가 여러 개인 그래프</label>
    <p class="hint" data-event-graph-count role="status"></p>
    <label>사건 선택<select data-event-graph-list size="8"></select></label>
    </div><div class="event-graph-detail" data-event-graph-detail></div></div>`;
   body.querySelector('[data-event-graph-query]').addEventListener('input',()=>showList(state));
   body.querySelector('[data-event-graph-linked]').addEventListener('change',()=>showList(state));
   body.querySelector('[data-event-graph-list]').addEventListener('change',event=>{
    const graph=state.graphs.find(item=>item.id===event.target.value);
    if(graph)showGraph(state,graph);
   });
   body.addEventListener('click',event=>{
    const node=event.target.closest('[data-event-node]');
    if(node)showUnit(state,node.dataset.eventNode);
   });
   body.addEventListener('keydown',event=>{
    const node=event.target.closest('[data-event-node]');
    if(node&&['Enter',' '].includes(event.key)){event.preventDefault();showUnit(state,node.dataset.eventNode);}
   });
   showList(state);
  }catch(error){
   body.textContent='사건 그래프를 불러올 수 없습니다. '+error.message;
   viewers.delete(panelElement);
  }
 }

 document.addEventListener('toggle',event=>{
  if(event.target.open&&event.target.classList.contains('event-graph-viewer'))open(event.target);
 },true);

 return {panel};
})();
