'use strict';
(function(root){
  function ranges(record,citations=[]){
    const body=String(record.body??''),valid=[];
    for(const c of citations){
      if(c?.source_id!==record.id||c.revision!==record.revision||!Number.isSafeInteger(c.start)||!Number.isSafeInteger(c.end)||c.start<0||c.end<=c.start||c.end>body.length||typeof c.quote!=='string'||body.slice(c.start,c.end)!==c.quote)continue;
      valid.push({start:c.start,end:c.end});
    }
    valid.sort((a,b)=>a.start-b.start||a.end-b.end);const merged=[];
    for(const range of valid){const last=merged.at(-1);if(last&&range.start<=last.end)last.end=Math.max(last.end,range.end);else merged.push({...range});}
    return merged;
  }
  function segments(record,citations=[]){
    const body=String(record.body??''),parts=[];let at=0;
    for(const range of ranges(record,citations)){if(range.start>at)parts.push({text:body.slice(at,range.start),highlighted:false});parts.push({text:body.slice(range.start,range.end),highlighted:true});at=range.end;}
    if(at<body.length||!parts.length)parts.push({text:body.slice(at),highlighted:false});return parts;
  }
  const api={ranges,segments};if(typeof module==='object'&&module.exports)module.exports=api;else root.PlantRecordEvidence=api;
})(typeof window==='undefined'?null:window);
