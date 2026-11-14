import test from "node:test";
import assert from "node:assert/strict";
import {SHOTS,validateShots} from "./catalog.mjs";
import {choreography,mountDirector} from "./director.mjs";
test("50 exact IDs 101–150, five groups of ten",()=>{
 assert.equal(validateShots(),true);assert.equal(SHOTS.length,50);assert.equal(new Set(SHOTS.map(x=>x.key)).size,50);
 for(let i=0;i<50;i++)assert.equal(SHOTS[i].id,i+101);
 for(const f of ["SCENE","CAMERA","DEPTH","LIGHT","MOTION"])assert.equal(SHOTS.filter(s=>s.family===f).length,10);
});
for(const s of SHOTS)test("real camera/light/haze choreography for shot "+s.id,()=>{
 const f=choreography(s);assert.equal(f.cam.length,4);assert.equal(f.light.length,3);assert.equal(f.haze.length,3);
 assert.notEqual(f.cam[0].transform,f.cam[1].transform);
 assert.ok(f.duration>0&&f.duration<2500);
});
test("50 spatial signatures are distinct, no cloned trajectories",()=>{
 const sig=SHOTS.map(s=>JSON.stringify(choreography(s).cam));
 assert.equal(new Set(sig).size,50);
});
test("REDUCED has no moving duration",()=>assert.ok(SHOTS.every(s=>choreography(s,"REDUCED").duration===0)));
class Classes{constructor(){this.members=new Set()}add(x){this.members.add(x)}remove(x){this.members.delete(x)}}
class Node{
 constructor(tag,d){this.tag=tag;this.ownerDocument=d;this.nodeType=1;this.dataset={};this.children=[];this.classList=new Classes();this.animations=[];this.textContent="";}
 append(...v){this.children.push(...v)}setAttribute(){}closest(){return null}remove(){this.removed=true}
 animate(frames,opts){const a={frames,opts,cancelled:false,paused:false,cancel(){this.cancelled=true},pause(){this.paused=true},play(){this.paused=false}};this.animations.push(a);return a}
}
function fixture(){
 const d={hidden:false,listeners:{},createElement(tag){return new Node(tag,d)},addEventListener(k,f){this.listeners[k]=f},removeEventListener(k){delete this.listeners[k]},
 defaultView:{matchMedia:()=>({matches:false,addEventListener(){},removeEventListener(){}})}};
 const root=new Node("main",d);root.dataset.noxWowSlot="secondary";return {root,d}
}
test("all 50 previews actually execute three animations, old ones cancelled",()=>{
 const {root}=fixture(),m=mountDirector(root);
 for(const s of SHOTS){m.preview(s.id);assert.equal(m.current().id,s.id);assert.equal(m.current().source,"DEMO");assert.equal(m.current().runningAnimations,3)}
 const arr=root.children[0].children[0].animations;
 assert.equal(arr.length,50);assert.equal(arr.filter(x=>x.cancelled).length,49);
 m.destroy();assert.equal(root.children[0].removed,true);assert.equal(m.current().runningAnimations,0);
});
test("real interaction fails closed until trusted native callback approves",()=>{
 const a=fixture(),m=mountDirector(a.root);assert.throws(()=>m.activate(101),/HOST_APPROVAL_REQUIRED/);m.destroy();
 const b=fixture(),n=mountDirector(b.root,{authorize:s=>s.id===150});
 assert.throws(()=>n.activate(149),/HOST_APPROVAL_REQUIRED/);assert.equal(n.activate(150).id,150);n.destroy();
});
test("HOME protected, no competing slot mounts, cleanup works",()=>{
 const a=fixture();a.root.closest=()=>({});assert.throws(()=>mountDirector(a.root),/D02_HOME_LOCK/);
 const b=fixture(),m=mountDirector(b.root);assert.throws(()=>mountDirector(b.root),/ALREADY_MOUNTED/);m.destroy();
 assert.doesNotThrow(()=>mountDirector(b.root).destroy());
});
test("ECO, hidden page pause and reduced motion",()=>{
 const {root,d}=fixture(),m=mountDirector(root);m.preview(101);
 d.hidden=true;d.listeners.visibilitychange();assert.equal(root.children[0].children[0].animations.at(-1).paused,true);
 m.setMode("ECO");assert.equal(m.current().mode,"ECO");
 m.setReducedMotion(true);assert.equal(m.current().mode,"REDUCED");assert.equal(m.current().runningAnimations,0);
 m.preview(102);assert.equal(m.current().runningAnimations,0);m.destroy();assert.deepEqual(Object.keys(d.listeners),[]);
});
