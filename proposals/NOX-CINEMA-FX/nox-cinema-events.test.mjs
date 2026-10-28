import test from "node:test";
import assert from "node:assert/strict";
import {visualEvent,attachCinemaToNativeEvents} from "./nox-cinema-events.mjs";
const t0=Date.parse("2026-10-28T00:00:00Z");
function ev(type,sequence=1,pkg="P04",action="training.start"){
  return {schema:"NOX-INSTALLER-EVENT-v3",run_id:"RUN-001",
    event_id:"EVENT-"+sequence,event_type:type,event_sequence:sequence,
    task_id:"NIP01-26",package_id:pkg,action_id:action,
    state:"RUNNING",timestamp_utc:new Date(t0).toISOString(),
    source:"P04.QLoRA",message:"",evidence_verified:false};
}
test("documented events map to truthful animation only",()=>{
  assert.equal(visualEvent(ev("training.step"),t0).state,"training");
  assert.equal(visualEvent(ev("checkpoint.saved"),t0).state,"training");
  assert.equal(visualEvent(ev("model.stopped"),t0).state,"stopped");
  assert.equal(visualEvent(ev("task.failed"),t0).state,"error");
  assert.equal(visualEvent(ev("task.completed"),t0).state,"success");
});
test("gpu sample and unsupported events never represent training",()=>{
  assert.equal(visualEvent(ev("gpu.sample"),t0),null);
  assert.equal(visualEvent(ev("telemetry.snapshot"),t0),null);
  assert.equal(visualEvent(ev("training.step",1,"P05"),t0),null);
});
test("P03 actual model progress is the only loading signal",()=>{
  assert.equal(visualEvent(ev("task.progress",1,"P03","model.pull"),t0).state,"loading");
  assert.equal(visualEvent(ev("task.started",1,"P03","pull.model"),t0).state,"loading");
  assert.equal(visualEvent(ev("task.progress",1,"P02","chat.message"),t0),null);
});
test("stale, future, incorrect schema and incomplete v3 are rejected",()=>{
  assert.equal(visualEvent(ev("training.step"),t0+31000),null);
  assert.equal(visualEvent(ev("training.step"),t0-6000),null);
  assert.equal(visualEvent({...ev("training.step"),schema:"BAD-SCHEMA"},t0),null);
  assert.equal(visualEvent({...ev("training.step"),event_sequence:0},t0),null);
  assert.equal(visualEvent({...ev("training.step"),run_id:"INVALID RUN"},t0),null);
});
test("native bridge deduplicates events by run sequence and unsubscribes",()=>{
  let handler,closed=false;const changes=[];
  const detach=attachCinemaToNativeEvents({setState:(state,run)=>changes.push([state,run])},
    fn=>{handler=fn;return()=>{closed=true;};},{now:()=>t0});
  handler(ev("training.step",2));
  handler(ev("task.failed",1));
  handler(ev("task.completed",3));
  assert.deepEqual(changes,[["training","RUN-001"],["success","RUN-001"]]);
  detach();detach();handler(ev("task.failed",4));
  assert.equal(closed,true);
  assert.equal(changes.length,2);
});
test("visual updates do not mutate original model records",()=>{
  let handle;const changes=[];
  const detach=attachCinemaToNativeEvents({setState:s=>changes.push(s)},
    callback=>{handle=callback;return()=>{};},{now:()=>t0});
  const original=ev("training.step"),before=JSON.stringify(original);
  handle(original);detach();
  assert.equal(JSON.stringify(original),before);
  assert.deepEqual(changes,["training"]);
});
