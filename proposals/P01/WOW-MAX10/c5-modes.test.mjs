import test from "node:test";import assert from "node:assert/strict";
import {createP01ModeController as create} from "./p01-mode-controller.mjs";
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
test("C5.11 explicit WOW rejection must restore previous cinema mode",()=>{const x=fixture();
 x.wow.setMode=()=>false;const c=create(x.fx,x.wow);
 assert.equal(c.set("MAX"),false);assert.equal(x.get()[0],"BALANCED");
});
test("C5.12 rejected FX profile restores its prior state",()=>{
 let mode="BALANCED";const fx={setProfile(next){mode=next;return next!=="MAX";}};
 const c=create(fx,null);assert.equal(c.set("MAX"),false);
 assert.equal(mode,"BALANCED");assert.equal(c.get().mode,"BALANCED");
});
test("C5.09 closed controller rejects mutation",()=>{const x=fixture();const c=create(x.fx,x.wow);c.close();
 assert.equal(c.set("ECO"),false);assert.equal(c.get().closed,true);});
test("C5.10 read-only status does not manufacture sensor state",()=>{const x=fixture();
 const c=create(x.fx,x.wow);assert.equal(c.get().telemetry,"UNMODIFIED");
 assert.equal(Object.isFrozen(c.get()),true);});
