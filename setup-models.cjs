const path=require('node:path'),{download}=require('./local/download.cjs'),models=require('./local/model-registry.cjs');
const root=path.resolve(process.argv[2]||__dirname);
(async()=>{for(const model of models.filter(m=>m.default)){let last='';await download(model,root,p=>{const line=model.id+' '+p.phase+' '+Math.floor(100*p.downloaded/p.total)+'%';if(line!==last){console.log(line);last=line;}});}console.log('기본 모델 준비 완료. 모델 평가 또는 생성은 실행하지 않았습니다.');})().catch(e=>{console.error(e.message);process.exitCode=1;});
