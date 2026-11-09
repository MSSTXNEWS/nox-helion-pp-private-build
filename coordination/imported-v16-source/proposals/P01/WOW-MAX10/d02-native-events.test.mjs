import test from "node:test";
import assert from "node:assert/strict";
import {createD02NativeVisualBus} from "./d02-native-events.mjs";
const NOW=1700000000000;
const CORES=Array.from({length:8},(_,i)=>"CORE_"+(i+1));
function fixture(){
  let native=null,subscriptions=0,unsubscribed=0,clock=NOW,nextHandle=0;
  const timers=new Map(),calls=[];
  const port={subscribeNative(fn){
    subscriptions++;native=fn;return ()=>{unsubscribed++;native=null;};
  }};
  const fx={setState(state,runId,coreId){calls.push({state,runId,coreId});return true;}};
  const bus=createD02NativeVisualBus(port,fx,CORES,{
    now:()=>clock,
    schedule(fn){const id=++nextHandle;timers.set(id,fn);return id;},
    cancel(id){timers.delete(id);}
  });
  const raw=(sequence=1,overrides={})=>({
    schema:"NOX-INSTALLER-EVENT-v3",evidence_verified:true,
    event_type:"task.started",event_sequence:sequence,
    event_id:"EV-"+sequence,run_id:"RUN-1",task_id:"T-1",
    action_id:"model.pull",package_id:"P03",
    receipt_sha256:"f".repeat(64),
    timestamp_utc:new Date(clock).toISOString(),
    core_id:"CORE_1",...overrides
  });
  return {bus,port,fx,raw,calls,timers,
    send:(event)=>native?.(event),
    advance(ms){clock+=ms;},
    flush(){for(const [id,fn] of [...timers]){timers.delete(id);fn();}},
    subscriptions:()=>subscriptions,unsubscribed:()=>unsubscribed};
}
test("T06: eight distinct CoreIDs mandatory and no extra owner renderer",()=>{
  assert.throws(()=>createD02NativeVisualBus({subscribeNative:()=>()=>{}},
    {setState:()=>true},CORES.slice(0,7)),/EIGHT_CORES/);
  assert.throws(()=>createD02NativeVisualBus({subscribeNative:()=>()=>{}},
    {setState:()=>true},[...CORES.slice(0,7),CORES[0]]),/EIGHT_CORES/);
});
test("T07: verified native v3 maps to the exact live CoreID, never invented training",()=>{
  const f=fixture();
  f.send(f.raw());assert.equal(f.calls.length,1);
  assert.deepEqual(f.calls[0],{state:"loading",runId:"RUN-1",coreId:"CORE_1"});
  assert.equal(f.bus.snapshot().acceptedNativeEvents,1);
  assert.equal(f.bus.snapshot().hostIntegrationVerified,false);
  f.bus.destroy();
});
test("T07: unverified, wrong CoreID, unknown event and stale timestamp remain HOLD",()=>{
  const f=fixture();
  for(const ev of [
    f.raw(1,{evidence_verified:false}),
    f.raw(2,{core_id:"CORE_9"}),
    f.raw(3,{event_type:"training.fake"}),
    f.raw(4,{timestamp_utc:new Date(NOW-32000).toISOString()})
  ])f.send(ev);
  assert.equal(f.calls.length,0);
  assert.equal(f.bus.snapshot().acceptedNativeEvents,0);
  f.bus.destroy();
});
test("T07: replay and old per-run sequence cannot overwrite a newer state",()=>{
  const f=fixture();
  f.send(f.raw(5));
  f.send(f.raw(5,{event_id:"EV-5b"}));
  f.send(f.raw(4));
  f.send(f.raw(6));
  assert.equal(f.calls.length,2);
  assert.equal(f.bus.snapshot().acceptedNativeEvents,2);
  f.bus.destroy();
});
test("T08: a verified state expires to idle unless new native evidence refreshes it",()=>{
  const f=fixture();
  f.send(f.raw(1));
  assert.equal(f.timers.size,1);
  f.advance(1000);f.send(f.raw(2));
  assert.equal(f.timers.size,1);
  f.flush();
  assert.equal(f.calls.at(-1).state,"idle");
  assert.equal(f.calls.at(-1).coreId,"CORE_1");
  assert.equal(f.bus.snapshot().activeCoreStates,0);
  f.bus.destroy();
});
test("T09: exactly one native subscription fans out to existing secondary WOW",()=>{
  const f=fixture();
  let seenA=0,seenB=0;
  const offA=f.bus.subscribe(()=>{seenA++;throw Error("panel failure");});
  f.bus.subscribe(()=>{seenB++;});
  f.send(f.raw());
  assert.equal(f.subscriptions(),1);
  assert.equal(seenA,1);assert.equal(seenB,1);
  offA();f.send(f.raw(2));
  assert.equal(seenA,1);assert.equal(seenB,2);
  f.bus.destroy();assert.equal(f.unsubscribed(),1);
});
test("T10: destroying the scene cancels expiry and detaches native input",()=>{
  const f=fixture();f.send(f.raw());
  assert.equal(f.timers.size,1);
  f.bus.destroy();
  assert.equal(f.timers.size,0);
  assert.equal(f.unsubscribed(),1);
  f.flush();assert.equal(f.calls.length,1);
  assert.throws(()=>f.bus.subscribe(()=>{}),/SUBSCRIBER_REQUIRED/);
});

test("T06: undefined/numeric CoreID cannot pass regex string coercion",()=>{
 for(const bad of [undefined,123]){
   const ids=CORES.slice();ids[7]=bad;
   assert.throws(()=>createD02NativeVisualBus(
     {subscribeNative:()=>()=>{}},{setState:()=>true},ids),/EIGHT_CORES/);
 }
});
