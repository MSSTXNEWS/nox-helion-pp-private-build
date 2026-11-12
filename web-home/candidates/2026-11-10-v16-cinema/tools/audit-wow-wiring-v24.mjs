/* NOX V24 strict source / asset wiring audit.
   This is NOT a claim that physical GPU, login, voices or full WOW30
   passed runtime acceptance. It rejects missing ORIGINAL source engines. */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
const dir=path.resolve(process.argv[2]||'dist');
const file=name=>{
 const target=path.resolve(dir,name),relative=path.relative(dir,target);
 if(relative.startsWith('..')||path.isAbsolute(relative)||!fs.statSync(target).isFile())throw Error('NOX_SOURCE_OUTSIDE_BUILD:'+name);
 return fs.readFileSync(target);
};
const src=name=>file(name).toString('utf8');
const assert=(condition,reason)=>{if(!condition)throw Error('NOX_WOW_WIRING_MISSING:'+reason)};
const must=(fileName,content)=>assert(src(fileName).includes(content),fileName+':'+content);
const immediate=[
 ['ORIGINAL_D02','nox-home.mjs'],
 ['PHYSICAL_14_WORLDS','nox-engines/physical-worlds-v7.mjs'],
 ['ORIGINAL_ORBIT_MOTION','nox-orbit-14.js'],
 ['THREE_0160','vendor/three/three.module.js'],
 ['THREE_EFFECT_COMPOSER','vendor/three/addons/postprocessing/EffectComposer.js'],
 ['THREE_RENDER_PASS','vendor/three/addons/postprocessing/RenderPass.js'],
 ['THREE_BLOOM','vendor/three/addons/postprocessing/UnrealBloomPass.js'],
 ['THREE_OUTPUT_PASS','vendor/three/addons/postprocessing/OutputPass.js'],
 ['STL_LOADER','vendor/three/addons/loaders/STLLoader.js'],
 ['RGBE_LOADER','vendor/three/addons/loaders/RGBELoader.js'],
 ['ORIGINAL_GSAP','vendor/fx/gsap.min.js'],
 ['ORIGINAL_LIQUID_GLASS','vendor/nox-liquid-glass/liquid-glass.js'],
 ['ORIGINAL_GLASS_CSS','vendor/nox-liquid-glass/liquid-glass.css'],
 ['ORIGINAL_INDUSTRIAL_EFFECTS','industrial-effects.mjs']
];
const lazy=[
 ['TSPARTICLES','vendor/nox-extra/tsparticles.slim.bundle.min.js'],
 ['PHOTOSWIPE','vendor/nox-extra/photoswipe.esm.js'],
 ['FULLCALENDAR','vendor/nox-extra/fullcalendar.global.min.js'],
 ['SHAKA_PLAYER','vendor/nox-extra/shaka-player.compiled.js'],
 ['PDFJS','vendor/nox-extra/pdf.mjs'],
 ['EPUB','vendor/nox-extra/epub.min.js'],
 ['LEAFLET','vendor/nox-extra/leaflet.js'],
 ['FUSE','vendor/nox-extra/fuse.min.js']
];
for(const [,name] of immediate.concat(lazy))assert(file(name).byteLength>900,'EMPTY:'+name);
const index=src('index.html');
must('nox-orbit-14.js','physical-worlds-v7.mjs');
must('nox-orbit-14.js','nox-glass-init.mjs');
must('nox-glass-init.mjs','createLiquidGlass');
must('nox-owner-fidelity-v21.js','window.gsap');
for(const addon of ['EffectComposer.js','RenderPass.js','UnrealBloomPass.js','OutputPass.js'])
 must('nox-home.mjs','three/addons/postprocessing/'+addon);
for(const link of ['nox-home.mjs','nox-orbit-14.js','nox-owner-release-v22.js',
 'nox-visual-source-lock-v24.js','nox-visual-source-lock-v24.css',
 'vendor/three/three.module.js','vendor/fx/gsap.min.js'])assert(index.includes(link),'HOME_UNWIRED:'+link);
const v24=src('nox-visual-source-lock-v24.css');
for(const original of ['#noxEclipseCanvas','#noxWorldsV6Canvas','filter:none!important',
 'nox-core-shell 22s','clip-path:inset(0 0 36% 0)',
 'clip-path:inset(92% 0 0 0)'])assert(v24.includes(original),'V24_FIDELITY:'+original);
for(const lib of ['tsparticles.slim.bundle.min.js','photoswipe.esm.js','fullcalendar.global.min.js',
 'shaka-player.compiled.js','pdf.mjs','epub.min.js','leaflet.js','fuse.min.js'])
 must('nox-universe-v19.js',lib);
const manifest=JSON.parse(src('assets/nox-approved/MANIFEST.json'));
assert(Array.isArray(manifest.files)&&manifest.files.length===14,'14_PBR_HDR_SOURCE_HASHES');
const cssI=index.indexOf('nox-visual-source-lock-v24.css');
const v22I=index.indexOf('nox-owner-release-v22.css');
assert(cssI>v22I&&cssI!==-1,'FIDELITY_CSS_ORDER');
const digest=name=>crypto.createHash('sha256').update(file(name)).digest('hex');
const originalSha256={
 'nox-home.mjs':'8066bc0a0f8ef5bb5f0fb1f58ad3f6ee29dc8506385c09d77d38d4235c7e42e9',
 'nox-engines/physical-worlds-v7.mjs':'3f27609ea37b96579a711928e4c67778ec71e2ff7b090a3b7bb41e29040f3905',
 'assets/nox-owner-approved/NOX_HOME_OWNER_APPROVED_WEB.webp':'3253d26819a70b49259fdb2a56c2eaa2455c6878cb2ccb8d62b225ec6ccdfa22'
};
for(const [name,sha] of Object.entries(originalSha256))
 assert(digest(name)===sha,'ORIGINAL_SOURCE_SHA_CHANGED:'+name);
const report={
 scope:'ORIGINAL_SOURCE_WIRING_ONLY',source_sha256:{
  d02:digest('nox-home.mjs'),pbr14:digest('nox-engines/physical-worlds-v7.mjs'),
  owner_art:digest('assets/nox-owner-approved/NOX_HOME_OWNER_APPROVED_WEB.webp')},
 immediate_engines:immediate.map(x=>x[0]),on_demand_engines:lazy.map(x=>x[0]),
 approved_pbr_hdr_files:manifest.files.length,
 original_shader_modified_by_audit:false,physical_gpu_acceptance:'HOLD',
 owner_visual_acceptance:'HOLD',backend_acceptance:'HOLD',
 no_mock_pass:true
};
console.log('NOX_V24_SOURCE_ENGINES_CHECKED '+JSON.stringify(report));