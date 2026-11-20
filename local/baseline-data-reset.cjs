'use strict';
const fs=require('node:fs'),path=require('node:path');
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const id=value=>{if(typeof value!=='string'||!/^[-\w]{1,80}$/.test(value))throw Error('삭제 작업 정보가 올바르지 않습니다.');return value;};
function emptyOwnedDirectory(root,directory){
 if(!fs.existsSync(directory))return;
 const workspace=fs.realpathSync(root),base=fs.realpathSync(directory),relative=path.relative(workspace,base);
 if(!relative||relative.startsWith('..')||path.isAbsolute(relative)||!relative.startsWith('.local'+path.sep+'baseline'+path.sep))throw Error('삭제 경로가 앱 데이터 폴더 밖에 있습니다.');
 for(const entry of fs.readdirSync(base,{withFileTypes:true})){
  const target=path.resolve(base,entry.name),inside=path.relative(base,target);
  if(!inside||inside.startsWith('..')||path.isAbsolute(inside))throw Error('삭제 대상 경로가 올바르지 않습니다.');
  if(entry.isSymbolicLink()){fs.unlinkSync(target);continue;}
  const resolved=fs.realpathSync(target),resolvedRelative=path.relative(base,resolved);
  if(resolvedRelative.startsWith('..')||path.isAbsolute(resolvedRelative))throw Error('앱 데이터 밖의 파일은 삭제하지 않습니다.');
  if(entry.isDirectory())fs.rmSync(target,{recursive:true,force:true});else fs.unlinkSync(target);
 }
}
function createBaselineReset(engine,runtime,chatSearch,{cancelSetup=()=>{}}={}){
 let lease=null;
 function assertLease(value){if(lease!==id(value))throw Error('전체 삭제 작업을 먼저 준비해 주세요.');}
 function preview(){const db=engine.store.db;return {runs:Number(db.prepare('SELECT count(*) n FROM runs').get().n),artifacts:fs.existsSync(path.join(engine.store.dir,'artifacts'))?fs.readdirSync(path.join(engine.store.dir,'artifacts')).length:0};}
 async function begin(value){
  value=id(value);if(lease&&lease!==value)throw Error('다른 전체 삭제 작업이 진행 중입니다.');lease=value;
  try{
   cancelSetup();engine.abort?.abort();await chatSearch.indexes.suspend();await runtime.stopAll();
   const deadline=Date.now()+30000;while(engine.busy){if(Date.now()>deadline)throw Error('진행 중인 작업이 아직 정리되지 않았습니다. 잠시 후 다시 시도해 주세요.');await delay(50);}
   return {prepared:true};
  }catch(error){lease=null;chatSearch.indexes.resume();throw error;}
 }
 async function clear(value){
  assertLease(value);const db=engine.store.db;
  db.exec('PRAGMA secure_delete=ON; BEGIN IMMEDIATE');
  try{
   const tables=db.prepare("SELECT name FROM pragma_table_list WHERE schema='main' AND type IN ('table','virtual') AND name NOT LIKE 'sqlite_%'").all();
   for(const table of tables)db.exec('DELETE FROM "'+table.name.replaceAll('"','""')+'"');
   db.exec('COMMIT');
  }catch(error){db.exec('ROLLBACK');throw error;}
  chatSearch.forget();for(const key of ['_summary','_structured','_rawChunks','_attention'])engine[key]=undefined;
  emptyOwnedDirectory(engine.root,path.join(engine.store.dir,'artifacts'));
  emptyOwnedDirectory(engine.root,path.join(engine.store.dir,'runtime'));
  db.exec('PRAGMA wal_checkpoint(TRUNCATE)');
  return {cleared:true};
 }
 function release(value){assertLease(value);lease=null;chatSearch.indexes.resume();return {released:true};}
 return {preview,begin,clear,release,locked:()=>lease!==null};
}
module.exports={createBaselineReset,emptyOwnedDirectory};
