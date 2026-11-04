import test from 'node:test';
import assert from 'node:assert/strict';
import {mountCanonicalMenuCinematics} from './p01-cinematic-menu.mjs';

const EIGHT=['work','intelligence','knowledge','creative','people','development','world','system'];
const TEN=['work','intelligence','knowledge','learning','entertainment','people','creative','business','world','pc'];
function fixture(){
  let failingIndex=1;
  const view={PointerEvent:function(){},addEventListener(){},removeEventListener(){},
    matchMedia:()=>({matches:false,addEventListener(){},removeEventListener(){}})};
  const doc={defaultView:view,hidden:false,addEventListener(){},removeEventListener(){}};
  const make=(index)=>{
    const props=new Map(), classes=new Set();
    return {nodeType:1,ownerDocument:doc,dataset:{},
      style:{getPropertyValue:key=>props.get(key)||'',setProperty:(key,value)=>props.set(key,value),
        removeProperty:key=>props.delete(key)},
      classList:{add:key=>classes.add(key),remove:key=>classes.delete(key),contains:key=>classes.has(key)},
      addEventListener(type){if(index===failingIndex && type==='pointermove')
        throw Error('INJECTED_POINTER_LISTENER_FAILURE');},
      removeEventListener(){},closest(){return null;},querySelector(){return null;},
      setAttribute(){},append(){},remove(){}};
  };
  doc.createElement=()=>make(-1);
  const root=make(-1);
  root.contains=()=>true;
  const tiles=EIGHT.map((id,i)=>({id,routeId:'tile.'+id,element:make(i)}));
  const worlds=TEN.map((id,i)=>({id,routeId:'world.'+id,element:make(100+i)}));
  tiles[0].element.style.setProperty('--nox-r11-index','ORIGINAL');
  return {root,tiles,worlds,doc,view,setFail:index=>failingIndex=index,
    mount(){return mountCanonicalMenuCinematics({root,tiles,worlds,documentRef:doc,windowRef:view});}};
}
test('failed original cinematic mount rolls back CSS, classes and owner dataset',()=>{
  const f=fixture();
  assert.throws(()=>f.mount(),/INJECTED_POINTER_LISTENER_FAILURE/);
  assert.equal(f.tiles[0].element.style.getPropertyValue('--nox-r11-index'),'ORIGINAL');
  assert.equal(f.tiles[1].element.style.getPropertyValue('--nox-r11-index'),'');
  assert.equal(f.tiles[0].element.classList.contains('nox-r11-cinematic-tile'),false);
  assert.equal(f.root.classList.contains('nox-r11-cinematic-root'),false);
  assert.deepEqual(f.root.dataset,{});
  f.setFail(-200);
  const mounted=f.mount();
  assert.equal(mounted.status().originalMenuTiles,8);
  assert.equal(mounted.status().originalSubworlds,10);
  mounted.destroy();
  assert.equal(f.tiles[0].element.style.getPropertyValue('--nox-r11-index'),'ORIGINAL');
  assert.equal(f.root.classList.contains('nox-r11-cinematic-root'),false);
});
test('normal cinematic destruction returns the original visuals, never overwrites media',()=>{
  const f=fixture();f.setFail(-200);
  f.root.dataset.noxR11CinematicMode='OWNER_PREEXISTING';
  const mounted=f.mount();
  assert.equal(mounted.setMode('MAX'),true);
  mounted.destroy();
  assert.equal(f.root.dataset.noxR11CinematicMode,'OWNER_PREEXISTING');
  assert.equal(f.tiles.length,8);assert.equal(f.worlds.length,10);
  assert.equal(f.tiles[0].element.style.getPropertyValue('--nox-r11-index'),'ORIGINAL');
});
