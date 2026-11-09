import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {loadDataset,validate} from './lib.mjs';
const dir=path.dirname(fileURLToPath(import.meta.url));
const data=loadDataset(dir),result=validate(data,dir);
// Negative controls demonstrate that integrity success is not a model-quality claim.
const clone=()=>structuredClone(data);
const mutations=[
 ['wrong source quote',d=>{d.sources.records[0].gold.facts[0].evidence[0].quote='wrong';}],
 ['stale deleted evidence',d=>{d.questions.questions.find(q=>q.id==='F28-Q2').gold.evidence_groups=[{id:'G1',any_of_fact_ids:['F28-A-P1']}];}],
 ['cross-owner evidence',d=>{d.questions.questions.find(q=>q.id==='F30-Q1').gold.evidence_groups=[{id:'G1',any_of_fact_ids:['F30-B-P1']}];}],
 ['state replay mismatch',d=>{d.contexts.contexts.find(c=>c.id==='F27-AFTER').setup.steps=[];}],
 ['self-linked question variant',d=>{const q=d.questions.questions[0];q.variant={of:q.id};}]
];
result.negative_controls=mutations.map(([name,mutate])=>{const d=clone();mutate(d);return {name,rejected:!validate(d,dir,{checkHashes:false}).ok};});
result.ok=result.ok&&result.negative_controls.every(x=>x.rejected);
result.scope='STATIC_DATA_INTEGRITY_ONLY; no model, retrieval service or product evaluation executed';
if(process.argv.includes('--write-report'))fs.writeFileSync(path.join(dir,'validation-report.json'),JSON.stringify(result,null,2)+'\n');
console.log(JSON.stringify(result,null,2));
process.exitCode=result.ok?0:1;
