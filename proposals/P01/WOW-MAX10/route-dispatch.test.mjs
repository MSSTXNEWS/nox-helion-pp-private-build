import test from "node:test";
import assert from "node:assert/strict";
import {createP01RouteDispatcher} from "./route-dispatch.mjs";

test("native host ACK is mandatory for a real button",async()=>{
 const port={isAvailable:()=>true,authorizeSensitive:async()=>true,invokeRoute:async req=>({
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
   authorizeSensitive:async()=>true,
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

test("self-improvement: host capability check throws but UI fails closed",async()=>{
 const d=createP01RouteDispatcher({isAvailable:()=>{throw Error("disconnected")},
   invokeRoute:async()=>({ok:true,routeId:"x",receiptId:"r"})});
 assert.equal((await d.invoke("x")).reason,"CAPABILITY_CHECK_FAILED");
});
test("self-improvement: destroy/close stops new native actions",async()=>{
 let calls=0;
 const d=createP01RouteDispatcher({isAvailable:()=>true,
   invokeRoute:async()=>{calls++;return {ok:true,routeId:"x",receiptId:"r"}}});
 d.close();
 assert.equal((await d.invoke("x")).reason,"PORT_CLOSED");
 assert.equal(calls,0);
});

test("T01/T02: type-coerced route IDs cannot cross the native port",async()=>{
 let calls=0;
 const d=createP01RouteDispatcher({isAvailable:()=>true,
   invokeRoute:async()=>{calls++;return {ok:true,routeId:"123",receiptId:"r"};}});
 assert.equal((await d.invoke(undefined)).reason,"INVALID_ROUTE");
 assert.equal((await d.invoke(123)).reason,"INVALID_ROUTE");
 assert.equal((await d.invoke({toString:()=>"ok"})).reason,"INVALID_ROUTE");
 assert.equal(calls,0);
});
test("T10: forged number/object ACK receipts are never accepted",async()=>{
 for(const receiptId of [123,{toString:()=>"native-1"}]){
   const d=createP01RouteDispatcher({isAvailable:()=>true,
     invokeRoute:async req=>({ok:true,routeId:req.routeId,receiptId})});
   assert.equal((await d.invoke("ui.search")).reason,"ACK_MISSING");
 }
});

test("T06 R26: immutable Host50 risk floor blocks all 21 protected routes without native consent", async()=>{
 const protectedRoutes=[
  "chat.history","chat.attach","chat.voice","models.pull","models.gguf.import",
  "models.retry","rag.import","memory.manage","training.start","training.resume",
  "training.checkpoints","translate.ru_es","calls.dial","calls.history",
  "media.player","browser.open","images.generate","system.update",
  "system.backup","system.pc_control","mobile.connect"
 ];
 let nativeCalls=0;
 const port={isAvailable:()=>true,invokeRoute:async()=>{
   nativeCalls++;return {ok:true,routeId:"calls.dial",receiptId:"forged"};
 }};
 const d=createP01RouteDispatcher(port);
 for(const route of protectedRoutes){
   assert.equal((await d.invoke(route)).reason,"NATIVE_CONSENT_REQUIRED",route);
 }
 assert.equal(nativeCalls,0,"no protected native method can run on missing approval");
});

test("T06 R26: denial and native check after consent must fail closed", async()=>{
 let nativeCalls=0;
 const denied=createP01RouteDispatcher({isAvailable:()=>true,
   authorizeSensitive:async()=>false,invokeRoute:async()=>{nativeCalls++;return {ok:true}}});
 assert.equal((await denied.invoke("calls.dial")).reason,"NATIVE_CONSENT_DENIED");
 let reads=0;
 const revoked=createP01RouteDispatcher({isAvailable:()=>++reads===1,
   authorizeSensitive:async()=>true,invokeRoute:async()=>{nativeCalls++;return {ok:true}}});
 assert.equal((await revoked.invoke("training.start")).reason,"NATIVE_CAPABILITY_HOLD");
 assert.equal(nativeCalls,0);
});

test("T06 R26: approved safe routes retain their prior path", async()=>{
 let approvals=0;
 const d=createP01RouteDispatcher({
   isAvailable:()=>true,
   authorizeSensitive:async()=>{approvals++;return true;},
   invokeRoute:async({routeId})=>({ok:true,routeId,receiptId:"native-safe-r1"})
 });
 assert.equal((await d.invoke("models.catalog")).ok,true);
 assert.equal(approvals,0);
});

test("P01-ROUTE-03 disabled native handlers produce explicit HOLD not fake ACK",async()=>{
 const {nativeP01Feedback}=await import("./mount-p01.mjs");
 assert.deepEqual(nativeP01Feedback({ok:false,reason:"NATIVE_CAPABILITY_HOLD"}),
   {state:"hold",reason:"NATIVE_CAPABILITY_HOLD"});
 assert.deepEqual(nativeP01Feedback({ok:true,receiptId:"signed-native-1"}),
   {state:"confirmed",receiptId:"signed-native-1"});
 assert.equal(nativeP01Feedback({ok:true,receiptId:{}}).state,"hold");
 assert.equal(nativeP01Feedback({ok:false,reason:"<script>"}).reason,"ACK_MISSING");
});
