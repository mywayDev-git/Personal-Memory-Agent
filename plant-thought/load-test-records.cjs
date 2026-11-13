'use strict';
const fs=require('node:fs');
const path=require('node:path');
const fixture=require('./test-records.json');
const base='http://127.0.0.1:4321/api/baseline';
const reportPath=path.join(__dirname,'test-records-load-report.json');
const report={started_at:new Date().toISOString(),status:'running',records:[]};
function checkpoint(){fs.writeFileSync(reportPath,JSON.stringify(report,null,2));}
async function read(endpoint){
  const response=await fetch(base+endpoint,{signal:AbortSignal.timeout(15000)});
  const value=await response.json();if(!response.ok)throw Error(value.error||'조회 실패');return value;
}
function input(record){return '제목: [테스트] '+record.title+'\n기록일: '+record.date+'\n감정: 미지정\n\n'+record.body;}
async function existingTexts(){
  const {memories}=await read('/summary-memory');const texts=new Map();
  for(const memory of memories){const {source}=await read('/summary-memory/original?key='+encodeURIComponent(memory.memory_key));if(source?.text)texts.set(source.text,memory);}
  return texts;
}
async function main(){
  let boot=await read('/bootstrap');
  if(boot.busy||boot.setup?.status==='RUNNING')throw Error('현재 진행 중인 작업이 있습니다. 완료 후 다시 실행해 주세요.');
  const models=boot.runtime.models.filter(model=>model.present&&model.role==='generation');
  const model=(models.find(model=>model.default)||models[0])?.id;if(!model)throw Error('설치된 생성 모델이 없습니다.');
  let texts=await existingTexts();checkpoint();
  for(const [index,record]of fixture.records.entries()){
    const text=input(record);let memory=texts.get(text);const started=Date.now();
    if(memory){console.log((index+1)+'/10 이미 저장됨: '+record.title);}
    else{
      console.log((index+1)+'/10 저장 시작: '+record.title);
      const heartbeat=setInterval(()=>console.log((index+1)+'/10 처리 중 ('+Math.floor((Date.now()-started)/1000)+'초): '+record.title),45000);
      try{
        boot=await read('/bootstrap');
        const response=await fetch(base+'/summary-memory/save',{method:'POST',headers:{Origin:'http://127.0.0.1:4321','Content-Type':'application/json','X-Memory-Lab-Token':boot.token},body:JSON.stringify({text,config:{model,route:'M1',top_k:3}})});
        const result=await response.json();if(!response.ok)throw Error(result.error||'저장 실패');
        memory=result.memory;if(!memory?.memory_key)throw Error('저장 결과가 비어 있습니다.');
        texts.set(text,memory);
      }finally{clearInterval(heartbeat);}
      console.log((index+1)+'/10 저장 완료 ('+Math.floor((Date.now()-started)/1000)+'초): '+record.title);
    }
    report.records.push({date:record.date,title:'[테스트] '+record.title,memory_key:memory.memory_key,summary_artifact_id:memory.summary_artifact_id,question:record.question,elapsed_ms:Date.now()-started});checkpoint();
  }
  texts=await existingTexts();
  const missing=fixture.records.filter(record=>!texts.has(input(record)));
  if(missing.length)throw Error('최종 확인에서 '+missing.length+'개 기록이 누락됐습니다.');
  report.status='complete';report.finished_at=new Date().toISOString();checkpoint();
  console.log('완료: 가상 기록 10개 저장 및 원문 일치 확인.');
}
main().catch(error=>{report.status='error';report.error=error.message;checkpoint();console.error(error.message);process.exitCode=1;});
