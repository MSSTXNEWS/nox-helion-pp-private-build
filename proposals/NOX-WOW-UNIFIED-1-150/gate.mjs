/* NOX V16 / WOW 1–150 single admission seam.
 * Existing CSS cue engine #31 + existing WAAPI director #32; D02 #30 retained.
 * No competing event writer, no GPU worker, no network, no frontend capability grant.
 */
import {CUES,validateCueCatalog} from "../NOX-WOW51-100/catalog.mjs";
import {createCinematicCues} from "../NOX-WOW51-100/wow51-100.mjs";
import {SHOTS,validateShots} from "../NOX-WOW101-150/catalog.mjs";
import {mountDirector} from "../NOX-WOW101-150/director.mjs";
import {COMPOSITIONS,COMPOSITION_BY_ID,verifyCompositions} from "../NOX-WOW151-200/catalog.mjs";

const SCHEMA="NOX-INSTALLER-EVENT-v3";
const EVENTS=new Set(["task.started","task.progress","training.step","checkpoint.saved",
  "task.completed","task.failed","model.stopped","gpu.sample"]);
const ID=/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const SHA=/^[0-9a-f]{64}$/i;
const MODES=new Set(["ECO","BALANCED","MAX","REDUCED"]);
const adopted=new WeakMap();
const hostCueIds=new Set(CUES.filter(x=>x.trigger==="VERIFIED_HOST_EVENT").map(x=>x.id));

/* The source bus does NOT have voice.listening, chat.streaming, training.paused,
 * system.offline, etc. Those cues remain DEMO/HOLD until a canonical approved
 * producer exists. Never change event_type in the real events.v3 log.
 */
export function translateNativeEvent(raw,now=Date.now()){
  if(!raw || typeof raw!=="object" || raw.schema!==SCHEMA ||
    raw.evidence_verified!==true || !EVENTS.has(raw.event_type) ||
    typeof raw.run_id!=="string" || !ID.test(raw.run_id) ||
    typeof raw.event_id!=="string" || !ID.test(raw.event_id) ||
    typeof raw.task_id!=="string" || !ID.test(raw.task_id) ||
    typeof raw.action_id!=="string" || !ID.test(raw.action_id) ||
    !["P01","P02","P03","P04","P05","E06"].includes(raw.package_id) ||
    !Number.isSafeInteger(raw.event_sequence) || raw.event_sequence<1 ||
    typeof raw.receipt_sha256!=="string" || !SHA.test(raw.receipt_sha256) ||
    typeof raw.timestamp_utc!=="string" ||
    !Number.isFinite(now))return null;
  const t=Date.parse(raw.timestamp_utc);
  if(!Number.isFinite(t)||t>now+5000||now-t>30000)return null;
  if(raw.numerator!==undefined && raw.numerator!==null){
    if(!Number.isSafeInteger(raw.numerator) || raw.numerator<0 ||
       !Number.isSafeInteger(raw.denominator) || raw.denominator<1 ||
       raw.numerator>raw.denominator)return null;
  }
  // Select only direct semantically justified mappings:
  let cue=null,syntheticPresentationType=null;
  if(raw.event_type==="task.started"){cue=81;syntheticPresentationType="task.started";}
  else if(raw.package_id==="P03" && raw.event_type==="task.progress" &&
    /^(pull|download|model[._-](?:pull|download))/.test(raw.action_id)){
    cue=85;syntheticPresentationType="models.downloading";
  }
  else if(raw.package_id==="P04" &&
    (raw.event_type==="training.step"||raw.event_type==="checkpoint.saved")){
    cue=87;syntheticPresentationType="training.step";
  }
  else if(raw.event_type==="model.stopped" &&
    (raw.package_id==="P03"||raw.package_id==="P04")){
    cue=89;syntheticPresentationType="task.stopped";
  }
  else if(raw.package_id==="P04" && raw.event_type==="task.completed" &&
    /^(rag[._-](?:index|ingest|reindex))/.test(raw.action_id)){
    cue=86;syntheticPresentationType="rag.indexed";
  }
  if(!hostCueIds.has(cue))return null;
  // This object goes ONLY into the existing visual component's receiveEvent;
  // the canonical native event remains immutable and retains its real type.
  const presentation=Object.freeze({...raw,event_type:syntheticPresentationType});
  return Object.freeze({cueId:cue,runId:raw.run_id,sequence:raw.event_sequence,
    eventId:raw.event_id,timeMs:t,presentation});
}

