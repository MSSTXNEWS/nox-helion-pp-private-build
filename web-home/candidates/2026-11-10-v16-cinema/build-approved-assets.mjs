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
const {installExtras}=await import('./nox-install-extra-v19.mjs');
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
const pinned=JSON.parse(fs.readFileSync(path.join(root,'ASSET-MANIFEST-V17.json'),'utf8'));
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
const extrasReceipt=await installExtras(out);
// Historical UI imports the Three ES module locally. Restore the pinned official module
// without changing the legacy WebGL entrypoints or the 14 PBR controls.
const threeModule=path.join(out,'vendor/nox-extra/three.module.js');
if(!fs.existsSync(threeModule))throw Error('NOX_THREE_MODULE_PIN_MISSING');
fs.mkdirSync(path.join(out,'vendor/three'),{recursive:true});
fs.copyFileSync(threeModule,path.join(out,'vendor/three/three.module.js'));
for(const loader of ['STLLoader.js','RGBELoader.js']){
 const source=path.join(out,'vendor/nox-extra/addons/loaders',loader);
 if(!fs.existsSync(source))throw Error('NOX_THREE_ADDON_MISSING:'+loader);
 const destination=path.join(out,'vendor/three/addons/loaders',loader);
 fs.mkdirSync(path.dirname(destination),{recursive:true});
 fs.copyFileSync(source,destination);
}
for(const name of ['nox-glass-home.css','nox-glass-film.css','nox-glass-init.mjs']){
 if(!fs.existsSync(path.join(out,name)))throw Error('NOX_GLASS_BRIDGE_MISSING:'+name);
}
execFileSync('node',['--check',path.join(out,'nox-glass-init.mjs')],{stdio:'pipe'});

