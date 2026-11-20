'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {Library,makeBackup,readBackup,payload}=require('../ui/library.cjs');
test('edited conversation titles survive saving, reopening and backup restoration',()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'pma-title-test-'));let library;
 try{
  library=new Library(dir);const thread={id:'renamed-thread',title:'발표 준비 기록',titleEdited:true,draft:'다음 질문 초안',messages:[{kind:'user',text:'처음 대화'}]};
  library.save(0,()=>({threads:[thread],records:[]}));library.close();library=new Library(dir);
  const state=library.read();assert.equal(state.threads[0].title,'발표 준비 기록');assert.equal(state.threads[0].titleEdited,true);assert.equal(state.threads[0].draft,'다음 질문 초안');
  const restored=readBackup(makeBackup(state));assert.equal(restored.threads[0].titleEdited,true);assert.equal(restored.threads[0].title,'발표 준비 기록');
 }finally{library?.close();if(path.dirname(dir)===os.tmpdir()&&path.basename(dir).startsWith('pma-title-test-'))fs.rmSync(dir,{recursive:true,force:true});}
});
test('older conversations stay compatible and malformed title flags are rejected',()=>{
 const old=payload({threads:[{id:'old-thread',title:'기존 대화',messages:[]}],records:[]});assert.equal(Object.hasOwn(old.threads[0],'titleEdited'),false);
 assert.throws(()=>payload({threads:[{id:'bad-thread',titleEdited:'yes',messages:[]}],records:[]}));
});
