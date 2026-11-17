#!/usr/bin/env node
'use strict';
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {evaluateCandidates,evaluateCase}=require('../local/summary-preservation.cjs');
const file=path.join(__dirname,'../tests/fixtures/summary-preservation-v1.json'),fixture=JSON.parse(fs.readFileSync(file,'utf8')),manifest=require('../tests/fixtures/summary-preservation-v1.manifest.json');
if(crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')!==manifest.fixture_sha256)throw Error('Frozen criteria hash mismatch');
const args=process.argv.slice(2),get=flag=>{const i=args.indexOf(flag);return i<0?null:args[i+1];};
if(args.includes('--self-check')&&args.includes('--candidates')){console.error('Choose either --self-check or --candidates; they cannot be combined.');process.exit(2);}
for(let i=0;i<args.length;i++){const flag=args[i];if(flag==='--self-check')continue;if(['--candidates','--output'].includes(flag)&&args[i+1]&&!args[i+1].startsWith('--')){i++;continue;}console.error('Unknown or incomplete argument: '+flag);process.exit(2);}
let report;
if(args.includes('--self-check')){
 const failures=fixture.cases.map(c=>({id:c.id,result:evaluateCase(c,c.failed_summary).status}));
 const positives=fixture.cases.flatMap(c=>[{id:c.id+'-original',summary:c.original},...c.accepted].map(a=>({id:a.id,result:evaluateCase(c,a.summary).status})));
 const ok=failures.every(x=>x.result==='FAIL')&&positives.every(x=>x.result==='PASS');
 report={mode:'checker-self-check',meaning:'Checks rejection of known bad outputs and acceptance of original/corrected/equivalent expressions. Does not run or improve the summarization model.',status:ok?'PASS':'FAIL',known_bad_detected:failures.filter(x=>x.result==='FAIL').length,known_bad_total:22,accepted_passed:positives.filter(x=>x.result==='PASS').length,accepted_total:positives.length,axis_coverage:Object.fromEntries(fixture.axes.map(a=>[a,fixture.cases.filter(c=>c.axes.includes(a)).map(c=>c.id)])),failures,positives};
 process.exitCode=ok?0:1;
}else if(get('--candidates')){
 const input=JSON.parse(fs.readFileSync(path.resolve(get('--candidates')),'utf8'));
 report={mode:'candidate-regression',...evaluateCandidates(fixture,Array.isArray(input)?input:input.candidates)};
 process.exitCode=report.status==='PASS'?0:report.status==='FAIL'?1:2;
}else{
 console.error('Usage: node tools/check-summary-preservation.cjs --self-check [--output result.json]\n       node tools/check-summary-preservation.cjs --candidates candidates.json [--output result.json]');process.exit(2);
}
if(get('--output'))fs.writeFileSync(path.resolve(get('--output')),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report,null,2));
