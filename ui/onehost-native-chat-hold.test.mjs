/** Original single WebView2 native chat busy-state regression (source-only).
 * node --test ui/onehost-native-chat-hold.test.mjs
 * Trust of message source/nonce/route is separately enforced in createNativeMenuClient.
 */
import test from "node:test";
import assert from "node:assert/strict";
import {isNativeChatTerminal} from "./onehost-menu-bindings.mjs";

test("native terminal HOLD for unknown model error unlocks Send",()=>{
  assert.equal(isNativeChatTerminal({routeId:"helion.chat",state:"HOLD",errorCode:"MODEL_NOT_INSTALLED"}),true);
});
test("original native consent-denial HOLD still unlocks",()=>{
  assert.equal(isNativeChatTerminal({routeId:"helion.chat",state:"HOLD",errorCode:"NATIVE_PERMISSION_DENIED"}),true);
});
test("native completed with done=true unlocks",()=>{
  assert.equal(isNativeChatTerminal({routeId:"helion.chat",state:"COMPLETED",result:{done:true}}),true);
});
test("incomplete native COMPLETED cannot unlock another concurrent chat",()=>{
  assert.equal(isNativeChatTerminal({routeId:"helion.chat",state:"COMPLETED",result:{done:false}}),false);
});
test("STOP_REQUESTED means STOP still pending, not terminal proof",()=>{
  assert.equal(isNativeChatTerminal({routeId:"helion.chat",state:"STOP_REQUESTED",result:{done:false}}),false);
});
test("unrelated route HOLD cannot release chat",()=>{
  assert.equal(isNativeChatTerminal({routeId:"models.cancel",state:"HOLD"}),false);
});
test("HOLD without native route matching cannot release chat",()=>{
  assert.equal(isNativeChatTerminal({state:"HOLD",errorCode:"MODEL_NOT_INSTALLED"}),false);
});
