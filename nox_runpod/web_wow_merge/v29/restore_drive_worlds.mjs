// Drive-original immersive 14-worlds repair. Preserve all original scene controls,
// routes, NASA Bennu geometry and same WebGL owner. No second application/backend.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
const root=path.join(process.cwd(),'web_v29_preview_dist');
const edited=[];
const sha=s=>crypto.createHash('sha256').update(s).digest('hex');
function patch(name,fn){
 const file=path.join(root,name);
 if(!fs.existsSync(file))throw Error('NOX_WORLD_SOURCE_MISSING:'+name);
 const orig=fs.readFileSync(file,'utf8'),now=fn(orig);
 if(now===orig)throw Error('NOX_WORLD_PATCH_NO_EFFECT:'+name);
 fs.writeFileSync(file,now);
 edited.push({name,sha256:sha(Buffer.from(now))});
}
for(const prefix of ['','pc/']){
 patch(prefix+'nox-engines/physical-worlds-v7.mjs',s=>{
  if(!s.includes('l.scale.setScalar(o.size)')||!s.includes('M=e,b+=t,C!=='))throw Error('NOX_WORLD_SOURCE_DRIFT');
  s=s.replace('./assets/nox-approved/hdr/machine_shop_01_1k.hdr','./assets/nox-approved/hdr/machine_shop_01_2k.hdr')
   .replaceAll('Metal012_1K-JPG_','Metal012_2K-JPG_')
   .replace('./assets/nox-approved/planets/"+t+".jpg','./assets/nox-approved/metal/Metal012_2K-JPG_Color.jpg')
   .replace('engine:"Three.js MeshPhysicalMaterial shared WebGL scene + NASA Bennu geometry"','engine:"Verified Drive Metal012 2K PBR + Poly Haven HDRI 2K + NASA Bennu geometry"');
  // Reuse one set of PBR textures across the worlds, not 11 duplicate GPU uploads.
  const locate='const N=new Map,R=[];';
  if(!s.includes(locate))throw Error('NOX_WORLD_MAP_ANCHOR_DRIFT');
  const shared=[
   'const drivePbr={};',
   'const drivePbrNames={normalMap:"Metal012_2K-JPG_NormalGL.jpg",roughnessMap:"Metal012_2K-JPG_Roughness.jpg",metalnessMap:"Metal012_2K-JPG_Metalness.jpg"};',
   'for(const [slot,name] of Object.entries(drivePbrNames)){',
   ' const tx=h.load("./assets/nox-approved/metal/"+name,()=>{',
   '  if(slot==="normalMap")tx.colorSpace=e.NoColorSpace;',
   '  for(const item of R){if(!item.data.asteroid){item.mesh.material[slot]=tx;item.mesh.material.needsUpdate=true;}}',
   ' },void 0,err=>console.error("NOX_DRIVE_PBR_LOAD_HOLD",name,err));',
   ' tx.wrapS=tx.wrapT=e.RepeatWrapping;tx.anisotropy=Math.min(8,r.capabilities.getMaxAnisotropy());',
   ' drivePbr[slot]=tx;',
   '}'
  ].join('\n');
  s=s.replace(locate,locate+shared);
  const inject=[
   'if(!o.asteroid && l.material){',
   ' l.material.metalness=.75;l.material.roughness=.39;l.material.bumpMap=null;',
   ' Object.assign(l.material,drivePbr);',
   ' const gold=["#f6ad58","#e69e47","#ff692d","#72c5dc","#59caa3","#b38be2","#ffb55b","#cdb0a4","#6ca7d1","#e4c8a9","#77d9c4"];',
   ' l.material.emissive=new e.Color(gold[n]||"#d5ab6a");l.material.emissiveIntensity=.10;',
   ' l.material.onBeforeCompile=shader=>{',
   '  shader.uniforms.uNoxMoltenTime={value:0};shader.uniforms.uNoxMoltenColor={value:l.material.emissive};',
   '  shader.vertexShader=shader.vertexShader.replace("void main() {","varying vec3 vNoxMineral; void main() {").replace("#include <begin_vertex>","#include <begin_vertex>\\nvNoxMineral=position;");',
   '  shader.fragmentShader=shader.fragmentShader.replace("void main() {","varying vec3 vNoxMineral; uniform float uNoxMoltenTime; uniform vec3 uNoxMoltenColor; void main() {").replace("#include <emissivemap_fragment>", "#include <emissivemap_fragment>\\n"+',
   '   "float lineA=sin(vNoxMineral.x*29.0+vNoxMineral.y*31.0+sin(vNoxMineral.z*19.0)*4.0+uNoxMoltenTime*.12);\\n"+',
   '   "float lineB=sin(vNoxMineral.z*33.0-vNoxMineral.y*20.0+sin(vNoxMineral.x*15.0)*4.0-uNoxMoltenTime*.09);\\n"+',
   '   "float cracks=pow(1.0-abs(lineA),22.0)+pow(1.0-abs(lineB),25.0);\\n"+',
   '   "float patch=0.55+0.45*sin(vNoxMineral.x*10.0+sin(vNoxMineral.z*6.0)*2.0);\\n"+',
   '   "totalEmissiveRadiance+=uNoxMoltenColor*min(1.0,cracks*patch)*1.45;");',
   '  l.material.userData.noxMoltenShader=shader;',
   ' };',
   '}'
  ].join('\n');
  s=s.replace('l.scale.setScalar(o.size)',inject+'\nl.scale.setScalar(o.size)');
  s=s.replace('M=e,b+=t,C!==','M=e,b+=t,R.forEach(item=>{const sh=item.mesh.material?.userData?.noxMoltenShader;if(sh)sh.uniforms.uNoxMoltenTime.value=b;}),C!==');
  return s;
 });
}
for(const p of ['nox-core-bg.mjs','pc/nox-core-bg.mjs']){
 const f=path.join(root,p);
 if(fs.existsSync(f)){
  const before=fs.readFileSync(f,'utf8');
  const after=before.replace('filter:brightness(.8) saturate(.82)','filter:brightness(1.08) saturate(1.04)');
  if(after!==before){fs.writeFileSync(f,after);edited.push({name:p,sha256:sha(Buffer.from(after))})}
 }
}
const receiptFile=path.join(root,'NOX_DRIVE_VISUAL_RESTORE_RECEIPT.json');
const receipt=JSON.parse(fs.readFileSync(receiptFile,'utf8'));
receipt.worldFiles=edited;receipt.worlds14='SOURCE_PATCHED_PENDING_BROWSER_GPU';
receipt.originalControls=true;receipt.productionDeployed=false;
fs.writeFileSync(receiptFile,JSON.stringify(receipt,null,2));
console.log('NOX_DRIVE_WORLDS_INSTALL_PASS',JSON.stringify({files:edited.length,pbr:'2K',hdr:'2K',renderAcceptance:'PENDING_BROWSER_GPU'}));
