import test from "node:test";import assert from "node:assert/strict";
import {createP01ModeController as create} from "./p01-mode-controller.mjs";
import {effectiveP01MotionMode} from "./mount-p01.mjs";
function fixture(){let fxMode="BALANCED",wowMode="BALANCED";
 const fx={setProfile(m){fxMode=m;return true}};
 const wow={setMode(m){wowMode=m}};
 return {fx,wow,get:()=>[fxMode,wowMode]};}
test("C5.01 must have real FX target",()=>assert.throws(()=>create({}),/TARGET/));
test("C5.02 begins BALANCED",()=>{const x=fixture();assert.equal(create(x.fx,x.wow).get().mode,"BALANCED");});
for(const [i,mode] of ["ECO","BALANCED","MAX","REDUCED"].entries())
 test("C5.0"+(i+3)+" "+mode,()=>{const x=fixture();const c=create(x.fx,x.wow);assert.equal(c.set(mode),true);assert.deepEqual(x.get(),[mode,mode]);});
test("C5.07 invalid mode leaves scene unchanged",()=>{const x=fixture();const c=create(x.fx,x.wow);
 assert.equal(c.set("SUPER"),false);assert.deepEqual(x.get(),["BALANCED","BALANCED"]);});
test("C5.08 one scene error rolls existing FX back",()=>{const x=fixture();
 x.wow.setMode=()=>{throw Error("renderer unavailable")};const c=create(x.fx,x.wow);
 assert.equal(c.set("MAX"),false);assert.equal(x.get()[0],"BALANCED");});
test("C5.09 closed controller rejects mutation",()=>{const x=fixture();const c=create(x.fx,x.wow);c.close();
 assert.equal(c.set("ECO"),false);assert.equal(c.get().closed,true);});
test("C5.10 read-only status does not manufacture sensor state",()=>{const x=fixture();
 const c=create(x.fx,x.wow);assert.equal(c.get().telemetry,"UNMODIFIED");
 assert.equal(Object.isFrozen(c.get()),true);});

test("C5.11 OS Reduced Motion overrides MAX before original D02 FX mounts",()=>{
 for(const mode of ["MAX","BALANCED","ECO","REDUCED"])
   assert.equal(effectiveP01MotionMode(mode,true),"REDUCED");
});
test("C5.12 user mode resumes only when system Reduced Motion is disabled",()=>{
 assert.equal(effectiveP01MotionMode("MAX",false),"MAX");
 assert.equal(effectiveP01MotionMode("ECO",false),"ECO");
 assert.equal(effectiveP01MotionMode("MAX",true),"REDUCED");
 assert.equal(effectiveP01MotionMode("MAX",false),"MAX");
});
