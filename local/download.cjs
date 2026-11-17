const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {Readable,Transform}=require('node:stream');
const {pipeline}=require('node:stream/promises');
async function fileHash(file){const h=crypto.createHash('sha256');for await(const b of fs.createReadStream(file))h.update(b);return h.digest('hex');}
async function download(model,root,progress=()=>{}){
 const dir=path.join(root,'.models');fs.mkdirSync(dir,{recursive:true});const final=path.join(dir,model.file),partial=final+'.part';
 if(fs.existsSync(final)){
  if(fs.statSync(final).size!==model.bytes || await fileHash(final)!==model.sha256)throw Error('기존 모델 파일 해시 불일치: '+model.file);
  progress({phase:'complete',downloaded:model.bytes,total:model.bytes});return final;
 }
 let offset=fs.existsSync(partial)?fs.statSync(partial).size:0;
 if(offset>model.bytes)throw Error('부분 다운로드 크기가 예상보다 큽니다: '+partial);
 if(offset<model.bytes){
  const url=`https://huggingface.co/${model.repo}/resolve/${model.revision}/${model.file}`;
  const response=await fetch(url,{headers:offset?{Range:`bytes=${offset}-`}:{},signal:AbortSignal.timeout(1800000)});
  if(!response.ok)throw Error('다운로드 HTTP '+response.status);
  if(offset&&response.status!==206)offset=0;
  if(response.status===206&&!response.headers.get('content-range')?.startsWith('bytes '+offset+'-'))throw Error('다운로드 Range 불일치');
  let downloaded=offset,last=0;progress({phase:'download',downloaded,total:model.bytes});
  await pipeline(Readable.fromWeb(response.body),new Transform({transform(chunk,_,cb){downloaded+=chunk.length;if(Date.now()-last>1000){last=Date.now();progress({phase:'download',downloaded,total:model.bytes});}cb(null,chunk);}}),fs.createWriteStream(partial,{flags:offset?'a':'w'}));
 }
 progress({phase:'verify',downloaded:model.bytes,total:model.bytes});
 if(fs.statSync(partial).size!==model.bytes || await fileHash(partial)!==model.sha256)throw Error('모델 다운로드 크기/해시 불일치');
 fs.renameSync(partial,final);fs.writeFileSync(final+'.verified.json',JSON.stringify({sha256:model.sha256,bytes:model.bytes,verified_at:new Date().toISOString(),repo:model.repo,revision:model.revision}));
 progress({phase:'complete',downloaded:model.bytes,total:model.bytes});return final;
}
module.exports={download,fileHash};
