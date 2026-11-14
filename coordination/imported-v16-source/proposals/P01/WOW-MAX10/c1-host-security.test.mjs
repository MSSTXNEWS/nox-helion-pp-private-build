import test from "node:test";
import assert from "node:assert/strict";
import {createP01RouteDispatcher as create} from "./route-dispatch.mjs";
const host=(overrides={})=>({isAvailable:()=>true,invokeRoute:async r=>({ok:true,routeId:r.routeId,receiptId:"receipt01"}),...overrides});
test("C1.01 host contract required",()=>assert.throws(()=>create({}),/E06_PORT_REQUIRED/));
test("C1.02 malformed route rejected",async()=>assert.equal((await create(host()).invoke("../escape")).reason,"INVALID_ROUTE"));
test("C1.03 unavailable route does not invoke",async()=>{
 let runs=0;const d=create(host({isAvailable:()=>false,invokeRoute:async()=>{runs++}}));
 assert.equal((await d.invoke("app.run")).reason,"NATIVE_CAPABILITY_HOLD");assert.equal(runs,0);
});
test("C1.04 capability exception fails closed",async()=>{
 assert.equal((await create(host({isAvailable:()=>{throw Error("disconnect")}})).invoke("x")).reason,"CAPABILITY_CHECK_FAILED");
});
test("C1.05 sensitive route needs host consent",async()=>{
 assert.equal((await create(host()).invoke("system.pc_control")).reason,"NATIVE_CONSENT_REQUIRED");
});
test("C1.06 denied sensitive consent does not invoke",async()=>{
 let runs=0;const d=create(host({authorizeSensitive:async()=>false,invokeRoute:async()=>{runs++}}));
 assert.equal((await d.invoke("system.update")).reason,"NATIVE_CONSENT_DENIED");assert.equal(runs,0);
});
test("C1.07 approval permits exact route only",async()=>{
 const d=create(host({authorizeSensitive:async x=>x.routeId==="system.update"}));
 assert.equal((await d.invoke("system.update")).ok,true);
});
test("C1.08 wrong native ACK route rejected",async()=>{
 assert.equal((await create(host({invokeRoute:async()=>({ok:true,routeId:"wrong",receiptId:"r"})})).invoke("media.play")).reason,"ACK_MISSING");
});
test("C1.09 synchronous reentry blocked",async()=>{
 let d,reentered;const h=host({isAvailable:()=>{reentered=d.invoke("x");return true;}});
 d=create(h);const result=await d.invoke("x");
 assert.equal(result.ok,true);assert.equal((await reentered).reason,"PENDING");
});
test("C1.10 close suppresses late native ACK",async()=>{
 let finish;const d=create(host({invokeRoute:()=>new Promise(r=>finish=r)}));
 const request=d.invoke("media.open");d.close();finish({ok:true,routeId:"media.open",receiptId:"r"});
 assert.equal((await request).reason,"PORT_CLOSED");
});
