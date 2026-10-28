import {test} from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {admitNativeVisualEvent,CINEMA_EVENT_CONTRACT} from "./cinema50-events.mjs";

const catalog=JSON.parse(readFileSync(new URL("./catalog.json",import.meta.url),"utf8"));
const action=catalog.actions[0];
const stamp=Date.parse("2026-10-28T00:00:00.000Z");
function packet(route=action,overrides={}){
 return {routeId:route.routeId,raw:{
   schema:"NOX-INSTALLER-EVENT-v3",evidence_verified:true,
   event_type:"task.started",run_id:"run-32",event_id:"evt-77",
   task_id:route.taskId,action_id:"chat.start",package_id:"P0"+route.owner,
   event_sequence:1,receipt_sha256:"a".repeat(64),
   timestamp_utc:new Date(stamp).toISOString(),...overrides
 }};
}
test("canonical native source maps to selected route and bounded visual status",()=>{
 const result=admitNativeVisualEvent(packet(),catalog,{now:stamp+1000});
 assert.equal(result.routeId,action.routeId);
 assert.equal(result.state,"running");
 assert.equal(result.sequence,1);
 assert.equal(result.expires,stamp+30000);
 assert.equal(CINEMA_EVENT_CONTRACT.defaultDisabled,true);
});
test("all 50 legitimate task.started owner envelopes are supported",()=>{
 assert.equal(catalog.actions.length,50);
 for(const route of catalog.actions){
   const x=admitNativeVisualEvent(packet(route),catalog,{now:stamp+1000});
   assert.equal(x?.routeId,route.routeId,route.routeId);
 }
});
test("unregistered route, wrong owner, bad signature proxy and bare UI flags rejected",()=>{
 const valid=packet();
 for(const value of [
   {...valid,routeId:"fake.unregistered"},
   packet(action,{package_id:"P03"}),
   packet(action,{receipt_sha256:"fake"}),
   packet(action,{evidence_verified:false}),
   packet(action,{schema:"my-other-schema"}),
   packet(action,{event_sequence:0}),
   packet(action,{event_id:"<svg>"}),
   {routeId:action.routeId,source:"NOX_EVENT_V3_VERIFIED",evidenceVerified:true}
 ]){
   assert.equal(admitNativeVisualEvent(value,catalog,{now:stamp+1000}),null);
 }
});
test("stale (>30s), future (>5s), invalid progress and unknown event types fail closed",()=>{
 for(const [v,time] of [
   [packet(),stamp+30001],
   [packet(),stamp-5001],
   [packet(action,{numerator:5,denominator:2}),stamp+100],
   [packet(action,{numerator:0,denominator:0}),stamp+100],
   [packet(action,{event_type:"voice.listening"}),stamp+100],
   [packet(action,{event_type:"gpu.sample"}),stamp+100],
 ])assert.equal(admitNativeVisualEvent(v,catalog,{now:time}),null);
});
test("P03 pull and P04 training animate only matching owner-action pairs",()=>{
 const model=catalog.actions.find(x=>x.routeId==="models.pull");
 const train=catalog.actions.find(x=>x.routeId==="training.start");
 const p=packet(model,{event_type:"task.progress",action_id:"model.pull",
   numerator:1,denominator:6});
 const t=packet(train,{event_type:"training.step",action_id:"training.step",
   numerator:2,denominator:8});
 assert.equal(admitNativeVisualEvent(p,catalog,{now:stamp}).state,"downloading");
 assert.equal(admitNativeVisualEvent(t,catalog,{now:stamp}).state,"training");
 assert.equal(admitNativeVisualEvent({...p,raw:{...p.raw,action_id:"system.clean"}},
   catalog,{now:stamp}),null);
 assert.equal(admitNativeVisualEvent({...t,raw:{...t.raw,package_id:"P03"}},
   catalog,{now:stamp}),null);
});
test("native stopped event is not mislabeled paused or training",()=>{
 const model=catalog.actions.find(x=>x.routeId==="models.cancel");
 const p=packet(model,{event_type:"model.stopped",action_id:"model.stop"});
 assert.equal(admitNativeVisualEvent(p,catalog,{now:stamp}).state,"stopped");
});
