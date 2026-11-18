'use strict';
const crypto=require('node:crypto');
const {record,payload,hash,MAX_BYTES}=require('./library.cjs');
const fail=(message,status=400)=>{throw Object.assign(Error(message),{status,stage:'execution'});};
const uuid=()=>crypto.randomUUID();
class ActionService{
 constructor(library){
  this.library=library;this.db=library.db;
  this.db.exec(`CREATE TABLE IF NOT EXISTS action_tasks(id TEXT PRIMARY KEY,thread_id TEXT NOT NULL,request_id TEXT NOT NULL,goal TEXT NOT NULL,state TEXT NOT NULL,detail TEXT NOT NULL);
   CREATE TABLE IF NOT EXISTS action_proposals(id TEXT PRIMARY KEY,thread_id TEXT NOT NULL,request_id TEXT NOT NULL UNIQUE,version INTEGER NOT NULL,state TEXT NOT NULL,payload TEXT NOT NULL);
   CREATE TABLE IF NOT EXISTS action_receipts(id TEXT PRIMARY KEY,proposal_id TEXT NOT NULL UNIQUE,fingerprint TEXT NOT NULL,payload TEXT NOT NULL);
   CREATE TABLE IF NOT EXISTS record_history(operation_id TEXT PRIMARY KEY,record_id TEXT NOT NULL,before_json TEXT,after_json TEXT NOT NULL);
   CREATE TABLE IF NOT EXISTS action_requests(id TEXT PRIMARY KEY,fingerprint TEXT NOT NULL,result TEXT NOT NULL);
   CREATE TABLE IF NOT EXISTS action_goal_plans(id TEXT PRIMARY KEY,fingerprint TEXT NOT NULL,payload TEXT NOT NULL);`);
 }
 assertThread(threadId){if(this.library.isThreadPurged(threadId))fail('완전히 삭제한 대화입니다. 새 대화를 시작해 주세요.',410);}
 tasks(threadId){return this.db.prepare("SELECT * FROM action_tasks WHERE thread_id=? ORDER BY (state='waiting') DESC,rowid DESC LIMIT 24").all(threadId).map(r=>({...r,detail:JSON.parse(r.detail)}));}
 pending(threadId){return this.db.prepare("SELECT * FROM action_proposals WHERE thread_id=? AND state='pending' ORDER BY rowid DESC").all(threadId).map(r=>this.decode(r));}
 decode(row){return row?{...JSON.parse(row.payload),id:row.id,version:row.version,status:row.state}:null;}
 proposal(id){return this.decode(this.db.prepare('SELECT * FROM action_proposals WHERE id=?').get(id));}
 receipt(id){const r=this.db.prepare('SELECT payload FROM action_receipts WHERE id=?').get(id);return r?JSON.parse(r.payload):null;}
 recentReceipts(threadId){return this.db.prepare("SELECT payload FROM action_receipts WHERE json_extract(payload,'$.thread_id')=? ORDER BY rowid DESC LIMIT 12").all(threadId).map(r=>{const {record,...receipt}=JSON.parse(r.payload);return receipt;});}
 getGoalPlan(data){const row=this.db.prepare('SELECT * FROM action_goal_plans WHERE id=?').get(data.request_id);if(!row)return null;if(row.fingerprint!==hash(data))fail('같은 요청 ID의 목표 제출 내용이 다릅니다.',409);return JSON.parse(row.payload);}
 rememberGoalPlan(data,plan){this.assertThread(data.thread_id);const old=this.getGoalPlan(data);if(old)return old;this.db.prepare('INSERT INTO action_goal_plans VALUES(?,?,?)').run(data.request_id,hash(data),JSON.stringify(plan));return plan;}
 proposalForRequest(requestId){return this.decode(this.db.prepare('SELECT * FROM action_proposals WHERE request_id=?').get(requestId));}
 bindGoal(taskId,proposals){for(const p of proposals){const stored=this.proposal(p.id);if(!stored)continue;p.task_id=taskId;this.db.prepare('UPDATE action_proposals SET payload=? WHERE id=?').run(JSON.stringify({...stored,task_id:taskId}),p.id);}}
 cached(data){const r=this.db.prepare('SELECT * FROM action_requests WHERE id=?').get(data.request_id);if(!r)return null;if(r.fingerprint!==hash(data))fail('같은 요청 ID의 제출 내용이 다릅니다.',409);const result=JSON.parse(r.result);
  if(result.proposals){result.proposals=result.proposals.map(p=>this.proposal(p.id)||p);const receipts=result.proposals.map(p=>this.receipt(p.operation_id)).filter(Boolean);result.executions=[...new Map([...(result.executions||[]),...receipts].map(r=>[r.proposal_id,r])).values()];result.stored=result.executions.some(r=>r.status==='succeeded'&&r.operation==='create');if(result.action_trace?.steps)for(const step of result.action_trace.steps){const receipt=result.executions.find(r=>r.proposal_id===step.proposal_id);if(receipt)step.status=receipt.status==='succeeded'?'committed':'cancelled';}}
  if(result.proposal){result.proposal=this.proposal(result.proposal.id);const receipt=this.receipt(result.proposal.operation_id);if(receipt){result.execution=receipt;result.answer=receipt.message;result.action=receipt.status==='cancelled'?'cancelled':'committed';result.stored=receipt.status==='succeeded'&&receipt.operation==='create';}}return result;}
 remember(data,result){this.assertThread(data.thread_id);this.db.prepare('INSERT INTO action_requests VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET result=excluded.result').run(data.request_id,hash(data),JSON.stringify(result));}
 task(data,decision,detail){this.assertThread(data.thread_id);
  const rows=this.tasks(data.thread_id),existing=rows.find(t=>t.request_id===data.request_id)||(decision.task_id&&rows.find(t=>t.id===decision.task_id&&t.state==='waiting'));
  const id=existing?.id||uuid(),goal=existing?.goal||decision.goal||data.text;
  if(detail.steps){const pending=(existing?.detail?.steps||[]).filter(s=>s.proposal_id&&s.status==='awaiting_confirmation'&&!detail.steps.some(next=>next.proposal_id===s.proposal_id));detail={...detail,steps:[...pending,...detail.steps]};}
  const status=detail.steps?.some(s=>s.status==='awaiting_confirmation')?'waiting':decision.status||(decision.action==='clarify'?'waiting':'completed');
  this.db.prepare('INSERT OR REPLACE INTO action_tasks VALUES(?,?,?,?,?,?)').run(id,data.thread_id,data.request_id,goal,status,JSON.stringify(detail));return id;
 }
 propose(data,decision,change,sourceRefs){this.assertThread(data.thread_id);
  const old=this.db.prepare('SELECT * FROM action_proposals WHERE request_id=?').get(data.request_id);
  if(old){const p=this.decode(old);if(p.thread_id!==data.thread_id||p.submitted_text!==data.text||(p.request_fingerprint&&p.request_fingerprint!==hash(data)))fail('같은 요청 ID의 내용이 다릅니다.',409);return p;}
  if(!['create','update','delete','restore'].includes(decision.action))fail('지원하지 않는 기록 작업입니다.');
  const target=decision.action!=='create'&&decision.target_id?this.library.read().records.find(r=>r.id===decision.target_id):null;
  if(decision.action!=='create'&&!target)fail('변경할 개인 기록을 찾지 못했습니다.',404);
  if(target&&decision.expected_revision!=null&&target.revision!==decision.expected_revision)fail('초안을 준비하는 동안 원문이 변경되었습니다. 다시 요청해 주세요.',409);
  if(target&&((decision.action==='restore')!==!!target.deleted_at))fail('기록 상태가 바뀌었습니다. 다시 확인해 주세요.',409);
  const id=uuid(),operation_id=uuid(),p={id,thread_id:data.thread_id,request_id:data.request_id,submitted_text:data.text,request_fingerprint:hash(data),operation_id,operation:decision.action,version:1,status:'pending',target_id:target?.id||uuid(),expected_revision:target?.revision||0,before:target||null,after:change||null,sources:sourceRefs,created_at:new Date().toISOString()};
  this.db.prepare('INSERT INTO action_proposals VALUES(?,?,?,?,?,?)').run(id,data.thread_id,data.request_id,1,'pending',JSON.stringify(p));return p;
 }
 execute(input){
  // Approval is an explicit UI command bound to this immutable proposal, never a model field.
  const fingerprint=hash({proposal_id:input.proposal_id,version:input.version,thread_id:input.thread_id,decision:input.decision});
  this.db.exec('BEGIN IMMEDIATE');
  try{
   const p=this.proposal(input.proposal_id);if(!p||p.thread_id!==input.thread_id)fail('확인할 작업을 찾지 못했습니다.',404);
   if(input.operation_id!==p.operation_id||input.version!==p.version)fail('확인한 초안의 버전이 바뀌었습니다.',409);
   const old=this.db.prepare('SELECT * FROM action_receipts WHERE id=?').get(p.operation_id);
   if(old){if(old.fingerprint!==fingerprint)fail('이미 처리한 작업과 확인 내용이 다릅니다.',409);this.db.exec('COMMIT');return JSON.parse(old.payload);}
   if(p.status!=='pending')fail('이미 종료된 초안입니다.',409);
   const state=this.library.read(),thread=state.threads.find(t=>t.id===p.thread_id);
   if(!thread||thread.deletedAt)fail('이 대화가 삭제되어 작업을 실행할 수 없습니다.',409);
   if(!['confirm','cancel'].includes(input.decision))fail('확인 또는 취소를 선택해 주세요.');
   let result={operation_id:p.operation_id,proposal_id:p.id,thread_id:p.thread_id,operation:p.operation,status:'cancelled',revision:state.revision,record_id:p.target_id};
   if(input.decision==='confirm'){
    const before=state.records.find(r=>r.id===p.target_id);
    if(p.expected_revision?(before?.revision!==p.expected_revision):!!before)fail('기록이 다른 곳에서 변경되었습니다. 새 초안을 확인해 주세요.',409);
    const now=new Date().toISOString();let after;
    if(p.operation==='create')after=record({...p.after,id:p.target_id,revision:1,synthetic:false,search_enabled:true,created_at:now,updated_at:now,kind:p.after.kind,sources:p.sources});
    if(p.operation==='update')after=record({...before,...p.after,id:before.id,revision:before.revision+1,created_at:before.created_at,updated_at:now,sources:[...(before.sources||[]),...p.sources]});
    if(p.operation==='delete')after=record({...before,revision:before.revision+1,deleted_at:now,updated_at:now});
    if(p.operation==='restore')after=record({...before,revision:before.revision+1,deleted_at:null,updated_at:now});
    const records=before?state.records.map(r=>r.id===after.id?after:r):[...state.records,after];
    const next=payload({...state,records});if(Buffer.byteLength(JSON.stringify(next))>MAX_BYTES)fail('저장 용량을 초과했습니다.',413);
    this.db.prepare('UPDATE library SET revision=?,payload=? WHERE id=1').run(state.revision+1,JSON.stringify(next));
    this.db.prepare('INSERT INTO record_history VALUES(?,?,?,?)').run(p.operation_id,p.target_id,before?JSON.stringify(before):null,JSON.stringify(after));
    result={...result,status:'succeeded',revision:state.revision+1,record_revision:after.revision,record:after};
   }
   result.message=result.status==='cancelled'?'초안을 취소했어요.':({create:'개인 자료함에 저장했어요.',update:'기록을 수정했어요.',delete:'기록을 삭제했어요.',restore:'기록을 복원했어요.'})[p.operation];
   this.db.prepare('INSERT INTO action_receipts VALUES(?,?,?,?)').run(p.operation_id,p.id,fingerprint,JSON.stringify(result));
   this.db.prepare('UPDATE action_proposals SET state=? WHERE id=?').run(result.status,p.id);
   if(p.task_id){const task=this.db.prepare('SELECT * FROM action_tasks WHERE id=?').get(p.task_id);if(task&&task.thread_id===p.thread_id){const detail=JSON.parse(task.detail);for(const step of detail.steps||[])if(step.proposal_id===p.id)step.status=result.status==='succeeded'?'committed':'cancelled';const waiting=!!detail.reply_error||(detail.steps||[]).some(s=>['planned','awaiting_confirmation','needs_input','failed'].includes(s.status));this.db.prepare('UPDATE action_tasks SET state=?,detail=? WHERE id=?').run(waiting?'waiting':'completed',JSON.stringify(detail),task.id);}}
   this.db.exec('COMMIT');return result;
  }catch(error){this.db.exec('ROLLBACK');throw error;}
 }
}
module.exports={ActionService};
