import test from 'node:test';
import assert from 'node:assert/strict';
import {mountCanonicalMenuCinematics} from './p01-cinematic-menu.mjs';

const EIGHT=['work','intelligence','knowledge','creative','people','development','world','system'];
const TEN=['work','intelligence','knowledge','learning','entertainment','people','creative','business','world','pc'];
function emitter(target={}) {
  const handlers=new Map();
  target.addEventListener=(name,fn)=>{const a=handlers.get(name)||new Set();a.add(fn);handlers.set(name,a);};
  target.removeEventListener=(name,fn)=>handlers.get(name)?.delete(fn);
  target.emit=(name,event={})=>{for(const fn of [...(handlers.get(name)||[])])fn(event);};
  return target;
}
function fixture() {
  const motion=emitter({matches:false});
  const view=emitter({PointerEvent:function(){},matchMedia:()=>motion});
  const doc=emitter({hidden:false,defaultView:view});
  function node() {
    const props=new Map(),classes=new Set();
    const el=emitter({nodeType:1,ownerDocument:doc,dataset:{},
      style:{getPropertyValue:k=>props.get(k)||'',setProperty:(k,v)=>props.set(k,v),removeProperty:k=>props.delete(k)},
      classList:{add:k=>classes.add(k),remove:k=>classes.delete(k),contains:k=>classes.has(k)},
      closest:()=>null,querySelector:()=>null,append(){},remove(){},setAttribute(){},
      getBoundingClientRect:()=>({left:0,top:0,width:100,height:100})});
    return el;
  }
  doc.createElement=()=>node();
  const root=node();root.contains=()=>true;
  const tiles=EIGHT.map(id=>({id,routeId:'tile.'+id,element:node()}));
  const worlds=TEN.map(id=>({id,routeId:'world.'+id,element:node()}));
  tiles[0].element.style.setProperty('--nox-r11-px','ORIGINAL_X');
  tiles[0].element.style.setProperty('--nox-r11-py','ORIGINAL_Y');
  tiles[0].element.classList.add('nox-r11-cinematic-tile');
  root.classList.add('nox-r11-cinematic-root');
  worlds[0].element.classList.add('nox-r11-cinematic-subworld');
  const mount=()=>mountCanonicalMenuCinematics({root,tiles,worlds,mode:'MAX',documentRef:doc,windowRef:view});
  return {doc,motion,root,tiles,worlds,mount};
}
function baseline(el){
  assert.equal(el.style.getPropertyValue('--nox-r11-px'),'ORIGINAL_X');
  assert.equal(el.style.getPropertyValue('--nox-r11-py'),'ORIGINAL_Y');
}
const move={clientX:80,clientY:20};

test('pointerleave restores original D02 offsets, not blank CSS',()=>{
  const f=fixture(),scene=f.mount(),tile=f.tiles[0].element;
  tile.emit('pointermove',move);
  assert.notEqual(tile.style.getPropertyValue('--nox-r11-px'),'ORIGINAL_X');
  tile.emit('pointerleave');
  baseline(tile);scene.destroy();baseline(tile);
});

test('ECO, OS reduced motion and background visibility clear stale MAX pointer transforms',()=>{
  const f=fixture(),scene=f.mount(),tile=f.tiles[0].element;
  tile.emit('pointermove',move);
  assert.equal(scene.setMode('ECO'),true);
  baseline(tile);
  scene.setMode('MAX');tile.emit('pointermove',move);
  f.motion.matches=true;f.motion.emit('change');
  assert.equal(scene.status().effectiveMode,'REDUCED');baseline(tile);
  f.motion.matches=false;f.motion.emit('change');tile.emit('pointermove',move);
  f.doc.hidden=true;f.doc.emit('visibilitychange');baseline(tile);
  scene.destroy();baseline(tile);
});

test('normal destruction retains preexisting original classes on eight tiles and ten worlds',()=>{
  const f=fixture(),scene=f.mount();scene.destroy();
  assert.equal(f.root.classList.contains('nox-r11-cinematic-root'),true);
  assert.equal(f.tiles[0].element.classList.contains('nox-r11-cinematic-tile'),true);
  assert.equal(f.worlds[0].element.classList.contains('nox-r11-cinematic-subworld'),true);
  assert.equal(f.tiles[1].element.classList.contains('nox-r11-cinematic-tile'),false);
  baseline(f.tiles[0].element);
});

test('failed mount also retains preexisting classes and original owner offsets',()=>{
  const f=fixture(),el=f.tiles[1].element;
  const add=el.addEventListener;el.addEventListener=(name,fn)=>{
    if(name==='pointermove')throw Error('SIMULATED_NATIVE_MOUNT_FAILURE');add(name,fn);
  };
  assert.throws(()=>f.mount(),/SIMULATED_NATIVE_MOUNT_FAILURE/);
  assert.equal(f.root.classList.contains('nox-r11-cinematic-root'),true);
  assert.equal(f.tiles[0].element.classList.contains('nox-r11-cinematic-tile'),true);
  baseline(f.tiles[0].element);
});

test('EXPRESS mounts the eight cinematic tiles without optional ten worlds',()=>{
  const f=fixture();f.worlds.length=0;
  const scene=f.mount();
  assert.equal(scene.status().originalMenuTiles,8);
  assert.equal(scene.status().originalSubworlds,0);
  scene.destroy();
});
