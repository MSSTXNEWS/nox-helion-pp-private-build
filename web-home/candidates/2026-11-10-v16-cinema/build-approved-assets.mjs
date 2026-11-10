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
for(const name of fs.readdirSync(root)){if(['dist','node_modules','.git'].includes(name))continue;fs.cpSync(path.join(root,name),path.join(out,name),{recursive:true});}
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
  if(expected==='stl'&&bytes.length<1000)throw new Error('Bad STL '+url);
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
// Genuine NASA Bennu STL is a separate required asset, not counted among the 14 pinned PBR/HDRI files.
const bennuUrl='https://assets.science.nasa.gov/content/dam/science/cds/3d/resources/printable/asteroid-101955-bennu/Asteroid%20101955%20Bennu.stl';
const bennuPath=path.join(out,'assets13/asteroid_bennu.stl');
await get(bennuUrl,bennuPath,'stl');
const bennuBytes=fs.readFileSync(bennuPath);
if(bennuBytes.length<1000||bennuBytes.length>12000000)throw Error('NOX_BENNU_SIZE_INVALID');
const header=bennuBytes.toString('ascii',0,Math.min(5,bennuBytes.length));
const triangles=bennuBytes.length>=84?bennuBytes.readUInt32LE(80):0;
const binaryStl=triangles>0&&84+triangles*50===bennuBytes.length;
const asciiStl=header.toLowerCase()==='solid'&&bennuBytes.subarray(0,4096).includes(Buffer.from('facet'));
if(!binaryStl&&!asciiStl)throw Error('NOX_BENNU_STL_INVALID');
fs.writeFileSync(path.join(out,'assets13/BENNU-RECEIPT.json'),JSON.stringify({source:bennuUrl,bytes:bennuBytes.length,sha256:crypto.createHash('sha256').update(bennuBytes).digest('hex'),triangles:binaryStl?triangles:null,verifiedStlStructure:true},null,2));
for(const name of ['Color','NormalGL','Metalness','Roughness']){
 if(!records.some(x=>x.path==='metal/Metal012_1K-JPG_'+name+'.jpg'))throw new Error('Missing metal map '+name);
}
// Verify every downloaded byte against the already accepted V17 hashes.
const pinned=JSON.parse(fs.readFileSync(path.join(root,'nox-approved-pin.json'),'utf8'));
for(const item of records){
 const expected=pinned.files.find(x=>x.path===item.path);
 if(!expected||expected.sha256!==item.sha256||expected.bytes!==item.bytes)throw Error('NOX_PINNED_ASSET_MISMATCH:'+item.path);
}
if(records.length!==pinned.files.length)throw Error('NOX_PINNED_ASSET_COUNT_MISMATCH');
for(const file of ['nox-home.mjs','nox-home-flow.js','nox-home-recovery.js','nox-resonance-cinema-v13.js','nox-engines/physical-worlds-v7.mjs','nox-cinematic-health.js','industrial-assets.mjs','industrial-effects.mjs','nox-orbit-original.js']){
 execFileSync('node',['--check',path.join(out,file)],{stdio:'pipe'});
}
for(const name of ['nox-home-flow.css','nox-home-flow.js'])if(!fs.existsSync(path.join(out,name)))throw Error('NOX_HOME_FLOW_MISSING:'+name);
for(const name of ['index.html','chat.html','models.html','memory.html','training.html','system.html','projects.html','cinema.html','settings.html','install.html']){
 if(!fs.existsSync(path.join(out,name)))throw Error('NOX_MISSING_PAGE:'+name);
}
const moduleSource=fs.readFileSync(path.join(out,'industrial-assets.mjs'),'utf8');
for(const item of ['metal/Metal012_1K-JPG_Color.jpg','metal/Metal012_1K-JPG_NormalGL.jpg','metal/Metal012_1K-JPG_Metalness.jpg','metal/Metal012_1K-JPG_Roughness.jpg','hdr/machine_shop_01_1k.hdr']){
 if(!moduleSource.includes('assets/nox-approved/'+item))throw Error('NOX_CORE_MATERIAL_DISCONNECTED:'+item);
}
// Shared V18 UI gets injected into the original TEN HTML pages at build time.
// The original functional page bodies, navigation and D02 scene are retained.
const pages=['index.html','chat.html','cinema.html','install.html','memory.html','models.html','projects.html','settings.html','system.html','training.html'];
for(const page of pages){
 const p=path.join(out,page);
 let html=fs.readFileSync(p,'utf8');
 if(!/<\/head>/i.test(html)||!/<\/body>/i.test(html))throw Error('NOX_PAGE_STRUCTURE:'+page);
 const style='<link rel="stylesheet" href="./nox-global-wow-v18.css" data-nox-wow-shared="v18">';
 const vendor='<link rel="stylesheet" href="./vendor/nox-liquid-glass/liquid-glass.css" data-nox-vendor-glass="original">';
 const script='<script defer src="./nox-global-wow-v18.js" data-nox-wow-shared="v18"></script>';
 if(!html.includes('nox-global-wow-v18.css'))html=html.replace(/<\/head>/i,style+'</head>');
 if(!html.includes('vendor/nox-liquid-glass/liquid-glass.css')){
  if(!fs.existsSync(path.join(out,'vendor/nox-liquid-glass/liquid-glass.css')))throw Error('NOX_GLASS_VENDOR_MISSING');
  html=html.replace(/<\/head>/i,vendor+'</head>');
 }
 if(!html.includes('nox-global-wow-v18.js'))html=html.replace(/<\/body>/i,script+'</body>');
 fs.writeFileSync(p,html);
}
for(const f of ['nox-global-wow-v18.js','nox-global-wow-v18.css']){
 if(!fs.existsSync(path.join(out,f)))throw Error('NOX_WOW_MISSING:'+f);
}
execFileSync('node',['--check',path.join(out,'nox-global-wow-v18.js')],{stdio:'pipe'});
records.sort((a,b)=>a.path.localeCompare(b.path));
fs.writeFileSync(path.join(target,'MANIFEST.json'),JSON.stringify({version:'2026-11-10',licenses:{planets:'Solar System Scope CC BY 4.0 — https://www.solarsystemscope.com/textures/',hdr:'Poly Haven Machine Shop 01 CC0',metal:'ambientCG Metal012 CC0'},files:records},null,2));
fs.writeFileSync(path.join(target,'ATTRIBUTION.txt'),'Planet textures © Solar System Scope, licensed under CC BY 4.0. https://www.solarsystemscope.com/textures/\nHDRI Machine Shop 01 © Poly Haven, CC0.\nMetal012 PBR © ambientCG, CC0.\n');
console.log('NOX ASSETS INSTALLED:',records.length,'total bytes:',records.reduce((s,x)=>s+x.bytes,0));

