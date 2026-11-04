// Source-level 9-sphere mount / identity / visibility regressions.
// Stub ONLY PR30's renderer; actual PR30 files remain SHA-pinned by stage_wow200.py.
import test from 'node:test';
import {makeFakeD02Dom} from './fake_d02_dom.mjs';
import assert from 'node:assert/strict';
import {mkdtempSync, mkdirSync, copyFileSync, writeFileSync, rmSync} from 'node:fs';
import {join,dirname} from 'node:path';
import {tmpdir} from 'node:os';
import {pathToFileURL,fileURLToPath} from 'node:url';
const home=fileURLToPath(new URL('../runtime/home-scene.mjs',import.meta.url));
const temp=mkdtempSync(join(tmpdir(),'nox-home-mount-'));
const target=join(temp,'runtime','home-scene.mjs');mkdirSync(dirname(target),{recursive:true});copyFileSync(home,target);
const donor=join(temp,'proposals','NOX-CINEMA-FX','nox-cinema.mjs');mkdirSync(dirname(donor),{recursive:true});
writeFileSync(donor,`export function installNoxCinemaFX({root,orbs,profile}) {\n  if (orbs.length!==9||orbs[0].id!=="HELION") throw Error("BAD_ORBS");\n  let visible=true,ended=false,mode=profile;\n  return {setVisible(x){visible=x},setProfile(x){mode=x;return true},snapshot(){return {visible,mode,coreCount:8,ended}},destroy(){ended=true}};\n}\n`);
const {mountApprovedHome}=await import(pathToFileURL(target).href);
const ids=['CONSCIOUSNESS','PERSONA','ATLAS','VOICE','REFLECTION','CORE','NEXUS','FORGE'];
function fixture(custom=ids){return makeFakeD02Dom({coreIds:custom});}

test('actual D02 identity mounts exactly HELION + 8 with no fabricated backend',()=>{
 const f=fixture();const mount=mountApprovedHome(f.doc);
 assert.equal(mount.snapshot().coreCount,8);
 assert.equal(mount.snapshot().kind,'decorative-d02');
 assert.equal(mount.snapshot().backendAccepted,false);
 assert.equal(f.observers.length,2);
 assert.equal(f.central.dataset.noxVerifiedFx,'active');
 assert.equal(mount.setProfile('ECO'),true);
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
test('five genuine planet buttons switch quality; manual selection ends AUTO',()=>{
 const f=fixture(),mount=mountApprovedHome(f.doc),dock=f.findDock();
 assert.ok(dock,'five-planet dock must physically mount on HOME');
 const buttons=[...f.findButtons()];
 assert.deepEqual(buttons.map(b=>b.dataset.quality),
   ['MAX_WOW','CINEMA','ECO','MINI_START','AUTO']);
 assert.equal(dock.dataset.noxEffective,'balanced');
 buttons[0].emit('click');
 assert.equal(mount.snapshot().mode,'MAX');
 assert.equal(dock.dataset.noxEffective,'max');
 assert.equal(f.stored.get('nox.d02.graphics.preference.v1'),'MAX_WOW');
 buttons[3].emit('click');
 assert.equal(mount.snapshot().mode,'REDUCED');
 assert.equal(dock.dataset.noxEffective,'reduced');
 buttons[4].emit('click');
 assert.equal(dock.dataset.noxSelected,'auto');
 assert.ok(f.frames.size>0,'AUTO must sample real frames only on opt-in');
 buttons[2].emit('click');
 assert.equal(mount.snapshot().mode,'ECO');
 assert.equal(f.frames.size,0,'manual ECO must cancel AUTO');
 assert.equal(f.stored.get('nox.d02.graphics.preference.v1'),'ECO');
 mount.destroy();
 assert.equal(f.findDock(),undefined);
 assert.equal(f.intervals.size,0);
});
test('planetary world panels and palette switch without native model or GPU writes',()=>{
 const f=fixture(),mount=mountApprovedHome(f.doc),dock=f.findDock();
 const toggle=dock.children[0].children.at(-1);
 assert.equal(toggle.getAttribute('aria-expanded'),'false');
 toggle.emit('click');
 assert.equal(toggle.getAttribute('aria-expanded'),'true');
 assert.equal(dock.children[2].hidden,false);
 assert.equal(f.home.dataset.noxWorldOpen,'true','expanded cockpit must reenter document flow');
 const palettes=dock.children[2].children[2].children;
 assert.equal(palettes.length,3);
 palettes[1].emit('click');
 assert.equal(f.home.dataset.noxPlanetPalette,palettes[1].dataset.palette);
 const panelActions=dock.children[2].children[3].children;
 assert.equal(panelActions[0].href,'/creative/studio.html');
 assert.equal(panelActions[1].href,'/creative/modelcenter/index.html');
 assert.ok(f.intervals.size>0);
 mount.destroy();
 assert.equal(f.intervals.size,0);
 assert.equal(f.home.dataset.noxPlanetPalette,undefined);
 assert.equal(f.home.dataset.noxWorldOpen,undefined);
});
