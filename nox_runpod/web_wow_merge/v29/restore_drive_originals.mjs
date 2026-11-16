// NOX HELION · Drive-origin visual engines (2026-11-16).
// Import from original user-owned Google Drive downloads; never modify OneHost/S03.
// Exact archive SHA checks fail closed. This runs AFTER the V29 SHA-pinned site build.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import zlib from 'node:zlib';
const base=path.join(process.cwd(),'nox_runpod/web_wow_merge/v29/drive_assets');
const site=path.join(process.cwd(),'web_v29_preview_dist');
const digest=b=>crypto.createHash('sha256').update(b).digest('hex');
const expected={
 metal:'68eba86af3ab65a1394cacc84bb35b92cd1006e9459ec5a6a4c9467d51a73d59',
 hdr:'2873e0e8a7fdff45d1815f4a8c3cb60c9f425b74c88d7981bf14c32d0464f29a',
 heat:'a62dedb79d12eefcf87a1847824e2a6c19e433bc45482670501560cf3777c145'
};
function checked(data,sha,label){if(!data||digest(data)!==sha)throw Error('NOX_DRIVE_SHA_HOLD:'+label);return data}
function bundle(prefix,count,sha){
 const arr=[];
 for(let i=0;i<count;i++){
  const f=path.join(base,prefix+'.part'+String(i).padStart(2,'0'));
  if(!fs.existsSync(f))throw Error('NOX_DRIVE_CHUNK_MISSING:'+f);
  arr.push(fs.readFileSync(f));
 }
 return checked(Buffer.concat(arr),sha,prefix);
}
function extract(zip,wanted){
 let end=-1;
 for(let i=zip.length-22;i>=Math.max(0,zip.length-65558);i--){
  if(zip.readUInt32LE(i)===0x06054b50){end=i;break}
 }
 if(end<0)throw Error('NOX_DRIVE_ZIP_INVALID_EOCD');
 let at=zip.readUInt32LE(end+16),out=new Map();
 for(let i=0;i<zip.readUInt16LE(end+10);i++){
  if(zip.readUInt32LE(at)!==0x02014b50)throw Error('NOX_DRIVE_ZIP_INVALID_CENTRAL');
  const n=zip.readUInt16LE(at+28),extra=zip.readUInt16LE(at+30),comment=zip.readUInt16LE(at+32);
  const name=zip.subarray(at+46,at+46+n).toString('utf8');
  if(wanted.has(name)){
   const offset=zip.readUInt32LE(at+42),method=zip.readUInt16LE(at+10);
   if(zip.readUInt32LE(offset)!==0x04034b50)throw Error('NOX_DRIVE_ZIP_INVALID_LOCAL');
   const start=offset+30+zip.readUInt16LE(offset+26)+zip.readUInt16LE(offset+28);
   const c=zip.subarray(start,start+zip.readUInt32LE(at+20));
   const data=method===0?c:method===8?zlib.inflateRawSync(c):null;
   if(!data||data.length!==zip.readUInt32LE(at+24))throw Error('NOX_DRIVE_ZIP_INVALID_ENTRY:'+name);
   out.set(name,data);
  }
  at+=46+n+extra+comment;
 }
 if(out.size!==wanted.size)throw Error('NOX_DRIVE_ZIP_MISSING_REQUIRED');
 return out;
}
const put=(rel,data)=>{const file=path.join(site,rel);fs.mkdirSync(path.dirname(file),{recursive:true});fs.writeFileSync(file,data)};
const changed=[];
function edit(rel,anchor,fn){
 const file=path.join(site,rel);if(!fs.existsSync(file))throw Error('NOX_DRIVE_MISSING_SITE:'+rel);
 const old=fs.readFileSync(file,'utf8');if(!old.includes(anchor))throw Error('NOX_DRIVE_ANCHOR_DRIFT:'+rel);
 const next=fn(old);if(next===old)throw Error('NOX_DRIVE_PATCH_EMPTY:'+rel);
 fs.writeFileSync(file,next);changed.push(rel);
}
if(!fs.existsSync(path.join(site,'index.html')))throw Error('NOX_DRIVE_SITE_NOT_BUILT');
const metal=bundle('metal2k',17,expected.metal),hdr=bundle('hdr2k',9,expected.hdr);
const heat=checked(fs.readFileSync(path.join(base,'HeatDistortionEffect-master.zip')),expected.heat,'heat');
const maps={
 Color:'9d429c973ff686ea31d64ac6ca804d1d3130a0e06d364a1438934f1d584b9d92',
 NormalGL:'326b329f83f7466f0a3c29a055e38b6dd00e68994891adb76ede59db8501f8d7',
 Roughness:'4baa2e0d195f056abd3f3aa2c78ee0266e62a3e4856096450a93875d17c5a746',
 Metalness:'b65d6b9091747bd81ee58adedcb6209d8ee21b2bde9298d7216989ada85ef622'
};
const names=Object.keys(maps).map(k=>'Metal012_2K-JPG_'+k+'.jpg');
const files=extract(metal,new Set(names));
const assets=[];
for(const [k,sha] of Object.entries(maps)){
 const name='Metal012_2K-JPG_'+k+'.jpg',data=checked(files.get(name),sha,name);
 for(const prefix of ['','pc/'])put(prefix+'assets/nox-approved/metal/'+name,data);
 assets.push({name,bytes:data.length,sha256:sha});
}
for(const prefix of ['','pc/'])put(prefix+'assets/nox-approved/hdr/machine_shop_01_2k.hdr',hdr);
assets.push({name:'machine_shop_01_2k.hdr',bytes:hdr.length,sha256:expected.hdr});
const shaders=['haze-desert.frag','haze-flight.frag','simple.vert'];
const targets=shaders.map(x=>'HeatDistortionEffect-master/src/shaders/'+x);
const shaderFiles=extract(heat,new Set(targets));
for(const [name,data] of shaderFiles){
 put('vendor/nox-drive-original/codrops/'+path.basename(name),data);
 assets.push({name:path.basename(name),bytes:data.length,sha256:digest(data)});
}
const olds={
 Color:'9d32b9bbcf071433a3ed69f0409cc11886bb3c554300acaf0da93a92a2059e5b',
 NormalGL:'6ea43f0b48f5fc7d1d11ead571c22f11233053e2a1926c5e21ea27de7d3a4287',
 Roughness:'d808a07ffe8786a8b410dfa29f19b0a31492e450256dd9191bb9731e110dba40',
 Metalness:'843102638fa0a5bf897888868877efab8ccdc4cb84a48e57bdb52bfb30f5e714'
};
for(const prefix of ['','pc/']){
 edit(prefix+'industrial-assets.mjs','Metal012_1K-JPG_Color.jpg',s=>{
  for(const k of Object.keys(maps)){s=s.replace('Metal012_1K-JPG_'+k+'.jpg','Metal012_2K-JPG_'+k+'.jpg').replace(olds[k],maps[k]);}
  return s.replace('machine_shop_01_1k.hdr','machine_shop_01_2k.hdr').replace('0c4b0aef41f93bd9f3ab598e8ca87c46813b67505d49331d42c86fde0f8d6b63',expected.hdr);
 });
 edit(prefix+'industrial-effects.mjs','classic?[.10,.075,.045]',s=>s
  .replace('classic?[.10,.075,.045]','classic?[.66,.55,.43]')
  .replace('uClassicBlackSun.value=classic?1:0','uClassicBlackSun.value=classic?.68:0'));
 edit(prefix+'eclipse-materials.mjs','vec3(.003,.004,.0055)',s=>s
  .replace('vec3(.003,.004,.0055),vec3(.026,.029,.033)','vec3(.015,.012,.012),vec3(.080,.062,.053)')
  .replace('vec3(.12,.10,.075),uClassicBlackSun','vec3(.56,.49,.42),uClassicBlackSun')
  .replace('smoothstep(.003,.015,fractured)','smoothstep(.010,.035,fractured)')
  .replace('molten*(.075+1.15*rim+.20*light)','molten*(.26+1.52*rim+.44*light)'));
 edit(prefix+'nox-background-engine.mjs','"classic"===m||"HOLD"===y.status',s=>s
  .replaceAll('"classic"===m?"CLASSIC":"INITIALIZING"','"INITIALIZING"')
  .replaceAll('"classic"===m?(T(),A("CLASSIC")):A("INITIALIZING")','A("INITIALIZING")')
  .replace('"classic"===m||"HOLD"===y.status','"HOLD"===y.status'));
}
const bg='/* NOX Drive original materials · live source shaders retained */\nbody[data-page="index"] main.helion-stage::before{content:"";position:absolute;inset:0;z-index:0;pointer-events:none;background:radial-gradient(ellipse 45% 48% at 50% 48%,rgba(177,72,13,.16),rgba(49,18,12,.07) 49%,transparent 75%),linear-gradient(118deg,transparent 27%,rgba(55,24,12,.08) 53%,transparent 83%);mix-blend-mode:screen}';
put('nox-drive-visuals.css',Buffer.from(bg));
edit('index.html','</head>',s=>s.replace('</head>','<link rel="stylesheet" href="./nox-drive-visuals.css" data-nox-source="drive-originals">\n</head>'));
const receipt={schema:'NOX_DRIVE_VISUAL_RESTORE_V1',origin:'EXACT_DRIVE_BYTES',timestamp:'2026-11-16',assets,changed,backendChanged:false,weightsChanged:false,productionDeployed:false,sources:[
'https://drive.google.com/file/d/1T5lNswiov54-84MTI_jvuq787WxY60og/view',
'https://drive.google.com/file/d/1QmMNY9jsRm0aFBIBPb3gIzj4U_KOKwYn/view',
'https://drive.google.com/file/d/18ZZqWEWYSUpvFuLfakpR_lDiU3fS2lw8/view'
]};
put('NOX_DRIVE_VISUAL_RESTORE_RECEIPT.json',Buffer.from(JSON.stringify(receipt,null,2)));
console.log('NOX_DRIVE_ORIGINAL_INSTALL_PASS',JSON.stringify({assets:assets.length,changed:changed.length}));
