import test from 'node:test';
import assert from 'node:assert/strict';
import {installNoxCinemaFX} from './nox-cinema.mjs';

// G7-A R30: original nine D02 orbs, OS Reduced Motion and RAF in a DOM fixture.
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
  let now=100,cb=null,seq=0;
  const raf=new Map();
  const media={matches:true,
    addEventListener(_k,fn){cb=fn;},
    removeEventListener(){cb=null;}
  };
  const win={
    performance:{now:()=>now},
    matchMedia(){return media;},
    requestAnimationFrame(fn){raf.set(++seq,fn);return seq;},
    cancelAnimationFrame(id){raf.delete(id);}
  };
  const doc={defaultView:win,hidden:false,
    createElement:()=>new Element(doc),
    createElementNS:()=>new Element(doc),
    addEventListener(){},removeEventListener(){}
  };
  const root=new Element(doc),orbs=[];
  for(let i=0;i<9;i++){
    const element=new Element(doc);root.appendChild(element);
    orbs.push({id:i?'CORE_'+i:'HELION',element});
  }
  return {root,orbs,clock:()=>now,
    pending:()=>raf.size,
    advance(value){now=value;},
    media(matches){
      if(!cb)throw Error('G7A_MISSING_MEDIA_LISTENER');
      media.matches=matches;cb({matches});
    },
    tick(value){
      now=value;
      const first=raf.entries().next().value;
      if(!first)throw Error('G7A_MISSING_RAF');
      raf.delete(first[0]);first[1](value);
    }
  };
}

// One G7-A addressable regression covering two valid user-profile transitions.
test('G7-A R30 preserves selected profile while OS Reduced Motion suspends D02 FX',()=>{
  for(const [initial,target,min,max] of [
    ['BALANCED','MAX',10000,22000],
    ['REDUCED','BALANCED',18000,35000]
  ]){
    const f=fixture();
    const fx=installNoxCinemaFX({
      root:f.root,orbs:f.orbs,clock:f.clock,profile:'BALANCED',random:()=>.5
    });
    if(initial==='REDUCED')assert.equal(fx.setProfile('REDUCED'),true);
    assert.equal(fx.snapshot().profile,'REDUCED');
    assert.equal(fx.setProfile(target),true,'select '+target+' while OS Reduced');
    assert.equal(fx.snapshot().profile,'REDUCED','OS veto stays active');
    assert.equal(f.pending(),0,'zero RAF while reduced');
    assert.equal(fx.snapshot().particles,0,'zero particle budget while reduced');

    f.advance(200);f.media(false);
    assert.equal(fx.snapshot().profile,target,'remember target on resume');
    assert.equal(f.pending(),1,'one resumed RAF');
    f.tick(201);
    f.tick(200+min-1);
    assert.equal(fx.snapshot().emitted,0,'no premature burst');
    f.tick(200+max+50);
    assert.equal(fx.snapshot().emitted,2,'HELION burst before target max bound');
    fx.destroy();
    assert.equal(f.pending(),0,'RAF cleaned');
    assert.equal(f.root.children.length,9,'nine original D02 orbs untouched');
    assert.equal(f.root.dataset.noxFxMode,undefined,'decorator removed');
  }
});
