import test from 'node:test';
import assert from 'node:assert/strict';
import {installNoxCinemaFX} from './nox-cinema.mjs';

// One R30 G7-A R08 focused regression: stale deadlines after three actual
// D02 suspension paths must be rebased without changing original artwork.
class Classes {
  constructor(){this.names=new Set();}
  add(x){this.names.add(x);}
  remove(x){this.names.delete(x);}
  contains(x){return this.names.has(x);}
}
class Element {
  constructor(doc){
    this.nodeType=1;this.ownerDocument=doc;this.children=[];this.parent=null;
    this.className='';this.classList=new Classes();this.dataset={};
  }
  appendChild(e){e.parent=this;this.children.push(e);return e;}
  contains(e){return e===this||this.children.some(x=>x.contains(e));}
  querySelector(selector){
    const wanted=selector.slice(1);
    const find=e=>{
      if(e.classList.contains(wanted)||e.className.split(' ').includes(wanted))return e;
      for(const child of e.children){const hit=find(child);if(hit)return hit;}
      return null;
    };
    for(const child of this.children){const hit=find(child);if(hit)return hit;}
    return null;
  }
  setAttribute(k,v){if(k==='class')this.className=String(v);}
  remove(){
    if(this.parent)this.parent.children=this.parent.children.filter(x=>x!==this);
    this.parent=null;
  }
}
function fixture(){
  let now=100,seq=0,onIntersection=null;
  const raf=new Map(), listeners=new Map();
  const media={matches:false,addEventListener(){},removeEventListener(){}};
  const win={
    performance:{now:()=>now},matchMedia(){return media;},
    requestAnimationFrame(fn){raf.set(++seq,fn);return seq;},
    cancelAnimationFrame(id){raf.delete(id);},
    IntersectionObserver:class{
      constructor(cb){onIntersection=cb;}
      observe(){}
      disconnect(){onIntersection=null;}
    }
  };
  const doc={defaultView:win,hidden:false,
    createElement:()=>new Element(doc),
    createElementNS:()=>new Element(doc),
    addEventListener(name,cb){listeners.set(name,cb);},
    removeEventListener(name){listeners.delete(name);}
  };
  const root=new Element(doc),orbs=[];
  for(let i=0;i<9;i++){
    const element=new Element(doc);root.appendChild(element);
    orbs.push({id:i?'CORE_'+i:'HELION',element});
  }
  return {root,orbs,clock:()=>now,pending:()=>raf.size,
    advance(value){now=value;},
    hidden(value){
      doc.hidden=value;
      const cb=listeners.get('visibilitychange');
      if(!cb)throw Error('G7A_MISSING_VISIBILITY_LISTENER');
      cb();
    },
    intersection(value){
      if(!onIntersection)throw Error('G7A_MISSING_INTERSECTION_OBSERVER');
      onIntersection([{isIntersecting:value}]);
    },
    tick(value){
      now=value;
      const entry=raf.entries().next().value;
      if(!entry)throw Error('G7A_MISSING_RAF');
      raf.delete(entry[0]);entry[1](value);
    }
  };
}
test('G7-A R30 R08 rebases real D02 resumes from host, tab and intersection pauses',()=>{
  for(const pauseKind of ['host','tab','intersection']){
    const f=fixture();
    const fx=installNoxCinemaFX({
      root:f.root,orbs:f.orbs,clock:f.clock,profile:'BALANCED',random:()=>.5
    });
    assert.equal(f.pending(),1,pauseKind+' initial RAF');
    f.tick(200);
    if(pauseKind==='host')assert.equal(fx.setVisible(false),true);
    if(pauseKind==='tab')f.hidden(true);
    if(pauseKind==='intersection')f.intersection(false);
    assert.equal(f.pending(),0,pauseKind+' suspended RAF');
    f.advance(100000);
    if(pauseKind==='host')assert.equal(fx.setVisible(true),true);
    if(pauseKind==='tab')f.hidden(false);
    if(pauseKind==='intersection')f.intersection(true);
    assert.equal(f.pending(),1,pauseKind+' resume RAF');
    f.tick(100001);
    assert.equal(fx.snapshot().emitted,0,pauseKind+' no immediate stale burst');
    f.tick(117999);
    assert.equal(fx.snapshot().emitted,0,pauseKind+' no early burst');
    f.tick(135100);
    assert.equal(fx.snapshot().emitted,2,pauseKind+' HELION resumes within profile upper bound');
    fx.destroy();
    assert.equal(f.pending(),0,pauseKind+' cleanup RAF');
    assert.equal(f.root.children.length,9,pauseKind+' original D02 orbs');
    assert.equal(f.root.dataset.noxFxMode,undefined,pauseKind+' decoration cleanup');
  }
});