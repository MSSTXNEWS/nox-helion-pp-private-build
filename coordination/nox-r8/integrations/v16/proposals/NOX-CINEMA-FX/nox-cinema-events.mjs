/*
 * NOX HELION · CINEMA FX bridge to the ALREADY EXISTING events.v3 bus.
 * Only the trusted WPF/WebView2 host supplies subscribeNative().
 * No second event writer/bus, no new routes or accessibility changes.
 * This bridge changes decorative visual states ONLY. It never changes
 * training status/percent, models, progress, security flags or data.
 */
const SCHEMA="NOX-INSTALLER-EVENT-v3";
const allowed=new Set(["task.started","task.progress","training.step",
   "checkpoint.saved","task.completed","task.failed","model.stopped","gpu.sample"]);
const id=/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
export function visualEvent(raw,now=Date.now()){
  if(!raw||typeof raw!=="object"||raw.schema!==SCHEMA ||
    typeof raw.run_id!=="string"||!id.test(raw.run_id) ||
    typeof raw.event_id!=="string"||!id.test(raw.event_id) ||
    !Number.isSafeInteger(raw.event_sequence)||raw.event_sequence<1 ||
    !allowed.has(raw.event_type) ||
    typeof raw.package_id!=="string"||
    typeof raw.action_id!=="string" ||
    typeof raw.state!=="string" ||
    typeof raw.timestamp_utc!=="string")return null;
  if(!Number.isFinite(now))return null;
  const when=Date.parse(raw.timestamp_utc);
  // Ignore stale/replayed and future events, but never infer a success from timeout.
  if(!Number.isFinite(when)||when>now+5000||now-when>30000)return null;
  // R11: native terminal event_type cannot contradict state or evidence.
  const nativeState=raw.state.toUpperCase();
  const active=new Set(["RUNNING","STARTED","IN_PROGRESS","PROGRESS"]);
  const success=new Set(["COMPLETED","SUCCESS","SUCCEEDED"]);
  const failed=new Set(["FAILED","ERROR"]);
  const stopped=new Set(["STOPPED","CANCELLED","CANCELED"]);
  const terminal=raw.event_type==="task.completed"||
    raw.event_type==="task.failed"||raw.event_type==="model.stopped";
  if(terminal&&raw.evidence_verified!==true)return null;
  let visual=null;
  switch(raw.event_type){
    case "training.step":
    case "checkpoint.saved":
      if(raw.package_id==="P04"&&active.has(nativeState)) visual="training";
      break;
    case "model.stopped":
      if(raw.package_id==="P04"&&stopped.has(nativeState)) visual="stopped";
      break;
    case "task.started":
    case "task.progress":
      if(!active.has(nativeState))break;
      if(raw.package_id==="P03"&&/^(pull|download|model\.)/.test(raw.action_id))
        visual="loading";
      if(raw.package_id==="P04"&&/^(training|qlora|lora)/.test(raw.action_id))
        visual="training";
      break;
    case "task.completed":
      if(success.has(nativeState))visual="success";
      break;
    case "task.failed":
      if(failed.has(nativeState))visual="error";
      break;
    // GPU sensor samples never imply learning.
    default:break;
  }
  if(!visual)return null;
  return Object.freeze({state:visual,runId:raw.run_id,
    sequence:raw.event_sequence,timeMs:when,coreId:null,terminal});
}
export function attachCinemaToNativeEvents(scene,subscribeNative,{
  now=()=>Date.now()
}={}){
  if(!scene||typeof scene.setState!=="function"||
    typeof subscribeNative!=="function"||
    typeof now!=="function")throw Error("NOX_CINEMA_NATIVE_HOST_REQUIRED");
  let closed=false;const latestByRun=new Map();
  const onNative=raw=>{
    if(closed)return;
    let visual;
    // R12: malformed host envelope/clock never crashes an existing native event bus.
    try{visual=visualEvent(raw,now());}catch(_){return;}
    if(!visual)return;
    const last=latestByRun.get(visual.runId);
    if(last&&(visual.sequence<=last.sequence||last.terminal))return;
    // R12: an event is consumed only after the existing D02 renderer accepts it.
    try{if(scene.setState(visual.state,visual.runId)!==true)return;}
    catch(_){return;}
    // No eviction on rejected/failed render; 40-entry bound is unchanged.
    if(latestByRun.size>=40&&!latestByRun.has(visual.runId))
      latestByRun.delete(latestByRun.keys().next().value);
    latestByRun.set(visual.runId,{sequence:visual.sequence,terminal:visual.terminal});
  };
  let un;
  try{un=subscribeNative(onNative);}
  catch(error){closed=true;latestByRun.clear();throw error;}
  if(typeof un!=="function"){
    // A host that violates unsubscribe cannot keep a live orphaned FX callback.
    closed=true;latestByRun.clear();
    throw Error("NOX_CINEMA_NEEDS_HOST_UNSUBSCRIBE");
  }
  return ()=>{if(closed)return;closed=true;latestByRun.clear();un();};
}
