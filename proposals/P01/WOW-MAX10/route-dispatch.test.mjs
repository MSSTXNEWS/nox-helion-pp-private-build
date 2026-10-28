import test from "node:test";
import assert from "node:assert/strict";
import {createP01RouteDispatcher} from "./route-dispatch.mjs";

test("native host ACK is mandatory for a real button",async()=>{
 const port={isAvailable:()=>true,invokeRoute:async req=>({
   ok:true,routeId:req.routeId,receiptId:"native-receipt-1"})};
 const d=createP01RouteDispatcher(port);
 assert.deepEqual(await d.invoke("system.update"),{
   ok:true,routeId:"system.update",receiptId:"native-receipt-1"});
});
test("unavailable host capability stays HOLD; no native call",async()=>{
 let count=0;
 const d=createP01RouteDispatcher({isAvailable:()=>false,
   invokeRoute:async()=>{count++;return {ok:true}}});
 assert.equal((await d.invoke("system.pc_control")).reason,"NATIVE_CAPABILITY_HOLD");
 assert.equal(count,0);
});
test("forged/missing ACK does not become button success",async()=>{
 const d=createP01RouteDispatcher({isAvailable:()=>true,
   invokeRoute:async()=>({ok:true,routeId:"media.play"})});
 assert.equal((await d.invoke("media.play")).ok,false);
});
test("duplicate in-flight click does not duplicate work",async()=>{
 let release;
 const gate=new Promise(resolve=>release=resolve);
 const d=createP01RouteDispatcher({isAvailable:()=>true,
   invokeRoute:async req=>{await gate;return {ok:true,routeId:req.routeId,receiptId:"done"};}});
 const first=d.invoke("models.pull");
 assert.equal(d.isPending("models.pull"),true);
 assert.equal((await d.invoke("models.pull")).reason,"PENDING");
 release();
 assert.equal((await first).ok,true);
 assert.equal(d.isPending("models.pull"),false);
});
test("native error and invalid routes fail closed",async()=>{
 const d=createP01RouteDispatcher({isAvailable:()=>true,invokeRoute:async()=>{throw Error("OFFLINE")}});
 assert.equal((await d.invoke("x<unsafe>")).ok,false);
 assert.equal((await d.invoke("model.pull")).reason,"NATIVE_ERROR");
});
