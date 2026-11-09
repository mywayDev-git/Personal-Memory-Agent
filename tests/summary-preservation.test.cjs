const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {VERSION,AXES,normalize,evaluateCase,evaluateCandidates}=require('../local/summary-preservation.cjs');
const file=path.join(__dirname,'fixtures/summary-preservation-v1.json'),fixture=JSON.parse(fs.readFileSync(file,'utf8')),manifest=require('./fixtures/summary-preservation-v1.manifest.json');
test('frozen criteria retain all 22 audited failures and original provenance',()=>{
 assert.equal(fixture.version,VERSION);assert.equal(crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex'),manifest.fixture_sha256);
 assert.equal(fixture.cases.length,22);assert.deepEqual(fixture.cases.map(c=>c.id),manifest.case_ids);assert.equal(new Set(fixture.cases.map(c=>c.source_id)).size,16);
 for(const c of fixture.cases){assert.ok(c.rule.expected_atoms.length);assert.ok(c.axes.length&&c.axes.every(a=>AXES.includes(a)));assert.match(c.provenance.summary_id,/^[a-f0-9]{64}$/);assert.match(c.provenance.original_artifact_id,/^[a-f0-9]{64}$/);assert.ok(c.original&&c.failed_summary&&c.provenance.audit_reason);}
});
for(const c of fixture.cases){
 test(`${c.id} rejects actual saved error: ${c.title}`,()=>{const r=evaluateCase(c,c.failed_summary);assert.equal(r.status,'FAIL',JSON.stringify(r));for(const axis of c.axes)assert.equal(r.axes[axis],'FAIL');});
 test(`${c.id} accepts the complete original, including historical corrections and other actors`,()=>assert.equal(evaluateCase(c,c.original).status,'PASS'));
 for(const accepted of c.accepted)test(`${accepted.id} accepts ${accepted.kind}`,()=>assert.equal(evaluateCase(c,accepted.summary).status,'PASS',JSON.stringify(evaluateCase(c,accepted.summary))));
}
test('representation normalization preserves meaningful distinctions',()=>{
 for(const [a,b]of [['5,000원','0.5만 원'],['1,536 MB','1536MB'],['열두 명','12명'],['육십 개','예순 개'],['오후 2시','14:00'],['오후 2시','14시'],['오후 3시 반','15:30'],['오전 11시','11:00'],['오후 네 시 오십 분','16:50']])assert.equal(normalize(a),normalize(b));
 for(const [a,b]of [['오전 11시','오후 11시'],['아직 보내지 않았다','이미 보냈다'],['수정하면','수정했다'],['1GB=1024MB','1GB=1536MB'],['나윤에게 보낸 5000원','나윤에게서 받은 5000원']])assert.notEqual(normalize(a),normalize(b));
});
test('identical numbers with the wrong person, role, time, or direction still fail',()=>{
 const samples={C07:'H 메모리는 1536MB. 1GB=1536MB로 정했다.',C18:'금요일 오후 반납하기로 했다. 일요일 낮 반환 기한도 유지한다.',C19:'은재에게 수령 완료만 전달했다.',C20:'도운은 일요일 23시에 장비를 반납했다.',C21:'16:50 나윤이 일찍 도착했다. 17:10 나윤이 차를 마시러 오기로 약속했다. 약속은 17:00.',C22:'장터에서 받은 5,000원은 버스표 정산이다.'};
 for(const [id,s]of Object.entries(samples))assert.equal(evaluateCase(fixture.cases.find(c=>c.id===id),s).status,'FAIL',id);
});
test('matching good words never masks an explicit contradictory claim elsewhere',()=>{
 for(const c of fixture.cases.filter(c=>evaluateCase(c,c.failed_summary).checks[0].code==='CONTRADICTION'))assert.equal(evaluateCase(c,c.accepted[0].summary+'\n'+c.failed_summary).status,'FAIL',c.id);
});
test('a different actor being pending does not negate completed address delivery',()=>{
 const c=fixture.cases.find(c=>c.id==='C16');assert.equal(evaluateCase(c,'다해가 반주자 주소를 전달했다. 관객 메시지는 현우가 아직 보내지 않았다.').status,'PASS');
 assert.equal(evaluateCase(c,'다해의 반주자 주소 안내는 발송 예정이다. 현우가 다른 안내를 보냈다.').status,'FAIL');
});
test('explicitly denying a bad claim is not itself that bad claim',()=>{
 const c=fixture.cases.find(c=>c.id==='C01');assert.equal(evaluateCase(c,'초안 작성 완료는 아니다. 초안은 내가 작성할 예정이다.').status,'PASS');
 const t=fixture.cases.find(c=>c.id==='C08');assert.equal(evaluateCase(t,'H 메모리는 1536MB로 측정됐다. 1536MB로 증가했다는 뜻은 아니다.').status,'PASS');
});
test('unrecognized equivalent wording requires review rather than a false error or automatic pass',()=>{
 const c=fixture.cases.find(c=>c.id==='C19');const r=evaluateCase(c,'도운은 은재에게 빌릴 수 있다는 소식만 전했다. 받아 왔다는 소식은 전하지 않은 상태였다.');assert.equal(r.status,'REVIEW');
 assert.equal(evaluateCase(c,'이 문장은 해당 사실을 해석할 수 없는 새 표현이다.').status,'REVIEW');
});
test('each of the four axes is reported separately; irrelevant checks are not passes',()=>{
 const rows=fixture.cases.map(c=>({case_id:c.id,summary:c.accepted[0].summary})),r=evaluateCandidates(fixture,rows);assert.equal(r.status,'PASS');assert.equal(r.complete,true);assert.equal(r.counts.PASS,22);
 for(const axis of AXES){assert.equal(r.axes[axis].PASS,fixture.cases.filter(c=>c.axes.includes(axis)).length);assert.equal(r.axes[axis].NOT_APPLICABLE,fixture.cases.filter(c=>!c.axes.includes(axis)).length);}
});
test('missing cases, duplicate or unknown identities, and empty outputs cannot silently pass',()=>{
 const c=fixture.cases[0];let r=evaluateCandidates(fixture,[]);assert.equal(r.complete,false);assert.equal(r.status,'REVIEW');assert.equal(r.counts.NOT_RUN,22);
 r=evaluateCandidates(fixture,[{case_id:c.id,summary:c.accepted[0].summary}]);assert.equal(r.counts.NOT_RUN,21);assert.equal(r.status,'REVIEW');
 assert.throws(()=>evaluateCandidates(fixture,[{case_id:'unknown',summary:'x'}]),/Unknown/);assert.throws(()=>evaluateCandidates(fixture,[{case_id:c.id,summary:'x'},{case_id:c.id,summary:'y'}]),/Duplicate/);
 assert.throws(()=>evaluateCandidates(fixture,[{case_id:c.id,source_id:c.source_id,summary:'x'}]),/exactly one/);
 assert.equal(evaluateCase(c,' ').status,'FAIL');
 const invalid=structuredClone(c);invalid.rule.required=[];assert.throws(()=>evaluateCase(invalid,'x'),/Invalid regression/);
 const shared=fixture.cases.filter(x=>x.source_id===fixture.cases.find(x=>x.id==='C15').source_id),source=shared[0].source_id;const bySource=evaluateCandidates(fixture,[{source_id:source,summary:shared[0].original}]);assert.equal(bySource.counts.PASS,shared.length);
});
test('declared numerical values cannot pass just because another condition matches',()=>{
 const c=fixture.cases.find(c=>c.id==='C04');assert.notEqual(evaluateCase(c,'H는 같은 입력 60개에서 24초에서 31초로 변경됐다.').status,'PASS');
 const u=fixture.cases.find(c=>c.id==='C07');assert.notEqual(evaluateCase(u,'H의 메모리는 2048MB다. 1GB=1024MB로 정했다.').status,'PASS');
});
test('CLI separates known-error detection from new candidate grading and returns nonzero for incomplete runs',()=>{
 const {spawnSync}=require('node:child_process'),os=require('node:os'),dir=fs.mkdtempSync(path.join(os.tmpdir(),'pma-preservation-')),cli=path.join(__dirname,'../tools/check-summary-preservation.cjs');
 const run=args=>spawnSync(process.execPath,[cli,...args],{encoding:'utf8'});
 try{
  let r=run(['--self-check']);assert.equal(r.status,0,r.stderr);let j=JSON.parse(r.stdout);assert.equal(j.mode,'checker-self-check');assert.equal(j.known_bad_detected,22);assert.equal(j.accepted_passed,88);
  const file=path.join(dir,'candidates.json');fs.writeFileSync(file,JSON.stringify(fixture.cases.map(c=>({case_id:c.id,summary:c.failed_summary}))));r=run(['--candidates',file]);assert.equal(r.status,1);j=JSON.parse(r.stdout);assert.equal(j.mode,'candidate-regression');assert.equal(j.counts.FAIL,22);
  fs.writeFileSync(file,'[]');r=run(['--candidates',file]);assert.equal(r.status,2);assert.equal(JSON.parse(r.stdout).counts.NOT_RUN,22);
  r=run(['--self-check','--candidates',file]);assert.equal(r.status,2);
 }finally{fs.rmSync(dir,{recursive:true,force:true});}
});