const mandatory=['index.html','nox-home.mjs','nox-home-flow.js','nox-home-flow.css','nox-home-recovery.js','nox-ui.css','nox-global-wow-v18.css','nox-global-wow-v18.js','nox-orbit-original.js','nox-engines/physical-worlds-v7.mjs','assets/nox-approved/MANIFEST.json','assets13/asteroid_bennu.stl','assets13/BENNU-RECEIPT.json'];
const remaining=mandatory.filter(f=>!fs.existsSync(path.join(out,f)));
if(remaining.length)throw Error('NOX_P0_FILES_MISSING:'+remaining.join(','));
const pagesEvidence=pages.map(n=>{const source=fs.readFileSync(path.join(out,n),'utf8');return {page:n,style:source.includes('nox-global-wow-v18.css'),script:source.includes('nox-global-wow-v18.js'),glass:source.includes('vendor/nox-liquid-glass/liquid-glass.css')}});
if(pagesEvidence.some(p=>!p.style||!p.script||!p.glass))throw Error('NOX_P0_UI_PAGE_DISCONNECTED');
const bennuReceipt=JSON.parse(fs.readFileSync(path.join(out,'assets13/BENNU-RECEIPT.json'),'utf8'));
const packReceipt={
 version:'2026-11-10-P0',assembly:'BUILD_SCRIPT_EXECUTED',pbrHdrCount:records.length,
 bennu:{bytes:bennuReceipt.bytes,sha256:bennuReceipt.sha256,triangles:bennuReceipt.triangles,stlStructure:bennuReceipt.verifiedStlStructure},
 pages:pagesEvidence,requiredFiles:mandatory.length,
 d02Source:'RECONSTRUCTION_PENDING_EXACT_HISTORIC_SOURCE',
 deployedGpuQA:'HOLD',browserAcceptance:'NOT_EXECUTED',productionModified:false
};
fs.writeFileSync(path.join(out,'NOX-P0-RECEIPT.json'),JSON.stringify(packReceipt,null,2));
console.log('NOX_P0_BUILD_RECEIPT:',JSON.stringify({pages:pagesEvidence.length,assets:records.length,bennuBytes:bennuReceipt.bytes,stlVerified:bennuReceipt.verifiedStlStructure,gpuAcceptance:'HOLD'}));

