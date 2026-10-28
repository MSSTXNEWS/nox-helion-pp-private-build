import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import assert from 'node:assert/strict';

const raw=readFileSync(new URL('./home-scene.mjs',import.meta.url),'utf8');
const clean=raw.replace(/^import \\{installNoxCinemaFX\\} from .*;\\r?\\n/m,'').replace(/^export /gm,'')
  .replace(/^if\\(typeof document!=='undefined'\\)\\{[\\s\\S]*$/m,'');
const factory=new Function('installNoxCinemaFX','document','console',clean+'\\nreturn mountApprovedHome');

function fixture({failInitial=false}={}){
  const ids=['CONSCIOUSNESS','PERSONA','ATLAS','VOICE','REFLECTION','CORE','NEXUS','FORGE'];
  const central={dataset:{},getAttribute(){return null}};
  const items=ids.map(coreId=>({dataset:{coreId},getAttribute(){return null}}));
  const stage={querySelector:s=>s==='.nox-eclipse'?central:null,
    querySelectorAll:s=>s==='.nox-orbit-core'?items:s==='.nox-eclipse'?[central]:[]};
  const home={querySelector:s=>s==='.nox-orbit-stage'?stage:null,
    classList:{contains:s=>s==='screen'||s==='active'}};
  const queuedMutation=[],queuedMotion=[];
  const media={matches:false,addEventListener:(_,cb)=>queuedMotion.push(cb),removeEventListener(){}};
  class Observer {constructor(cb){queuedMutation.push(cb)}observe(){}disconnect(){}}
  const doc={body:{classList:{contains:()=>false}},
    defaultView:{MutationObserver:Observer,matchMedia:()=>media},
    getElementById:id=>id==='home'?home:null};
  let destroyed=false,postDisposeCalls=0,liveCalls=0,initialFailure=failInitial;
  const renderer=()=>({
    setVisible(){if(destroyed){postDisposeCalls++;throw Error('DEAD_RENDERER_CALLED')}
      if(initialFailure){initialFailure=false;throw Error('INITIAL_SYNC_FAILURE')}
      liveCalls++;return true},
    setProfile(){if(destroyed){postDisposeCalls++;throw Error('DEAD_RENDERER_CALLED')}return true},
    destroy(){destroyed=true},snapshot(){return {}}
  });
  return {mount:factory(renderer,undefined,{warn(){}}),doc,queuedMutation,queuedMotion,
    state:()=>({destroyed,postDisposeCalls,liveCalls})};
}

test('E01-W2-R20-01 queued MutationObserver never calls a disposed D02 renderer',()=>{
  const f=fixture(),scene=f.mount(f.doc);scene.destroy();
  assert.doesNotThrow(()=>f.queuedMutation[0]());
  assert.equal(f.state().postDisposeCalls,0);
});
test('E01-W2-R20-02 queued OS Reduced Motion callback cannot resurrect disposed D02',()=>{
  const f=fixture(),scene=f.mount(f.doc);scene.destroy();
  assert.doesNotThrow(()=>f.queuedMotion[0]());
  assert.equal(f.state().postDisposeCalls,0);
});
test('regression R17: partial failed mount also fences queued MutationObserver',()=>{
  const f=fixture({failInitial:true});
  assert.throws(()=>f.mount(f.doc),/INITIAL_SYNC_FAILURE/);
  assert.equal(f.state().destroyed,true);
  assert.doesNotThrow(()=>f.queuedMutation[0]());
  assert.equal(f.state().postDisposeCalls,0);
});
test('regression: live D02 observers still update state until destroy',()=>{
  const f=fixture(),scene=f.mount(f.doc);
  f.queuedMutation[0]();f.queuedMotion[0]();
  assert.equal(f.state().liveCalls,3);
  scene.destroy();
});