export function reviewWowScopes(pack01=null){
  validateCueCatalog();validateShots();verifyCompositions();
  const groups=Object.freeze({
    uiFirst50:pack01===null?0:50,
    materialsAndAtmosphere51to100:CUES.length,
    director101to150:SHOTS.length,
    cinematicFinale151to200:COMPOSITIONS.length,
    aggregate:pack01===null?150:200
  });
  if(pack01!==null){
    if(!Array.isArray(pack01?.actions)||pack01.actions.length!==50||
       new Set(pack01.actions.map(x=>x.routeId)).size!==50)
       throw Error("PACK01_ROUTE_IDENTITY_REQUIRED");
  }
  return Object.freeze({groups,hostDrivenAvailable:
    Object.freeze([81,85,86,87,89]),
    hostDrivenHold:Object.freeze([82,83,84,88,90]),
    externalUiPrerequisite:pack01===null,
    notEquivalentToAcceptedExe:true});
}

export function mountUnifiedCinema(root,{mode="BALANCED",trustedEventPort=null,
  nativeAuthorizeShot=null,nativeAuthorizeComposition=null,
  reducedMotion=false,now=()=>Date.now()}={}){
  reviewWowScopes();
  if(!root||root.nodeType!==1||root.dataset?.noxWowSlot!=="secondary"||
     root.closest?.('[data-nox-page="home"]')||
     typeof now!=="function"||!MODES.has(mode)||
     (trustedEventPort!==null&&typeof trustedEventPort.subscribe!=="function")||
     (nativeAuthorizeShot!==null&&typeof nativeAuthorizeShot!=="function")||
     (nativeAuthorizeComposition!==null&&typeof nativeAuthorizeComposition!=="function"))
    throw Error("NOX_UNIFIED_SECONDARY_TRUSTED_SLOT_REQUIRED");
  if(adopted.has(root)||root.classList?.contains?.("nox-finale-scope")||
     root.classList?.contains?.("nox-unified-wow"))
    throw Error("NOX_UNIFIED_DUPLICATE_MOUNT");
  // Do not force additional 3D layers onto D02 or existing PACK01.
  let cues=null,director=null,unsubscribe=null,disposed=false,selected=null;
  const lastByRun=new Map();
  try {
    cues=createCinematicCues(root,{mode,reducedMotion});
    director=mountDirector(root,{mode,reducedMotion,authorize:nativeAuthorizeShot});
    root.classList.add("nox-unified-wow");
    root.dataset.unifiedWow="none";
    root.dataset.noxWowEvidence="none";
    function choose(group){
      root.dataset.unifiedWow=group;
      // Director has 3 WAAPI tracks; cancel when cue layer takes focus.
      if(group==="cue")director.setReducedMotion(true);
      else director.setReducedMotion(reducedMotion);
    }
    function receiveCanonicalEvent(raw){
      if(disposed)return false;
      const mapped=translateNativeEvent(raw,now());
      if(!mapped)return false;
      const previous=lastByRun.get(mapped.runId);
      if(previous && (mapped.sequence<previous.seq ||
        (mapped.sequence===previous.seq)))return false;
      if(lastByRun.size>=64&&!lastByRun.has(mapped.runId))
        lastByRun.delete(lastByRun.keys().next().value);
      // Current time must match original visual engine's own 30s gate.
      if(!cues.receiveEvent(mapped.presentation))return false;
      lastByRun.set(mapped.runId,{seq:mapped.sequence,id:mapped.eventId});
      choose("cue");
      root.dataset.noxWowEvidence="trusted-native-v3";
      delete root.dataset.noxWowComposition;
      selected=mapped.cueId;
      return true;
    }
    if(trustedEventPort){
      unsubscribe=trustedEventPort.subscribe(receiveCanonicalEvent);
      if(typeof unsubscribe!=="function")
        throw Error("NOX_NATIVE_EVENT_UNSUBSCRIBE_REQUIRED");
    }
    const api=Object.freeze({
      preview(id){
        if(disposed)throw Error("NOX_UNIFIED_DISPOSED");
        if(Number.isInteger(id)&&id>=51&&id<=100){
          const out=cues.preview(id);choose("cue");selected=id;
          root.dataset.noxWowEvidence="demo";delete root.dataset.noxWowComposition;
          return out;
        }
        if(Number.isInteger(id)&&id>=101&&id<=150){
          choose("director");
          const out=director.preview(id);selected=id;
          root.dataset.noxWowEvidence="demo";delete root.dataset.noxWowComposition;
          return out;
        }
        if(Number.isInteger(id)&&id>=151&&id<=200){
          const item=COMPOSITION_BY_ID.get(id);
          if(!item)throw Error("UNKNOWN_COMPOSITION");
          // The SAME two components already mounted above. No third engine or scheduler.
          cues.preview(item.opticalId);director.preview(item.directorId);
          choose("composition");selected=id;
          root.dataset.noxWowComposition=String(id);
          root.dataset.noxWowEvidence="demo";
          return item;
        }
        throw Error("UNKNOWN_WOW_51_200");
      },
      activateApprovedShot(id){
        if(disposed)throw Error("NOX_UNIFIED_DISPOSED");
        if(!Number.isInteger(id)||id<101||id>150)
          throw Error("APPROVED_SHOT_101_150_ONLY");
        // Existing director independently enforces trusted host authorization.
        // Do not change current source/selected cue when host denies it.
        const prev=root.dataset.unifiedWow;
        director.setReducedMotion(reducedMotion);
        let shot;
        try {shot=director.activate(id);}
        catch(err){if(prev==="cue")director.setReducedMotion(true);throw err;}
        choose("director");selected=id;
        root.dataset.noxWowEvidence="native-shot";delete root.dataset.noxWowComposition;
        return shot;
      },
      activateApprovedComposition(id){
        if(disposed)throw Error("NOX_UNIFIED_DISPOSED");
        const item=COMPOSITION_BY_ID.get(id);
        if(!item)throw Error("APPROVED_COMPOSITION_151_200_ONLY");
        // This callback MUST be supplied by native trusted host, not a page action.
        if(!nativeAuthorizeComposition||nativeAuthorizeComposition(item)!==true)
          throw Error("HOST_COMPOSITION_APPROVAL_REQUIRED");
        cues.preview(item.opticalId);director.preview(item.directorId);
        choose("composition");selected=id;
        root.dataset.noxWowComposition=String(id);
        root.dataset.noxWowEvidence="native-composition";
        return item;
      },
      receiveCanonicalEvent,
      setMode(next){
        if(disposed)throw Error("NOX_UNIFIED_DISPOSED");
        if(!MODES.has(next))throw Error("INVALID_WOW_PROFILE");
        cues.setMode(next);director.setMode(next);
      },
      current:()=>Object.freeze({selected,active:root.dataset.unifiedWow,
        visualEvidence:root.dataset.noxWowEvidence,
        sourceOnly:true,acceptedExe:false,hostRunCount:lastByRun.size}),
      destroy(){
        if(disposed)return;disposed=true;
        try{unsubscribe?.()}finally{
          director?.destroy();cues?.destroy();
          root.classList.remove("nox-unified-wow");
          delete root.dataset.unifiedWow;
          delete root.dataset.noxWowEvidence;
          delete root.dataset.noxWowComposition;
          lastByRun.clear();adopted.delete(root);
        }
      }
    });
    adopted.set(root,api);
    return api;
  }catch(err){
    try{if(typeof unsubscribe==="function")unsubscribe()}finally{
      director?.destroy();cues?.destroy();
      root.classList.remove("nox-unified-wow");
      delete root.dataset.unifiedWow;
      delete root.dataset.noxWowEvidence;
      delete root.dataset.noxWowComposition;
    }
    throw err;
  }
}
