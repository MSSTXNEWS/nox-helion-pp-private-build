import {test} from "node:test";
import assert from "node:assert/strict";
import {CUES} from "../NOX-WOW51-100/catalog.mjs";
import {SHOTS} from "../NOX-WOW101-150/catalog.mjs";
import {reviewWowScopes,translateNativeEvent,mountUnifiedCinema} from "./gate.mjs";
import {readFileSync} from "node:fs";

const now=Date.now();
const base={schema:"NOX-INSTALLER-EVENT-v3",run_id:"test-1",event_id:"event-1",
  event_sequence:1,task_id:"NIP01-21",package_id:"P04",action_id:"training.step",
  timestamp_utc:new Date(now).toISOString(),event_type:"training.step",
  evidence_verified:true,receipt_sha256:"a".repeat(64)};

test("source-only catalogs cover 51–150 and leave 1–50 separate",()=>{
 const status=reviewWowScopes();
 assert.equal(status.groups.aggregate,150);
 assert.equal(status.groups.cinematicFinale151to200,50);
 assert.equal(status.externalUiPrerequisite,true);
 const actions=Array.from({length:50},(_,i)=>({routeId:"route-"+i}));
 const all=reviewWowScopes({actions});
 assert.equal(all.groups.aggregate,200);
 assert.equal(all.groups.uiFirst50,50);
 assert.equal(CUES.length,50);assert.equal(SHOTS.length,50);
 assert.deepEqual(all.hostDrivenAvailable,[81,85,86,87,89]);
 assert.deepEqual(all.hostDrivenHold,[82,83,84,88,90]);
});
test("exact documented canonical events map only to truthful WOW semantics",()=>{
 assert.equal(translateNativeEvent(base,now)?.cueId,87);
 assert.equal(translateNativeEvent({...base,package_id:"P03",event_type:"task.progress",
  action_id:"model.pull"},now)?.cueId,85);
 assert.equal(translateNativeEvent({...base,event_type:"task.started"},now)?.cueId,81);
 assert.equal(translateNativeEvent({...base,event_type:"model.stopped"},now)?.cueId,89);
 assert.equal(translateNativeEvent({...base,event_type:"task.completed",
   action_id:"rag.ingest"},now)?.cueId,86);
 for(const invalid of [
  {...base,event_type:"voice.listening"},
  {...base,event_type:"system.offline"},
  {...base,event_type:"chat.streaming"},
  {...base,event_type:"training.paused"},
  {...base,evidence_verified:false},
  {...base,receipt_sha256:"bad"},
  {...base,event_sequence:0},
  {...base,event_id:4},
  {...base,run_id:"bad token"},
  {...base,package_id:"UNKNOWN"},
  {...base,action_id:"javascript:alert(1)"},
  {...base,numerator:12,denominator:8},
  {...base,timestamp_utc:new Date(now-50000).toISOString()},
 ]){
   assert.equal(translateNativeEvent(invalid,now),null);
 }
});
class ClassBag {
 constructor(){this.v=new Set()}
 add(x){this.v.add(x)}remove(x){this.v.delete(x)}
}
class MockElement {
 constructor(doc){
  this.nodeType=1;this.ownerDocument=doc;this.dataset={};this.children=[];
  this.classList=new ClassBag();this.textContent="";this.animations=[];
 }
 append(...x){this.children.push(...x)}
 setAttribute(){}
 remove(){this.removed=true}
 closest(){return null}
 animate(frames,options){
  const a={frames,options,cancelled:false,cancel(){this.cancelled=true},pause(){},play(){}};
  this.animations.push(a);return a;
 }
}
function fixture(){
 const listeners=new Map();
 const media={matches:false,addEventListener(){},removeEventListener(){}};
 const doc={hidden:false,listeners,createElement(){return new MockElement(doc)},
  defaultView:{matchMedia:()=>media},
  addEventListener(k,cb){listeners.set(k,cb)},
  removeEventListener(k){listeners.delete(k)}
 };
 const root=new MockElement(doc);root.dataset.noxWowSlot="secondary";
 return {root,doc,media,listeners};
}
test("150 secondary visual scenes are selectable without replacing HOME art",()=>{
 const {root,listeners}=fixture();const ui=mountUnifiedCinema(root);
 for(let id=51;id<=200;id++){
   ui.preview(id);
   assert.equal(ui.current().selected,id);
 }
 assert.equal(ui.current().active,"composition");
 assert.equal(ui.current().visualEvidence,"demo");
 assert.equal(root.dataset.noxWowComposition,"200");
 assert.equal(ui.current().acceptedExe,false);
 assert.equal(root.children.length,4); // both layers and their labels only
 ui.preview(54);assert.equal(ui.current().active,"cue");
 ui.destroy();assert.equal(listeners.size,0);
 assert.equal(root.classList.v.has("nox-unified-wow"),false);
});
test("real events require trusted port and monotonic sequence, never fake speech",()=>{
 const {root}=fixture();let callback,off=0;
 const ui=mountUnifiedCinema(root,{trustedEventPort:{subscribe(fn){callback=fn;return ()=>off++}}});
 assert.equal(typeof callback,"function");
 // Public page methods cannot spoof training status even with a copied valid envelope.
 assert.equal(ui.receiveCanonicalEvent(base),false);
 assert.equal(callback(base),true);
 assert.equal(ui.current().selected,87);
 assert.equal(callback(base),false);
 assert.equal(callback({...base,event_sequence:2,event_id:"event-2"}),true);
 assert.equal(callback({...base,event_sequence:1,event_id:"event-3"}),false);
 assert.equal(callback({...base,event_sequence:3,event_id:"event-4",event_type:"voice.listening"}),false);
 ui.destroy();assert.equal(off,1);assert.equal(callback(base),false);
});
test("host denial does not switch to approved director cue",()=>{
 const {root}=fixture();
 const ui=mountUnifiedCinema(root,{nativeAuthorizeShot:shot=>shot.id===150});
 ui.preview(52);assert.equal(ui.current().active,"cue");
 assert.throws(()=>ui.activateApprovedShot(149),/HOST_APPROVAL_REQUIRED/);
 assert.equal(ui.current().active,"cue");
 assert.equal(ui.activateApprovedShot(150).id,150);
 assert.equal(ui.current().active,"director");
 ui.setMode("ECO");ui.destroy();
});
test("mount failures are reversible; no duplicate roots or D02 entry",()=>{
 const {root}=fixture();
 root.closest=()=>({});
 assert.throws(()=>mountUnifiedCinema(root),/TRUSTED_SLOT_REQUIRED/);
 root.closest=()=>null;
 const ui=mountUnifiedCinema(root);
 assert.throws(()=>mountUnifiedCinema(root),/DUPLICATE_MOUNT/);
 ui.destroy();
 assert.doesNotThrow(()=>mountUnifiedCinema(root).destroy());
 const broken=fixture();
 assert.throws(()=>mountUnifiedCinema(broken.root,{
  trustedEventPort:{subscribe(){return true}}
 }),/NATIVE_EVENT_UNSUBSCRIBE_REQUIRED/);
 assert.doesNotThrow(()=>mountUnifiedCinema(broken.root).destroy());
});
test("CSS has one active scene, no new networking, GPU or native host",()=>{
 const css=readFileSync(new URL("./scene.css",import.meta.url),"utf8");
 const js=readFileSync(new URL("./gate.mjs",import.meta.url),"utf8");
 assert.match(css,/data-unified-wow="cue"/);
 assert.match(css,/data-unified-wow="director"/);
 assert.match(css,/prefers-reduced-motion/);
 assert.equal(js.includes("fetch("),false);
 assert.equal(js.includes("innerHTML"),false);
 assert.equal(js.includes("child_process"),false);
});

