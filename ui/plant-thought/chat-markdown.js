'use strict';
// markdown-it 15.0.3 is vendored locally, with its MIT license alongside it.
(function(root,factory){
  if(typeof module==='object'&&module.exports)module.exports=factory(require('./markdown-it.min.js'));
  else root.PlantMarkdown=factory(root.markdownit);
})(typeof window==='object'?window:globalThis,function(markdownit){
  if(typeof markdownit!=='function')return null;
  // Raw HTML is always text. Images remain literal and cannot issue network requests.
  const md=markdownit({html:false,breaks:true,linkify:false,typographer:false}).disable('image');
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
  md.renderer.rules.fence=(tokens,index,options,env,self)=>fence(tokens,index,options,env,self).replace('<pre>','<pre tabindex="0" aria-label="코드 블록">');
  return Object.freeze({render:text=>md.render(String(text??''))});
});
