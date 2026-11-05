// E01 W2 R17: source-derived DOM lifecycle checks; NO native WebView2 claim.
// Run on exact owner source: node --test integrations/wow200/runtime/home-scene.lifecycle.r17.test.mjs
import {readFileSync} from 'node:fs';
import {makeFakeD02Dom} from '../tests/fake_d02_dom.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';

const raw=readFileSync(new URL('./home-scene.mjs',import.meta.url),'utf8');
const clean=raw.replace(/^import \{installNoxCinemaFX\} from .*;\r?\n/m,'')
  .replace(/^export /gm,'')
  .replace(/^if\(typeof document!=='undefined'\)\{[\s\S]*$/m,'');
const factory=new Function('installNoxCinemaFX','document','console',clean+'\nreturn mountApprovedHome');

function harness(options={}){
 const f=makeFakeD02Dom({reduced:!!options.reduced,throwObserver:!!options.throwObserver});
 let created=0,disposed=0,throwSync=!!options.throwSync;
 const renderer=opts=>{created++;return {
   setVisible(){if(throwSync){throwSync=false;throw Error('SYNC_FAIL');}return true;},
   setProfile(){return true;},
   snapshot(){return {profile:opts.profile,frames:0,particles:0};},
   destroy(){disposed++;if(options.throwRendererDestroy)throw Error('DESTROY_FAIL');}
 }};
 return {mount:factory(renderer,undefined,{warn(){}}),doc:f.doc,
   all:[f.central,...f.cores],counts:()=>({created,disposed})};
}

test('E01-W2-R17-01: failed sync returns all nine FX markers and permits remount',()=>{
  const f=harness({throwSync:true});
  assert.throws(()=>f.mount(f.doc),/SYNC_FAIL/);
  assert.ok(f.all.every(e=>e.dataset.noxVerifiedFx!=='active'));
  const second=f.mount(f.doc);
  assert.equal(f.counts().created,2);
  second.destroy();
});

test('E01-W2-R17-02: observer disconnect fault does not trap ownership',()=>{
  const f=harness({throwObserver:true}),first=f.mount(f.doc);
  first.destroy();
  assert.ok(f.all.every(e=>e.dataset.noxVerifiedFx!=='active'));
  assert.equal(f.counts().disposed,1);
  assert.notEqual(f.mount(f.doc),first);
});

test('E01-W2-R17-03: stale destroy cannot poison a newer mount',()=>{
  const f=harness(),first=f.mount(f.doc);
  first.destroy();
  const second=f.mount(f.doc);
  first.destroy();
  assert.ok(f.all.every(e=>e.dataset.noxVerifiedFx==='active'));
  assert.equal(f.mount(f.doc),second);
  second.destroy();
});

test('E01-W2-R17-04: native renderer teardown exception must release mounted handle',()=>{
  const f=harness({throwRendererDestroy:true}),first=f.mount(f.doc);
  assert.throws(()=>first.destroy(),/DESTROY_FAIL/);
  assert.ok(f.all.every(e=>e.dataset.noxVerifiedFx!=='active'));
  assert.notEqual(f.mount(f.doc),first);
});

test('regression: HELION + eight original CoreIDs remain intact',()=>{
  const f=harness(),scene=f.mount(f.doc);
  assert.equal(f.all.length,9);
  assert.ok(f.all.every(e=>e.dataset.noxVerifiedFx==='active'));
  scene.destroy();
});

test('regression: Windows reduced-motion initial profile remains dominant',()=>{
  const f=harness({reduced:true}),scene=f.mount(f.doc);
  assert.equal(scene.snapshot().profile,'REDUCED');
  scene.destroy();
});
