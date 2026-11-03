import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
const source=readFileSync(new URL('./express-wow-v2.mjs',import.meta.url),'utf8');
function fixture(){
  function node(){const events={},vars=new Map();return {
    vars,style:{setProperty(k,v){vars.set(k,v)}},
    addEventListener(k,fn){(events[k]??=[]).push(fn)},
    removeEventListener(k,fn){events[k]=(events[k]||[]).filter(f=>f!==fn)},
    fire(k,evt={}){(events[k]||[]).forEach(fn=>fn(evt))},
    getBoundingClientRect(){return {left:0,top:0,width:100,height:100}},
    setAttribute(){}
  }}
  const sun=node(),planet=node(),fx=node(),reduce=node();
  reduce.matches=false;
  const stage={dataset:{},querySelectorAll(){return [planet]}};
  const doc={readyState:'complete',body:{dataset:{fx:'BALANCED'}},
    querySelector(q){return q==='.universe'?stage:q==='.sun'?sun:null},
    getElementById(){return fx},dispatchEvent(){}};
  const win=node(),frames=new Map();let counter=0;
  win.innerWidth=1200;
  win.matchMedia=q=>q.includes('reduced-motion')?reduce:{matches:true};
  win.requestAnimationFrame=cb=>{const id=++counter;frames.set(id,cb);return id};
  win.cancelAnimationFrame=id=>frames.delete(id);
  const fired=[...frames.values()];
  win.flush=()=>{const callbacks=[...frames.values()];frames.clear();callbacks.forEach(cb=>cb())};
  runInNewContext(source,{document:doc,window:win,KeyboardEvent:class {}});
  return {sun,fx,reduce,doc,win,pointer(){sun.fire('pointermove',{clientX:95,clientY:50})}};
}
test('ECO before pending frame cannot reapply tilt',()=>{
 const x=fixture();x.pointer();x.doc.body.dataset.fx='ECO';x.win.flush();
 assert.equal(x.sun.vars.get('--sun-y'),'0deg');
});
test('Reduced Motion invalidates queued RAF and resets transform',()=>{
 const x=fixture();x.pointer();x.reduce.matches=true;x.reduce.fire('change');x.win.flush();
 assert.equal(x.sun.vars.get('--sun-y'),'0deg');
});
test('ECO button resets already painted sun parallax',()=>{
 const x=fixture();x.pointer();x.win.flush();
 assert.notEqual(x.sun.vars.get('--sun-y'),'0deg');
 x.doc.body.dataset.fx='ECO';x.fx.fire('click');
 assert.equal(x.sun.vars.get('--sun-y'),'0deg');
});
test('pagehide aborts pending pointer frame and resets tilt',()=>{
 const x=fixture();x.pointer();x.win.fire('pagehide');x.win.flush();
 assert.equal(x.sun.vars.get('--sun-y'),'0deg');
});
