/* NOX V16 G3-03 R13 — independent source-level D02 RED regression.
 * Owner: G3-03 visual QA. Only reads E01/WOW staging owner source.
 * Tests the REAL home-scene.mjs mount function with a controlled DOM/matchMedia
 * fixture; no claims about Windows/WebView2 or final approved assets.
 * Do not edit the owner module or claim a passing EXE from these checks.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';

const OWNER = new URL('../../../integrations/wow200/runtime/home-scene.mjs', import.meta.url);
const EXPECTED = Object.freeze([
  'CONSCIOUSNESS','PERSONA','ATLAS','VOICE',
  'REFLECTION','CORE','NEXUS','FORGE'
]);

function probe({reducedAtStart=false,initialBodyMode='BALANCED',ids=EXPECTED}={}) {
  const source=readFileSync(OWNER,'utf8');
  const ownerBlob=createHash('sha1')
    .update(`blob ${Buffer.byteLength(source,'utf8')}\0`).update(source,'utf8')
    .digest('hex');
  const bare=source.replace(/^import\s+[^\n]*\n/gm,'')
    .replace(/^export\s+/gm,'');
  assert.match(bare,/function mountApprovedHome\(/,
    'owner D02 source missing: cannot use a replacement fixture');
  let reduced=reducedAtStart,profile=null,visible=null,destroyed=false;
  const profiles=[],listeners=new Set(),watches=[];
  const media={
    get matches(){return reduced;},
    addEventListener(type,fn){if(type==='change')listeners.add(fn);},
    removeEventListener(type,fn){if(type==='change')listeners.delete(fn);}
  };
  const bodyClasses=new Set(initialBodyMode==='MAX'?['nox-wow-max']:
    initialBodyMode==='ECO'?['nox-wow-eco']:[]);
  const homeClasses=new Set(['screen','active']);
  const body={classList:{contains:name=>bodyClasses.has(name)}};
  const home={classList:{contains:name=>homeClasses.has(name)},
    querySelector:name=>name==='.nox-orbit-stage'?stage:null};
  class MutationObserver {
    constructor(fn){this.fn=fn;this.active=true;}
    observe(node){watches.push({node,observer:this});}
    disconnect(){this.active=false;}
  }
  const view={matchMedia:()=>media,MutationObserver};
  const central={dataset:{},getAttribute:name=>
    name==='data-nox-verified-fx'?central.dataset.noxVerifiedFx:null};
  const items=ids.map(coreId=>({dataset:{coreId},getAttribute(name){
    return name==='data-nox-verified-fx'?this.dataset.noxVerifiedFx:null;
  }}));
  const stage={
    querySelector:sel=>sel==='.nox-eclipse'?central:null,
    querySelectorAll:sel=>sel==='.nox-orbit-core'?items:
      sel==='.nox-eclipse'?[central]:[]
  };
  const doc={body,defaultView:view,getElementById:id=>id==='home'?home:null};
  const fx={
    setVisible(value){visible=value;return true;},
    setProfile(value){profile=value;profiles.push(value);return true;},
    snapshot(){return {profile};},
    destroy(){destroyed=true;}
  };
  const captured=[];
  const installNoxCinemaFX=args=>{
    captured.push(args);profile=args.profile;profiles.push(profile);return fx;
  };
  const moduleFactory=new Function('installNoxCinemaFX',
    `${bare}\nreturn {mountApprovedHome,CANONICAL_CORES};`);
  const module=moduleFactory(installNoxCinemaFX);
  const emitMutation=node=>{
    for(const w of watches)if(w.node===node&&w.observer.active)w.observer.fn();
  };
  return {
    ownerBlob,module,doc,ids,central,items,captured,profiles,
    mount:()=>module.mountApprovedHome(doc),
    get profile(){return profile;},get visible(){return visible;},
    get destroyed(){return destroyed;},get motionListeners(){return listeners.size;},
    setBodyMode(next){bodyClasses.delete('nox-wow-eco');bodyClasses.delete('nox-wow-max');
      if(next==='ECO'||next==='MAX')bodyClasses.add(`nox-wow-${next.toLowerCase()}`);
      emitMutation(body);
    },
    setReduced(next){reduced=next;
      for(const fn of [...listeners])fn({matches:next});
    },
    toggleHome(active){if(active)homeClasses.add('active');else homeClasses.delete('active');
      emitMutation(home);
    }
  };
}

test('CANONICAL: exactly eight unique approved CoreIDs and one HELION',()=>{
  const t=probe(),s=t.mount();
  try {
    assert.deepEqual(t.module.CANONICAL_CORES,EXPECTED);
    assert.deepEqual(t.captured[0].orbs.map(x=>x.id),['HELION',...EXPECTED]);
  }finally{s.destroy();}
});

test('CANONICAL: duplicate CoreID is rejected before FX installation',()=>{
  const dup=[...EXPECTED];dup[7]=dup[0];const t=probe({ids:dup});
  assert.throws(()=>t.mount(),/D02_EXACT_HELION_PLUS_EIGHT_CORE_LOCK/);
  assert.equal(t.captured.length,0);
});

test('GREEN: normal idle BALANCED profile and truthful decorative snapshot',()=>{
  const t=probe(),s=t.mount();
  try {
    assert.equal(t.profile,'BALANCED');
    assert.equal(s.snapshot().backendAccepted,false);
    assert.equal(s.snapshot().kind,'decorative-d02');
  }finally{s.destroy();}
});

test('GREEN: ECO body class changes actual FX profile',()=>{
  const t=probe(),s=t.mount();
  try {t.setBodyMode('ECO');assert.equal(t.profile,'ECO');}
  finally{s.destroy();}
});

test('GREEN: MAX body class changes actual FX profile when motion allowed',()=>{
  const t=probe(),s=t.mount();
  try {t.setBodyMode('MAX');assert.equal(t.profile,'MAX');}
  finally{s.destroy();}
});

test('GREEN: initial OS Reduced Motion takes precedence over MAX',()=>{
  const t=probe({reducedAtStart:true,initialBodyMode:'MAX'}),s=t.mount();
  try {assert.equal(t.profile,'REDUCED');}
  finally{s.destroy();}
});

test('RED: OS Reduced Motion change must immediately reduce the primary FX',()=>{
  const t=probe(),s=t.mount();
  try {t.setReduced(true);assert.equal(t.profile,'REDUCED');}
  finally{s.destroy();}
});

test('RED: clearing OS Reduced Motion must restore the requested MAX mode',()=>{
  const t=probe({reducedAtStart:true,initialBodyMode:'MAX'}),s=t.mount();
  try {t.setReduced(false);assert.equal(t.profile,'MAX');}
  finally{s.destroy();}
});

test('RED: public setProfile(MAX) must not bypass active OS Reduced Motion',()=>{
  const t=probe({reducedAtStart:true}),s=t.mount();
  try {s.setProfile('MAX');assert.equal(t.profile,'REDUCED');}
  finally{s.destroy();}
});

test('RED: Reduced Motion listener must be disposed with scene',()=>{
  const t=probe(),s=t.mount();
  try {assert.equal(t.motionListeners,1,'primary FX has no matchMedia change listener');}
  finally {s.destroy();assert.equal(t.motionListeners,0);}
});

test('GREEN: dispose restores original attributes and stops mutation sync',()=>{
  const t=probe(),s=t.mount();
  assert.equal(t.central.dataset.noxVerifiedFx,'active');
  s.destroy();
  assert.equal(t.central.dataset.noxVerifiedFx,undefined);
  assert.ok(t.items.every(x=>x.dataset.noxVerifiedFx===undefined));
  const n=t.profiles.length;
  t.setBodyMode('ECO');
  assert.equal(t.profiles.length,n);
  assert.equal(t.destroyed,true);
});

test('GREEN: hidden HOME turns off visual visibility without changing real states',()=>{
  const t=probe(),s=t.mount();
  try {t.toggleHome(false);assert.equal(t.visible,false);
    t.toggleHome(true);assert.equal(t.visible,true);}
  finally{s.destroy();}
});