const pages=['index.html','chat.html','cinema.html','install.html','memory.html','models.html','projects.html','settings.html','system.html','training.html'];
for(const page of pages){
 const p=path.join(out,page);
 let html=fs.readFileSync(p,'utf8');
 if(!/<\/head>/i.test(html)||!/<\/body>/i.test(html))throw Error('NOX_PAGE_STRUCTURE:'+page);
 const style='<link rel="stylesheet" href="./nox-global-wow-v18.css" data-nox-wow-shared="v18">';
 const vendor='<link rel="stylesheet" href="./vendor/nox-liquid-glass/liquid-glass.css" data-nox-vendor-glass="original">';
 const script='<script defer src="./nox-global-wow-v18.js" data-nox-wow-shared="v18"></script>';
 const universeStyle='<link rel="stylesheet" href="./nox-universe-v19.css" data-nox-universe="v19">';
 const universeScript='<script defer src="./nox-universe-v19.js" data-nox-universe="v19"></script>';
 if(!html.includes('nox-global-wow-v18.css'))html=html.replace(/<\/head>/i,style+'</head>');
 if(!html.includes('vendor/nox-liquid-glass/liquid-glass.css')){
  if(!fs.existsSync(path.join(out,'vendor/nox-liquid-glass/liquid-glass.css')))throw Error('NOX_GLASS_VENDOR_MISSING');
  html=html.replace(/<\/head>/i,vendor+'</head>');
 }
 if(!html.includes('nox-global-wow-v18.js'))html=html.replace(/<\/body>/i,script+'</body>');
 if(!html.includes('nox-universe-v19.css'))html=html.replace(/<\/head>/i,universeStyle+'</head>');
 if(!html.includes('nox-universe-v19.js'))html=html.replace(/<\/body>/i,universeScript+'</body>');
 if(page==='system.html'||page==='training.html'){
  const progressStyle='<link rel="stylesheet" href="./nox-progress-panel.css" data-nox-progress="evidence-only">';
  const progressScript='<script defer src="./nox-progress-panel.js" data-nox-progress="evidence-only"></script>';
  if(!html.includes('nox-progress-panel.css'))html=html.replace(/<\/head>/i,progressStyle+'</head>');
  if(!html.includes('nox-progress-panel.js'))html=html.replace(/<\/body>/i,progressScript+'</body>');
 }
 // Pin all known shared UI/chart dependencies to verifiable same-origin assets.
 const pinnedCdn={
   'https://cdn.jsdelivr.net/npm/lucide@0.456.0/dist/umd/lucide.min.js':'./vendor/nox-extra/lucide.min.js',
   'https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js':'./vendor/nox-extra/echarts.min.js'
 };
 for(const [remote,local] of Object.entries(pinnedCdn)){
   if(html.includes(remote)){
    const bin=path.join(out,local.slice(2));
    if(!fs.existsSync(bin))throw Error('NOX_PINNED_CDN_LOCAL_MISSING:'+local);
    html=html.replaceAll(remote,local);
   }
 }
 // Use exactly the previously pinned Three version, but without the CDN at runtime.
 const tablerRemote='https://cdn.jsdelivr.net/npm/@tabler/core@1.0.0-beta21/dist/css/tabler.min.css';
 const tablerLocal='./vendor/nox-extra/tabler-core.min.css';
 if(html.includes(tablerRemote)){
  if(!fs.existsSync(path.join(out,tablerLocal.slice(2))))throw Error('NOX_TABLER_LOCAL_CSS_MISSING');
  html=html.replaceAll(tablerRemote,tablerLocal);
 }
 const originalThree='https://cdn.jsdelivr.net/npm/three@0.160.1/';
 html=html.replaceAll(originalThree+'build/three.module.js','./vendor/three/three.module.js');
 html=html.replaceAll(originalThree+'examples/jsm/','./vendor/three/addons/');
 if(html.includes('src="/https://'))html=html.replaceAll('src="/https://','src="https://'); // Repair three historically malformed Lucide URLs.
 if(page==='memory.html')html=html.replace(/<img\s+src="nox-memory-core\.svg"[^>]*>/i,'');
 if(page==='index.html'){
  for(const asset of ['nox-owner-release-v22.css','nox-owner-release-v22.js'])
   if(!fs.existsSync(path.join(out,asset)))throw Error('NOX_V22_SOURCE_MISSING:'+asset);
  if(!html.includes('nox-owner-release-v22.css'))html=html.replace('</head>','<link rel="stylesheet" href="./nox-owner-release-v22.css" data-nox-v22="source-repair"></head>');
  if(!html.includes('nox-owner-release-v22.js'))html=html.replace('</body>','<script defer src="./nox-owner-release-v22.js" data-nox-v22="source-repair"></script></body>');
  for(const name of ['nox-visual-source-lock-v24.css','nox-visual-source-lock-v24.js'])
   if(!fs.existsSync(path.join(out,name)))throw Error('NOX_V24_FIDELITY_ASSET_MISSING:'+name);
  if(!html.includes('nox-visual-source-lock-v24.css'))html=html.replace('</head>','<link rel="stylesheet" href="./nox-visual-source-lock-v24.css" data-nox-v24="original-materials"></head>');
  if(!html.includes('nox-visual-source-lock-v24.js'))html=html.replace('</body>','<script defer src="./nox-visual-source-lock-v24.js" data-nox-v24="original-materials"></script></body>');
 }
 if(page==='chat.html'){
  for(const asset of ['nox-chat-training-v23.css','nox-chat-training-v23.mjs'])
   if(!fs.existsSync(path.join(out,asset)))throw Error('NOX_V23_CHAT_SOURCE_MISSING:'+asset);
  if(!html.includes('nox-chat-training-v23.css'))
   html=html.replace('</head>','<link rel="stylesheet" href="./nox-chat-training-v23.css" data-nox-v23="native-evidence"></head>');
  if(!html.includes('nox-chat-training-v23.mjs'))
   html=html.replace('</body>','<script type="module" src="./nox-chat-training-v23.mjs" data-nox-v23="native-evidence"></script></body>');
 }
 fs.writeFileSync(p,html);
}
for(const name of ['nox-universe-v19.js','nox-universe-v19.css','nox-section-map-v19.json','nox-install-extra-v19.mjs'])if(!fs.existsSync(path.join(out,name)))throw Error('NOX_UNIVERSE_V19_MISSING:'+name);
for(const f of ['nox-global-wow-v18.js','nox-global-wow-v18.css']){
 if(!fs.existsSync(path.join(out,f)))throw Error('NOX_WOW_MISSING:'+f);
}
execFileSync('node',['--check',path.join(out,'nox-global-wow-v18.js')],{stdio:'pipe'});
execFileSync('node',['--check',path.join(out,'nox-universe-v19.js')],{stdio:'pipe'});
for(const file of ['nox-progress-core.mjs','nox-progress-panel.js','nox-progress-panel.css','tools/nox-audit-distillation.mjs'])
 if(!fs.existsSync(path.join(out,file)))throw Error('NOX_PROGRESS_SOURCE_MISSING:'+file);
