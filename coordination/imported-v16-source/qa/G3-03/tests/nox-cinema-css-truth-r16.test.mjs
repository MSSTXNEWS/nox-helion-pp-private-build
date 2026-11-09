/* NOX HELION V16 / W2·03 / R16 · owner code read-only, actual-module component QA.
 * Load proposals/NOX-CINEMA-FX/nox-cinema.mjs from this checkout. Test the real
 * exported installer against isolated DOM/OS collaborators, not a reimplementation.
 * A failure here is SOURCE RED, never proof of failure of a Windows EXE.
 * Owner file's verified 2026-10-28 blob before this QA cycle:
 * a0bc34add0990b3f70bdbfd94fe52615193a4c08
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { installNoxCinemaFX } from '../../../proposals/NOX-CINEMA-FX/nox-cinema.mjs';

function fixture(initialReduced=false, initialProfile='BALANCED') {
  let reduced=initialReduced;
  const listeners=new Set();
  const classes=(...initial)=>{
    const values=new Set(initial);
    return {contains:x=>values.has(x),add:x=>values.add(x),remove:x=>values.delete(x)};
  };
  const doc={hidden:false,createElement(tag){return new Element(tag);},
    createElementNS(_ns,tag){return new Element(tag);},
    addEventListener(){},removeEventListener(){}};
  const media={get matches(){return reduced;},
    addEventListener(type,listener){if(type==='change')listeners.add(listener);},
    removeEventListener(type,listener){if(type==='change')listeners.delete(listener);}};
  let rafIndex=0;
  doc.defaultView={matchMedia:()=>media,requestAnimationFrame:()=>++rafIndex,
    cancelAnimationFrame(){},performance:{now:()=>100}};
  function Element(tag){this.nodeType=1;this.tagName=tag;this.ownerDocument=doc;
    this.classList=classes();this.dataset={};this.className='';this.children=[];
    this.parentNode=null;this.attributes={};}
  Element.prototype.appendChild=function(node){node.parentNode=this;this.children.push(node);return node;};
  Element.prototype.remove=function(){if(this.parentNode){this.parentNode.children=this.parentNode.children.filter(x=>x!==this);this.parentNode=null;}};
  Element.prototype.contains=function(other){for(let p=other;p;p=p.parentNode)if(p===this)return true;return false;};
  Element.prototype.querySelector=function(selector){
    if(selector!=='.nox-cinema-orb__layers')return null;
    const queue=[...this.children];
    while(queue.length){const item=queue.shift();
      if(item.className?.split(' ').includes('nox-cinema-orb__layers'))return item;
      queue.push(...item.children);}
    return null;
  };
  Element.prototype.setAttribute=function(k,value){this.attributes[k]=String(value);};
  const root=new Element('main');
  const orbs=Array.from({length:9},(_,i)=>{
    const element=new Element('div');root.appendChild(element);
    return {id:i===0?'HELION':'CORE'+i,element};
  });
  const button=new Element('button');root.appendChild(button);
  const panel=new Element('section');root.appendChild(panel);
  const fx=installNoxCinemaFX({root,orbs,controls:[button],panels:[panel],
    profile:initialProfile,clock:()=>100,random:()=>.5});
  return {root,orbs,button,panel,fx,
    listenerCount:()=>listeners.size,
    changeReduced(next){reduced=next;for(const listener of [...listeners])listener({matches:next});}};
}

function withScene(fn,initialReduced=false,initialProfile='BALANCED'){
  const s=fixture(initialReduced,initialProfile);
  try{fn(s);}finally{s.fx.destroy();}
}

test('R16-01 normal BALANCED CSS and FX snapshot agree',()=>withScene(s=>{
  assert.equal(s.root.dataset.noxFxMode,'balanced');
  assert.equal(s.fx.snapshot().profile,'BALANCED');
}));

test('R16-02 initial OS reduction makes FX CSS mode reduced',()=>withScene(s=>{
  assert.equal(s.fx.snapshot().profile,'REDUCED');
  assert.equal(s.root.dataset.noxFxMode,'reduced');
},true));

test('R16-03 live OS reduction immediately updates FX CSS mode',()=>withScene(s=>{
  s.changeReduced(true);
  assert.equal(s.fx.snapshot().profile,'REDUCED');
  assert.equal(s.root.dataset.noxFxMode,'reduced');
}));

test('R16-04 OS motion restoration retains original ECO CSS mode',()=>withScene(s=>{
  s.changeReduced(true);s.changeReduced(false);
  assert.equal(s.fx.snapshot().profile,'ECO');
  assert.equal(s.root.dataset.noxFxMode,'eco');
},false,'ECO'));

test('R16-05 manual MAX cannot expose CSS MAX while OS reduction is active',()=>withScene(s=>{
  assert.equal(s.fx.setProfile('MAX'),true);
  assert.equal(s.fx.snapshot().profile,'REDUCED');
  assert.equal(s.root.dataset.noxFxMode,'reduced');
},true,'ECO'));

test('R16-06 explicit REDUCED stays reduced after OS preference clears',()=>withScene(s=>{
  assert.equal(s.fx.setProfile('REDUCED'),true);
  s.changeReduced(true);s.changeReduced(false);
  assert.equal(s.fx.snapshot().profile,'REDUCED');
  assert.equal(s.root.dataset.noxFxMode,'reduced');
}));

test('R16-07 invalid mode is rejected without changing CSS or snapshot',()=>withScene(s=>{
  assert.equal(s.fx.setProfile({mode:'MAX'}),false);
  assert.equal(s.root.dataset.noxFxMode,'balanced');
  assert.equal(s.fx.snapshot().profile,'BALANCED');
}));

test('R16-08 original nine CoreID element references remain intact',()=>withScene(s=>{
  assert.equal(s.orbs.length,9);
  assert.equal(s.orbs[0].id,'HELION');
  assert.equal(new Set(s.orbs.map(x=>x.element)).size,9);
}));

test('R16-09 decorative FX never replaces original button',()=>withScene(s=>{
  assert.equal(s.button.classList.contains('nox-cinema-control'),true);
  assert.equal(s.root.contains(s.button),true);
}));

test('R16-10 destroy removes owned DOM and OS change subscription',()=>{
  const s=fixture();s.fx.destroy();
  assert.equal(s.listenerCount(),0);
  assert.equal(s.root.dataset.noxFxMode,undefined);
  assert.equal(s.root.classList.contains('nox-cinema-scope'),false);
});
