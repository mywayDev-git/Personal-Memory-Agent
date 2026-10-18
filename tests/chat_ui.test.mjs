import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';

const code = await readFile(new URL('../pma/static/chat.js', import.meta.url), 'utf8');
const {setupChat} = await import('data:text/javascript;base64,' + Buffer.from(code).toString('base64'));

class Element {
  constructor(tag, text = '') { this.tag = tag; this.textContent = text; this.children = []; this.listeners = {}; this.classList = {add() {},remove() {},toggle() {}}; this.style={}; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  setAttribute() {}
  addEventListener(name, fn) { this.listeners[name] = fn; }
  focus() {}
}
function descendants(element, tag) {
  return [...(element.tag === tag ? [element] : []), ...element.children.flatMap(child => descendants(child, tag))];
}

test('citation offsets use code points and malformed layouts retain all verified items', async () => {
  const elements = new Map();
  const get = id => { if (!elements.has(id)) elements.set(id, new Element('div')); return elements.get(id); };
  globalThis.document = {getElementById: get, querySelector: get, createTextNode: text => new Element('#text', text)};
  const response = {
    status: 'answered',
    items: [{text: '서울숲에 갔다.', citations: ['m1']}, {text: '<script>not executable</script>', citations: []}],
    blocks: [null, {type: 'script'}, {type: 'table', item_indices: ['map', -1, 0]}],
    citation_details: [{item_index: 0, memory_id: 'm1', record_id:'r1', revision_id:'v1', start: 2, end: 5, quote: '서울숲'}],
  };
  const session = {id: 's', title: '대화', messages: [{question: '어디?', state: 'completed', response,
    evidence: [{id: 'm1', record_id:'r1', revision_id:'v1', version: 1, source_text: '😊 서울숲에 갔다.'}]}]};
  const submitted = [];
  setupChat({
    api: async (path, method, body) => {
      if (method === 'POST') submitted.push(body);
      return path === '/chat/sessions' ? {items: [session]} : session;
    },
    node: (tag, text) => new Element(tag, text),
    action: (text, fn) => Object.assign(new Element('button', text), {click: fn}),
    notice: () => {}, today: () => '2026-10-18',
  });
  await get('chat-refresh').listeners.click();
  await get('chat-list').children[0].click();
  assert.equal(get('chat-evidence-panel').hidden, true);
  await descendants(get('chat-messages'), 'button').find(e=>e.textContent === '근거 1건').click();
  assert.deepEqual(descendants(get('chat-evidence-content'), 'mark').map(e => e.textContent), ['서울숲']);
  assert(descendants(get('chat-messages'), 'p').some(e => e.textContent === '<script>not executable</script>'));
  assert.equal(descendants(get('chat-messages'), 'script').length, 0);
  Object.assign(session.messages[0], {state: 'failed', request_id: 'retry', request_today: '2026-10-17'});
  await get('chat-refresh').listeners.click();
  const retry = descendants(get('chat-messages'), 'button').find(e => e.textContent === '다시 시도');
  await retry.click();
  assert.equal(submitted[0].today, '2026-10-17');
  assert.equal(submitted[0].request_id, 'retry');
});

test('deduplicates original records, rejects forged spans, and expires old clarification choices', async () => {
  const elements = new Map();
  const get = id => { if (!elements.has(id)) elements.set(id,new Element('div')); return elements.get(id); };
  globalThis.document = {getElementById:get,querySelector:get,createTextNode:t=>new Element('#text',t)};
  const source = {record_id:'r',revision_id:'v',version:1,source_text:'동아리 민수'};
  const response = {status:'needs_clarification',clarification:'어떤 민수인가요?',items:[{text:'동아리 민수',citations:['a','b','bad']}],
    citation_details:['a','b'].map(memory_id=>({memory_id,item_index:0,record_id:'r',revision_id:'v',start:0,end:6,quote:'동아리 민수'})).concat({memory_id:'bad',item_index:0,record_id:'r',revision_id:'forged',start:0,end:6,quote:'동아리 민수'})};
  const session={id:'s',title:'민수',messages:[{id:'m',question:'민수는 누구?',state:'completed',response,evidence:['a','b','bad'].map(id=>({...source,id}))}]};
  const sent=[];
  setupChat({api:async(path,method,body)=>{if(method==='POST')sent.push(body);return path==='/chat/sessions'?{items:[session]}:session;},
    node:(tag,t)=>new Element(tag,t),action:(t,fn)=>Object.assign(new Element('button',t),{click:fn}),notice:()=>{},today:()=> '2026-10-18'});
  await get('chat-refresh').listeners.click(); await get('chat-list').children[0].click();
  let buttons=descendants(get('chat-messages'),'button');
  assert.equal(buttons.filter(b=>b.textContent==='근거 1건').length,1);
  assert.equal(buttons.filter(b=>b.textContent==='근거 2건').length,0);
  await buttons.find(b=>b.textContent==='동아리 민수').click();
  assert.equal(sent[0].context_message_id,'m');
  assert.equal(sent[0].question,'동아리 민수');
  session.messages[0].error_code='SOURCE_MODIFIED';
  await get('chat-refresh').listeners.click();
  buttons=descendants(get('chat-messages'),'button');
  assert(!buttons.some(b=>b.textContent==='동아리 민수'));
  assert(descendants(get('chat-messages'),'p').some(p=>p.textContent.includes('만료')));
  let prevented=false;
  get('chat-question').listeners.keydown({key:'Enter',isComposing:true,preventDefault:()=>{prevented=true;}});
  assert.equal(prevented,false);
});

test('restores general mode, preserves retry mode, and renders code as inert text', async () => {
  const elements = new Map();
  const get = id => { if (!elements.has(id)) elements.set(id,new Element('div')); return elements.get(id); };
  globalThis.document = {getElementById:get,querySelector:get,createTextNode:t=>new Element('#text',t)};
  const session = {id:'s',title:'Code',mode:'general',messages:[{id:'m',request_id:'retry',mode:'general',question:'example',state:'completed',response:{status:'answered',items:[{text:'```python\n<script>alert(1)</script>\n```',citations:[],source_type:'general'},{text:'| 항목 | 값 |\n| --- | --- |\n| 코드 | 안전 |',citations:[]}]}}]};
  const sent=[];
  setupChat({api:async(path,method,body)=>{if(method==='POST')sent.push(body);return path==='/chat/sessions'?{items:[session]}:session;},node:(tag,t)=>new Element(tag,t),action:(t,fn)=>Object.assign(new Element('button',t),{click:fn}),notice:()=>{},today:()=> '2026-10-18'});
  await get('chat-refresh').listeners.click(); await get('chat-list').children[0].click();
  assert.equal(get('chat-mode').value,'general');
  assert.equal(descendants(get('chat-messages'),'th').length,2);
  assert.equal(descendants(get('chat-messages'),'td').length,2);
  assert.equal(descendants(get('chat-messages'),'code')[0].textContent,'<script>alert(1)</script>\n');
  assert.equal(descendants(get('chat-messages'),'script').length,0);
  session.messages[0].state='failed';
  await get('chat-refresh').listeners.click();
  get('chat-mode').value='memory';
  await descendants(get('chat-messages'),'button').find(b=>b.textContent==='다시 시도').click();
  assert.equal(sent[0].mode,'general');
});
