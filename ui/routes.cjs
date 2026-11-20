'use strict';
const fs=require('node:fs'),path=require('node:path');
const plantFiles=new Map([
  ['/','index.html'],['/index.html','index.html'],['/plant-thought','index.html'],['/plant-thought/','index.html'],
  ...['index.html','style.css','preview.css','layout.js','preview.js','diary-dates.js','archive-data.js','archive-preview.js','record-evidence.js','archive-preview.css','event-network.js','event-network.css','archive-floating.js','archive-floating.css','conversation-context.js','dialogue-map.js','chat-version.js','search-modes.js','search-select.js','graph-index-controls.js','chat-state.js','record-drafts.js','record-markdown.js','markdown-editor.js','record-markdown.css','markdown-it.min.js','chat-markdown.js','chat-connect.js','chat-connect.css','archive-readiness.js','archive-readiness.css','data-transfer.js','data-reset-ui.js','data-transfer.css','response-inspector.js','response-inspector.css','response-floating.js','response-floating.css','floating-workspace.js','dialogue-floating.js','dialogue-floating.css'].map(name=>['/plant-thought/'+name,name]),
]);
function handleUi(req,res,url,root,{connected=false}={}){
  const file=plantFiles.get(url.pathname);
  if(!file&&url.pathname!=='/memorylab-preview')return false;
  if(req.method!=='GET'&&req.method!=='HEAD'){res.writeHead(405,{'Allow':'GET, HEAD'});res.end();return true;}
  const full=file?path.join(root,'ui','plant-thought',file):path.join(root,'index.html');
  if(!fs.existsSync(full)){res.writeHead(404);res.end('UI file not found');return true;}
  const connectPolicy=connected?"'self'":"'none'";
  res.writeHead(200,{'Content-Type':full.endsWith('.js')?'text/javascript; charset=utf-8':full.endsWith('.css')?'text/css; charset=utf-8':'text/html; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff',
    'Content-Security-Policy':file?"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; connect-src "+connectPolicy+"; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'":"default-src 'self'; script-src 'self'; style-src 'self'; connect-src "+connectPolicy+"; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"});
  if(req.method==='HEAD')res.end();
  else if(!file){
    let html=fs.readFileSync(full,'utf8');
    html=html.replaceAll('http://127.0.0.1:4319/','/').replace('<nav>','<nav><a class="nav" href="/#memorylab">← <span>서재로 돌아가기</span></a>');
    res.end(html);
  }else if(connected&&file==='index.html'){
    let html=fs.readFileSync(full,'utf8');
    html=html.replace('</head>','<link rel="stylesheet" href="/plant-thought/chat-connect.css"><link rel="stylesheet" href="/plant-thought/record-markdown.css"><link rel="stylesheet" href="/plant-thought/archive-readiness.css"><link rel="stylesheet" href="/plant-thought/data-transfer.css"><link rel="stylesheet" href="/plant-thought/response-inspector.css"><link rel="stylesheet" href="/plant-thought/response-floating.css"><link rel="stylesheet" href="/plant-thought/dialogue-floating.css"></head>');
    html=html.replace('</body>','<script src="/plant-thought/conversation-context.js"></script><script src="/plant-thought/dialogue-map.js"></script><script src="/plant-thought/chat-version.js"></script><script src="/plant-thought/search-modes.js"></script><script src="/plant-thought/search-select.js"></script><script src="/plant-thought/graph-index-controls.js"></script><script src="/plant-thought/chat-state.js"></script><script src="/plant-thought/record-drafts.js"></script><script src="/plant-thought/markdown-it.min.js"></script><script src="/plant-thought/chat-markdown.js"></script><script src="/plant-thought/record-markdown.js"></script><script src="/plant-thought/markdown-editor.js"></script><script src="/plant-thought/response-inspector.js"></script><script src="/plant-thought/chat-connect.js"></script><script src="/plant-thought/archive-readiness.js"></script><script src="/plant-thought/data-transfer.js"></script><script src="/plant-thought/response-floating.js"></script><script src="/plant-thought/floating-workspace.js"></script><script src="/plant-thought/dialogue-floating.js"></script></body>');
    res.end(html);
  }else{const stream=fs.createReadStream(full);stream.on('error',()=>res.destroy());stream.pipe(res);}return true;
}
module.exports={handleUi};
