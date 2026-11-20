'use strict';
const {DatabaseSync}=require('node:sqlite');
const fs=require('node:fs'),path=require('node:path');
const {Worker,isMainThread,parentPort,workerData}=require('node:worker_threads');
const {createHash}=require('node:crypto');

function load(root) {
  const base=path.join(root,'.local','baseline');
  if(!fs.existsSync(path.join(base,'lab.sqlite'))) return {views:[]};
  const db=new DatabaseSync(path.join(base,'lab.sqlite'),{readOnly:true});
  try {
    const run=db.prepare(`SELECT id,created_at,json_extract(payload,'$.config.dataset') dataset,
      json_extract(payload,'$.summary_batch.context_artifact_ids') batch
      FROM runs WHERE deleted_at IS NULL AND json_extract(payload,'$.config.event_graph_mode')='linked-v2'
      AND json_array_length(payload,'$.results')>0 ORDER BY rowid DESC LIMIT 1`).get();
    if(!run)return {views:[]};
    const refs=db.prepare(`SELECT json_extract(value,'$.stages.extraction.artifact_id') extraction FROM runs,json_each(payload,'$.results') WHERE runs.id=?`).all(run.id);
    function read(id){
      if(!/^[0-9a-f]{64}$/.test(id))throw Error('잘못된 색인 참조');
      const raw=fs.readFileSync(path.join(base,'artifacts',id+'.json'));
      if(createHash('sha256').update(raw).digest('hex')!==id)throw Error('색인 무결성 확인 실패');
      return JSON.parse(raw);
    }
    const views=[],seen=new Set(), originals=new Map();
    if (/^[a-zA-Z0-9._-]+$/.test(run.dataset) && !run.dataset.includes('..')) {
      const file=path.join(root,'datasets',run.dataset,'sources.json');
      if(fs.existsSync(file))for(const r of JSON.parse(fs.readFileSync(file,'utf8')).records||[])originals.set(r.id+'@'+r.revision,r);
    }
    for(const id of new Set([...(JSON.parse(run.batch||'[]')||[]),...refs.map(x=>x.extraction).filter(Boolean)])){
      const extraction=read(id),ref=extraction.event_graph_index?.artifact_id;
      if(!ref||seen.has(ref))continue;
      seen.add(ref);
      const index=read(ref),units=new Map();
      for(const unitRef of index.index_ids){
        for(const u of read(unitRef).units){
          const r=originals.get(u.source_id+'@'+u.revision);
          units.set(u.id,{id:u.id,text:u.raw_text||u.text,source:u.source_id,revision:u.revision,start:u.start,entities:u.entities,title:r?.metadata?.title,original:r?.text});
        }
      }
      const graphs=index.graphs.map(g=>({id:g.id,label:g.events?.join(' · ')||g.description.replace(/^(검색 표현|관계|장소):\s*/, '').split(/,|\n/)[0],description:g.description,
        members:g.members.map(m=>units.get(m.unit_id)).filter(Boolean),links:g.links||[]}));
      views.push({id:ref,context:extraction.context_id,graphs});
    }
    views.sort((a,b)=>b.graphs.filter(g=>g.links.length).length-a.graphs.filter(g=>g.links.length).length);
    return {dataset:run.dataset,date:run.created_at,views};
  }finally{db.close()}
}
if(!isMainThread)parentPort.postMessage(load(workerData));
let cached, expires=0;
module.exports=async function graphData(root){
  if(!cached||Date.now()>expires){expires=Date.now()+60000;
    cached=new Promise((resolve,reject)=>{const worker=new Worker(__filename,{workerData:root});worker.once('message',resolve);worker.once('error',reject);}).catch(error=>{cached=null;throw error;});
  }
  return cached;
};

module.exports.invalidate=()=>{cached=null;expires=0;};
