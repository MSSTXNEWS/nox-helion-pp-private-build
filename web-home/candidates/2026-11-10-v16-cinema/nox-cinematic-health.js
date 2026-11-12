/* NOX HOME V18 — read-only, no synthetic GPU metrics or fake PASS.
   Inspection is opt-in via window.NOX_CINEMATIC_HEALTH. */
(()=>{'use strict';
const base="./assets/nox-approved/";
const finite=n=>typeof n==="number"&&Number.isFinite(n);
const capture=(fn)=>{try{return typeof fn==="function"?fn():null;}catch(e){return {error:String(e?.message||e)};}};
function snapshot(){
 const core=capture(window.noxHomeDiagnostics);
 const world=capture(window.NOX_PHYSICAL_WORLDS_QA);
 const orbit=capture(window.NOX_ORBIT_14_DEMO?.diagnostics);
 const motion=capture(window.NOX_ORBIT_MOTION_QA);
 const fallback=capture(window.NOX_HOME_RECOVERY_QA);
 const resonance=capture(window.NOX_RESONANCE_VISUAL_QA);
 const industrial=core?.industrial||null;
 const selectors=[...document.querySelectorAll('.nox-orbital-controls button.nox-free-drift-object')];
 const selected=selectors.filter(b=>b.getAttribute('aria-pressed')==='true').length;
 const interactive=[...document.querySelectorAll('a[href],button')].filter(el=>{const b=el.getBoundingClientRect(),cs=getComputedStyle(el);return b.width>0&&b.height>0&&cs.visibility!=='hidden'&&cs.display!=='none';});
 const interactiveBounds=interactive.map(el=>({label:el.getAttribute('aria-label')||el.textContent.trim().slice(0,60),href:el.getAttribute('href'),r:el.getBoundingClientRect()}));
 const minHitSize=interactiveBounds.filter(x=>x.r.width<24||x.r.height<24).map(x=>({label:x.label,width:Math.round(x.r.width),height:Math.round(x.r.height)}));
 const outOfViewport=interactiveBounds.filter(x=>x.r.right>innerWidth+2||x.r.left< -2).map(x=>({label:x.label,x:Math.round(x.r.left),right:Math.round(x.r.right)}));
 const overlap=(a,b)=>{const x=Math.max(0,Math.min(a.right,b.right)-Math.max(a.left,b.left)),y=Math.max(0,Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top));return x*y};
 const resonanceLink=document.getElementById('noxCoreEntry')||document.getElementById('homeChatTile');
 const resonanceRect=resonanceLink?.getBoundingClientRect();
 const coreRect=document.getElementById('noxEclipseCanvas')?.getBoundingClientRect();
 const resonanceCoreOverlay=Boolean(resonanceRect&&coreRect&&overlap(resonanceRect,coreRect)>0); // canvas may intentionally cover full stage; only informational.
 const controlBounds=selectors.map(el=>el.getBoundingClientRect());
 const controlOverlaps=[];for(let i=0;i<controlBounds.length;i++)for(let j=i+1;j<controlBounds.length;j++)if(overlap(controlBounds[i],controlBounds[j])>16)controlOverlaps.push([i,j]);
 const main=document.getElementById('noxEclipseCanvas');
 const pbr=document.getElementById('noxWorldsV6Canvas');
 const rect=x=>{if(!x)return null;const b=x.getBoundingClientRect();return {x:+b.left.toFixed(1),y:+b.top.toFixed(1),width:+b.width.toFixed(1),height:+b.height.toFixed(1)};};
 const coreReal=!!(core?.status==='READY'&&finite(core?.renderCount)&&core.renderCount>0);
 const pbrReal=!!(world?.render==='yes'&&world.count===14&&world.allMaterialAssetsReady===true&&world.textureFailures===0);
 return {
  inspectedAt:new Date().toISOString(),viewport:[innerWidth,innerHeight],reducedMotion:matchMedia('(prefers-reduced-motion: reduce)').matches,
  core:{state:core?.status||'UNAVAILABLE',realFrameCount:core?.renderCount??null,renderer:core?.threeRevision?'Three.js':null,realRendered:coreReal,fallback:fallback?.render||null,rect:rect(main)},
  worlds:{count:world?.count??null,realRendered:pbrReal,hdrEnvironment:world?.hdrEnvironment??'UNVERIFIED',assetBase:world?.assetBase??null,mapsLoaded:world?.texturesLoaded??null,planetMapsReady:world?.planetMapsReady??null,metalMapsReady:world?.metalMapsReady??null,allMaterialAssetsReady:world?.allMaterialAssetsReady===true,loadFailures:world?.textureFailures??null,asteroid:world?.asteroid??null,rect:rect(pbr)},
  effects:{industrialMaps:industrial?.maps??null,industrialEnvironment:industrial?.environment??null,heatPass:industrial?.heat??null,errors:industrial?.errors??[]},
  motion:{frames:motion?.frames??null,contacts:motion?.actualImpacts??null,blocked:motion?.blockedMoves??null,overlappingPairs:orbit?.collisionPairs??null},
  controls:{total:selectors.length,selected,expected:14,overlappingControlPairs:controlOverlaps,outOfViewport,minHitSize},layout:{resonanceOverStageCanvas:resonanceCoreOverlay,interactiveCount:interactive.length,viewport:innerWidth},resonance:{href:resonance?.link??null,frames:resonance?.frames??null,rect:rect(document.getElementById('noxCoreEntry'))},
  graphicsAcceptance:coreReal&&pbrReal&&selectors.length===14&&selected===3&&orbit?.collisionPairs===0&&controlOverlaps.length===0&&outOfViewport.length===0?'CANDIDATE':'HOLD',
  notes:'A candidate still requires on-device screenshot, long-running collision/motion and local runtime acceptance.'
 };
}
async function checkAssets(){
 const response=await fetch(base+'MANIFEST.json',{cache:'no-store'});
 if(!response.ok)throw Error('NOX_ASSET_MANIFEST_HTTP_'+response.status);
 const manifest=await response.json();
 const results=[];
 for(const item of manifest.files){
  const res=await fetch(base+item.path,{cache:'force-cache'});
  if(!res.ok){results.push({path:item.path,state:'HTTP_'+res.status});continue;}
  const bytes=await res.arrayBuffer();
  const digest=await crypto.subtle.digest('SHA-256',bytes);
  const sha=[...new Uint8Array(digest)].map(x=>x.toString(16).padStart(2,'0')).join('');
  results.push({path:item.path,state:sha===item.sha256&&bytes.byteLength===item.bytes?'PASS':'HASH_MISMATCH',bytes:bytes.byteLength});
 }
 return {total:results.length,passed:results.filter(x=>x.state==='PASS').length,results,visualQA:'NOT_TESTED_BY_THIS_CHECK'};
}
window.NOX_CINEMATIC_HEALTH=Object.freeze({snapshot,checkAssets});
})();