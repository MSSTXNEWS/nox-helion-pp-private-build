import test from "node:test";
import assert from "node:assert/strict";
import {createD02NativeVisualBus} from "./d02-native-events.mjs";

const NOW=1700000000000;
const IDS=["CONSCIOUSNESS","PERSONA","ATLAS","VOICE","REFLECTION","CORE","NEXUS","FORGE"];
function rig(){
  let receive;const state=[];const callbacks=new Map();
  const port={subscribeNative(cb){receive=cb;return()=>{receive=null;}}};
  const fx={setState(s,run,core){state.push({s,run,core});return true}};
  const bus=createD02NativeVisualBus(port,fx,IDS,{
    now:()=>NOW,schedule:fn=>{const key=callbacks.size+1;callbacks.set(key,fn);return key;},
    cancel:key=>callbacks.delete(key)
  });
  const observed=[];bus.subscribe(e=>observed.push(e));
  const event=(seq=1,patch={})=>({
    schema:"NOX-INSTALLER-EVENT-v3",event_type:"task.started",
    evidence_verified:true,run_id:"RUN-100",event_id:"EV-"+seq,
    event_sequence:seq,task_id:"T-100",action_id:"model.pull",
    package_id:"P03",receipt_sha256:"a".repeat(64),
    timestamp_utc:new Date(NOW).toISOString(),core_id:IDS[0],...patch
  });
  return {bus,state,observed,event,send:e=>receive?.(e)};
}
test("E01-01 valid native event updates actual CoreID and panel exactly once",()=>{
  const r=rig();r.send(r.event());assert.equal(r.state.length,1);
  assert.equal(r.observed.length,1);r.bus.destroy();
});
test("E01-02 forged success flag never reaches secondary WOW",()=>{
  const r=rig();r.send(r.event(1,{evidence_verified:false}));
  assert.equal(r.state.length,0);assert.equal(r.observed.length,0);r.bus.destroy();
});
test("E01-03 tampered receipt digest never reaches secondary WOW",()=>{
  const r=rig();r.send(r.event(1,{receipt_sha256:"untrusted"}));
  assert.equal(r.observed.length,0);r.bus.destroy();
});
test("E01-04 unknown CoreID is denied before any visual fanout",()=>{
  const r=rig();r.send(r.event(1,{core_id:"FOREIGN"}));
  assert.equal(r.observed.length,0);r.bus.destroy();
});
test("E01-05 duplicate sequence not replayed to secondary WOW",()=>{
  const r=rig();r.send(r.event(1));r.send(r.event(1));
  assert.equal(r.observed.length,1);r.bus.destroy();
});
test("E01-06 older sequence not replayed to secondary WOW",()=>{
  const r=rig();r.send(r.event(3));r.send(r.event(2));
  assert.equal(r.observed.length,1);r.bus.destroy();
});
test("E01-07 stale timestamp does not reach secondary WOW",()=>{
  const r=rig();r.send(r.event(1,{timestamp_utc:new Date(NOW-65000).toISOString()}));
  assert.equal(r.observed.length,0);r.bus.destroy();
});
test("E01-08 unknown event family is not a training indicator",()=>{
  const r=rig();r.send(r.event(1,{event_type:"training.fake"}));
  assert.equal(r.observed.length,0);r.bus.destroy();
});
test("E01-09 native callback isolates secondary observer exceptions",()=>{
  const r=rig();r.bus.subscribe(()=>{throw Error("decorative fault")});
  r.send(r.event(1));assert.equal(r.state.length,1);r.bus.destroy();
});
test("E01-10 teardown prevents further propagation",()=>{
  const r=rig();r.send(r.event());r.bus.destroy();r.send(r.event(2));
  assert.equal(r.observed.length,1);assert.equal(r.bus.snapshot().activeCoreStates,0);
});