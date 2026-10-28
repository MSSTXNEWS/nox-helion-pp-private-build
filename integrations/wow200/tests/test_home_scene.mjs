// Source-level 9-sphere mount / identity / visibility regressions.
// Stub ONLY PR30's renderer; actual PR30 files remain SHA-pinned by stage_wow200.py.
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync, mkdirSync, copyFileSync, writeFileSync, rmSync} from 'node:fs';
import {join,dirname} from 'node:path';
import {tmpdir} from 'node:os';
import {pathToFileURL,fileURLToPath} from 'node:url';
const home=fileURLToPath(new URL('../home-scene.mjs',import.meta.url));
const temp=mkdtempSync(join(tmpdir(),'nox-home-mount-'));
const target=join(temp,'runtime','home-scene.mjs');mkdirSync(dirname(target),{recursive:true});copyFileSync(home,target);
const donor=join(temp,'proposals','NOX-CINEMA-FX','nox-cinema.mjs');mkdirSync(dirname(donor),{recursive:true});
writeFileSync(donor,`export function installNoxCinemaFX({root,orbs,profile}) {\n  if (orbs.length!==9||orbs[0].id!=="HELION") throw Error("BAD_ORBS");\n  let visible=true,ended=false,mode=profile;\n  return {setVisible(x){visible=x},setProfile(x){mode=x},snapshot(){return {visible,mode,coreCount:8,ended}},destroy(){ended=true}};\n}\n`);
const {mountApprovedHome}=await import(pathToFileURL(target).href);
const ids=['CONSCIOUSNESS','PERSONA','ATLAS','VOICE','REFLECTION','CORE','NEXUS','FORGE'];
function fixture(custom=ids){
 const central={dataset:{},getAttribute:()=>null};
 const cores=custom.map(coreId=>({dataset:{coreId},getAttribute:()=>null}));
 const stage={querySelector:x=>x==='.nox-eclipse'?central:null,querySelectorAll:x=>
    x==='.nox-orbit-core'?cores:x==='.nox-eclipse'?[central]:[]};
 const home={classList:{contains:x=>x==='screen'||x==='active'},querySelector:x=>x==='.nox-orbit-stage'?stage:null};
 const observers=[];
 class Observer{observe(){observers.push(this)}disconnect(){this.disconnected=true}}
 const doc={body:{classList:{contains:()=>false}},getElementById:x=>x==='home'?home:null,
    defaultView:{MutationObserver:Observer,matchMedia:()=>({matches:false})}};
 return {doc,home,stage,central,cores,observers};
}
test('actual D02 identity mounts exactly HELION + 8 with no fabricated backend',()=>{
 const f=fixture();const mount=mountApprovedHome(f.doc);
 assert.equal(mount.snapshot().coreCount,8);
 assert.equal(mount.snapshot().kind,'decorative-d02');
 assert.equal(mount.snapshot().backendAccepted,false);
 assert.equal(f.observers.length,2);
 assert.equal(f.central.dataset.noxVerifiedFx,'active');
 assert.equal(mount.setProfile('ECO'),undefined);
 assert.equal(mount.snapshot().mode,'ECO');
 mount.destroy();assert.equal(f.central.dataset.noxVerifiedFx,undefined);
 assert.ok(f.observers.every(x=>x.disconnected===true));
});
test('wrong identity cannot mount or silently create fake CoreID',()=>{
 const f=fixture([...ids.slice(0,7),'EXTRA_FAKE']);
 assert.throws(()=>mountApprovedHome(f.doc),/EXACT_HELION_PLUS_EIGHT/);
});
test('missing core cannot mount',()=>{
 const f=fixture(ids.slice(1));
 assert.throws(()=>mountApprovedHome(f.doc),/EXACT_HELION_PLUS_EIGHT/);
});