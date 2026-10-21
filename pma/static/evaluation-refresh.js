// Polling compares observable progress before touching the DOM.
export function summaryRevision(summary){return JSON.stringify({status:summary.status,counts:summary.case_counts,metrics:summary.metrics,caseId:summary.progress?.case_id,stage:summary.progress?.stage});}
export function shouldPoll({hidden,busy,updating,status}){return !hidden&&!busy&&!updating&&['running','pending'].includes(status);}