test("151-200 use same optics/director, native composition approval only",()=>{
 const {root}=fixture();
 let nativeCalls=0;
 const ui=mountUnifiedCinema(root,{
  nativeAuthorizeComposition:item=>{nativeCalls++;return item.id===200},
  mode:"BALANCED"
 });
 const childCount=root.children.length;
 for(let id=151;id<=200;id++){
   const item=ui.preview(id);
   assert.equal(item.id,id);
   assert.equal(ui.current().visualEvidence,"demo");
   assert.equal(ui.current().active,"composition");
   assert.equal(root.children.length,childCount);
 }
 assert.equal(nativeCalls,0); // Pure source preview does NOT claim native authorization.
 assert.throws(()=>ui.activateApprovedComposition(199),/HOST_COMPOSITION_APPROVAL_REQUIRED/);
 assert.equal(ui.current().selected,200);
 const accepted=ui.activateApprovedComposition(200);
 assert.equal(accepted.id,200);
 assert.equal(ui.current().visualEvidence,"native-composition");
 assert.equal(ui.current().acceptedExe,false);
 ui.setMode("ECO");assert.equal(root.dataset.noxMode,"ECO");
 ui.setMode("REDUCED");assert.equal(root.dataset.noxMode,"REDUCED");
 ui.destroy();assert.equal(root.dataset.noxWowComposition,undefined);
 assert.equal(root.dataset.noxMode,undefined);
});
test("composition action denied without native authorized callback",()=>{
 const {root}=fixture();
 const ui=mountUnifiedCinema(root);
 ui.preview(151);
 assert.throws(()=>ui.activateApprovedComposition(151),/HOST_COMPOSITION_APPROVAL_REQUIRED/);
 assert.equal(ui.current().visualEvidence,"demo");
 ui.destroy();
});
