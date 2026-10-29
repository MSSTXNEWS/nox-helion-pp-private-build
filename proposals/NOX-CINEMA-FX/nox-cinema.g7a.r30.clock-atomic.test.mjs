import test from 'node:test';
import assert from 'node:assert/strict';
import {installNoxCinemaFX} from './nox-cinema.mjs';

// G7-A exclusive regression: rejected ECO transition must not mutate live D02 FX.
class Classes {
  constructor(){this.names=new Set();}
  add(name){this.names.add(name);}
  remove(name){this.names.delete(name);}
  contains(name){return this.names.has(name);}
}
class Element {
  constructor(doc){
    this.nodeType=1;this.ownerDocument=doc;this.children=[];
    this.parent=null;this.classList=new Classes();this.className='';this.dataset={};
  }
  appendChild(child){child.parent=this;this.children.push(child);return child;}
  contains(node){return node===this||this.children.some(child=>child.contains(node));}
  querySelector(selector){
    const cls=selector.slice(1);
    const find=node=>(node.classList.contains(cls)||node.className.split(' ').includes(cls))
      ?node:node.children.map(find).find(Boolean);
    return this.children.map(find).find(Boolean)||null;
  }
  setAttribute(name,value){if(name==='class')this.className=String(value);}
  remove(){
    if(this.parent)this.parent.children=this.parent.children.filter(x=>x!==this);
    this.parent=null;
  }
}
function fixture(){
  let now=100,seq=0;const pending=new Map();
  const win={
    performance:{now:()=>now},
    requestAnimationFrame(fn){pending.set(++seq,fn);return seq;},
    cancelAnimationFrame(id){pending.delete(id);},
    matchMedia(){return {matches:false,addEventListener(){},removeEventListener(){}};}
  };
  const doc={
    defaultView:win,hidden:false,
    createElement:()=>new Element(doc),
    createElementNS:()=>new Element(doc),
    addEventListener(){},removeEventListener(){}
  };
  const root=doc.createElement(),orbs=[];
  for(let index=0;index<9;index++){
    const element=doc.createElement();
    root.appendChild(element);
    orbs.push({id:index?'CORE_'+index:'HELION',element});
  }
  return {
    root,orbs,now:()=>now,
    tick(value){
      now=value;
      const first=pending.entries().next().value;
      if(!first)throw Error('EXPECTED_PENDING_RAF');
      pending.delete(first[0]);first[1](value);
    },
    pending:()=>pending.size
  };
}
test('G7-A R30: ECO rejected on invalid clock leaves live D02 scene unchanged',()=>{
  for(const broken of ['nan','throw']){
    const host=fixture();let clockFault=null;
    const clock=()=>{
      if(clockFault==='nan')return NaN;
      if(clockFault==='throw')throw Error('CLOCK_FAILED');
      return host.now();
    };
    const fx=installNoxCinemaFX({
      root:host.root,orbs:host.orbs,profile:'MAX',
      random:()=>0,clock
    });
    host.tick(5000); // HELION + eight existing orbs produce > ECO particle budget.
    const before=fx.snapshot();
    assert.ok(before.particles>3,'fixture must exceed ECO maxParticles');
    clockFault=broken;
    assert.equal(fx.setProfile('ECO'),false,broken+' rejects profile');
    assert.deepEqual(fx.snapshot(),before,broken+' must not delete live particles');
    clockFault=null;
    assert.equal(fx.setProfile('ECO'),true,'valid clock accepts profile');
    assert.equal(fx.snapshot().particles,3,'accepted ECO now trims live budget');
    assert.equal(fx.snapshot().profile,'ECO');
    fx.destroy();
    assert.equal(host.pending(),0,'no RAF remains after teardown');
    assert.equal(host.root.dataset.noxFxMode,undefined,'original DOM restored');
  }
});
