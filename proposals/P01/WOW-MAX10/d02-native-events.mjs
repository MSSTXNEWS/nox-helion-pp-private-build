/* E01 D02 native visual adapter. A SINGLE subscription to the existing host.
 * No browser input can set running/training and no new event producer is created.
 * Unknown CoreIDs, stale/forged/replayed receipts and missing host => HOLD.
 */
import {translateNativeEvent} from "../../NOX-WOW-UNIFIED-1-150/gate.mjs";

const VALID_ID=/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const CUE_STATE=Object.freeze({
  81:"loading", 85:"loading", 86:"success", 87:"training", 89:"stopped"
});
export function createD02NativeVisualBus(hostPort,fx,coreIds,options={}){
  const now=options.now??Date.now;
  const schedule=options.schedule??setTimeout;
  const cancel=options.cancel??clearTimeout;
  if(typeof hostPort?.subscribeNative!=="function" ||
     typeof fx?.setState!=="function" ||
     !Array.isArray(coreIds)||coreIds.length!==8 ||
     new Set(coreIds).size!==8||coreIds.some(id=>typeof id!=="string"||
       !VALID_ID.test(id)||id==="HELION")||
     [now,schedule,cancel].some(fn=>typeof fn!=="function"))
    throw Error("D02_NATIVE_SOURCE_AND_EIGHT_CORES_REQUIRED");
  const valid=new Set(["HELION",...coreIds]);
  const observers=new Set(),lastRunSequence=new Map(),stateByCore=new Map(),timers=new Map();
  let detached=false,accepted=0;
  const resetCore=(core)=>{
    const current=stateByCore.get(core);
    if(!current||detached)return;
    fx.setState("idle",null,core==="HELION"?null:core);
    stateByCore.delete(core);timers.delete(core);
  };
  const onNative=(raw)=>{
    if(detached)return;
    // Admit the ONE genuine native event before notifying ANY visual surface.
    // A decorative observer must never see forged/stale/replayed host messages.
    let mapped;
    try{mapped=translateNativeEvent(raw,now());}catch{return;}
    if(!mapped)return;
    const core=raw.core_id??"HELION";
    if(typeof core!=="string"||!valid.has(core))return;
    const prior=lastRunSequence.get(mapped.runId);
    if(prior!==undefined && mapped.sequence<=prior)return;
    const old=stateByCore.get(core);
    if(old && mapped.timeMs<old.timeMs)return;
    const state=CUE_STATE[mapped.cueId];
    if(!state||fx.setState(state,mapped.runId,core==="HELION"?null:core)!==true)return;
    if(lastRunSequence.size>=64&&!lastRunSequence.has(mapped.runId))
      lastRunSequence.delete(lastRunSequence.keys().next().value);
    lastRunSequence.set(mapped.runId,mapped.sequence);
    // One validated, monotonic event fans out to the existing secondary scene.
    for(const fn of [...observers]){try{fn(raw);}catch{/* isolated panel failure */}}
    if(timers.has(core))cancel(timers.get(core));
    const stamp=Object.freeze({runId:mapped.runId,timeMs:mapped.timeMs,sequence:mapped.sequence});
    stateByCore.set(core,stamp);
    timers.set(core,schedule(()=>{
      if(stateByCore.get(core)===stamp)resetCore(core);
    },30000));
    accepted++;
  };
  const unsubscribe=hostPort.subscribeNative(onNative);
  if(typeof unsubscribe!=="function")
    throw Error("D02_NATIVE_UNSUBSCRIBE_REQUIRED");
  return Object.freeze({
    subscribe(fn){
      if(detached||typeof fn!=="function")throw Error("D02_NATIVE_SUBSCRIBER_REQUIRED");
      observers.add(fn);
      return ()=>{observers.delete(fn);};
    },
    snapshot(){return Object.freeze({coreCount:8,acceptedNativeEvents:accepted,
      activeCoreStates:stateByCore.size,hostIntegrationVerified:false});},
    destroy(){
      if(detached)return;
      detached=true;
      for(const handle of timers.values())cancel(handle);
      timers.clear();stateByCore.clear();lastRunSequence.clear();observers.clear();
      unsubscribe();
    }
  });
}