execFileSync('node',['--check',path.join(out,'nox-progress-panel.js')],{stdio:'pipe'});
execFileSync('node',['--check',path.join(out,'nox-chat-training-v23.mjs')],{stdio:'pipe'});
execFileSync('node',['--check',path.join(out,'nox-progress-core.mjs')],{stdio:'pipe'});
execFileSync('node',['--check',path.join(out,'tools/nox-audit-distillation.mjs')],{stdio:'pipe'});
// The static browser never invents an on-disk RunPod checkpoint; a real audit may
// replace this receipt using the authenticated same-origin NOX runtime.
fs.writeFileSync(path.join(out,'nox-progress-receipt.json'),JSON.stringify({
 schema:'nox-progress-receipt-v1',status:'HOLD',reason:'RUNPOD_CHECKPOINT_AND_TRAINER_STATE_NOT_CONNECTED',
 stepPercent:null,complete:false,weightUpdateVerified:false,windowsSyncVerified:false,
 qualityGainVerified:false,source:'STATIC_PREVIEW_NO_GPU_EVIDENCE'
},null,2));
records.sort((a,b)=>a.path.localeCompare(b.path));
fs.writeFileSync(path.join(target,'MANIFEST.json'),JSON.stringify({version:'2026-11-10',licenses:{planets:'Solar System Scope CC BY 4.0 — https://www.solarsystemscope.com/textures/',hdr:'Poly Haven Machine Shop 01 CC0',metal:'ambientCG Metal012 CC0'},files:records},null,2));
fs.writeFileSync(path.join(target,'ATTRIBUTION.txt'),'Planet textures © Solar System Scope, licensed under CC BY 4.0. https://www.solarsystemscope.com/textures/\nHDRI Machine Shop 01 © Poly Haven, CC0.\nMetal012 PBR © ambientCG, CC0.\n');
console.log('NOX ASSETS INSTALLED:',records.length,'total bytes:',records.reduce((s,x)=>s+x.bytes,0));

const ownerAsset='assets/nox-owner-approved/NOX_HOME_OWNER_APPROVED_WEB.webp';
const ownerFile=path.join(out,ownerAsset);
if(!fs.existsSync(ownerFile))throw Error('NOX_OWNER_APPROVED_ART_NOT_PACKAGED');
const ownerSha=crypto.createHash('sha256').update(fs.readFileSync(ownerFile)).digest('hex');
if(ownerSha!=='3253d26819a70b49259fdb2a56c2eaa2455c6878cb2ccb8d62b225ec6ccdfa22')throw Error('NOX_OWNER_APPROVED_WEB_ART_SHA_DRIFT');
const ownerPersonaSha={"kv":"4f349edf31118301b2c5d42b0fe5ad2c17aea05fae5622afab90a5a00950584b","am":"67390d082d29d0a90f09e09866875318fdd4c562ea6791f0f51c958adcd28768","la":"e03b0611b237f23ecafbbc1dd6e0aec93aabf38a3bb772af28b1ed0e90e27eaa","ev":"981b21da200f6a4d1c1741a4f5849c9379eb52d781d661ecfdb093ca29652c87","kw":"005d246edce84b4cd0f3d005a5eddb03adbedf8fdfe310ce29e6b95c6a16361e"};
for(const [id,expected] of Object.entries(ownerPersonaSha)){
 const rel='assets/nox-owner-approved/nox-owner-persona-'+id+'.webp';
 const file=path.join(out,rel);
 if(!fs.existsSync(file))throw Error('NOX_OWNER_PERSONA_FILE_MISSING:'+id);
 const sha=crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
 if(sha!==expected)throw Error('NOX_OWNER_PERSONA_SOURCE_SHA_DRIFT:'+id);
}

for(const f of ['nox-owner-director-v20.css','nox-owner-director-v20.js'])if(!fs.existsSync(path.join(out,f)))throw Error('NOX_OWNER_CINEMATIC_FILE_MISSING:'+f);
if(!fs.existsSync(path.join(out,'nox-resonance-cinema-v13.css')))throw Error('NOX_RESONANCE_APPROVED_CSS_MISSING');
execFileSync('node',['--check',path.join(out,'nox-owner-director-v20.js')],{stdio:'pipe'});
// V21 assets must exist in the actual Vercel output, not only the GitHub patch directory.
 for(const f of ['nox-owner-fidelity-v21.css','nox-owner-fidelity-v21.js'])if(!fs.existsSync(path.join(out,f)))throw Error('NOX_V21_FIDELITY_MISSING:'+f);
 execFileSync('node',['--check',path.join(out,'nox-owner-fidelity-v21.js')],{stdio:'pipe'});
