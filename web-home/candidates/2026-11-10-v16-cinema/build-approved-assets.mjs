/**
 * NOX HELION approved asset pack — deterministic Vercel build, Node 22.
 * Downloads from official license-backed providers, fails closed if absent.
 * Keeps original source intact, copies only into ephemeral dist/ output.
 */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {execFileSync} from 'node:child_process';

const root=process.cwd(), out=path.join(root,'dist');
fs.rmSync(out,{recursive:true,force:true});
fs.cpSync(root,out,{recursive:true,filter:s=>!s.startsWith(out)&&!s.includes('/node_modules/')&&!s.includes('/.git/')});
const target=path.join(out,'assets/nox-approved');
fs.mkdirSync(path.join(target,'planets'),{recursive:true});
fs.mkdirSync(path.join(target,'hdr'),{recursive:true});
fs.mkdirSync(path.join(target,'metal'),{recursive:true});
const base='https://raw.githubusercontent.com/Sanghel/solar-system-3d/develop/public/textures/';
const planets=['earth','mercury','venus','mars','jupiter','saturn','uranus','neptune'];
async function get(url,file,expected){
 const controller=new AbortController();
 const timer=setTimeout(()=>controller.abort(),45000);
 try{
  const response=await fetch(url,{signal:controller.signal,redirect:'follow'});
  if(!response.ok)throw new Error('HTTP '+response.status+' at '+url);
  const bytes=Buffer.from(await response.arrayBuffer());
  if(bytes.length<1024||bytes.length>14000000)throw new Error('Unexpected asset size '+url);
  if(expected==='jpg'&&!(bytes[0]===255&&bytes[1]===216))throw new Error('Bad JPEG '+url);
  if(expected==='hdr'&&!bytes.subarray(0,10).toString().startsWith('#?RADIANCE'))throw new Error('Bad HDR '+url);
  if(expected==='zip'&&!(bytes[0]===80&&bytes[1]===75))throw new Error('Bad ZIP '+url);
  fs.mkdirSync(path.dirname(file),{recursive:true});
  fs.writeFileSync(file,bytes);
  return bytes;
 }finally{clearTimeout(timer);}
}
const records=[];
async function record(url,relative,format){
 const file=path.join(target,relative);
 const buf=await get(url,file,format);
 records.push({path:relative,bytes:buf.length,sha256:crypto.createHash('sha256').update(buf).digest('hex'),source:url});
}
await Promise.all(planets.map(n=>record(base+n+'.jpg','planets/'+n+'.jpg','jpg')));
await record('https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/1k/machine_shop_01_1k.hdr','hdr/machine_shop_01_1k.hdr','hdr');
const zip=path.join(target,'metal','Metal012_1K-JPG.zip');
await get('https://ambientcg.com/get?file=Metal012_1K-JPG.zip',zip,'zip');
execFileSync('unzip',['-oq',zip,'-d',path.dirname(zip)],{stdio:'pipe'});
fs.rmSync(zip);
for(const file of fs.readdirSync(path.dirname(zip))){
 if(!/^Metal012_1K-JPG_(Color|NormalGL|Metalness|Roughness|Displacement)\.jpg$/.test(file))continue;
 const data=fs.readFileSync(path.join(path.dirname(zip),file));
 records.push({path:'metal/'+file,bytes:data.length,sha256:crypto.createHash('sha256').update(data).digest('hex'),source:'https://ambientcg.com/a/Metal012'});
}
for(const name of ['Color','NormalGL','Metalness','Roughness']){
 if(!records.some(x=>x.path==='metal/Metal012_1K-JPG_'+name+'.jpg'))throw new Error('Missing metal map '+name);
}
records.sort((a,b)=>a.path.localeCompare(b.path));
fs.writeFileSync(path.join(target,'MANIFEST.json'),JSON.stringify({version:'2026-11-10',licenses:{planets:'Solar System Scope CC BY 4.0 — https://www.solarsystemscope.com/textures/',hdr:'Poly Haven Machine Shop 01 CC0',metal:'ambientCG Metal012 CC0'},files:records},null,2));
fs.writeFileSync(path.join(target,'ATTRIBUTION.txt'),'Planet textures © Solar System Scope, licensed under CC BY 4.0. https://www.solarsystemscope.com/textures/\nHDRI Machine Shop 01 © Poly Haven, CC0.\nMetal012 PBR © ambientCG, CC0.\n');
console.log('NOX ASSETS INSTALLED:',records.length,'total bytes:',records.reduce((s,x)=>s+x.bytes,0));
