/** Original P01/D02/MENU10 native feedback regression.
 * Run: node --test proposals/P01/WOW-MAX10/mount-p01-rejected-ack.test.mjs
 * Source-only; not a Windows E07 or native permission substitute.
 */
import test from "node:test";
import assert from "node:assert/strict";
import {invokeP01NativeRouteFeedback} from "./mount-p01.mjs";

test("rejected asynchronous native OneHost ACK becomes HOLD without error leakage",async()=>{
  const output=await invokeP01NativeRouteFeedback({
    invoke:async()=>{throw Error("PRIVATE_SID_OR_HOST_DIAGNOSTIC");}
  },"core.atlas");
  assert.deepEqual(output,{state:"hold",reason:"NATIVE_DISPATCH_FAILED"});
});
test("synchronous native dispatch exception becomes HOLD",async()=>{
  const output=await invokeP01NativeRouteFeedback({
    invoke:()=>{throw Error("P02_NATIVE_UNAVAILABLE");}
  },"core.atlas");
  assert.deepEqual(output,{state:"hold",reason:"NATIVE_DISPATCH_FAILED"});
});
test("only a real explicitly successful native ACK with valid receipt may confirm",async()=>{
  const output=await invokeP01NativeRouteFeedback({
    invoke:async route=>({ok:route==="core.atlas",receiptId:"owner-20261102:7"})
  },"core.atlas");
  assert.deepEqual(output,{state:"confirmed",receiptId:"owner-20261102:7"});
});
test("owner ACL denial retains native uppercase reason without fabricated ACK",async()=>{
  const output=await invokeP01NativeRouteFeedback({
    invoke:async()=>({ok:false,reason:"NATIVE_ACL_DENIED"})
  },"core.atlas");
  assert.deepEqual(output,{state:"hold",reason:"NATIVE_ACL_DENIED"});
});
test("success flag without native receipt still HOLD",async()=>{
  const output=await invokeP01NativeRouteFeedback({
    invoke:async()=>({ok:true})
  },"core.atlas");
  assert.deepEqual(output,{state:"hold",reason:"ACK_MISSING"});
});
test("untrusted receipt format never confirms",async()=>{
  const output=await invokeP01NativeRouteFeedback({
    invoke:async()=>({ok:true,receiptId:"not trusted/receipt"})
  },"core.atlas");
  assert.deepEqual(output,{state:"hold",reason:"ACK_MISSING"});
});
