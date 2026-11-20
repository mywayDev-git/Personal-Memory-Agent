'use strict';
// Install the versions in plant-thought/markdown-editor.dependencies.json under
// .local/markdown-editor, or pass another node_modules directory as argv[2].
const fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'..'),deps=path.resolve(process.argv[2]||path.join(root,'.local/markdown-editor/node_modules')),dir=path.join(__dirname,'plant-thought');
require(path.join(deps,'esbuild')).buildSync({entryPoints:[path.join(dir,'markdown-editor-src.js')],bundle:true,format:'iife',globalName:'PlantMarkdownEditor',platform:'browser',target:['chrome110'],minify:true,legalComments:'eof',nodePaths:[deps],outfile:path.join(dir,'markdown-editor.js'),footer:{js:'if(typeof module==="object"&&module.exports)module.exports=PlantMarkdownEditor;'}});
fs.writeFileSync(path.join(dir,'markdown-editor.LICENSE.md'),['# Markdown editor dependencies\n\nBundled locally. Runtime uses no CDN.\n',...Object.entries(JSON.parse(fs.readFileSync(path.join(dir,'markdown-editor.dependencies.json'),'utf8')).runtime).map(([name,version])=>{const base=path.join(deps,name),file=['LICENSE','LICENSE.txt','LICENSE.md'].find(file=>fs.existsSync(path.join(base,file)));return '## '+name+' '+version+'\n\n'+(file?fs.readFileSync(path.join(base,file),'utf8'):JSON.parse(fs.readFileSync(path.join(base,'package.json'),'utf8')).license)+'\n';})].join('\n'));
