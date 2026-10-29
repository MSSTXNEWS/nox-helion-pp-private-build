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

test('G7-A R30 OS Reduced Motion resume preserves rare D02 burst windows',()=>{
  for(const [profile,min,max] of [
    ['MAX',10000,22000],
    ['BALANCED',18000,35000],
    ['ECO',32000,52000]
  ]){
    const host=fixture();
    const fx=installNoxCinemaFX({
      root:host.root,orbs:host.orbs,profile,random:()=>.5,clock:host.clock
    });
    host.advance(14000);host.tick(14000);
    assert.equal(fx.snapshot().emitted,2,profile+' original baseline');
    host.motion(true);
    assert.equal(fx.snapshot().profile,'REDUCED');
    assert.equal(host.pending(),0,'RAF sleeps during reduced motion');
    host.advance(100000);host.motion(false);
    assert.equal(fx.snapshot().profile,profile);
    host.tick(100000);
    assert.equal(fx.snapshot().emitted,2,profile+' no immediate stale burst');
    host.tick(100000+min-100);
    assert.equal(fx.snapshot().emitted,2,profile+' no premature burst');
    host.tick(100000+max+100);
    assert.equal(fx.snapshot().emitted,4,profile+' resumes by maximum deadline');
    fx.destroy();
    assert.equal(host.pending(),0,'RAF released');
    assert.equal(host.root.dataset.noxFxMode,undefined,'D02 decorator removed');
    assert.equal(host.root.children.length,9,'all original D02 nodes retained');
  }

  const host=fixture();
  const fx=installNoxCinemaFX({
    root:host.root,orbs:host.orbs,profile:'MAX',random:()=>.5,clock:host.clock
  });
  host.motion(true);host.advance(100000);host.failClock();host.motion(false);
  assert.equal(fx.snapshot().profile,'REDUCED','bad resume clock cannot mutate policy');
  assert.equal(host.pending(),0,'bad clock does not restart RAF');
  fx.destroy();
  assert.equal(host.pending(),0);
});
