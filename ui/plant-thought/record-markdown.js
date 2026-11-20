'use strict';
(function(root){
 const normalized=text=>String(text).replace(/\s+/g,' ').trim();
 function occurrences(text,quote){const found=[];if(!quote)return found;for(let at=0;(at=text.indexOf(quote,at))>=0;at+=quote.length)found.push(at);return found;}
 function locate(raw,offset,quote,visible,shown){
  const source=occurrences(raw,quote),rendered=occurrences(visible,shown),index=source.indexOf(offset);
  return index>=0&&source.length===rendered.length?{start:rendered[index],end:rendered[index]+shown.length}:null;
 }
 function textMap(target){
  const walker=document.createTreeWalker(target,NodeFilter.SHOW_TEXT),map=[];let text='',pending=null,node;
  while(node=walker.nextNode())for(let i=0;i<node.data.length;i++){
   const char=node.data[i];if(/\s/.test(char)){if(text&&!pending)pending={node,start:i,end:i+1};else if(pending&&pending.node===node)pending.end=i+1;continue;}
   if(pending){text+=' ';map.push(pending);pending=null;}text+=char;map.push({node,start:i,end:i+1});
  }
  return {text,map};
 }
 function annotate(element){element.classList.add('record-evidence-highlight');element.tabIndex=-1;element.setAttribute('aria-label','대화에서 참고한 구간');}
 function render(target,record,citations=[]){
  target.classList.add('ai-answer','record-markdown-read');target.innerHTML=root.PlantMarkdown.render(record.body,{sourceMap:true});
  const ranges=root.PlantRecordEvidence.ranges(record,citations),blocks=[...target.querySelectorAll('[data-record-from]')];
  for(const range of ranges)for(const block of blocks){
   const from=Number(block.dataset.recordFrom),to=Number(block.dataset.recordTo),start=Math.max(from,range.start),end=Math.min(to,range.end);if(end<=start)continue;
   const quote=record.body.slice(start,end),fragment=document.createElement('div');fragment.innerHTML=root.PlantMarkdown.render(quote);const shown=normalized(fragment.textContent),mapped=textMap(block),at=locate(record.body.slice(from,to),start-from,quote,mapped.text,shown);
   if(!at||!shown){annotate(block);continue;}
   const groups=new Map();for(const point of mapped.map.slice(at.start,at.end)){
    if(point.node.parentElement.closest('.record-evidence-highlight'))continue;
    const group=groups.get(point.node)||{start:point.start,end:point.end};group.start=Math.min(group.start,point.start);group.end=Math.max(group.end,point.end);groups.set(point.node,group);
   }
   for(const [node,part]of [...groups].reverse()){
    const selection=document.createRange();selection.setStart(node,part.start);selection.setEnd(node,part.end);const mark=document.createElement('mark');annotate(mark);selection.surroundContents(mark);
   }
  }
  return !!target.querySelector('.record-evidence-highlight');
 }
 const api={locate,normalized,render};if(typeof module==='object'&&module.exports)module.exports=api;else{root.PlantRecordMarkdown=api;document.dispatchEvent(new Event('plant:record-markdown-ready'));}
})(typeof window==='undefined'?null:window);
