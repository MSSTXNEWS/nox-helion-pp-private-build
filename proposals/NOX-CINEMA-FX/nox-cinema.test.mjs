import test from "node:test";
import assert from "node:assert/strict";
import {clamp,validateScene,profileFor,gravitationalSample,
        installNoxCinemaFX,PROFILES} from "./nox-cinema.mjs";

class FakeClassList {
  constructor(){this.values=new Set();}
  add(x){this.values.add(x);}
  remove(x){this.values.delete(x);}
  contains(x){return this.values.has(x);}
}
class FakeElement {
  constructor(doc,tag){
    this.nodeType=1;this.ownerDocument=doc;this.tag=tag;this.children=[];
    this.parentNode=null;this.classList=new FakeClassList();
    this.dataset={};this.attributes=new Map();this.className="";
  }
  appendChild(child){this.children.push(child);child.parentNode=this;return child;}
  setAttribute(k,v){this.attributes.set(k,String(v));if(k==="class")this.className=String(v);}
  getAttribute(k){return this.attributes.get(k);}
  remove(){
    if(this.parentNode){
      this.parentNode.children=this.parentNode.children.filter(c=>c!==this);
      this.parentNode=null;
    }
  }
  contains(needle){
    return this===needle||this.children.some(x=>x.contains(needle));
  }
  querySelector(selector){
    const cls=selector.startsWith(".")?selector.slice(1):null;
    const walk=e=>{
      if((cls && (e.className||"").split(" ").includes(cls))||e.classList.contains(cls))return e;
      for(const x of e.children){const q=walk(x);if(q)return q;}
      return null;
    };
    return this.children.map(walk).find(Boolean)||null;
  }
}
function fakeScene(){
  const handlers=new Map();
  const frames=new Map();
  let nextFrame=0,now=0,hidden=false;
  const mediaHandlers=[],observers=[];
  const media={matches:false,addEventListener(n,fn){mediaHandlers.push(fn);},
    removeEventListener(n,fn){let i=mediaHandlers.indexOf(fn);if(i>=0)mediaHandlers.splice(i,1);}};
  const win={performance:{now:()=>now},
    requestAnimationFrame(fn){frames.set(++nextFrame,fn);return nextFrame;},
    cancelAnimationFrame(id){frames.delete(id);},
    matchMedia(){return media;}
  };
  win.IntersectionObserver=class {constructor(cb){this.cb=cb;observers.push(this);} observe(){} disconnect(){}};
  const doc={defaultView:win,hidden,
    createElement(tag){return new FakeElement(doc,tag);},
    createElementNS(ns,tag){return new FakeElement(doc,tag);},
    addEventListener(name,fn){handlers.set(name,fn);},
    removeEventListener(name,fn){if(handlers.get(name)===fn)handlers.delete(name);}};
  const root=doc.createElement("div");
  const orbs=Array.from({length:9},(_,i)=>{
    const element=doc.createElement("button");element.dataset.original="preserve";
    root.appendChild(element);
    return {id:i===0?"HELION":"CORE_"+i,element};
  });
  const ctrl=doc.createElement("button");
  const panel=doc.createElement("div");
  root.appendChild(ctrl);root.appendChild(panel);
  return {doc,win,root,orbs,ctrl,panel,media,
    tick(t){
      now=t;
      const f=[...frames.values()];frames.clear();for(const fn of f)fn(now);
    },
    visibility(visible){
      doc.hidden=!visible;
      handlers.get("visibilitychange")?.();
    },
    reduced(value){media.matches=value;for(const fn of [...mediaHandlers])fn({matches:value});},
    intersect(value){for(const ob of observers)ob.cb([{isIntersecting:value}]);},
    get pending(){return frames.size;}};
}

