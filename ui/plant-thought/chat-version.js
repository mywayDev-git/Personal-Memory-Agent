'use strict';
(()=>{
 const key='plant-thought-chat-version-v1';let selected='v2';try{const saved=localStorage.getItem(key);if(['v1','v2'].includes(saved))selected=saved;}catch{}
 const bar=document.createElement('div');bar.className='chat-version-bar';bar.setAttribute('aria-label','대화 처리 버전 선택');
 const inner=document.createElement('div'),label=document.createElement('label'),select=document.createElement('select'),note=document.createElement('span');
 label.textContent='대화 버전';label.htmlFor='chatVersionSelect';select.id='chatVersionSelect';select.setAttribute('aria-label','대화 처리 버전');
 for(const [value,text]of [['v1','V1 · 기존 맥락 처리'],['v2','V2 · LLM 대화 지도']]){const option=document.createElement('option');option.value=value;option.textContent=text;select.append(option);}
 select.value=selected;note.textContent='다음 질문부터 적용';inner.append(label,select,note);bar.append(inner);document.querySelector('body>header').prepend(bar);
 window.PlantChatVersion=Object.freeze({current:()=>selected});
 function busy(){return typeof previewThreads!=='undefined'&&previewThreads.some(t=>!t.deletedAt&&t.messages.some(m=>m.kind==='assistant'&&m.status==='pending'&&!m.archived));}
 select.addEventListener('change',()=>{if(busy()){select.value=selected;previewToast('응답을 받은 뒤 버전을 바꿔 주세요.');return;}selected=select.value;try{localStorage.setItem(key,selected);}catch{}if(typeof previewRenderMessages==='function')previewRenderMessages();});
 new MutationObserver(()=>{select.disabled=busy();}).observe(document.getElementById('conversation'),{childList:true,subtree:true});
 window.PlantDialogueMapContent=function(result){
  const t=result.dialogue_trace;if(!t)return null;const node=(tag,text,cls)=>{const e=document.createElement(tag);if(text!=null)e.textContent=text;if(cls)e.className=cls;return e;};
  const details=node('details',null,'chat-dialogue-map');details.append(node('summary','대화 지도 · '+t.parts.length+'개 파트'));
  const list=node('ol');for(const part of t.parts){const selected=t.selected_part_ids.includes(part.id),row=node('li',null,selected?'is-selected':'');row.append(node('strong',part.title),node('small','발언 '+part.start+'–'+part.end+' · '+({open:'이어지는 중',closed:'마무리됨',waiting:'확인 대기'}[part.status]||part.status)+(selected?' · 이번 대화 대상':'')),node('p',part.summary));list.append(row);}details.append(list);
  details.append(node('small','파트 요약은 LLM의 연결 판단입니다. 답변에는 연결된 원문 발언을 함께 사용합니다.'));
  const augmented=node('details',null,'chat-augmented-input');augmented.append(node('summary','이번 입력에 연결한 맥락'),node('p',t.augmented_request));
  augmented.append(node('small',t.source==='archive'?'보관소 원문 조회':t.source==='conversation'?'현재 대화 원문 사용':'보관소 검색 없음'));
  for(const turn of t.references){const quote=node('blockquote');quote.append(node('small',turn.role==='user'?'사용자':'AI의 발언'),node('p',turn.text));augmented.append(quote);}details.append(augmented);return details;
 };
 window.PlantDialogueMapView=function(result){if(!result.dialogue_trace)return null;const button=document.createElement('button');button.type='button';button.className='chat-map-open';button.textContent='대화 지도 열기 · '+result.dialogue_trace.parts.length+'개 파트 ↗';button.addEventListener('click',()=>window.PlantDialogueFloating?.open(result.request_id));return button;};
})();
