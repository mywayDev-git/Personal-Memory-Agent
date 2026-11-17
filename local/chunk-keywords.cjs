const {chunks,hash}=require('./core.cjs');

const VERSION='original-chunk-keywords-v1';
const normalize=value=>value.normalize('NFKC').toLowerCase().replace(/\s+/gu,'');
const suffix=/(으로|에서|부터|까지|에게|에는|은|는|이|가|을|를|의|에|도|와|과)$/u;
const identifiers=text=>[...new Set([...text.matchAll(/\b[A-Z][A-Z0-9]{0,11}[-_]\d[A-Z0-9_-]*\b/giu)]
 .map(match=>match[0].toUpperCase()))];

function keywordSpans(text,offset){
 const result=new Map(),words=[];
 function add(start,end){
  if(end-start>64){
   for(let at=start;at<end;at+=32){
    let a=at,b=Math.min(end,at+48);
    if(a>0&&/[\uDC00-\uDFFF]/u.test(text[a])&&/[\uD800-\uDBFF]/u.test(text[a-1]))a--;
    if(b<text.length&&/[\uD800-\uDBFF]/u.test(text[b-1])&&/[\uDC00-\uDFFF]/u.test(text[b]))b++;
    add(a,b);
   }
   return;
  }
  const value=text.slice(start,end);
  const normalized=normalize(value);
  if(!normalized||value.length>64||result.has(normalized))return;
  result.set(normalized,{text:value,normalized,start:offset+start,end:offset+end});
 }
 for(const match of text.matchAll(/[\p{L}\p{N}][\p{L}\p{N}_:/+.\-]*/gu)){
  const value=match[0].replace(/[.,!?;:]+$/u,'');
  if(!value)continue;
  const start=match.index,end=start+value.length;
  words.push({start,end});
  add(start,end);
  const stem=value.replace(suffix,'');
  if(stem.length>=2&&stem!==value)add(start,start+stem.length);
 }
 for(let i=1;i<words.length;i++){
  const first=words[i-1],last=words[i];
  if(/^\s+$/u.test(text.slice(first.end,last.start))){
   add(first.start,last.end);
   const value=text.slice(first.start,last.end),stem=value.replace(suffix,'');
   if(stem.length>=2&&stem!==value)add(first.start,first.start+stem.length);
  }
 }
 return [...result.values()];
}

function indexSource(source){
 const source_hash=hash(source.text),owner_id=source.metadata.owner_id;
 const units=chunks(source,900,120).map(part=>{
  let {start,end}=part;
  if(start>0&&/[\uDC00-\uDFFF]/u.test(source.text[start])&&/[\uD800-\uDBFF]/u.test(source.text[start-1]))start--;
  if(end<source.text.length&&/[\uD800-\uDBFF]/u.test(source.text[end-1])&&/[\uDC00-\uDFFF]/u.test(source.text[end]))end++;
  const text=source.text.slice(start,end);
  const id='K-'+hash({version:VERSION,owner_id,source:source.id,revision:source.revision,source_hash,start,end}).slice(0,28);
  return {id,chunk_id:id,source_id:source.id,revision:source.revision,start,end,text,origin:'raw',
   keywords:keywordSpans(text,start),identifiers:identifiers(text)};
 });
 return {version:VERSION,owner_id,source_id:source.id,revision:source.revision,source_hash,units};
}

function validateIndex(index,source){
 if(!source)throw Error('현재 기억 범위에서 원문 구간의 출처를 확인할 수 없습니다.');
 if(index.version!==VERSION||index.owner_id!==source.metadata.owner_id||index.source_id!==source.id||
  index.revision!==source.revision||index.source_hash!==hash(source.text))
  throw Error('원문 구간 색인의 소유자·버전·내용이 현재 기억 범위와 다릅니다.');
 const expected=indexSource(source);
 if(JSON.stringify(index.units)!==JSON.stringify(expected.units))throw Error('원문 구간 또는 키워드 위치가 색인과 일치하지 않습니다.');
 return index;
}

module.exports={VERSION,normalize,identifiers,indexSource,validateIndex};
