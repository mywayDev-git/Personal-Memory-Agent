// No browser/server/models: exercise case rendering and selection against a small DOM double.
import assert from 'node:assert/strict';
import {CaseInspector,caseRow,shorten,answerState} from '../pma/static/evaluation-case-view.js';

let focused=null;
class Element {
  children=[];dataset={};attrs={};hidden=false;_text='';parentElement=null;
  constructor(tag){this.tagName=tag;const values=new Set();this.classList={add:v=>values.add(v),remove:v=>values.delete(v),contains:v=>values.has(v),toggle:(v,on)=>{if(on??!values.has(v))values.add(v);else values.delete(v);}};}
  set textContent(value){this._text=String(value??'');this.children=[];}
  get textContent(){return this._text+this.children.map(n=>n.textContent??'').join('');}
  set className(value){for(const name of value.split(' '))this.classList.add(name);}
  append(...values){for(const value of values){if(value&&typeof value==='object')value.parentElement=this;this.children.push(typeof value==='string'?{textContent:value}:value);}}
  replaceChildren(...values){this.children=[];this._text='';this.append(...values);}
  setAttribute(key,value){this.attrs[key]=String(value);}
  getAttribute(key){return this.attrs[key];}
  removeAttribute(key){delete this.attrs[key];}
  focus(){focused=this;}
  scrollIntoView(){}
  closest(selector){const tags=selector.split(',');for(let el=this;el;el=el.parentElement)if(tags.includes(el.tagName))return el;return null;}
}
const ids=new Map();
for(const id of ['inspector','inspector-title','answer-detail','behavior-detail','evidence','trace','case-summary','case-detail-notice']){const el=new Element('div');el.id=id;ids.set(id,el);}
const tabs=['answer','behavior','evidence','trace'].map(name=>{const tab=new Element('button');tab.dataset.caseTab=name;tab.setAttribute('aria-controls',({answer:'answer-detail',behavior:'behavior-detail',evidence:'evidence',trace:'trace'})[name]);return tab;});
globalThis.document={getElementById:id=>ids.get(id),createElement:tag=>new Element(tag),querySelectorAll:selector=>selector==='[data-case-tab]'?tabs:[]};
const labels={answer:'답변',clarify:'되물음',abstain:'답변 보류',pass:'통과',fail:'실패',pending_review:'검토 대기'};
const selected=[];
const longQuestion='질문 원문\n'+ '긴 질문 🙂 '.repeat(50);
const row=caseRow({case_id:'one',question_preview:longQuestion,expected_behavior:'answer',response_behavior:'abstain',verdict:'fail',expected_preview:'예상 '.repeat(70),actual_preview:'실제 '.repeat(70),latency_ms:15},
  {runId:'run',selectedId:'one',select:id=>selected.push(id),labels,failureNames:{}});
assert(row.classList.contains('is-selected'));
assert(!row.textContent.includes(longQuestion),'full question must not expand list rows');
assert.equal(row.children.length,5);
assert.equal(shorten('🙂'.repeat(100),88),'🙂'.repeat(88)+'…');
const link=row.children[0].children[0];let prevented=false;
link.onclick({button:0,preventDefault(){prevented=true;}});
assert(prevented);assert.deepEqual(selected,['one']);
link.onclick({button:0,ctrlKey:true,preventDefault(){assert.fail('preserve new-tab behavior');}});
assert.deepEqual(selected,['one']);

const calls=[],pending=new Map();
const api=path=>{calls.push(path);return new Promise(resolve=>pending.set(path,resolve));};
const inspector=new CaseInspector({api,labels,failureNames:{},stageNames:{question:'질문 이해'},gradeNames:{behavior_correct:'예상 동작 일치'}});
const data=id=>({case_id:id,question:`${id} 질문\n전체 원문 <script>alert(1)</script>`,expected_answer:'["0.89"]',actual_answer:`${id} 실제 답변\n전체 내용`,expected_behavior:'answer',response_behavior:'abstain',verdict:'fail',latency_ms:12,
  metadata:{scenario:{steps:[{action:'chat',question:'예상 질문'}]}},
  evaluation:{behavior_correct:false,observation:{steps:[{action:'chat',response:{status:'answered',items:[{text:'수집한 응답'}]},latency_ms:1},{action:'delete',response:{items:[{text:'이전 답변을 삭제 응답으로 표시하면 안 됨'}]},latency_ms:2}]}}});
