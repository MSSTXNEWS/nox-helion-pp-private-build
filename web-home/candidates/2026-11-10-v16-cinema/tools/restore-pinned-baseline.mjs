/* Restore only missing historical NOX WEB files from verified SHA-256 pinned public deployment.
 * Never overwrite the PR's changed D02, HTML, CSS, JS or approved artwork.
 * Run only within an ephemeral CI checkout. Fails closed on drift.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
const here=path.dirname(fileURLToPath(import.meta.url)),root=path.resolve(here,'..');
const origin='https://nox-helion-real-home-preview.vercel.app/';
const parts=await Promise.all([1,2,3].map(async i=>JSON.parse(await fs.readFile(path.join(here,'nox-public-baseline-pin-0'+i+'.json'),'utf8'))));
const files=parts.flat();
if(files.length!==173||new Set(files.map(x=>x.path)).size!==files.length)throw Error('NOX_BASELINE_PIN_MANIFEST_INVALID');
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
const preexisting=[],downloaded=[],errors=[];
let next=0;
async function worker(){
 while(next<files.length){
  const item=files[next++],rel=item.path;
  if(!rel||rel.startsWith('/')||rel.split('/').includes('..'))throw Error('NOX_UNSAFE_BASELINE_PATH');
  const dst=path.join(root,rel);
  try{
   if(await fs.stat(dst).then(s=>s.isFile()).catch(()=>false)){preexisting.push(rel);continue}
   let bytes,last;
   for(let attempt=0;attempt<2;attempt++){
    const c=new AbortController(),timer=setTimeout(()=>c.abort(),24000);
    try{
     const res=await fetch(new URL(rel,origin),{signal:c.signal,redirect:'error'});
     if(!res.ok)throw Error('HTTP_'+res.status);
     bytes=Buffer.from(await res.arrayBuffer());
     if(bytes.length!==item.bytes||hash(bytes)!==item.sha256)throw Error('SOURCE_SHA256_DRIFT');
     if(rel.endsWith('.js')||rel.endsWith('.mjs')||rel.endsWith('.css')){
      if(bytes.toString('utf8',0,256).toLowerCase().includes('<!doctype'))throw Error('HTML_INSTEAD_OF_CODE');
     }
     break;
    }catch(e){last=e;bytes=null}finally{clearTimeout(timer)}
   }
   if(!bytes)throw last;
   await fs.mkdir(path.dirname(dst),{recursive:true});await fs.writeFile(dst,bytes);
   downloaded.push(rel);
  }catch(e){errors.push({path:rel,error:String(e).slice(0,170)})}
 }
}
await Promise.all(Array.from({length:10},()=>worker()));
if(errors.length)throw Error('NOX_BASELINE_MISSING_OR_CHANGED:'+JSON.stringify(errors));
const check={originalHome:'8066bc0a0f8ef5bb5f0fb1f58ad3f6ee29dc8506385c09d77d38d4235c7e42e9',originalFlow:'a28dc4a9bd36638182aa05b89513d8ded2800ee78c0db3a52ccea07d292a52ca'};
for(const [file,expected] of [['nox-home.mjs',check.originalHome],['nox-home-flow.js',check.originalFlow]]){
 const bytes=await fs.readFile(path.join(root,file));if(hash(bytes)!==expected)throw Error('NOX_D02_SOURCE_LOCK_DRIFT:'+file);
}
const mandatory=['index.html','nox-ui.css','industrial-effects.mjs','industrial-effects.css','industrial-assets.mjs',
 'vendor/nox-liquid-glass/liquid-glass.css','nox-orbit-original.js','nox-home.mjs','chat.html','cinema.html','training.html','system.html'];
for(const f of mandatory)if(!await fs.stat(path.join(root,f)).then(s=>s.isFile()).catch(()=>false))throw Error('NOX_BASELINE_REQUIRED_MISSING:'+f);
const report={kind:'HISTORICAL_BASELINE_SHA256_RESTORE',pinnedFiles:files.length,downloaded:downloaded.length,
 preservedCandidateFiles:preexisting.length,origin,errors,productionChanged:false,browserAcceptance:'HOLD'};
await fs.writeFile(path.join(root,'NOX-BASELINE-RESTORE-RECEIPT.json'),JSON.stringify(report,null,2));
console.log('NOX_BASELINE_RESTORE_PASS',JSON.stringify(report));
