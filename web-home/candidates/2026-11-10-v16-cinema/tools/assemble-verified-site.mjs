// NOX HOME V18 source integrator. Does not deploy or mutate production.
// Usage:
// node tools/assemble-verified-site.mjs --baseline /path/to/complete/previous-site --output /tmp/nox-v18-assembled
// GitHub candidate folder is the source of truth for changed files only.
// Fails closed if a required historical file or approved asset is missing.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
const here=path.dirname(fileURLToPath(import.meta.url));
const candidate=path.resolve(here,'..');
const args=process.argv;
function option(name){const i=args.indexOf(name);return i>=0?args[i+1]:null}
const baseline=option('--baseline'),output=option('--output');
if(!baseline||!output)throw Error('Required: --baseline COMPLETE_SITE --output EMPTY_STAGING_DIRECTORY');
const src=path.resolve(baseline),dst=path.resolve(output);
if(src===dst||src===candidate||dst===candidate||dst.startsWith(src+path.sep)||src.startsWith(dst+path.sep))throw Error('NOX_UNSAFE_STAGE_PATH');
const exists=async f=>fs.stat(f).then(s=>s.isFile()).catch(()=>false);
if(await fs.stat(dst).then(()=>true).catch(()=>false))throw Error('NOX_OUTPUT_MUST_BE_ABSENT_TO_PROTECT_EXISTING_DATA');
const required=['index.html','nox-home.mjs','nox-ui.css','nox-orbit-original.js','nox-home-recovery.js','nox-engines/physical-worlds-v7.mjs',
'chat.html','cinema.html','install.html','memory.html','models.html','projects.html','settings.html','system.html','training.html'];
const missing=[];for(const p of required)if(!await exists(path.join(src,p)))missing.push(p);
if(missing.length)throw Error('NOX_INCOMPLETE_BASELINE: '+missing.join(', '));
const manifest=JSON.parse(await fs.readFile(path.join(candidate,'ASSET-MANIFEST-V17.json'),'utf8'));
if(manifest.files.length!==14)throw Error('NOX_ASSET_MANIFEST_COUNT');
const assetBase=path.join(src,'assets/nox-approved');
for(const a of manifest.files){
 const p=path.join(assetBase,a.path);
 if(!await exists(p)){missing.push('assets/nox-approved/'+a.path);continue}
 const bytes=await fs.readFile(p),sha=crypto.createHash('sha256').update(bytes).digest('hex');
 if(bytes.length!==a.bytes||sha!==a.sha256)throw Error('NOX_ASSET_INTEGRITY_FAILED: '+a.path);
}
if(missing.length)throw Error('NOX_MISSING_FILES: '+missing.join(', '));
await fs.cp(src,dst,{recursive:true,force:false,errorOnExist:true});
const overlays=[
 ['index.html','index.html'],
 ['nox-engines/physical-worlds-v7.mjs','nox-engines/physical-worlds-v7.mjs'],
 ['nox-cinematic-health.js','nox-cinematic-health.js'],
 ['nox-resonance-cinema-v13.js','nox-resonance-cinema-v13.js'],
 ['nox-resonance-cinema-v13.css','nox-resonance-cinema-v13.css'],
 ['nox-home-recovery.css','nox-home-recovery.css'],
 ['nox-home-flow.js','nox-home-flow.js'],
 ['nox-home-flow.css','nox-home-flow.css'],
 ['industrial-assets.mjs','industrial-assets.mjs'],
 ['nox-global-wow-v18.css','nox-global-wow-v18.css'],
 ['nox-global-wow-v18.js','nox-global-wow-v18.js'],
];
for(const [from,to] of overlays){
 const file=path.join(candidate,from);
 if(!await exists(file))throw Error('NOX_MISSING_PATCH: '+from);
 await fs.mkdir(path.dirname(path.join(dst,to)),{recursive:true});
 await fs.copyFile(file,path.join(dst,to));
}
// Single-source shared design for every live HTML route. Never replace functional page content.
const pages=['index.html','chat.html','cinema.html','install.html','memory.html','models.html','projects.html','settings.html','system.html','training.html'];
for(const file of pages){
 const target=path.join(dst,file);
 let html=await fs.readFile(target,'utf8');
 if(!/<\/head>/i.test(html)||!/<\/body>/i.test(html))throw Error('NOX_HTML_STRUCTURE_INVALID: '+file);
 const vendorGlass='<link rel="stylesheet" href="./vendor/nox-liquid-glass/liquid-glass.css" data-nox-vendor-glass="original">';
 const style='<link rel="stylesheet" href="./nox-global-wow-v18.css" data-nox-wow-shared="v18">';
 const script='<script defer src="./nox-global-wow-v18.js" data-nox-wow-shared="v18"></script>';
 if(!await exists(path.join(dst,'vendor/nox-liquid-glass/liquid-glass.css')))throw Error('NOX_ORIGINAL_GLASS_VENDOR_MISSING');
 if(!html.includes('vendor/nox-liquid-glass/liquid-glass.css'))html=html.replace(/<\/head>/i,vendorGlass+'</head>');
 if(!html.includes('nox-global-wow-v18.css'))html=html.replace(/<\/head>/i,style+'</head>');
 if(!html.includes('nox-global-wow-v18.js'))html=html.replace(/<\/body>/i,script+'</body>');
 await fs.writeFile(target,html);
}
const html=await fs.readFile(path.join(dst,'index.html'),'utf8');
const sameOrigin=['nox-home.mjs','nox-orbit-original.js','nox-engines/physical-worlds-v7.mjs'];
for(const p of sameOrigin){
 if(!await exists(path.join(dst,p)))throw Error('NOX_ENTRYPOINT_MISSING: '+p);
}
if(!html.includes('nox-home.mjs'))throw Error('NOX_MASTER_D02_NOT_REFERENCED');
const report={baseline:src,staging:dst,filesOverlaid:overlays.map(x=>x[1]),approvedAssetFiles:manifest.files.length,pagesEnhanced:pages,visibleDropdownsConvertedAtRuntime:true,assetIntegrity:'SHA256_VERIFIED',browserAcceptance:'NOT_RUN',physicalGpuAcceptance:'HOLD',productionChanged:false};
await fs.writeFile(path.join(dst,'NOX-V18-ASSEMBLY-RECEIPT.json'),JSON.stringify(report,null,2));
console.log('NOX source assembly complete, GPU acceptance HOLD:',JSON.stringify(report));
