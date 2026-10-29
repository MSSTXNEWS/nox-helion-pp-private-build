import test from 'node:test';
import assert from 'node:assert/strict';
import {installNoxCinemaFX} from './nox-cinema.mjs';

class TestClasses {
  constructor(){this.values=new Set();}
  add(x){this.values.add(x);}
  remove(x){this.values.delete(x);}
  contains(x){return this.values.has(x);}
}
class TestNode {
  constructor(doc,tag){
    this.nodeType=1;this.ownerDocument=doc;this.tag=tag;
    this.children=[];this.parent=null;this.classList=new TestClasses();
    this.className='';this.dataset={};
  }
  appendChild(child){this.children.push(child);child.parent=this;return child;}
  contains(node){return node===this||this.children.some(child=>child.contains(node));}
  setAttribute(name,value){if(name==='class')this.className=String(value);}
  querySelector(selector){
    const cls=selector.slice(1);
    const find=node=>node.classList.contains(cls)||node.className.split(' ').includes(cls)
      ? node : node.children.map(find).find(Boolean);
    return this.children.map(find).find(Boolean)||null;
  }
  remove(){
    if(this.parent)this.parent.children=this.parent.children.filter(x=>x!==this);
    this.parent=null;
  }
}
function sceneFixture(rafThrows=false){
  let frames=0;
  const win={
    performance:{now:()=>100},
    requestAnimationFrame:()=>{if(rafThrows)throw Error('RAF_FAILED');return ++frames;},
    cancelAnimationFrame(){},
    matchMedia:()=>({matches:false,addEventListener(){},removeEventListener(){}})
  };
  const doc={
    defaultView:win,hidden:false,
    createElement:tag=>new TestNode(doc,tag),
    createElementNS:(_,tag)=>new TestNode(doc,tag),
    addEventListener(){},removeEventListener(){}
  };
  const root=doc.createElement('section'),orbs=[];
  for(let i=0;i<9;i++){
    const element=doc.createElement('button');
    root.appendChild(element);
    orbs.push({id:i?'CORE_'+i:'HELION',element});
  }
  return {root,orbs};
}
test('G7-A R30: failed D02 subscriptions retire callbacks and release RAF subscription',()=>{
  for(const broken of ['invalid-return','subscribe-throws']){
    const o=sceneFixture();let notify;
    const hostEvents={subscribe(fn){
      notify=fn;
      if(broken==='subscribe-throws')throw Error('SUBSCRIBE_FAILED');
      return undefined;
    }};
    assert.throws(()=>installNoxCinemaFX({...o,hostEvents}),
      broken==='invalid-return' ? /NOX_FX_SUBSCRIBE_REQUIRES_CLEANUP/ : /SUBSCRIBE_FAILED/);
    assert.equal(o.root.classList.contains('nox-cinema-scope'),false);
    assert.equal(o.root.dataset.noxFxState,undefined);
    assert.doesNotThrow(()=>notify({trusted:true,state:'training',runId:'R-STALE'}));
    assert.equal(o.root.dataset.noxFxState,undefined);
    assert.equal(o.orbs.every(x=>x.element.dataset.noxFxState===undefined),true);
    // Rollback did not poison the original stage or block a later owner mount.
    const live=installNoxCinemaFX(o);
    assert.equal(live.snapshot().coreCount,8);
    live.destroy();
  }
  const badRaf=sceneFixture(true);let unsubscribeCalls=0;
  assert.throws(()=>installNoxCinemaFX({...badRaf,hostEvents:{subscribe(){
    return ()=>{unsubscribeCalls++;};
  }}}),/RAF_FAILED/);
  assert.equal(unsubscribeCalls,1);
  assert.equal(badRaf.root.dataset.noxFxState,undefined);
  assert.equal(badRaf.root.classList.contains('nox-cinema-scope'),false);
});
