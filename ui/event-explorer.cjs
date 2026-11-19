'use strict';
const {createHash,randomBytes}=require('node:crypto');
const graphData=require('./event-network.cjs');
const key=(...values)=>createHash('sha256').update(JSON.stringify(values)).digest('hex').slice(0,32);
const makeView=()=>({nodes:[],edges:[],sources:{}});
function builder(namespace){
  const view=makeView(),nodes=new Map(),edges=new Set();
  function node(id,kind,label,extra={}){
    if(!nodes.has(id)){const n={id,kind,label,...extra};nodes.set(id,n);view.nodes.push(n);}
    return nodes.get(id);
  }
  function edge(a,b,type,origin,proof,reason,candidate=false){
    if(!proof.length)return;
    const identity=key(namespace,a,b,type);
    const id=key(identity,proof.map(p=>[p.source,p.start,p.quote]));
    if(edges.has(id))return;edges.add(id);
    view.edges.push({id,identity,a,b,type,origin,proof,reason,candidate});
  }
  return {view,node,edge};
}
function evidence(source,quote,start){
  if(!quote)return null;
  if(source.text.slice(start,start+quote.length)!==quote){
    start=source.text.indexOf(quote);
    if(start<0||source.text.indexOf(quote,start+1)>=0)return null;
  }
  return {source:source.id,revision:source.revision,start,end:start+quote.length,quote};
}
function personal(records){
  const {view,node,edge}=builder('personal'),events=[];
  for(const r of records.filter(r=>!r.deleted_at && !r.synthetic)){
    const src=view.sources[r.id]={id:r.id,title:r.title,revision:r.revision,text:r.body,recorded:r.created_at};
    const seen=new Map();
    for(const match of r.body.matchAll(/[^\n.!?。！？]+(?:[.!?。！？]+|$)?/gu)){
      const quote=match[0].trim();if(!quote)continue;
      const start=match.index+match[0].indexOf(quote),p=evidence(src,quote,start);
      const occurrence=seen.get(quote)||0;seen.set(quote,occurrence+1);
      const id='e-'+key(r.id,quote,occurrence);
      const eventLike=/회의|논의|수정|발표|여행|만났|참석|시연|방문|다녀|재검토|운동/.test(quote);
      const title=quote.length>56?quote.slice(0,55)+'…':quote;
      const explicit=quote.match(/(?:^|[^0-9])(20\d{2})[년./-]\s*(\d{1,2})[월./-]\s*(\d{1,2})(?:일|\b)/);
      const stamp=explicit && [explicit[1],explicit[2].padStart(2,'0'),explicit[3].padStart(2,'0')].join('-');
      const date=stamp && Number.isFinite(Date.parse(stamp)) && new Date(stamp).toISOString().startsWith(stamp)?stamp:'';
      const event=node(id,eventLike?'event':'claim',title,{proof:[p],date,dateKind:'사건일',recorded:r.date||r.created_at});
      const claim=node('c-'+key(id),'statement','원문 진술',{proof:[p]});
      edge(id,claim.id,'진술 출처','원문 명시',[p],'기록의 해당 문장에서 가져온 진술입니다.');
      const projects=[...quote.matchAll(/(?:[A-Za-z0-9가-힣_-]+\s*프로젝트|캡스톤)/g)].map(m=>m[0].trim());
      for(const name of projects){const project=node('project-'+key(name),'project',name);edge(id,project.id,'프로젝트 언급','원문 명시',[p],'원문에 같은 프로젝트 명칭이 있습니다.');}
      const person=quote.match(/(?:담당(?:자|은|는|이|가)?\s*[:：]?\s*)([가-힣]{2,4}?)(?:이고|이며|이야|입니다|[,.\s]|$)/)||quote.match(/(?:^|\s)([가-힣]{2,3})(?:와|과)\s/);
      if(person){const n=node('person-'+key(id,person[1]),'person',person[1]);edge(id,n.id,'인물 언급','원문 명시',[p],'이 문장에 등장하는 이름입니다. 동명이인을 자동 병합하지 않습니다.');}
      events.push({event,quote,projects,p});
    }
  }
  for(const row of events){
    const ref=row.quote.match(/(\d{1,2})일\s*(?:논의|회의|검토)(?:를|을)?\s*(?:바탕으로|이어서|토대로)/);
    if(!ref)continue;
    const same=events.filter(x=>x!==row && x.projects.some(p=>row.projects.includes(p)) && new RegExp('(?:^|[^0-9])'+ref[1]+'일\\s').test(x.quote) && !/(바탕으로|토대로|이어서)/.test(x.quote));
    if(same.length===1)edge(same[0].event.id,row.event.id,'후속 작업','규칙 추정',[same[0].p,row.p],'같은 프로젝트와 이전 논의 날짜를 명시한 표현입니다.',true);
  }
  return view;
}
function laboratory(raw,namespace){
  const {view,node,edge}=builder(namespace);
  for(const g of raw.graphs){
    const hub=node(g.id,'event',g.label||'사건',{description:g.description,proof:[]});
    const excerpts=new Map();
    for(const m of g.members){
      const srcKey=m.source+'@'+m.revision+(m.original?'':':'+m.id);
      const src=view.sources[srcKey] ||= {id:srcKey,revision:m.revision,title:m.title||m.source,text:m.original||m.text,partial:!m.original};
      const p=evidence(src,m.text,m.original?m.start:0);
      if(!p)continue;
      const n=node(m.id,'statement',m.text.slice(0,45),{proof:[p]});excerpts.set(m.id,{src,p});
      hub.proof.push(p);edge(hub.id,n.id,'사건 발췌','AI 추출',[p],'저장된 사건 색인에 속한 발췌입니다.');
      for(const e of m.entities||[]){if(!e.name||!p.quote.includes(e.name))continue;
        const kind=({person:'person',place:'place',project:'project'})[e.type];if(!kind)continue;
        const entity=node(kind+'-'+key(kind==='person'?g.id:'',e.name),kind,e.name);
        edge(hub.id,entity.id,'대상 언급','AI 추출',[p],'색인에서 추출한 이름을 원문에서 확인했습니다.');
      }
    }
    for(const l of g.links){const proof=(l.proof||[]).map(q=>{const u=excerpts.get(q.unit_id);return u&&evidence(u.src,q.quote,u.p.start+u.p.quote.indexOf(q.quote));}).filter(Boolean);
      if(proof.length===2)edge(l.from,l.to,'같은 사건 판정','AI 추출',proof,l.reason);
    }
  }
  return view;
}
function api(library,root){
 const db=library.db,token=randomBytes(24).toString('hex');
 db.exec('CREATE TABLE IF NOT EXISTS graph_reviews(seq INTEGER PRIMARY KEY, edge TEXT NOT NULL, identity TEXT NOT NULL, status TEXT NOT NULL, label TEXT NOT NULL, at TEXT NOT NULL); CREATE INDEX IF NOT EXISTS graph_review_edge ON graph_reviews(edge,seq)');
 async function current(mode,scope){
   if(mode==='personal')return {view:personal(library.read().records),scopes:[]};
   const data=await graphData(root),s=data.views.find(v=>v.id===scope)||data.views[0];
   return {view:s?laboratory(s,data.dataset):makeView(),scopes:data.views.map(v=>({id:v.id,label:v.context})),scope:s?.id};
 }
 return async(req,res,url)=>{
   const json=(code,body)=>{res.writeHead(code,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'});res.end(JSON.stringify(body));};
   const mode=url.searchParams.get('mode')||'personal';
   if(!['personal','lab'].includes(mode))return json(400,{error:'자료함을 확인하세요.'});
   const result=await current(mode,url.searchParams.get('scope'));
   const rows=db.prepare('SELECT * FROM graph_reviews WHERE edge=? ORDER BY seq');
   if(req.method==='GET'){
     for(const e of result.view.edges){e.history=rows.all(e.id);e.changed=!e.history.length && !!db.prepare('SELECT 1 FROM graph_reviews WHERE identity=? AND edge<>? LIMIT 1').get(e.identity,e.id);}
     return json(200,{...result,token});
   }
   if(req.method!=='POST'||req.headers['x-graph-token']!==token)return json(403,{error:'화면을 새로고침하세요.'});
   let body='';for await(const chunk of req){body+=chunk;if(body.length>4096)return json(413,{error:'입력 길이 초과'});}
   let input;try{input=JSON.parse(body)}catch{return json(400,{error:'잘못된 입력'})}
   const e=result.view.edges.find(e=>e.id===input?.edge);if(!e)return json(409,{error:'근거가 바뀌었습니다. 새로고침하세요.'});
   const history=rows.all(e.id),last=history.at(-1);
   if((last?.seq||0)!==input.revision)return json(409,{error:'검토 이력이 바뀌었습니다. 새로고침하세요.'});
   let {status,label}=input;
   if(status==='undo'){if(!last)return json(400,{error:'되돌릴 변경이 없습니다.'});const prior=history.at(-2);status=prior?.status||'미검토';label=prior?.label||e.type;}
   if(!['미검토','확인','거절','수정'].includes(status)||typeof label!=='string'||!label.trim()||label.length>60)return json(400,{error:'검토 내용을 확인하세요.'});
   db.prepare('INSERT INTO graph_reviews(edge,identity,status,label,at) VALUES(?,?,?,?,?)').run(e.id,e.identity,status,label.trim(),new Date().toISOString());
   json(200,{history:rows.all(e.id)});
 };
}
module.exports={api,personal,laboratory};