test("require only canonical HELION + eight unique CoreIDs",()=>{
  const o=fakeScene();
  assert.equal(validateScene(o.orbs),true);
  assert.throws(()=>validateScene(o.orbs.slice(0,8)),/HELION_PLUS_EIGHT/);
  assert.throws(()=>validateScene(o.orbs.map((x,i)=>i===8?{...x,id:"CORE_1"}:x)),/CANONICAL_CORE_IDS/);
});
test("gravity ejecta emerges, accelerates outward then returns to same surface origin",()=>{
  const p={started:100,duration:3600,surfaceRadius:89,reach:32,
    angle:1.234,swirl:5,brightness:.85,rotation:12};
  const start=gravitationalSample(p,100);
  const apex=gravitationalSample(p,1900);
  const end=gravitationalSample(p,3700);
  assert.equal(start.done,false);assert.equal(end.done,true);
  assert.equal(start.opacity,0);assert.equal(end.opacity,0);
  assert.ok(apex.radius>start.radius+31);
  assert.ok(Math.abs(start.x-end.x)<1e-6&&Math.abs(start.y-end.y)<1e-6);
  assert.ok(apex.opacity>.8);
});
test("all modes preserve source GPU budget and true reduced motion",()=>{
  assert.equal(PROFILES.ECO.maxParticles,3);
  assert.ok(PROFILES.MAX.maxParticles<=24);
  assert.ok(profileFor("MAX",true).maxParticles===0);
  assert.throws(()=>profileFor("INVALID",false),/INVALID_PROFILE/);
  assert.equal(clamp(Number.NaN,0,1),0);
});
test("decorations preserve approved original elements/handlers/data; revert fully",()=>{
  const o=fakeScene();
  const originalElements=o.orbs.map(x=>x.element);
  const ctrlFn=()=>true;o.ctrl.onclick=ctrlFn;
  const scene=installNoxCinemaFX({root:o.root,orbs:o.orbs,
      controls:[o.ctrl],panels:[o.panel],random:()=>.25});
  assert.equal(scene.snapshot().coreCount,8);
  assert.equal(o.root.classList.contains("nox-cinema-scope"),true);
  assert.equal(o.ctrl.classList.contains("nox-cinema-control"),true);
  assert.equal(o.panel.classList.contains("nox-cinema-panel"),true);
  assert.equal(o.orbs[0].element.dataset.original,"preserve");
  assert.equal(o.ctrl.onclick,ctrlFn);
  assert.equal(o.orbs[0].element.querySelector(".nox-cinema-orb__layers")!==null,true);
  o.tick(12000); // The first rare burst starts (MAX resources not needed).
  assert.ok(scene.snapshot().particles<=PROFILES.BALANCED.maxParticles);
  assert.ok(scene.snapshot().emitted>=1);
  scene.destroy();
  assert.equal(scene.snapshot().particles,0);
  assert.equal(o.pending,0);
  assert.equal(o.root.classList.contains("nox-cinema-scope"),false);
  assert.equal(o.root.dataset.noxFxVisible,undefined);
  assert.equal(o.ctrl.classList.contains("nox-cinema-control"),false);
  assert.ok(o.orbs.every((orb,i)=>orb.element===originalElements[i]&&
    !orb.element.querySelector(".nox-cinema-orb__layers")&&
    orb.element.dataset.original==="preserve"));
  assert.equal(o.ctrl.onclick,ctrlFn);
});
test("fail closed on duplicate mount, untrusted data, unknown CoreID",()=>{
  const o=fakeScene();
  const x=installNoxCinemaFX({root:o.root,orbs:o.orbs});
  assert.throws(()=>installNoxCinemaFX({root:o.root,orbs:o.orbs}),/ALREADY_MOUNTED/);
  assert.equal(x.setState("training","RUN-123","CORE_2"),true);
  assert.equal(o.orbs[2].element.dataset.noxFxState,"training");
  assert.equal(x.setState("training","bad/../run"),false);
  assert.equal(x.setState("learning"),false);
  assert.equal(x.setState("training","RUN-123","unknown"),false);
  x.destroy();
});
test("hidden tab, ECO, reduced motion stop animation and release particles",()=>{
  const o=fakeScene(),scene=installNoxCinemaFX({
    root:o.root,orbs:o.orbs,profile:"MAX",random:()=>.25});
  o.tick(12000);
  assert.ok(scene.snapshot().particles>0);
  o.visibility(false);
  assert.equal(o.root.dataset.noxFxVisible,"false");
  assert.equal(scene.snapshot().particles,0);
  assert.equal(o.pending,0);
  o.visibility(true);
  assert.equal(o.root.dataset.noxFxVisible,"true");
  assert.ok(o.pending>0);
  assert.equal(scene.setProfile("ECO"),true);
  assert.equal(o.root.dataset.noxFxMode,"eco");
  assert.equal(scene.setProfile("REDUCED"),true);
  assert.equal(o.pending,0);
  assert.equal(scene.snapshot().profile,"REDUCED");
  assert.equal(scene.setProfile("MAX"),true);
  o.reduced(true);
  assert.equal(o.pending,0);
  assert.equal(scene.snapshot().profile,"REDUCED");
  scene.destroy();
});
test("host state applies only from explicitly approved subscription and unsubscribes",()=>{
  const o=fakeScene();
  let handler=null,unsubscribed=false;
  const events={subscribe(fn){handler=fn;return()=>{unsubscribed=true;}}};
  const scene=installNoxCinemaFX({root:o.root,orbs:o.orbs,hostEvents:events});
  handler({trusted:false,state:"training",runId:"fake"});
  assert.equal(o.root.dataset.noxFxState,"idle");
  handler({trusted:true,state:"training",runId:"RUN-2",coreId:"CORE_1"});
  assert.equal(o.orbs[1].element.dataset.noxFxState,"training");
  assert.equal(o.root.dataset.noxFxState,"idle");
  handler({trusted:true,state:"streaming",runId:"RUN-2"});
  assert.equal(o.root.dataset.noxFxState,"streaming");
  assert.equal(scene.snapshot().stateRunId,"RUN-2");
  scene.destroy();
  assert.equal(unsubscribed,true);
});
test("no additional GPU/API engines or dangerous process hooks in FX code",async()=>{
  const fs=await import("node:fs");
  const js=fs.readFileSync(new URL("./nox-cinema.mjs",import.meta.url),"utf8");
  assert.equal(/\b(fetch|XMLHttpRequest|WebSocket)\s*\(/.test(js),false);
  assert.equal(js.includes("innerHTML"),false);
  assert.equal(js.includes("child_process"),false);
  assert.equal(js.includes("setInterval"),false);
});

test("host mode and state survive profile, events and teardown",()=>{
 const o=fakeScene();o.root.dataset.noxMode="HOST_BALANCED";o.root.dataset.noxState="HOST_RUNNING";o.orbs[0].element.dataset.noxState="OWNER_LLM";
 const fx=installNoxCinemaFX({root:o.root,orbs:o.orbs});assert.equal(fx.setProfile("ECO"),true);assert.equal(fx.setState("training","R-1"),true);
 assert.equal(o.root.dataset.noxFxMode,"eco");assert.equal(o.root.dataset.noxMode,"HOST_BALANCED");assert.equal(o.root.dataset.noxState,"HOST_RUNNING");assert.equal(o.orbs[0].element.dataset.noxState,"OWNER_LLM");
 fx.destroy();assert.equal(o.root.dataset.noxMode,"HOST_BALANCED");assert.equal(o.root.dataset.noxState,"HOST_RUNNING");assert.equal(o.root.dataset.noxFxMode,undefined);
});
test("late observer and visibility cannot revive disposed renderer",()=>{
 const o=fakeScene(),fx=installNoxCinemaFX({root:o.root,orbs:o.orbs});o.intersect(false);assert.equal(o.root.dataset.noxFxVisible,"false");
 fx.destroy();o.intersect(true);o.visibility(false);o.visibility(true);assert.equal(o.root.dataset.noxFxVisible,undefined);assert.equal(o.pending,0);
 assert.equal(fx.setState("training","R-2"),false);assert.equal(fx.setProfile("MAX"),false);assert.equal(fx.setVisible(true),false);
});
test("late native event after unsubscribe cannot mutate disposed FX",()=>{
 const o=fakeScene();let notify;const fx=installNoxCinemaFX({root:o.root,orbs:o.orbs,hostEvents:{subscribe(fn){notify=fn;return()=>{};}}});
 fx.destroy();notify({trusted:true,state:"training",runId:"R-3"});assert.equal(o.root.dataset.noxFxState,undefined);
});
test("failed subscribe rolls back FX but preserves owner fields",()=>{
 const o=fakeScene();o.root.dataset.noxMode="OWNER";o.root.dataset.noxState="RUNNING";
 assert.throws(()=>installNoxCinemaFX({root:o.root,orbs:o.orbs,hostEvents:{subscribe(){throw new Error("SUBSCRIBE_FAILED");}}}),/SUBSCRIBE_FAILED/);
 assert.equal(o.root.dataset.noxMode,"OWNER");assert.equal(o.root.dataset.noxState,"RUNNING");assert.equal(o.root.classList.contains("nox-cinema-scope"),false);
});
test("saved CSS matches FX namespace, scoped motion and stable click targets",async()=>{
 const fs=await import("node:fs");const s=fs.readFileSync(new URL("./nox-cinema.css",import.meta.url),"utf8");
 assert.equal(s.includes("[data-nox-mode="),false);assert.equal(s.includes("[data-nox-state="),false);
 assert.equal(s.includes(".nox-cinema-scope *,"),false);
 assert.equal(s.includes('.nox-cinema-control[data-nox-float="true"]::before'),true);
 assert.equal(s.includes('[data-nox-fx-mode="eco"]'),true);
});

// R07 E01 owner negative regressions. Keep original fixtures and approved D02 assets.
test("R07 strict RunID/CoreID types reject coercion",()=>{const o=fakeScene(),fx=installNoxCinemaFX({root:o.root,orbs:o.orbs});for(const x of [7,false,{}, {toString(){return "RUN-7";}}])assert.equal(fx.setState("training",x),false);for(const x of [1,true,{}])assert.equal(fx.setState("training","RUN-7",x),false);assert.equal(o.root.dataset.noxFxState,"idle");fx.destroy();});
test("R07 bad native RunID cannot fabricate visual training",()=>{const o=fakeScene();let cb;const fx=installNoxCinemaFX({root:o.root,orbs:o.orbs,hostEvents:{subscribe(fn){cb=fn;return()=>{};}}});for(const x of [false,0,{}])cb({trusted:true,state:"training",runId:x});cb({trusted:true,state:"training",runId:"OK",coreId:0});assert.equal(o.root.dataset.noxFxState,"idle");cb({trusted:true,state:"training",runId:"OK"});assert.equal(o.root.dataset.noxFxState,"training");fx.destroy();});
test("R07 root foreign state never overwritten",()=>{const o=fakeScene();o.root.dataset.noxFxMode="OWNER";assert.throws(()=>installNoxCinemaFX({root:o.root,orbs:o.orbs}),/OWNERSHIP_COLLISION/);assert.equal(o.root.dataset.noxFxMode,"OWNER");assert.ok(o.orbs.every(x=>!x.element.querySelector(".nox-cinema-orb__layers")));});
test("R07 foreign CoreID visual data never overwritten",()=>{const o=fakeScene();o.orbs[5].element.dataset.noxFxState="OWNER";assert.throws(()=>installNoxCinemaFX({root:o.root,orbs:o.orbs}),/OWNERSHIP_COLLISION/);assert.equal(o.orbs[5].element.dataset.noxFxState,"OWNER");});
test("R07 pre-existing cosmetic classes survive teardown",()=>{const o=fakeScene();o.orbs[0].element.classList.add("nox-cinema-orb");o.ctrl.classList.add("nox-cinema-control");o.panel.classList.add("nox-cinema-panel");const fx=installNoxCinemaFX({root:o.root,orbs:o.orbs,controls:[o.ctrl],panels:[o.panel]});fx.destroy();assert.ok(o.orbs[0].element.classList.contains("nox-cinema-orb"));assert.ok(o.ctrl.classList.contains("nox-cinema-control"));assert.ok(o.panel.classList.contains("nox-cinema-panel"));});
test("R07 invalid gravitational coordinates rejected",()=>{const p={started:0,duration:2200,surfaceRadius:89,reach:18,swirl:1,angle:0,brightness:.5,rotation:0};for(const f of ["surfaceRadius","reach","swirl","angle","brightness","rotation"])assert.throws(()=>gravitationalSample({...p,[f]:NaN},500),/INVALID_PARTICLE/);assert.throws(()=>gravitationalSample({...p,reach:-4},500),/INVALID_PARTICLE/);});
test("R07 malformed RNG cannot crash cinema renderer",()=>{for(const random of [()=>NaN,()=>{throw Error("rng");}]){const o=fakeScene(),fx=installNoxCinemaFX({root:o.root,orbs:o.orbs,random});o.tick(14000);assert.ok(fx.snapshot().particles<=PROFILES.BALANCED.maxParticles);fx.destroy();}});
test("R07 REDUCED queues no unnecessary animation",()=>{const o=fakeScene(),fx=installNoxCinemaFX({root:o.root,orbs:o.orbs,profile:"REDUCED"});assert.equal(o.pending,0);assert.equal(fx.setProfile("MAX"),true);assert.ok(o.pending>0);assert.equal(fx.setProfile("REDUCED"),true);assert.equal(o.pending,0);fx.destroy();});
test("R07 setVisible explicit boolean and native data preserved",()=>{const o=fakeScene(),fx=installNoxCinemaFX({root:o.root,orbs:o.orbs});o.root.dataset.noxState="HOST";assert.equal(fx.setVisible(false),true);assert.equal(o.pending,0);assert.equal(fx.setVisible(true),true);assert.ok(o.pending>0);assert.equal(o.root.dataset.noxState,"HOST");fx.destroy();assert.equal(fx.setVisible(true),false);});
test("R07 actual training selector not fictional running",async()=>{const fs=await import("node:fs");const css=fs.readFileSync(new URL("./nox-cinema.css",import.meta.url),"utf8");assert.ok(css.includes('[data-nox-fx-state="training"]'));assert.equal(css.includes('[data-nox-fx-state="running"]'),false);});

test("R08 invalid clock types reject before DOM edits",()=>{for(const clock of [0,1,"now",{},false]){const o=fakeScene();assert.throws(()=>installNoxCinemaFX({root:o.root,orbs:o.orbs,clock}),/INVALID_CLOCK/);assert.ok(o.orbs.every(x=>!x.element.querySelector(".nox-cinema-orb__layers")));}});
test("R08 clock exceptions cannot partially mount",()=>{const o=fakeScene();assert.throws(()=>installNoxCinemaFX({root:o.root,orbs:o.orbs,clock(){throw Error("time");}}),/INVALID_CLOCK/);assert.equal(o.root.classList.contains("nox-cinema-scope"),false);});
test("R08 nonfinite clock rejects before D02 decoration",()=>{for(const v of [NaN,Infinity,-1]){const o=fakeScene();assert.throws(()=>installNoxCinemaFX({root:o.root,orbs:o.orbs,clock:()=>v}),/INVALID_CLOCK/);}});
test("R08 sampled clock initialized exactly once for all nine cores",()=>{const o=fakeScene();let reads=0;const fx=installNoxCinemaFX({root:o.root,orbs:o.orbs,clock:()=>{reads++;return 1;}});assert.equal(reads,1);fx.destroy();});
test("R08 failing 4th SVG creation restores approved orbs",()=>{const o=fakeScene();const original=o.doc.createElementNS;let n=0;o.doc.createElementNS=function(...args){if(++n===4)throw Error("svg failure");return original.apply(this,args);};assert.throws(()=>installNoxCinemaFX({root:o.root,orbs:o.orbs}),/svg failure/);assert.ok(o.orbs.every(x=>!x.element.querySelector(".nox-cinema-orb__layers")&&!Object.hasOwn(x.element.dataset,"noxFxState")));o.doc.createElementNS=original;const fx=installNoxCinemaFX({root:o.root,orbs:o.orbs});fx.destroy();});
test("R08 failing panel cosmetics rolls back orb and control classes",()=>{const o=fakeScene();const original=o.panel.classList.add;o.panel.classList.add=function(x){if(x==="nox-cinema-panel")throw Error("panel");return original.call(this,x);};assert.throws(()=>installNoxCinemaFX({root:o.root,orbs:o.orbs,controls:[o.ctrl],panels:[o.panel]}),/panel/);assert.ok(o.orbs.every(x=>!x.element.querySelector(".nox-cinema-orb__layers")));assert.equal(o.ctrl.classList.contains("nox-cinema-control"),false);});
test("R08 failing visibility subscription rolls back and allows retry",()=>{const o=fakeScene();const orig=o.doc.addEventListener;o.doc.addEventListener=function(){throw Error("visibility");};assert.throws(()=>installNoxCinemaFX({root:o.root,orbs:o.orbs}),/visibility/);o.doc.addEventListener=orig;const fx=installNoxCinemaFX({root:o.root,orbs:o.orbs});fx.destroy();});
test("R08 failing motion subscription restores original DOM",()=>{const o=fakeScene();const orig=o.media.addEventListener;o.media.addEventListener=function(){throw Error("motion");};assert.throws(()=>installNoxCinemaFX({root:o.root,orbs:o.orbs}),/motion/);assert.ok(o.orbs.every(x=>!x.element.querySelector(".nox-cinema-orb__layers")));o.media.addEventListener=orig;const fx=installNoxCinemaFX({root:o.root,orbs:o.orbs});fx.destroy();});
test("R08 throwing IntersectionObserver.observe rolls back D02",()=>{const o=fakeScene();const Original=o.win.IntersectionObserver;o.win.IntersectionObserver=class{constructor(){}observe(){throw Error("intersection");}disconnect(){}};assert.throws(()=>installNoxCinemaFX({root:o.root,orbs:o.orbs}),/intersection/);assert.ok(o.orbs.every(x=>!x.element.querySelector(".nox-cinema-orb__layers")));o.win.IntersectionObserver=Original;const fx=installNoxCinemaFX({root:o.root,orbs:o.orbs});fx.destroy();});
test("R08 throwing requestAnimationFrame rolls back ownership",()=>{const o=fakeScene();const original=o.win.requestAnimationFrame;o.win.requestAnimationFrame=function(){throw Error("raf");};assert.throws(()=>installNoxCinemaFX({root:o.root,orbs:o.orbs}),/raf/);assert.equal(o.root.classList.contains("nox-cinema-scope"),false);o.win.requestAnimationFrame=original;const fx=installNoxCinemaFX({root:o.root,orbs:o.orbs});fx.destroy();});
test("R08 setVisible rejects nonboolean without hiding host scene",()=>{const o=fakeScene();const fx=installNoxCinemaFX({root:o.root,orbs:o.orbs});for(const value of [0,1,null,undefined,"false",{}])assert.equal(fx.setVisible(value),false);assert.equal(o.root.dataset.noxFxVisible,"true");fx.destroy();});
test("R08 reduced profile reports inactive and no false live FX",()=>{const o=fakeScene();const fx=installNoxCinemaFX({root:o.root,orbs:o.orbs,profile:"REDUCED"});assert.equal(fx.snapshot().active,false);assert.equal(o.pending,0);assert.equal(fx.setProfile("MAX"),true);assert.equal(fx.snapshot().active,true);o.reduced(true);assert.equal(fx.snapshot().active,false);fx.destroy();});
// R09 E01-owned source regressions (no original DOM/assets/host mutation).
test("R09-01 rejects brightness > 1",()=>{const p={started:0,duration:2200,surfaceRadius:89,reach:18,swirl:1,angle:0,brightness:.5,rotation:0};assert.throws(()=>gravitationalSample({...p,brightness:1.001},900),/INVALID_PARTICLE/);});
test("R09-02 rejects oversize surface",()=>{const p={started:0,duration:2200,surfaceRadius:89,reach:18,swirl:1,angle:0,brightness:.5,rotation:0};assert.throws(()=>gravitationalSample({...p,surfaceRadius:201},900),/INVALID_PARTICLE/);});
test("R09-03 rejects oversize reach",()=>{const p={started:0,duration:2200,surfaceRadius:89,reach:18,swirl:1,angle:0,brightness:.5,rotation:0};assert.throws(()=>gravitationalSample({...p,reach:201},900),/INVALID_PARTICLE/);});
test("R09-04 rejects oversize swirl",()=>{const p={started:0,duration:2200,surfaceRadius:89,reach:18,swirl:1,angle:0,brightness:.5,rotation:0};assert.throws(()=>gravitationalSample({...p,swirl:201},900),/INVALID_PARTICLE/);});
test("R09-05 rejects pathological azimuth",()=>{const p={started:0,duration:2200,surfaceRadius:89,reach:18,swirl:1,angle:0,brightness:.5,rotation:0};assert.throws(()=>gravitationalSample({...p,angle:1e30},900),/INVALID_PARTICLE/);});
test("R09-06 rejects pathological rotation",()=>{const p={started:0,duration:2200,surfaceRadius:89,reach:18,swirl:1,angle:0,brightness:.5,rotation:0};assert.throws(()=>gravitationalSample({...p,rotation:361},900),/INVALID_PARTICLE/);});
test("R09-07 rejects timestamp overflow",()=>{const p={started:-1e308,duration:2200,surfaceRadius:89,reach:18,swirl:1,angle:0,brightness:.5,rotation:0};assert.throws(()=>gravitationalSample(p,1e308),/INVALID_PARTICLE/);});
test("R09-08 invalid frame time stops decorative particles",()=>{const o=fakeScene(),fx=installNoxCinemaFX({root:o.root,orbs:o.orbs,profile:"MAX",random:()=>.25});o.tick(12000);assert.ok(fx.snapshot().particles>0);o.tick(Infinity);assert.equal(fx.snapshot().particles,0);assert.equal(o.pending,0);fx.destroy();});
test("R09-09 MAX to ECO prunes EXISTING particles now",()=>{const o=fakeScene(),fx=installNoxCinemaFX({root:o.root,orbs:o.orbs,profile:"MAX",random:()=>.25});o.tick(12000);assert.ok(fx.snapshot().particles>PROFILES.ECO.maxParticles);assert.equal(fx.setProfile("ECO"),true);assert.ok(fx.snapshot().particles<=PROFILES.ECO.maxParticles);assert.equal(o.root.dataset.noxFxMode,"eco");fx.destroy();});
test("R09-10 reduced/hidden teardown preserve native state",()=>{const o=fakeScene();o.root.dataset.noxState="HOST_RUNNING";const fx=installNoxCinemaFX({root:o.root,orbs:o.orbs,profile:"MAX",random:()=>.25});o.tick(12000);o.reduced(true);assert.equal(fx.snapshot().particles,0);o.visibility(false);fx.destroy();assert.equal(o.root.dataset.noxState,"HOST_RUNNING");assert.ok(o.orbs.every(x=>!x.element.querySelector(".nox-cinema-orb__layers")));});
test("R15-01 initial OS Reduced Motion syncs CSS before RAF",()=>{
  const o=fakeScene();o.reduced(true);
  const fx=installNoxCinemaFX({root:o.root,orbs:o.orbs,profile:"MAX"});
  assert.equal(o.root.dataset.noxFxMode,"reduced");
  assert.equal(fx.snapshot().profile,"REDUCED");
  assert.equal(o.pending,0);fx.destroy();
});
test("R15-02 OS motion toggles CSS without altering selected mode",()=>{
  const o=fakeScene(),fx=installNoxCinemaFX({root:o.root,orbs:o.orbs,profile:"ECO"});
  o.reduced(true);assert.equal(o.root.dataset.noxFxMode,"reduced");
  assert.equal(fx.snapshot().profile,"REDUCED");
  o.reduced(false);assert.equal(o.root.dataset.noxFxMode,"eco");
  assert.equal(fx.snapshot().profile,"ECO");fx.destroy();
});
test("R15-03 user MAX cannot override active OS motion reduction",()=>{
  const o=fakeScene(),fx=installNoxCinemaFX({root:o.root,orbs:o.orbs});
  o.reduced(true);assert.equal(fx.setProfile("MAX"),true);
  assert.equal(o.root.dataset.noxFxMode,"reduced");
  assert.equal(fx.snapshot().profile,"REDUCED");
  assert.equal(o.pending,0);fx.destroy();
});
