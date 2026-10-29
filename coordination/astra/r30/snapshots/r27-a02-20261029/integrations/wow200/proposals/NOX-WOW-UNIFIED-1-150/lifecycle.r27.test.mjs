import test from 'node:test';
import assert from 'node:assert/strict';
import {createCinematicCues} from '../NOX-WOW51-100/wow51-100.mjs';
import {mountDirector} from '../NOX-WOW101-150/director.mjs';
function fixture(){
 const motion=[],visibility=[];let removed=0;
 const media={matches:false,addEventListener(_,f){motion.push(f)},removeEventListener(){removed++}};
 const doc={hidden:false,defaultView:{matchMedia:()=>media},addEventListener(_,f){visibility.push(f)},removeEventListener(){removed++},createElement(){return el()}};
 function el(){const classes=new Set();return {nodeType:1,ownerDocument:doc,dataset:{},children:[],classList:{add:v=>classes.add(v),remove:v=>classes.delete(v),contains:v=>classes.has(v)},append(...x){this.children.push(...x)},setAttribute(){},remove(){this.removed=true},closest(){return null},animate(){return {cancel(){},play(){},pause(){}}}}}
 const root=el();root.dataset.noxWowSlot='secondary';return {root,doc,media,motion,visibility,removed:()=>removed};
}
test('R27 cue subscription failures rollback DOM/listeners and revoke callbacks',()=>{
 for(const broken of ['return','throw']){
  const x=fixture();let callback;
  assert.throws(()=>createCinematicCues(x.root,{eventPort:{subscribe(fn){callback=fn;if(broken==='throw')throw Error('subscribe failed');return false}}}),/SUBSCRIBE|subscribe failed/);
  assert.equal(callback({}),false);assert.equal(x.removed(),2);
  assert.equal(x.root.children.every(c=>c.removed),true);assert.equal(x.root.classList.contains('nox-w51-slot'),false);
  assert.doesNotThrow(()=>createCinematicCues(x.root).destroy());
 }
});
test('R27 cue unsubscribe failure still frees both listeners and remount identity',()=>{
 const x=fixture();const ui=createCinematicCues(x.root,{eventPort:{subscribe(){return ()=>{throw Error('unsubscribe failed')}}}});
 assert.throws(()=>ui.destroy(),/unsubscribe failed/);assert.equal(x.removed(),2);
 assert.equal(x.root.children.every(c=>c.removed),true);assert.doesNotThrow(()=>createCinematicCues(x.root).destroy());
});
test('R27 queued media/visibility callbacks are inert after both engine disposals',()=>{
 for(const mount of [createCinematicCues,mountDirector]){
  const x=fixture();const ui=mount(x.root);const stage=x.root.children[0];ui.destroy();
  const previous={...stage.dataset};x.media.matches=true;x.doc.hidden=true;
  x.motion.forEach(f=>f());x.visibility.forEach(f=>f());assert.deepEqual(stage.dataset,previous);
 }
});
