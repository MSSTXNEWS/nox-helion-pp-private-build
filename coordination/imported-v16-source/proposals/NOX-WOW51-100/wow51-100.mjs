/* NOX WOW 51–100: lightweight CSS motion orchestrator for APPROVED SECONDARY SCENE ONLY.
   Source candidate; no replacement of D02 HOME, no fabricated backend state or telemetry. */
import {CUES,CUE_BY_ID,validateCueCatalog} from "./catalog.mjs";
const SCHEMA="NOX-INSTALLER-EVENT-v3";
const RUN_RE=/^[A-Za-z0-9][A-Za-z0-9._:-]{1,127}$/;
const SHA_RE=/^[a-f0-9]{64}$/i;
const MODES=new Set(["MAX","BALANCED","ECO","REDUCED"]);
const mounted=new WeakMap();
const eventMap=new Map(CUES.filter(c=>c.trigger==="VERIFIED_HOST_EVENT").map(c=>[c.eventType,c.id]));
export function validateVisualEvent(e,now=Date.now(),prev=null){
 if(!e||typeof e!=="object"||e.schema!==SCHEMA||!RUN_RE.test(e.run_id||"")||
    !Number.isSafeInteger(e.event_sequence)||e.event_sequence<0 ||
    !eventMap.has(e.event_type)||e.evidence_verified!==true ||
    !SHA_RE.test(e.receipt_sha256||""))return false;
 const at=Date.parse(e.timestamp_utc||"");
 if(!Number.isFinite(at)||at>now+5000||now-at>30000)return false;
 if(prev&&prev.run===e.run_id&&e.event_sequence<=prev.seq)return false;
 return true;
}
export function createCinematicCues(root,{mode="BALANCED",eventPort=null,reducedMotion=false}={}){
 validateCueCatalog();
 if(!root||root.nodeType!==1||root.dataset?.noxWowSlot!=="secondary"||
   (typeof root.closest==="function"&&root.closest('[data-nox-page="home"]')))
   throw Error("APPROVED_SECONDARY_SLOT_REQUIRED_D02_LOCK");
 if(mounted.has(root))throw Error("WOW_ALREADY_MOUNTED");
 if(!MODES.has(mode))throw Error("UNKNOWN_PERFORMANCE_PROFILE");
 if(eventPort && typeof eventPort.subscribe!=="function")throw Error("TRUSTED_HOST_PORT_REQUIRED");
 const doc=root.ownerDocument||document;
 const surface=doc.createElement("div");
 surface.className="nox-w51-stage";
 surface.setAttribute("aria-hidden","true");
 surface.dataset.cue="";
 const rays=doc.createElement("div");rays.className="nox-w51-rays";
 const veil=doc.createElement("div");veil.className="nox-w51-veil";
 const field=doc.createElement("div");field.className="nox-w51-field";
 surface.append(rays,veil,field);
 root.classList.add("nox-w51-slot");
 root.append(surface);
 let disposed=false,selected=null,last=null,currentMode=mode,unsubscribe=null;
 let reduced=!!reducedMotion;
 const media=doc.defaultView?.matchMedia?.("(prefers-reduced-motion: reduce)")||null;
 function applyReduced(){
   surface.dataset.mode=reduced||!!media?.matches?"REDUCED":currentMode;
 }
 const onMotion=()=>applyReduced();
 media?.addEventListener?.("change",onMotion);
 const onVisibility=()=>{surface.dataset.hidden=doc.hidden?"true":"false"};
 doc.addEventListener?.("visibilitychange",onVisibility);
 applyReduced();onVisibility();
 const label=doc.createElement("output");
 label.className="nox-w51-label";
 label.textContent="SOURCE DEMO — без реальных состояний ИИ";
 label.setAttribute("aria-live","off");
 root.append(label);
 function show(id,tag){
   if(disposed)throw Error("WOW_DESTROYED");
   const cue=CUE_BY_ID.get(id);
   if(!cue)throw Error("UNKNOWN_CINEMATIC_CUE");
   surface.dataset.cue=String(cue.id);
   surface.dataset.family=cue.family;
   surface.dataset.mode=reduced||!!media?.matches?"REDUCED":currentMode;
   surface.dataset.provenance=tag;
   label.textContent=(tag==="DEMO"?"ДЕМО · ":"СОБЫТИЕ · ")+cue.name;
   selected=cue.id;
   return cue;
 }
 function preview(id){return show(id,"DEMO");}
 function activate(id){
   const c=CUE_BY_ID.get(id);
   if(!c)throw Error("UNKNOWN_CINEMATIC_CUE");
   if(c.trigger==="VERIFIED_HOST_EVENT")throw Error("HOST_EVENT_CUE_REQUIRES_EVIDENCE");
   return show(id,"INTERACTION");
 }
 function receiveEvent(evt){
   if(disposed)return false;
   if(!validateVisualEvent(evt,Date.now(),last))return false;
   last={run:evt.run_id,seq:evt.event_sequence};
   show(eventMap.get(evt.event_type),"VERIFIED_EVENT");
   return true;
 }
 if(eventPort){unsubscribe=eventPort.subscribe(receiveEvent);if(unsubscribe!=null&&typeof unsubscribe!=="function")throw Error("INVALID_EVENT_UNSUBSCRIBE");}
 const api=Object.freeze({
   preview,activate,receiveEvent,
   setMode(next){if(disposed)throw Error("WOW_DESTROYED");if(!MODES.has(next))throw Error("UNKNOWN_PERFORMANCE_PROFILE");currentMode=next;applyReduced();},
   setReducedMotion(value){if(disposed)throw Error("WOW_DESTROYED");reduced=value===true;applyReduced();},
   current(){return Object.freeze({cue:selected,mode:surface.dataset.mode,provenance:surface.dataset.provenance||null});},
   destroy(){if(disposed)return;disposed=true;unsubscribe?.();media?.removeEventListener?.("change",onMotion);
     doc.removeEventListener?.("visibilitychange",onVisibility);
     surface.remove();label.remove();root.classList.remove("nox-w51-slot");mounted.delete(root);}
 });
 mounted.set(root,api);
 return api;
}