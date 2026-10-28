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
  const when=Date.parse(raw.timestamp_utc);
  // Ignore stale/replayed and future events, but never infer a success from timeout.
  if(!Number.isFinite(when)||when>now+5000||now-when>30000)return null;
  let visual=null;
  switch(raw.event_type){
    case "training.step":
    case "checkpoint.saved":
      if(raw.package_id==="P04") visual="training";
      break;
    case "model.stopped":
      if(raw.package_id==="P04") visual="stopped";
      break;
    case "task.started":
    case "task.progress":
      if(raw.package_id==="P03"&&/^(pull|download|model\.)/.test(raw.action_id))
        visual="loading";
      if(raw.package_id==="P04"&&/^(training|qlora|lora)/.test(raw.action_id))
        visual="training";
      break;
    case "task.completed":visual="success";break;
    case "task.failed":visual="error";break;
    // gpu.sample is a sensor measurement, NEVER a statement that a model trains.
    default:break;
  }
  if(!visual)return null;
  return Object.freeze({state:visual,runId:raw.run_id,
    sequence:raw.event_sequence,timeMs:when,coreId:null});
}
export function attachCinemaToNativeEvents(scene,subscribeNative,{
  now=()=>Date.now()
}={}){
  if(!scene||typeof scene.setState!=="function"||
    typeof subscribeNative!=="function"||
    typeof now!=="function")throw Error("NOX_CINEMA_NATIVE_HOST_REQUIRED");
  let closed=false;const latestByRun=new Map();
  const un=subscribeNative(raw=>{
    if(closed)return;
    const visual=visualEvent(raw,now());
    if(!visual)return;
    const last=latestByRun.get(visual.runId)||0;
    if(visual.sequence<=last)return;
    // No unbounded historical run cache: only 40 active/recent entries retained.
    if(latestByRun.size>=40 && !latestByRun.has(visual.runId))
      latestByRun.delete(latestByRun.keys().next().value);
    latestByRun.set(visual.runId,visual.sequence);
    scene.setState(visual.state,visual.runId);
  });
  if(typeof un!=="function")throw Error("NOX_CINEMA_NEEDS_HOST_UNSUBSCRIBE");
  return ()=>{if(closed)return;closed=true;latestByRun.clear();un();};
}
