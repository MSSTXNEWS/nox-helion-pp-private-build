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
const result={pages:pages.length,localReferences:checked.length,missingCount:missing.length,missing};
console.log('NOX_STATIC_REFERENCE_AUDIT',JSON.stringify(result));
if(missing.length)process.exitCode=1;
