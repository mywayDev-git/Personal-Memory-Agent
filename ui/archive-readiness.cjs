'use strict';
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
function describeRecord(source){
  const base={record_id:source.id,revision:source.revision,original_checked:false,search_revision:null};
  if(typeof source.text!=='string'||!source.text.trim()||!Number.isSafeInteger(source.revision)||source.revision<1)return {...base,status:'error',reason_code:'invalid_original',reason:'원문 내용 또는 버전을 확인하지 못했습니다.'};
  base.original_checked=true;
  // Original availability is independent of whether a particular query has matches.
  return {...base,status:'ready',search_revision:source.revision,reason_code:'all_originals',reason:'전체 원문 검색에 사용할 수 있습니다.'};
}
async function buildReadiness(root,{profile,example_id,collection='samples'}){
  if(!['samples','personal'].includes(collection))throw Object.assign(Error('자료함을 확인해 주세요.'),{status:400});
  if(collection==='personal'){
    const file=path.join(root,'.local/library/library.sqlite');let originals=[];
    if(fs.existsSync(file)){const {DatabaseSync}=require('node:sqlite'),db=new DatabaseSync(file,{readOnly:true});try{const row=db.prepare('SELECT payload FROM library WHERE id=1').get();originals=JSON.parse(row?.payload||'{"records":[]}').records.filter(r=>!r.deleted_at);}finally{db.close();}}
    const records=originals.map(record=>{const info=describeRecord({id:record.id,revision:record.revision,text:record.body});return info.status==='ready'&&record.search_enabled!==true?{...info,status:'excluded',search_revision:null,reason_code:'search_disabled',reason:'개인 기록 검색 설정에서 제외한 기록입니다. 원문은 보관되어 있습니다.'}:info;});
    const counts={total:records.length,ready:0,error:0,excluded:0};for(const record of records)counts[record.status]++;
    return {collection:'personal',profile:'personal',example_id:'',scope_mode:'personal',context_id:'personal',checked_at:new Date().toISOString(),source_files:{},records,counts,preparation:'on-demand-original-search',model_inference:false};
  }
  if(!['development','confirmation'].includes(profile)||typeof example_id!=='string'||example_id.length>120)throw Object.assign(Error('선택한 자료와 사례를 확인해 주세요.'),{status:400});
  const dir=path.join(root,'datasets/pma-generalization-v1.0.0'),files={};
  const read=name=>{const bytes=fs.readFileSync(path.join(dir,name+'.json'));files[name+'.json']=crypto.createHash('sha256').update(bytes).digest('hex');return JSON.parse(bytes);};
  const sources=read('sources').records,questions=read('questions').questions,contexts=read('contexts').contexts;
  const question=questions.find(q=>q.id===example_id&&q.profile===profile),context=question&&contexts.find(c=>c.id===question.context_id);
  if(!context)throw Object.assign(Error('선택한 사례의 기록 범위를 확인하지 못했습니다.'),{status:400});
  const records=sources.map(source=>describeRecord(source)),counts={total:records.length,ready:0,error:0};
  for(const record of records)counts[record.status]++;
  return {collection:'samples',profile,example_id,scope_mode:'all-originals',context_id:'all-originals',reference_time:context.now,checked_at:new Date().toISOString(),source_files:files,records,counts,preparation:'on-demand-original-search',model_inference:false};
}
function createReadinessApi(root){
  return {async handle(req,res,url){
    if(url.pathname!=='/api/archive/readiness')return false;
    const json=(code,data)=>{res.writeHead(code,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'});res.end(JSON.stringify(data));};
    const host=req.headers.host||'';
    if(!/^(127\.0\.0\.1|localhost):\d+$/.test(host)||(req.headers.origin&&req.headers.origin!=='http://'+host)){json(403,{error:'현재 로컬 화면에서만 확인할 수 있습니다.'});return true;}
    if(req.method!=='GET'){json(405,{error:'조회 요청만 지원합니다.'});return true;}
    try{json(200,await buildReadiness(root,{profile:url.searchParams.get('profile'),example_id:url.searchParams.get('example_id'),collection:url.searchParams.get('collection')||'samples'}));}
    catch(error){json(error.status||500,{error:error.status?error.message:'기록 준비 상태를 확인하지 못했습니다. 다시 확인해 주세요.'});}
    return true;
  }};
}
module.exports={buildReadiness,describeRecord,createReadinessApi};
