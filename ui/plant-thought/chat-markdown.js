'use strict';
// markdown-it 15.0.3 is vendored locally, with its MIT license alongside it.
(function(root,factory){
  if(typeof module==='object'&&module.exports)module.exports=factory(require('./markdown-it.min.js'));
  else root.PlantMarkdown=factory(root.markdownit);
})(typeof window==='object'?window:globalThis,function(markdownit){
  if(typeof markdownit!=='function')return null;
  // Raw HTML is always text. Images remain literal and cannot issue network requests.
  const md=markdownit({html:false,breaks:true,linkify:false,typographer:false}).disable('image');
  // Render task markers ourselves, rather than enabling raw HTML from notes.
  md.core.ruler.after('inline','task_checkboxes',state=>{
    for(let i=2;i<state.tokens.length;i++){
      const token=state.tokens[i];if(token.type!=='inline'||state.tokens[i-2].type!=='list_item_open')continue;
      const first=token.children?.[0],match=first?.type==='text'&&token.content.match(/^\[([ xX])\]\s+/);if(!match)continue;
      first.content=first.content.slice(match[0].length);const checkbox=new state.Token('html_inline','',0);
      checkbox.content='<input class="markdown-task-checkbox" type="checkbox" disabled'+(match[1].toLowerCase()==='x'?' checked':'')+' aria-label="'+(match[1].toLowerCase()==='x'?'완료':'미완료')+'"> ';
      token.children.unshift(checkbox);state.tokens[i-2].attrJoin('class','markdown-task-item');
    }
  });
  md.core.ruler.after('block','record_source_blocks',state=>{
    if(!state.env.recordSourceMap)return;
    const source=state.env.recordSourceText??state.src,starts=[0];for(let i=0;i<source.length;i++)if(source[i]==='\r'){if(source[i+1]==='\n')i++;starts.push(i+1);}else if(source[i]==='\n')starts.push(i+1);starts.push(source.length);
    for(const token of state.tokens){
      if(!token.map)continue;const from=starts[token.map[0]]??source.length,to=starts[token.map[1]]??source.length;
      if(['fence','code_block'].includes(token.type))token.meta={...token.meta,recordSource:{from,to}};
      else if(['paragraph_open','heading_open','tr_open','hr'].includes(token.type)){token.attrSet('data-record-from',String(from));token.attrSet('data-record-to',String(to));token.hidden=false;}
    }
  });
  const sourceAttrs=token=>token.meta?.recordSource?' data-record-from="'+token.meta.recordSource.from+'" data-record-to="'+token.meta.recordSource.to+'"':'';
  const validateLink=md.validateLink;
  md.validateLink=url=>/^(?:https?:\/\/|mailto:)/i.test(url)&&validateLink(url);
  const linkOpen=md.renderer.rules.link_open||((tokens,index,options,env,self)=>self.renderToken(tokens,index,options));
  md.renderer.rules.link_open=(tokens,index,options,env,self)=>{
    tokens[index].attrSet('target','_blank');
    tokens[index].attrSet('rel','noopener noreferrer');
    return linkOpen(tokens,index,options,env,self);
  };
  md.renderer.rules.table_open=()=>'<div class="ai-table-scroll" role="region" aria-label="답변 표" tabindex="0"><table>\n';
  md.renderer.rules.table_close=()=>'</table></div>\n';
  const fence=md.renderer.rules.fence;
  md.renderer.rules.fence=(tokens,index,options,env,self)=>fence(tokens,index,options,env,self).replace('<pre>','<pre tabindex="0" aria-label="코드 블록"'+sourceAttrs(tokens[index])+'>');
  const codeBlock=md.renderer.rules.code_block;
  md.renderer.rules.code_block=(tokens,index,options,env,self)=>codeBlock(tokens,index,options,env,self).replace('<pre>','<pre'+sourceAttrs(tokens[index])+'>');
  return Object.freeze({render:(text,options={})=>md.render(String(text??''),{recordSourceMap:options.sourceMap===true,recordSourceText:String(text??'')})});
});
