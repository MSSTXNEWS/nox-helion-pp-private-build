import test from "node:test";
import assert from "node:assert/strict";
import {visualEvent,attachCinemaToNativeEvents} from "./nox-cinema-events.mjs";
const t0=Date.parse("2026-10-28T00:00:00Z");
function ev(type,sequence=1,pkg="P04",action="training.start"){
  return {schema:"NOX-INSTALLER-EVENT-v3",run_id:"RUN-001",
    event_id:"EVENT-"+sequence,event_type:type,event_sequence:sequence,
    task_id:"NIP01-26",package_id:pkg,action_id:action,
    state:type==="task.completed"?"COMPLETED":type==="task.failed"?"FAILED":
      type==="model.stopped"?"STOPPED":"RUNNING",
    timestamp_utc:new Date(t0).toISOString(),
    source:"P04.QLoRA",message:"",evidence_verified:true};
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

test("terminal native-state contradiction fails closed",()=>{
  assert.equal(visualEvent({...ev("task.completed"),state:"FAILED"},t0),null);
  assert.equal(visualEvent({...ev("task.failed"),state:"COMPLETED"},t0),null);
  assert.equal(visualEvent({...ev("model.stopped"),state:"RUNNING"},t0),null);
});
test("unverified native terminal cannot assert success or failure",()=>{
  assert.equal(visualEvent({...ev("task.completed"),evidence_verified:false},t0),null);
  assert.equal(visualEvent({...ev("task.failed"),evidence_verified:false},t0),null);
});
test("running-only events cannot resurrect a failed/completed run",()=>{
  assert.equal(visualEvent({...ev("task.progress"),state:"FAILED"},t0),null);
  assert.equal(visualEvent({...ev("training.step"),state:"COMPLETED"},t0),null);
});
test("verified coherent success/error remain visible",()=>{
  assert.equal(visualEvent(ev("task.completed"),t0)?.state,"success");
  assert.equal(visualEvent(ev("task.failed"),t0)?.state,"error");
});
test("higher sequence late progress never overrides completion",()=>{
  let send;const states=[];
  const detach=attachCinemaToNativeEvents({setState:state=>states.push(state)},
    fn=>{send=fn;return()=>{};},{now:()=>t0});
  send(ev("task.completed",2));send(ev("task.progress",3));detach();
  assert.deepEqual(states,["success"]);
});
test("verified failure locks out later contradictory success",()=>{
  let send;const states=[];
  const detach=attachCinemaToNativeEvents({setState:state=>states.push(state)},
    fn=>{send=fn;return()=>{};},{now:()=>t0});
  send(ev("task.failed",2));send(ev("task.completed",3));detach();
  assert.deepEqual(states,["error"]);
});
test("terminal cache is isolated by RunID",()=>{
  let send;const states=[];
  const detach=attachCinemaToNativeEvents({setState:(state,run)=>states.push([state,run])},
    fn=>{send=fn;return()=>{};},{now:()=>t0});
  send(ev("task.completed",2));send({...ev("task.progress",3),run_id:"RUN-002"});detach();
  assert.deepEqual(states,[["success","RUN-001"],["training","RUN-002"]]);
});

test("R12-01 rejected render retains sequence for retry",()=>{
 let cb,ok=false,out=[];const off=attachCinemaToNativeEvents({setState:s=>{if(!ok)return false;out.push(s);return true;}},f=>{cb=f;return()=>{};},{now:()=>t0});
 cb(ev("task.progress",1,"P03","model.pull"));ok=true;cb(ev("task.progress",1,"P03","model.pull"));off();assert.deepEqual(out,["loading"]);
});
test("R12-02 render exception is isolated and retry succeeds",()=>{
 let cb,fail=true,out=[];const off=attachCinemaToNativeEvents({setState:s=>{if(fail)throw Error("GONE");out.push(s);return true;}},f=>{cb=f;return()=>{};},{now:()=>t0});
 assert.doesNotThrow(()=>cb(ev("task.completed",2)));fail=false;cb(ev("task.completed",2));off();assert.deepEqual(out,["success"]);
});
test("R12-03 rejected terminal does not latch a false result",()=>{
 let cb,ok=false,out=[];const off=attachCinemaToNativeEvents({setState:s=>{if(!ok)return false;out.push(s);return true;}},f=>{cb=f;return()=>{};},{now:()=>t0});
 cb(ev("task.failed",1));ok=true;cb(ev("task.progress",2,"P03","model.pull"));off();assert.deepEqual(out,["loading"]);
});
test("R12-04 throwing native object getter does not escape host callback",()=>{
 let cb,out=[];const off=attachCinemaToNativeEvents({setState:s=>out.push(s)},f=>{cb=f;return()=>{};},{now:()=>t0});
 const bad=new Proxy(ev("task.completed"),{get:(o,k)=>{if(k==="schema")throw Error("MALFORMED");return Reflect.get(o,k);}});
 assert.doesNotThrow(()=>cb(bad));off();assert.deepEqual(out,[]);
});
test("R12-05 failing native clock cannot crash event bus",()=>{
 let cb,out=[];const off=attachCinemaToNativeEvents({setState:s=>out.push(s)},f=>{cb=f;return()=>{};},{now:()=>{throw Error("CLOCK");}});
 assert.doesNotThrow(()=>cb(ev("task.completed")));off();assert.deepEqual(out,[]);
});
test("R12-06 nonfinite native clock cannot bypass event freshness",()=>{
 assert.equal(visualEvent(ev("task.completed"),NaN),null);assert.equal(visualEvent(ev("task.completed"),Infinity),null);
});
test("R12-07 invalid host unsubscribe quarantines registered callback",()=>{
 let cb,out=[];assert.throws(()=>attachCinemaToNativeEvents({setState:s=>out.push(s)},f=>{cb=f;return null;},{now:()=>t0}),/UNSUBSCRIBE/);
 cb(ev("task.completed"));assert.deepEqual(out,[]);
});
test("R12-08 subscribe throw quarantines callback already given to host",()=>{
 let cb,out=[];assert.throws(()=>attachCinemaToNativeEvents({setState:s=>out.push(s)},f=>{cb=f;throw Error("HOST_FAILED");},{now:()=>t0}),/HOST_FAILED/);
 cb(ev("task.completed"));assert.deepEqual(out,[]);
});
test("R12-09 verified success still latches against later progress",()=>{
 let cb,out=[];const off=attachCinemaToNativeEvents({setState:s=>{out.push(s);return true;}},f=>{cb=f;return()=>{};},{now:()=>t0});
 cb(ev("task.completed",2));cb(ev("task.progress",3,"P03","model.pull"));off();assert.deepEqual(out,["success"]);
});
test("R12-10 rejected 41st run does not evict old terminal result",()=>{
 let cb,ok=true,out=[];const off=attachCinemaToNativeEvents({setState:s=>{if(!ok)return false;out.push(s);return true;}},f=>{cb=f;return()=>{};},{now:()=>t0});
 for(let i=1;i<=40;i++)cb({...ev("task.completed",i),run_id:"RUN-"+i});
 ok=false;cb({...ev("task.progress",41,"P03","model.pull"),run_id:"RUN-41"});
 ok=true;cb({...ev("task.progress",42,"P03","model.pull"),run_id:"RUN-1"});
 off();assert.equal(out.length,40);
});
