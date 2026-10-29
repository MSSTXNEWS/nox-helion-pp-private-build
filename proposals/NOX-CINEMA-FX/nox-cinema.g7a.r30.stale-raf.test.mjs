import test from 'node:test';
import assert from 'node:assert/strict';
import {installNoxCinemaFX} from './nox-cinema.mjs';

// G7-A R30 R10: cancelled browser callbacks can still arrive late in a hostile/queued renderer.
class ClassList {
  constructor(){this.names=new Set();}
  add(n){this.names.add(n);}
  remove(n){this.names.delete(n);}
  contains(n){return this.names.has(n);}
}
class Element {
  constructor(doc){this.nodeType=1;this.ownerDocument=doc;this.children=[];this.parent=null;this.className='';this.classList=new ClassList();this.dataset={};}
  appendChild(child){child.parent=this;this.children.push(child);return child;}
  contains(child){return child===this||this.children.some(e=>e.contains(child));}
  querySelector(selector){
    const cls=selector.slice(1);
    const scan=e=>{
      if(e.classList.contains(cls)||e.className.split(' ').includes(cls))return e;
      for(const child of e.children){const hit=scan(child);if(hit)return hit;}
      return null;
    };
    for(const child of this.children){const hit=scan(child);if(hit)return hit;}
    return null;
  }
  setAttribute(name,value){if(name==='class')this.className=String(value);}
  remove(){if(this.parent)this.parent.children=this.parent.children.filter(x=>x!==this);this.parent=null;}
}
function fixture(){
  let nextId=0;const pending=new Map(),cancelled=[];
  const media={matches:false,addEventListener(){},removeEventListener(){}};
  const win={
    performance:{now:()=>100},
    requestAnimationFrame(cb){const id=nextId++;pending.set(id,cb);return id;},
    cancelAnimationFrame(id){cancelled.push(id);pending.delete(id);},
    matchMedia(){return media;}
  };
  const doc={defaultView:win,hidden:false,
    createElement:()=>new Element(doc),createElementNS:()=>new Element(doc),
    addEventListener(){},removeEventListener(){}
  };
  const root=new Element(doc);
  const orbs=Array.from({length:9},(_,i)=>{
    const element=new Element(doc);root.appendChild(element);
    return {id:i?'CORE_'+i:'HELION',element};
  });
  return {root,orbs,pending,cancelled};
}
test('G7-A R30 R10: a retired RAF callback must not revive or duplicate the resumed D02 loop',()=>{
  const f=fixture();
  const fx=installNoxCinemaFX({root:f.root,orbs:f.orbs,clock:()=>100,random:()=>.5});
  assert.equal([...f.pending.keys()].join(','),'0','zero is a live initial RAF handle');
  const cancelledCallback=f.pending.get(0);
  assert.equal(fx.setVisible(false),true);
  assert.equal(f.cancelled.includes(0),true,'first frame was cancelled');
  assert.equal(fx.setVisible(true),true);
  assert.equal([...f.pending.keys()].join(','),'1','resume schedules one live callback');
  cancelledCallback(101); // deliberately deliver a cancelled callback late
  assert.equal([...f.pending.keys()].join(','),'1','late cancelled callback may not queue a second frame');
  assert.equal(fx.snapshot().frames,0,'retired callback must not draw or count a frame');
  const resumedCallback=f.pending.get(1);
  f.pending.delete(1);resumedCallback(120);
  assert.equal([...f.pending.keys()].join(','),'2','current callback continues one RAF chain');
  fx.destroy();
  assert.equal(f.pending.size,0,'destroy cancels the remaining callback');
  assert.equal(f.root.children.length,9,'all original D02 orbs remain intact');
  assert.equal(f.root.dataset.noxFxMode,undefined,'decorative FX cleaned up');
});
