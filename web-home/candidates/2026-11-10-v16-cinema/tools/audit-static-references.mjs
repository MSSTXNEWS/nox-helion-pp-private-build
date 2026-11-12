// NOX V21: deterministic local-file integrity for all ten existing routes.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const here=path.dirname(fileURLToPath(import.meta.url));
const root=path.resolve(process.argv[2]||path.resolve(here,'../dist'));
const pages=['index','chat','cinema','install','memory','models','projects','settings','system','training'];
const missing=[],checked=[];
const assets=/\.(?:html|css|js|mjs|svg|json|png|jpg|jpeg|gif|webp|ico|woff|woff2|mp4|vtt)$/i;
for(const name of pages){
 const page=name+'.html',html=fs.readFileSync(path.join(root,page),'utf8');
 if(html.includes('src="/https://')||html.includes('href="/https://'))missing.push({page,reason:'MALFORMED_CDN_URL'});
 const regex=/\b(?:src|href)=["']([^"'<>]+)["']/g;let m;
 while((m=regex.exec(html))){
  const value=m[1].trim();
  if(!value||/^(?:https?:|data:|blob:|mailto:|tel:|#|\/\/)/i.test(value))continue;
  const clean=value.split(/[?#]/,1)[0];
  if(!assets.test(clean))continue;
  const relative=clean.startsWith('/')?clean.slice(1):clean;
  const absolute=path.resolve(root,relative);
  if(!absolute.startsWith(root+path.sep))throw Error('NOX_UNSAFE_HTML_ASSET:'+relative);
  checked.push({page,path:relative});
  if(!fs.existsSync(absolute)||!fs.statSync(absolute).isFile())missing.push({page,reason:'MISSING',path:relative});
 }
}
const cssReferences=[];
async function walkCss(dir){
 for(const item of fs.readdirSync(dir,{withFileTypes:true})){
  const abs=path.join(dir,item.name);
  if(item.isDirectory()){await walkCss(abs);continue}
  if(!item.isFile()||!item.name.endsWith('.css'))continue;
  const css=fs.readFileSync(abs,'utf8'),re=/url\(\s*['"]?([^)'"]+)/g;let m;
  while((m=re.exec(css))){
   const url=m[1].trim();
   if(!url || url.startsWith('//') || /^(?:https?:|data:|blob:|#)/i.test(url))continue;
   const clean=url.split(/[?#]/,1)[0],absolute=url.startsWith('/')?path.resolve(root,url.slice(1)):path.resolve(path.dirname(abs),clean);
   if(!absolute.startsWith(root+path.sep))throw Error('NOX_UNSAFE_CSS_ASSET:'+url);
   cssReferences.push({css:path.relative(root,abs),url});
   if(!fs.existsSync(absolute)||!fs.statSync(absolute).isFile())missing.push({css:path.relative(root,abs),reason:'MISSING_CSS_ASSET',url});
  }
 }
}
await walkCss(root);
const result={pages:pages.length,localReferences:checked.length,cssReferences:cssReferences.length,missingCount:missing.length,missing};
console.log('NOX_STATIC_REFERENCE_AUDIT',JSON.stringify(result));
if(missing.length)process.exitCode=1;