const first=inspector.open('run','a');
const second=inspector.open('run','b',{focus:true});
pending.get('/runs/run/cases/b')(data('b'));await second;
pending.get('/runs/run/cases/a')(data('a'));await first;
assert.equal(inspector.data.case_id,'b','late result from previous selection must be ignored');
assert(ids.get('answer-detail').textContent.includes('b 질문\n전체 원문 <script>'));
assert(!ids.get('answer-detail').textContent.includes('a 질문'));
assert.equal(focused,ids.get('inspector-title'));
assert.equal(calls.length,2,'trace must not be loaded merely by opening a case');
inspector.setTab('behavior');
assert.equal(ids.get('behavior-detail').hidden,false);
assert.equal(ids.get('answer-detail').hidden,true);
assert(ids.get('behavior-detail').textContent.includes('실제로 기록된 단계'));
assert(!ids.get('behavior-detail').textContent.includes('이전 답변을 삭제 응답으로 표시하면 안 됨'));
assert.equal(tabs[1].getAttribute('aria-selected'),'true');
tabs[1].onkeydown({key:'ArrowLeft',preventDefault(){}});
assert.equal(inspector.tab,'answer');assert.equal(tabs[0].tabIndex,0);
inspector.setTab('trace');
assert.equal(calls.at(-1),'/runs/run/cases/b/trace');
pending.get('/runs/run/cases/b/trace')({trace_status:'partial',stages:[{stage:'question',candidates:[{id:'memory',rank:1,score:'unavailable'}]}]});
await new Promise(resolve=>setImmediate(resolve));
assert(ids.get('trace').textContent.includes('질문 이해'));
assert(!ids.get('trace').textContent.includes('toFixed'));
const third=inspector.open('run','c');
inspector.clear();pending.get('/runs/run/cases/c')(data('c'));await third;
assert.equal(ids.get('inspector').hidden,true);
assert.equal(ids.get('answer-detail').textContent,'');
const masked=inspector.open('run','masked');
pending.get('/runs/run/cases/masked')({case_id:'masked',question:null,expected_answer:null,actual_answer:null,expected_behavior:'answer',response_behavior:null,verdict:'pending_review',text_masked:true});
await masked;const callCount=calls.length;inspector.setTab('trace');
assert.equal(calls.length,callCount,'masked trace must not be requested');
assert(ids.get('case-detail-notice').textContent.includes('원문 상세 조회가 꺼져'));
assert(!ids.get('answer-detail').textContent.includes('<script>'));
const manual={case_id:'manual',question:'입력 기능 검사',expected_answer:'[]',actual_answer:null,verdict:'pending_review',metadata:{scenario:{adapter:'review',review_checklist:['자연어 입력을 확인'],steps:[]}}};
inspector.render(manual);
assert(ids.get('case-detail-notice').textContent.includes('이전 버전의 수동 검토 결과'));
assert(ids.get('answer-detail').textContent.includes('자연어 입력을 확인'));
assert(!ids.get('answer-detail').textContent.includes('예상 답변이 정의되지'));
assert(answerState({verdict:'error'}).actual.includes('실행 중 오류'));
assert(answerState({suite_verdict:'NOT_RUN'}).actual.includes('실행되지 않았'));
assert(answerState({metadata:{scenario:{steps:[{action:'delete'}]}}}).actual.includes('동작을 검사'));
assert(answerState({expected_behavior:'abstain'}).expected.includes('답변을 보류'));
assert(answerState({expected_answer:'[]'}).expected.includes('정확도를 확정할 수 없습니다'));
inspector.render({...data('comparison'),evaluation:{answer_comparison:{status:'REVIEW_REQUIRED',required_facts:[{fact:'0.89',status:'MATCH'},{fact:'민수',status:'MISSING'}],forbidden_facts:[{fact:'0.95',status:'MENTIONED'}],coverage_gaps:['모바일 화면 미검증'],note:'단어 일치만으로 통과하지 않음'}}});
assert(ids.get('answer-detail').textContent.includes('일치 · 필수 사실: 0.89'));
assert(ids.get('answer-detail').textContent.includes('누락 · 필수 사실: 민수'));
assert(ids.get('answer-detail').textContent.includes('언급됨 · 문맥 확인 필요'));
assert(ids.get('answer-detail').textContent.includes('모바일 화면 미검증'));
inspector.render({...data('functional'),suite_verdict:'UNSUPPORTED',metadata:{scenario:{adapter:'contract_tests',steps:[{action:'contract_tests'}]}},evaluation:{probe:{unsupported:true,expected_checks:['지원 밖 필드 거절'],checks:[{id:'field[offset]',outcome:'passed'}]}}});
assert(ids.get('case-summary').textContent.includes('실제 제품 동작 검사'));
assert(ids.get('behavior-detail').textContent.includes('모델 정확도에서는 제외'));
assert(ids.get('behavior-detail').textContent.includes('기능 구현 완료로 계산하지 않습니다'));
assert(ids.get('behavior-detail').textContent.includes('통과 1 / 1개'));
assert(ids.get('behavior-detail').textContent.includes('field[offset]'));
inspector.render({...data('owner'),evaluation:{probe:{checks:[true,true,false]}}});
assert(ids.get('behavior-detail').textContent.includes('통과 2 / 3개'));
assert(!ids.get('behavior-detail').textContent.includes('undefined'));
inspector.render({...data('turn'),evaluation:{turn_contracts:[{step:0,passed:false,expected:{required_facts:['기억 검색']},actual_answer:'관리 단계',missing_facts:['기억 검색'],forbidden_mentions:['관리 단계']}]}});
assert(ids.get('behavior-detail').textContent.includes('1번째 단계: 기대 조건 미충족'));
assert(ids.get('behavior-detail').textContent.includes('관리 단계'));
console.log('case inspector: compact previews, selection races, tabs, lazy traces, keyboard, full text, owner checks, turn failures and masking passed');
