import {EditorState,StateField,StateEffect,Compartment} from '@codemirror/state';
import {EditorView,Decoration,WidgetType,keymap,drawSelection,placeholder} from '@codemirror/view';
import {history,historyKeymap,defaultKeymap,indentWithTab,redo} from '@codemirror/commands';
import {markdown,markdownLanguage} from '@codemirror/lang-markdown';
import {syntaxTree} from '@codemirror/language';

const focusEffect=StateEffect.define();
function activeLineNumbers(state,focused){
 const active=new Set();if(!focused)return active;
 for(const range of state.selection.ranges){const start=state.doc.lineAt(range.from).number,end=state.doc.lineAt(Math.max(range.from,range.to-(range.empty?0:1))).number;for(let n=start;n<=end;n++)active.add(n);}
 return active;
}
class Marker extends WidgetType{
 constructor(text,kind){super();this.text=text;this.kind=kind;}eq(other){return this.text===other.text&&this.kind===other.kind;}
 toDOM(){const span=document.createElement('span');span.className='md-render-marker '+this.kind;span.textContent=this.text;span.setAttribute('aria-hidden','true');return span;}
}
class Rule extends WidgetType{
 toDOM(){const span=document.createElement('span');span.className='md-render-rule';span.setAttribute('aria-hidden','true');return span;}
}
class Entity extends WidgetType{
 constructor(text){super();this.text=text;}eq(other){return this.text===other.text;}
 toDOM(){const span=document.createElement('span'),decoder=document.createElement('textarea');decoder.innerHTML=this.text;span.textContent=decoder.value;return span;}
}
class TableLine extends WidgetType{
 constructor(source,line,index){super();this.source=source;this.line=line;this.index=index;}eq(other){return this.source===other.source&&this.line===other.line&&this.index===other.index;}
 toDOM(view){
  const div=document.createElement('div');div.className='md-render-table-line ai-answer';
  if(this.index===1){div.classList.add('md-table-delimiter');}
  else{
   const template=document.createElement('div');template.innerHTML=window.PlantMarkdown.render(this.source);const row=template.querySelectorAll('tr')[this.index===0?0:this.index-1];
   if(row){const table=document.createElement('table'),group=document.createElement(this.index===0?'thead':'tbody');group.append(row);table.append(group);div.append(table);}
  }
  div.addEventListener('mousedown',event=>{event.preventDefault();view.dispatch({selection:{anchor:view.state.doc.line(this.line).to},scrollIntoView:true});view.focus();});return div;
 }
 ignoreEvent(){return false;}
}
export function decorate(state,focused){
 const ranges=[],active=activeLineNumbers(state,focused),doc=state.doc,lines=new Map();
 const lineClass=(number,name)=>{if(active.has(number))return;const classes=lines.get(number)||new Set();classes.add(name);lines.set(number,classes);};
 const mark=(from,to,cls)=>{if(to<=from)return;for(let n=doc.lineAt(from).number;n<=doc.lineAt(Math.max(from,to-1)).number;n++){if(active.has(n))continue;const line=doc.line(n),a=Math.max(from,line.from),b=Math.min(to,line.to);if(b>a)ranges.push(Decoration.mark({class:cls}).range(a,b));}};
 const replace=(from,to,widget)=>{if(to>from&&!active.has(doc.lineAt(from).number))ranges.push(Decoration.replace({widget}).range(from,to));};
 syntaxTree(state).iterate({enter(ref){
  const name=ref.name,node=ref.node,from=ref.from,to=ref.to,first=doc.lineAt(from),last=doc.lineAt(Math.max(from,to-1));
  if(name==='Image')return false; // Match the shared preview: no remote images.
  if(name==='Table'){
   const source=doc.sliceString(from,to);for(let n=first.number;n<=last.number;n++)if(!active.has(n)){
    const line=doc.line(n);if(line.length)ranges.push(Decoration.replace({widget:new TableLine(source,n,n-first.number),block:true,inclusive:false}).range(line.from,line.to));
   }return false;
  }
  if(/^(?:ATX|Setext)Heading[1-6]$/.test(name))for(let n=first.number;n<=last.number;n++)lineClass(n,'md-render-heading md-heading-'+name.at(-1));
  if(name==='StrongEmphasis')mark(from,to,'md-render-strong');
  if(name==='Emphasis')mark(from,to,'md-render-em');
  if(name==='Strikethrough')mark(from,to,'md-render-strike');
  if(name==='InlineCode')mark(from,to,'md-render-code');
  if(name==='FencedCode'||name==='CodeBlock')for(let n=first.number;n<=last.number;n++)lineClass(n,'md-render-code-line');
  if(name==='Blockquote')for(let n=first.number;n<=last.number;n++)lineClass(n,'md-render-quote');
  if(name==='Link'||name==='Autolink')mark(from,to,'md-render-link');
  if(name==='HeaderMark'||name==='QuoteMark')replace(from,to+(doc.sliceString(to,to+1)===' '?1:0));
  if(['EmphasisMark','StrikethroughMark','CodeMark','LinkMark'].includes(name))replace(from,to);
  if(name==='URL'&&node.parent?.name==='Link')replace(from,to);
  if(name==='LinkTitle'||name==='LinkLabel')replace(from,to);
  if(name==='ListMark'){const text=doc.sliceString(from,to),task=/^\s+\[[ xX]\]\s/.test(doc.sliceString(to,first.to));replace(from,to,task?undefined:new Marker(/^[-+*]$/.test(text)?'•':text,'md-list-marker'));}
  if(name==='TaskMarker')replace(from,to,new Marker(/[xX]/.test(doc.sliceString(from,to))?'☑':'☐','md-task-marker'));
  if(name==='HorizontalRule')replace(from,to,new Rule());
  if(name==='Escape')replace(from,from+1);
  if(name==='Entity')replace(from,to,new Entity(doc.sliceString(from,to)));
 }});
 for(const [number,classes]of lines)ranges.push(Decoration.line({class:[...classes].join(' ')}).range(doc.line(number).from));
 for(const number of active)ranges.push(Decoration.line({class:'md-active-source'}).range(doc.line(number).from));
 return Decoration.set(ranges,true);
}
const livePreview=StateField.define({
 create:state=>({focused:false,decorations:decorate(state,false)}),
 update(value,tr){let focused=value.focused;for(const effect of tr.effects)if(effect.is(focusEffect))focused=effect.value;
  return tr.docChanged||tr.selection||focused!==value.focused||syntaxTree(tr.startState)!==syntaxTree(tr.state)?{focused,decorations:decorate(tr.state,focused)}:value;},
 provide:field=>EditorView.decorations.from(field,value=>value.decorations)
});
const language=()=>markdown({base:markdownLanguage,completeHTMLTags:false,pasteURLAsLink:false});
export function previewState(text,anchor=0,head=anchor){return EditorState.create({doc:text,selection:{anchor,head},extensions:[language(),livePreview]});}
export function previewRanges(text,anchor=0,head=anchor,focused=true){const state=previewState(text,anchor,head),result=[];decorate(state,focused).between(0,state.doc.length,(from,to,value)=>{result.push({from,to,class:value.spec.class||'',widget:value.spec.widget?.constructor.name||'',replacement:value.spec.widget!==undefined||value.spec.class===undefined});});return result;}

