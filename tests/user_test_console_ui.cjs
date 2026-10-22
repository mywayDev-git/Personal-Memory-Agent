// Offline UI behavior: no browser, model, or network process is started.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
class Element {
  constructor() {this.children=[];this.listeners={};this.style={};this.classList={toggle(){}};this.value='';this.checked=false;this.textContent=''}
  addEventListener(type, callback) {this.listeners[type]=callback}
  append(...children) {this.children.push(...children)}
  replaceChildren(...children) {this.children=[...children]}
}
async function main() {
  const html=fs.readFileSync('scripts/user_test_console.html','utf8');
  const elements=Object.fromEntries([...html.matchAll(/id="([^"]+)"/g)].map(m=>[m[1],new Element()]));
  for(const [id,value] of Object.entries({device:'gpu',kind:'first',preset:'quick',group:'simple',profile:'baseline'}))elements[id].value=value;
  const requests=[], copied=[];let tick;
  const state={job:null,app_status:'stopped',model_source:'not_started'};
  const context={console,document:{getElementById:id=>elements[id],createElement:()=>new Element(),querySelectorAll:()=>[]},
    location:{hash:'#token=offline',pathname:'/'},sessionStorage:{getItem(){return null},setItem(){}},history:{replaceState(){}},
    navigator:{clipboard:{async writeText(text){copied.push(text)}}},
    window:{open(){return {location:{},close(){}}}},
    setInterval(callback){tick=callback;return 1},clearInterval(){},
    async fetch(path, options){requests.push({path,...options});let value;
      if(path==='/api/examples')value={items:[{question:'그 친구의 직업은?',anchor:'사진 모임 친구 예림은 누구야?'}]};
      else if(path==='/api/status')value=state;
      else if(path==='/api/run')value={run:'fake-ui-only'};
      else if(path==='/api/open-app')value={url:'http://127.0.0.1:18765/#token=offline'};
      else value={ready:true,groups:[],answers:[],restoration:[]};
      return {ok:true,async json(){return value}};
    }};
  vm.runInNewContext(html.split('<script>')[1].split('</script>')[0],context);
  const settle=async()=>{for(let i=0;i<3;i++)await new Promise(setImmediate)};
  await settle();assert.equal(typeof tick,'function',elements.message.textContent);await tick();await settle();
  assert(!requests.some(r=>r.path==='/api/run'||r.path==='/api/open-app'));
  const buttons=elements.examples.children[0].children[1].children;
  assert.equal(buttons.length,2);
  await buttons[0].listeners.click();await buttons[1].listeners.click();
  assert.deepEqual(copied,['사진 모임 친구 예림은 누구야?','그 친구의 직업은?']);
  elements.device.value='cpu';elements.kind.value='repeat';elements['pause-models'].checked=true;
  await elements.trial.listeners.submit({preventDefault(){}});await settle();
  const starts=requests.filter(r=>r.path==='/api/run');assert.equal(starts.length,1);
  assert.deepEqual(JSON.parse(starts[0].body),{device:'cpu',kind:'repeat',preset:'quick',group:'simple',pause_models:true});
  await elements['open-app'].listeners.click();await settle();
  assert.equal(requests.filter(r=>r.path==='/api/open-app').length,1);
  assert.equal(requests.filter(r=>r.path==='/api/run').length,1);
  console.log('UI: view/poll do not start trials; buttons dispatch explicit choices; follow-up questions copy separately');
}
main().catch(error=>{console.error(error);process.exitCode=1});
