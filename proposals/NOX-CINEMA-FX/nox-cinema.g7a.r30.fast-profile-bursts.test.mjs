import test from 'node:test';
import assert from 'node:assert/strict';
import {installNoxCinemaFX} from './nox-cinema.mjs';

// G7-A owns this isolated regression. Do not alter original controls or assets.
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
  let now=100,seq=0;const pending=new Map();
  const win={
    performance:{now:()=>now},
    requestAnimationFrame(fn){pending.set(++seq,fn);return seq;},
    cancelAnimationFrame(id){pending.delete(id);},
    matchMedia(){return {matches:false,addEventListener(){},removeEventListener(){}};}
  };
  const doc={
    defaultView:win,hidden:false,
    createElement:tag=>new Element(doc,tag),
    createElementNS:(_,tag)=>new Element(doc,tag),
    addEventListener(){},removeEventListener(){}
  };
  const root=doc.createElement('section'),orbs=[];
  for(let index=0;index<9;index++){
    const element=doc.createElement('button');
    root.appendChild(element);
    orbs.push({id:index?'CORE_'+index:'HELION',element});
  }
  return {
    root,orbs,clock:()=>now,advance(value){now=value;},
    tick(value){
      const first=pending.entries().next().value;
      if(!first)throw Error('EXPECTED_PENDING_RAF');
      pending.delete(first[0]);first[1](value);
    },
    pending:()=>pending.size
  };
}
test('G7-A R30: ECO to MAX/BALANCED cannot inherit ECO burst delay',()=>{
  for(const next of ['MAX','BALANCED']){
    const host=fixture();
    const fx=installNoxCinemaFX({
      root:host.root,orbs:host.orbs,profile:'ECO',
      random:()=>0.5,clock:host.clock
    });
    host.advance(14000);host.tick(14000);
    assert.equal(fx.snapshot().emitted,2,'ECO baseline HELION burst');
    assert.equal(fx.setProfile(next),true,next+' accepted');
    const bounds=next==='MAX'?{min:10000,max:22000}:{min:18000,max:35000};
    host.advance(14000+bounds.min-1000);host.tick(14000+bounds.min-1000);
    assert.equal(fx.snapshot().emitted,2,next+' avoids premature burst');
    host.advance(14000+bounds.max+100);host.tick(14000+bounds.max+100);
    assert.equal(fx.snapshot().emitted,4,next+' emits within new profile maximum');
    assert.equal(fx.snapshot().profile,next);
    fx.destroy();
    assert.equal(host.pending(),0,'RAF cleanup');
    assert.equal(host.root.dataset.noxFxMode,undefined,'original D02 restored');
  }
});
