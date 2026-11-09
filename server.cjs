const http=require('node:http'),fs=require('node:fs'),path=require('node:path'),{createApi}=require('./local/api.cjs');
const root=__dirname,api=createApi(root),port=Number(process.env.PORT||4319);
const staticFiles=new Map([['/usage-ui.js','usage-ui.js'],['/usage-ui.css','usage-ui.css'],['/structured-lab.js','structured-lab.js'],['/summary','summary.html'],['/summary.html','summary.html'],['/summary.js','summary.js'],['/summary.css','summary.css'],['/summary-lab.js','summary-lab.js'],['/','index.html'],['/index.html','index.html'],['/app.js','app.js'],['/style.css','style.css'],['/baseline','baseline.html'],['/baseline/','baseline.html'],['/baseline.html','baseline.html'],['/baseline.js','baseline.js'],['/timing.js','timing.js'],['/baseline.css','baseline.css'],['/stage-review.js','stage-review.js'],['/stage-review.css','stage-review.css'],['/answer-evaluation.js','answer-evaluation.js'],['/answer-evaluation.css','answer-evaluation.css']]);
const server=http.createServer(async(req,res)=>{
 const url=new URL(req.url,'http://127.0.0.1:'+port);if(await api.handle(req,res,url))return;
 const file=staticFiles.get(url.pathname);if(!file||req.method!=='GET'){res.writeHead(404);res.end('Not found');return;}
 const full=path.join(root,file);if(!fs.existsSync(full)){res.writeHead(404);res.end('Not found');return;}
 res.writeHead(200,{'Content-Type':file.endsWith('.js')?'text/javascript; charset=utf-8':file.endsWith('.css')?'text/css; charset=utf-8':'text/html; charset=utf-8','Cache-Control':'no-cache','X-Content-Type-Options':'nosniff','Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"});fs.createReadStream(full).pipe(res);
});
server.listen(port,'127.0.0.1',()=>console.log('Local: http://127.0.0.1:'+port+'/baseline'));
server.on('error',e=>{console.error(e.message);api.close().finally(()=>process.exit(1));});
let closing=false;async function close(){if(closing)return;closing=true;await api.close();server.close(()=>process.exit(0));setTimeout(()=>process.exit(0),2000).unref();}
process.on('SIGINT',close);process.on('SIGTERM',close);
