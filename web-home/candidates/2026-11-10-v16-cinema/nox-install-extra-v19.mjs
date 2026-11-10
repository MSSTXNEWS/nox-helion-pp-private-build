/** NOX V19: deterministic third-party retrieval at preview build time.
 * Produces actual local assets + hashes in dist/vendor/nox-extra; no runtime CDN dependence.
 * Every pinned download is required. No fake PASS if missing.
 * This file is part of the existing NOX static WEB build, not a second website.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';

const version='2026-11-10-v19';
const sources=[
 {name:'pdf.mjs',url:'https://cdn.jsdelivr.net/npm/pdfjs-dist@4.10.38/build/pdf.mjs',minBytes:100000,maxBytes:5000000,license:'Apache-2.0'},
 {name:'pdf.worker.mjs',url:'https://cdn.jsdelivr.net/npm/pdfjs-dist@4.10.38/build/pdf.worker.mjs',minBytes:100000,maxBytes:6000000,license:'Apache-2.0'},
 {name:'PDFJS-LICENSE.txt',url:'https://cdn.jsdelivr.net/npm/pdfjs-dist@4.10.38/LICENSE',minBytes:500,maxBytes:100000,license:'Apache-2.0'},
 {name:'epub.min.js',url:'https://cdn.jsdelivr.net/npm/epubjs@0.3.93/dist/epub.min.js',minBytes:30000,maxBytes:3500000,license:'BSD-2-Clause'},
 {name:'EPUB-LICENSE.txt',url:'https://cdn.jsdelivr.net/npm/epubjs@0.3.93/LICENSE',minBytes:50,maxBytes:100000,license:'BSD-2-Clause'},
 {name:'shaka-player.compiled.js',url:'https://cdn.jsdelivr.net/npm/shaka-player@4.15.67/dist/shaka-player.compiled.js',minBytes:200000,maxBytes:8500000,license:'Apache-2.0'},
 {name:'SHAKA-LICENSE.txt',url:'https://cdn.jsdelivr.net/npm/shaka-player@4.15.67/LICENSE',minBytes:500,maxBytes:100000,license:'Apache-2.0'}
];

async function getFile(entry,output){
 let last;
 for(let attempt=1;attempt<=2;attempt++){
  const ac=new AbortController();const timeout=setTimeout(()=>ac.abort(),45000);
  try{
   const res=await fetch(entry.url,{signal:ac.signal,redirect:'follow'});
   if(!res.ok)throw new Error(`HTTP_${res.status}`);
   if(res.url&&!new URL(res.url).hostname.endsWith('.jsdelivr.net'))throw Error('UNEXPECTED_DOWNLOAD_HOST');
   const bytes=Buffer.from(await res.arrayBuffer());
   if(bytes.length<entry.minBytes||bytes.length>entry.maxBytes)throw Error(`UNEXPECTED_SIZE:${bytes.length}`);
   const prefix=bytes.subarray(0,300).toString('utf8').toLowerCase();
   if(prefix.includes('<!doctype html')||prefix.includes('<html'))throw Error('HTML_INSTEAD_OF_LIBRARY');
   const sha256=createHash('sha256').update(bytes).digest('hex');
   await fs.writeFile(path.join(output,entry.name),bytes);
   return {file:entry.name,size:bytes.length,sha256,source:entry.url,license:entry.license};
  }catch(e){last=e}finally{clearTimeout(timeout)}
 }
 throw Error('NOX_V19_DEPENDENCY_NOT_DOWNLOADED:'+entry.name+':'+String(last));
}
export async function installExtras(out){
 const target=path.join(out,'vendor/nox-extra');await fs.mkdir(target,{recursive:true});
 const files=[];
 // Avoid exhausting CDN sockets during a constrained 4-core Vercel build.
 for(const src of sources)files.push(await getFile(src,target));
 const report={version,origin:'PINNED_CDN',fetchedDuringBuild:true,complete:files.length===sources.length,files,
  runtimePdf:'NOT_TESTED',runtimeEpub:'NOT_TESTED',runtimeHls:'NOT_TESTED',browserQa:'HOLD'};
 await fs.writeFile(path.join(target,'NOX-EXTRA-ASSETS-RECEIPT.json'),JSON.stringify(report,null,2));
 console.log('NOX V19 EXTRA ASSETS INSTALLED:',files.length,'verified SHA256',files.reduce((sum,x)=>sum+x.size,0),'bytes');
 return report;
}
