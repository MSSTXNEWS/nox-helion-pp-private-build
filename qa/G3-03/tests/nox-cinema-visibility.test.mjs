import test from "node:test";
import assert from "node:assert/strict";
import {clamp,validateScene,profileFor,gravitationalSample,
        installNoxCinemaFX,PROFILES} from "../candidates/nox-cinema.mjs";

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
  const intersections=[];
  let nextFrame=0,now=0,hidden=false;
  const mediaHandlers=[];
  const media={matches:false,addEventListener(n,fn){mediaHandlers.push(fn);},
    removeEventListener(n,fn){let i=mediaHandlers.indexOf(fn);if(i>=0)mediaHandlers.splice(i,1);}};
  const win={performance:{now:()=>now},
    requestAnimationFrame(fn){frames.set(++nextFrame,fn);return nextFrame;},
    cancelAnimationFrame(id){frames.delete(id);},
    matchMedia(){return media;},
    IntersectionObserver:class{constructor(cb){this.cb=cb;intersections.push(this);}observe(){}disconnect(){const i=intersections.indexOf(this);if(i>=0)intersections.splice(i,1);}}
  };
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
    intersect(value){for(const x of [...intersections])x.cb([{isIntersecting:value}]);},
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
  assert.equal(o.orbs[2].element.dataset.noxState,"training");
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
  assert.equal(o.root.dataset.noxMode,"eco");
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
  assert.equal(o.root.dataset.noxState,"idle");
  handler({trusted:true,state:"training",runId:"RUN-2",coreId:"CORE_1"});
  assert.equal(o.orbs[1].element.dataset.noxState,"training");
  assert.equal(o.root.dataset.noxState,"idle");
  handler({trusted:true,state:"streaming",runId:"RUN-2"});
  assert.equal(o.root.dataset.noxState,"streaming");
  assert.equal(scene.snapshot().stateRunId,"RUN-2");
  scene.destroy();
  assert.equal(unsubscribed,true);
});
test("no additional GPU/API engines or dangerous process hooks in FX code",async()=>{
  const fs=await import("node:fs");
  const js=fs.readFileSync(new URL("../candidates/nox-cinema.mjs",import.meta.url),"utf8");
  assert.equal(/\b(fetch|XMLHttpRequest|WebSocket)\s*\(/.test(js),false);
  assert.equal(js.includes("innerHTML"),false);
  assert.equal(js.includes("child_process"),false);
  assert.equal(js.includes("setInterval"),false);
});

test("host hide beats intersect-true callback",()=>{const o=fakeScene(),fx=installNoxCinemaFX({root:o.root,orbs:o.orbs,profile:"MAX"});fx.setVisible(false);o.intersect(true);assert.equal(o.pending,0);assert.equal(fx.snapshot().active,false);assert.equal(o.root.dataset.noxFxVisible,"false");fx.destroy();});
test("tab hidden + offscreen cannot start rAF",()=>{const o=fakeScene(),fx=installNoxCinemaFX({root:o.root,orbs:o.orbs,profile:"MAX"});o.intersect(false);fx.setVisible(true);assert.equal(o.pending,0);o.visibility(false);o.intersect(true);assert.equal(o.pending,0);assert.equal(o.root.dataset.noxFxVisible,"false");o.visibility(true);assert.equal(o.pending,1);fx.destroy();});
test("reduced mode and offscreen pause includes floating pseudo-element",async()=>{const fs=await import("node:fs");const css=fs.readFileSync(new URL("../candidates/nox-cinema.css",import.meta.url),"utf8");assert.match(css,/data-nox-mode="reduced"\\] \\.nox-cinema-control\\[data-nox-float="true"\\]::after/);assert.match(css,/data-nox-fx-visible="false"\\] \\.nox-cinema-control\\[data-nox-float="true"\\]::after/);assert.equal(css.includes('data-nox-state="running"'),false);});