execFileSync('node',['--check',path.join(out,'nox-owner-release-v22.js')],{stdio:'pipe'});
 const fuseFile=path.join(out,'vendor/nox-extra/fuse.min.js');
 if(!fs.existsSync(fuseFile)||fs.statSync(fuseFile).size<7000)throw Error('NOX_FUSE_LOCAL_VENDOR_MISSING');
 const ownerHtml=fs.readFileSync(path.join(out,'index.html'),'utf8');
for(const f of ['nox-owner-director-v20.css','nox-owner-director-v20.js','nox-owner-fidelity-v21.css','nox-owner-fidelity-v21.js'])if(!ownerHtml.includes(f))throw Error('NOX_OWNER_HTML_NOT_ATTACHED:'+f);
const mandatory=['index.html','nox-home.mjs','nox-home-flow.js','nox-home-flow.css','nox-home-recovery.js','nox-ui.css','nox-global-wow-v18.css','nox-global-wow-v18.js','nox-orbit-original.js','nox-engines/physical-worlds-v7.mjs','assets/nox-approved/MANIFEST.json','assets13/asteroid_bennu.stl','assets13/BENNU-RECEIPT.json'];
const remaining=mandatory.filter(f=>!fs.existsSync(path.join(out,f)));
if(remaining.length)throw Error('NOX_P0_FILES_MISSING:'+remaining.join(','));
const pagesEvidence=pages.map(n=>{const source=fs.readFileSync(path.join(out,n),'utf8');return {page:n,style:source.includes('nox-global-wow-v18.css'),script:source.includes('nox-global-wow-v18.js'),glass:source.includes('vendor/nox-liquid-glass/liquid-glass.css')}});
if(pagesEvidence.some(p=>!p.style||!p.script||!p.glass))throw Error('NOX_P0_UI_PAGE_DISCONNECTED');
const bennuReceipt=JSON.parse(fs.readFileSync(path.join(out,'assets13/BENNU-RECEIPT.json'),'utf8'));
const sourceOriginals={'nox-home.mjs':'8066bc0a0f8ef5bb5f0fb1f58ad3f6ee29dc8506385c09d77d38d4235c7e42e9','nox-home-flow.js':'a28dc4a9bd36638182aa05b89513d8ded2800ee78c0db3a52ccea07d292a52ca'};
for(const [filename,expected] of Object.entries(sourceOriginals)){
 const actual=crypto.createHash('sha256').update(fs.readFileSync(path.join(out,filename))).digest('hex');
 if(actual!==expected)throw Error('NOX_HISTORIC_ORIGINAL_CHANGED:'+filename);
}
const packReceipt={
 version:'2026-11-10-P0',assembly:'BUILD_SCRIPT_EXECUTED',pbrHdrCount:records.length,
 bennu:{bytes:bennuReceipt.bytes,sha256:bennuReceipt.sha256,triangles:bennuReceipt.triangles,stlStructure:bennuReceipt.verifiedStlStructure},
 pages:pagesEvidence,ownerApprovedArt:{file:ownerAsset,sha256:ownerSha,origin:'Google Drive owner-approved 2026-10-22 SHA256 382c1069afcaaaed11c319796f2c553d2bd977d7e46c68ecd7d55af26e132a4a'},ownerPersonaApprovedCrops:ownerPersonaSha,requiredFiles:mandatory.length,v19LibraryFiles:extrasReceipt.files.length,v19LibraryHashes:extrasReceipt.files.map(x=>({name:x.file,sha256:x.sha256})),
 d02Source:'HISTORICAL_ORIGINAL_VERCEL_SNAPSHOT_SHA256_VERIFIED',
 deployedGpuQA:'HOLD',browserAcceptance:'NOT_EXECUTED',productionModified:false
};
fs.writeFileSync(path.join(out,'NOX-P0-RECEIPT.json'),JSON.stringify(packReceipt,null,2));
console.log('NOX_P0_BUILD_RECEIPT:',JSON.stringify({pages:pagesEvidence.length,assets:records.length,bennuBytes:bennuReceipt.bytes,stlVerified:bennuReceipt.verifiedStlStructure,gpuAcceptance:'HOLD'}));

