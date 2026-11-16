// NOX HELION · install Internet-downloaded ORIGINAL Drive assets in the existing WEB.
// Only visual source files, no replacement site, no backend, OneHost, weights or S03.
// This runs after restore_drive_originals.mjs which verifies the original Drive SHA256.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
const root=path.join(process.cwd(),'web_v29_preview_dist');
const edited=[];
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
function patch(name,fn){
 const file=path.join(root,name);
 if(!fs.existsSync(file))throw Error('NOX_ORIGINAL_SOURCE_MISSING:'+name);
 const orig=fs.readFileSync(file,'utf8'),now=fn(orig);
 if(now===orig)throw Error('NOX_ORIGINAL_PATCH_EMPTY:'+name);
 fs.writeFileSync(file,now);
 edited.push({name,sha256:sha(Buffer.from(now))});
}
for(const pre of ['','pc/']){
 patch(pre+'nox-engines/physical-worlds-v7.mjs',s=>{
  const distinct='./assets/nox-approved/planets/';
  if(!s.includes(distinct)||!s.includes('l.scale.setScalar(o.size)'))
   throw Error('NOX_DISTINCT_PLANET_MAPS_MISSING:'+pre);
  // 8 distinct original planetary maps must remain 8 distinct UV images.
  if(!s.includes('loadedPlanetMaps.add(t)'))throw Error('NOX_PLANET_MAP_AUDIT_MISSING');
  if(s.includes('h.load("./assets/nox-approved/metal/Metal012_2K-JPG_Color.jpg",(()=>{g++;loadedPlanetMaps.add(t)})'))
   throw Error('NOX_ALL_PLANETS_REPLACED_BY_ONE_METAL_TEXTURE');
  s=s.replace('./assets/nox-approved/hdr/machine_shop_01_1k.hdr','./assets/nox-approved/hdr/machine_shop_01_2k.hdr')
   .replaceAll('Metal012_1K-JPG_','Metal012_2K-JPG_');
  const inject=`// Original visual identities stay independent: do NOT apply Metal012 to every world.
if(!o.asteroid&&l.material){
 l.material.roughness=o.rough;l.material.metalness=o.metal;
 if(n===9){l.material.roughness=.34;l.material.metalness=.68;l.material.bumpMap=null;}
 if(n===2){l.material.emissive=new e.Color("#9e2309");l.material.emissiveIntensity=.115;}
 if(n===4){l.material.emissive=new e.Color("#134a52");l.material.emissiveIntensity=.08;}
}
`;
  s=s.replace('l.scale.setScalar(o.size)',inject+'l.scale.setScalar(o.size)');
  if(s.includes('l.material.metalness=.75'))throw Error('NOX_GENERIC_METAL_OVERRIDES_WORLDS');
  return s.replace('engine:"Three.js MeshPhysicalMaterial shared WebGL scene + NASA Bennu geometry"',
    'engine:"8 distinct original UV maps + Drive Metal012 2K Liquid Metal + Poly Haven 2K + NASA Bennu"');
 });
 patch(pre+'eclipse-materials.mjs',s=>{
  const rules=[
   ['vec3(.015,.012,.012),vec3(.080,.062,.053)','vec3(.022,.020,.022),vec3(.092,.073,.063)'],
   ['crust)*(.29+light)','crust)*(.42+light)'],
   ['mappedBase*(.012+.045*light)','mappedBase*(.055+.19*light)'],
   ['vec3(.56,.49,.42),uClassicBlackSun','vec3(.72,.66,.60),uClassicBlackSun'],
   ['molten*(.26+1.52*rim+.44*light)','molten*(.30+1.62*rim+.50*light)'],
   ['if(h<.905)return vec3(0.);','if(h<.865)return vec3(0.);'],
   ['if(h<.935+(.5-cluster)*.045)return vec3(0.);','if(h<.910+(.5-cluster)*.045)return vec3(0.);'],
   ['vec3 sky=vec3(.0014,.0020,.0031)+vec3(.018,.016,.015)*dust*lane;','vec3 sky=vec3(.0018,.0026,.0044)+vec3(.024,.017,.018)*dust*lane;']
  ];
  for(const [before,after] of rules){
   if(!s.includes(before))throw Error('NOX_D02_SHADER_SOURCE_DRIFT:'+before);
   s=s.replace(before,after);
  }
  const anchor='vec2 p=(vUv-center)*span; float radius=length(p), t=clockTime;';
  if(!s.includes(anchor))throw Error('NOX_STARFIELD_SOURCE_DRIFT');
  // Keep ONE existing Three.js shader; use downloaded Codrops heat wave formula
  // close to the corona only, with no new renderer and no flattened PNG.
  s=s.replace(anchor,anchor+`
 float noxHeatBand=exp(-pow((radius-1.045)*13.0,2.0));
 p+=vec2(sin(p.y*25.0-t*.73),sin(p.x*40.0+t*.5))*.0028*noxHeatBand;
 radius=length(p);`);
  return s;
 });
 patch(pre+'industrial-effects.mjs',s=>{
  const old='uClassicBlackSun.value=classic?.68:0';
  if(!s.includes(old))throw Error('NOX_D02_LIGHT_PARAMETER_DRIFT');
  return s.replace(old,'uClassicBlackSun.value=classic?.36:0');
 });
}
const receiptFile=path.join(root,'NOX_DRIVE_VISUAL_RESTORE_RECEIPT.json');
if(!fs.existsSync(receiptFile))throw Error('NOX_DRIVE_ORIGINAL_ASSETS_NOT_INSTALLED');
const receipt=JSON.parse(fs.readFileSync(receiptFile,'utf8'));
receipt.worldFiles=edited;
receipt.worlds14='SOURCE_PATCHED_PENDING_REAL_BROWSER_GPU';
receipt.originalPlanetMapsPreserved=true;
receipt.originalCoreAndStarfieldShadersPreserved=true;
receipt.liveProductionDeployed=false;
fs.writeFileSync(receiptFile,JSON.stringify(receipt,null,2));
console.log('NOX_DRIVE_ORIGINAL_ENGINES_PATCHED',JSON.stringify({files:edited.length,worldMaps:8,material:'Metal012_2K',environment:'PolyHaven_2K',shader:'original D02',nativeGPU:'HOLD'}));
