import test from 'node:test';
import assert from 'node:assert/strict';
import {installNoxCinemaFX} from './nox-cinema.mjs';

// G7-A only: original D02 scene; fake DOM/RAF and OS media events, no installer.
class Classes {
  constructor(){this.names=new Set();}
  add(name){this.names.add(name);}
  remove(name){this.names.delete(name);}
  contains(name){return this.names.has(name);}
}
class Element {
  constructor(doc,tag){
    this.nodeType=1;this.ownerDocument=doc;this.tag=tag;
    this.children=[];this.parent=null;this.classList=new Classes();
    this.className='';this.dataset={};
  }
  appendChild(child){this.children.push(child);child.parent=this;return child;}
  contains(node){return node===this||this.children.some(child=>child.contains(node));}
  querySelector(selector){
    const cls=selector.slice(1);
    const find=node=>(node.classList.contains(cls)||node.className.split(' ').includes(cls))
      ?node:node.children.map(find).find(Boolean);
    return this.children.map(find).find(Boolean)||null;
  }
  setAttribute(key,value){if(key==='class')this.className=String(value);}
  remove(){
    if(this.parent)this.parent.children=this.parent.children.filter(x=>x!==this);
    this.parent=null;
  }
}
function fixture(){
  let now=100,seq=0,brokenClock=false,motion=null;
  const pending=new Map();
  const win={
    performance:{now:()=>now},
    requestAnimationFrame(fn){pending.set(++seq,fn);return seq;},
    cancelAnimationFrame(id){pending.delete(id);},
    matchMedia(){return {matches:false,
      addEventListener(_event,fn){motion=fn;},
      removeEventListener(){motion=null;}
    };}
  };
  const doc={
    defaultView:win,hidden:false,
    createElement:tag=>new Element(doc,tag),
    createElementNS:(_,tag)=>new Element(doc,tag),
    addEventListener(){},removeEventListener(){}
  };
  const root=doc.createElement('section');
  const orbs=[];
  for(let index=0;index<9;index++){
    const element=doc.createElement('button');
    root.appendChild(element);
    orbs.push({id:index?'CORE_'+index:'HELION',element});
  }
  return {
    root,orbs,clock:()=>brokenClock?NaN:now,
    advance(value){now=value;},
    failClock(){brokenClock=true;},
    motion(matches){if(!motion)throw Error('MOTION_LISTENER_MISSING');motion({matches});},
    tick(value){
      now=value;
      const first=pending.entries().next().value;
      if(!first)throw Error('EXPECTED_PENDING_RAF');
      pending.delete(first[0]);first[1](value);
    },
    pending:()=>pending.size
  };
}

// G7-A private targeted regression; no Installer, PACK01, PACK02 or native build.
test('G7-A R30 explicit REDUCED resume respects the new fast-profile maximum burst deadline',()=>{
  for(const [profile,min,max] of [['MAX',10000,22000],['BALANCED',18000,35000]]){
    const host=fixture();
    const fx=installNoxCinemaFX({root:host.root,orbs:host.orbs,
      profile:'BALANCED',random:()=>.5,clock:host.clock});
    assert.equal(fx.setProfile('ECO'),true,'enter slow profile');
    host.tick(32110);
    assert.equal(fx.snapshot().emitted,2,'ECO initial burst');
    assert.equal(fx.setProfile('REDUCED'),true,'explicit pause');
    assert.equal(fx.snapshot().profile,'REDUCED');
    assert.equal(host.pending(),0,'RAF stopped');
    assert.equal(fx.setProfile(profile),true,'resume '+profile);
    assert.equal(fx.snapshot().profile,profile);
    host.tick(32111);
    assert.equal(fx.snapshot().emitted,2,'no immediate stale burst '+profile);
    host.tick(32110+min-100);
    assert.equal(fx.snapshot().emitted,2,'no premature burst '+profile);
    host.tick(32110+max+100);
    assert.equal(fx.snapshot().emitted,4,'burst must occur by new max '+profile);
    fx.destroy();
    assert.equal(host.pending(),0,'all RAF released');
    assert.equal(host.root.children.length,9,'original D02 orbs preserved');
    assert.equal(host.root.dataset.noxFxMode,undefined,'FX decorator removed');
  }
  const host=fixture();
  const fx=installNoxCinemaFX({root:host.root,orbs:host.orbs,
    profile:'BALANCED',random:()=>.5,clock:host.clock});
  assert.equal(fx.setProfile('ECO'),true);
  host.tick(32110);
  assert.equal(fx.setProfile('REDUCED'),true);
  host.failClock();
  assert.equal(fx.setProfile('MAX'),false,'bad clock refuses resume');
  assert.equal(fx.snapshot().profile,'REDUCED','failed change is atomic');
  assert.equal(host.pending(),0);
  fx.destroy();
});