export function mount(textarea,options={}){
 if(!textarea||textarea.dataset.markdownMounted)return null;textarea.dataset.markdownMounted='true';
 const host=document.createElement('div');host.className='record-markdown-editor';textarea.after(host);
 const hint=document.createElement('p');hint.className='record-markdown-hint';hint.textContent='현재 줄은 마크다운 원문으로, 다른 줄은 서식이 적용된 모습으로 보여요.';host.before(hint);
 const native=Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value'),readonly=new Compartment();let syncing=false;
 const extensions=[
  language(),history(),drawSelection({cursorBlinkRate:0,drawRangeCursor:false}),placeholder(options.placeholder||'오늘 마음에 남은 일을 마크다운으로 기록해 보세요.'),keymap.of([{key:'Mod-Shift-z',run:redo,preventDefault:true},...defaultKeymap,...historyKeymap,indentWithTab]),EditorView.lineWrapping,livePreview,
  EditorView.focusChangeEffect.of((state,focused)=>focusEffect.of(focused)),
  EditorView.contentAttributes.of({'aria-label':options.label||'기록 내용','aria-multiline':'true','spellcheck':'false'}),
  readonly.of([EditorState.readOnly.of(textarea.disabled),EditorView.editable.of(!textarea.disabled)]),
  EditorView.updateListener.of(update=>{if(update.docChanged&&!syncing){native.set.call(textarea,update.state.doc.toString());textarea.dispatchEvent(new Event('input',{bubbles:true}));}}),
  EditorView.theme({'&':{backgroundColor:'transparent'},'.cm-scroller':{fontFamily:'inherit'},'.cm-focused':{outline:'none'}})
 ];
 const view=new EditorView({parent:host,state:EditorState.create({doc:textarea.value,extensions})});
 Object.defineProperty(textarea,'value',{configurable:true,get(){return native.get.call(this);},set(value){native.set.call(this,value);const next=native.get.call(this);if(view.state.doc.toString()!==next){syncing=true;try{view.setState(EditorState.create({doc:next,extensions}));view.dispatch({effects:readonly.reconfigure([EditorState.readOnly.of(textarea.disabled),EditorView.editable.of(!textarea.disabled)])});}finally{syncing=false;}}}});
 const nativeFocus=textarea.focus,wasHidden=textarea.hidden,oldAria=textarea.getAttribute('aria-hidden');let destroyed=false;textarea.classList.add('record-markdown-source');textarea.focus=()=>view.focus();textarea.hidden=true;textarea.setAttribute('aria-hidden','true');
 const observer=new MutationObserver(()=>{if(!destroyed)view.dispatch({effects:readonly.reconfigure([EditorState.readOnly.of(textarea.disabled),EditorView.editable.of(!textarea.disabled)])});});observer.observe(textarea,{attributes:true,attributeFilter:['disabled']});
 const destroy=view.destroy.bind(view);view.destroy=()=>{if(destroyed)return;destroyed=true;observer.disconnect();destroy();delete textarea.value;textarea.focus=nativeFocus;textarea.hidden=wasHidden;textarea.classList.remove('record-markdown-source');if(oldAria==null)textarea.removeAttribute('aria-hidden');else textarea.setAttribute('aria-hidden',oldAria);delete textarea.dataset.markdownMounted;host.remove();hint.remove();};
 return view;
}
if(typeof document!=='undefined')mount(document.getElementById('recordBody'));
