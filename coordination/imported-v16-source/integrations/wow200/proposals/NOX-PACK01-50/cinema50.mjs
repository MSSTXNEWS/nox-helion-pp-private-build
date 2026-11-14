/* NOX CINEMA 01/50. Display-only material/event controller for trusted local WebView2.
 * Owns no actual AI/GPU/network functionality, never fabricates sensor progress.
 * Does not touch original D02 HOME, approved art, Persona or native bridge.
 */
import {admitNativeVisualEvent} from "./cinema50-events.mjs";
const MODES=Object.freeze(["eco","balanced","max","reduced"]);

export function visualPreset(action,index){
  if(!action||!["chat","models","learning","voice","space"].includes(action.category)||
     !/^[a-z][a-z0-9]*(?:[._][a-z0-9]+)*$/.test(action.routeId)||
     !Number.isInteger(index)||index<0||index>49)throw Error("NOX_CINEMA_INVALID_ROUTE");
  return Object.freeze({
    domain:action.category,
    delay:"-"+(((index*7)%23)/10)+"s",
    cycle:(8+(index%5))+"s",
    material:["obsidian","titanium","ember","smoked-glass","liquid-metal"][index%5]
  });
}

// Backward-compatible legacy validator: the original source/evidence boolean
// was writable by any in-page script and must NOT be treated as native proof.
export function validateLiveVisualEvent(_legacyEvent,_knownRoutes){return false;}

export function mountCinematic(root,catalog,{subscribeVerifiedNative=null,now=()=>Date.now()}={}){
  if(typeof document==="undefined"||!root||root.nodeType!==1||
     !root.classList.contains("nox-pack01")||root.closest('[data-nox-page="home"]')||
     root.dataset.noxPage==="home")throw Error("NOX_CINEMA_SECONDARY_ONLY");
  if(!Array.isArray(catalog?.actions)||catalog.actions.length!==50)throw Error("NOX_CINEMA_50_REQUIRED");
  if(subscribeVerifiedNative!==null&&typeof subscribeVerifiedNative!=="function")
    throw Error("NOX_NATIVE_SUBSCRIPTION_MUST_BE_HOST_BOUND");
  if(typeof now!=="function")throw Error("NOX_CLOCK_REQUIRED");
  const actions=catalog.actions,known=new Set(actions.map(x=>x.routeId));
  if(known.size!==50)throw Error("NOX_CINEMA_DUPLICATE_ROUTES");
  const map=new Map(actions.map((a,i)=>[a.routeId,visualPreset(a,i)]));
  const live=new Map();
  const lastIds=new Map();
  let mode="balanced",destroyed=false,paused=false,visible=true,unsubscribe=null,expiryTimer=null;
  const lastSequenceByRun=new Map();
  const motion=typeof window!=="undefined"&&window.matchMedia?.("(prefers-reduced-motion: reduce)");
  const onReduced=()=>{root.dataset.cinemaMode=motion?.matches?"reduced":mode;};
  const onVisibility=()=>{visible=!document.hidden;root.dataset.cinemaPaused=String(!visible||paused)};
  const viewport=typeof IntersectionObserver==="function"?new IntersectionObserver(entries=>{
    paused=!entries.some(e=>e.isIntersecting);onVisibility();
  },{threshold:0}):null;
  if(viewport)viewport.observe(root);
  if(motion?.addEventListener)motion.addEventListener("change",onReduced);
  document.addEventListener("visibilitychange",onVisibility,{passive:true});
  root.dataset.cinemaReady="true";
  onReduced();onVisibility();

  function expireVisuals(){
    const time=now();
    for(const [route,value] of live)if(value.expires<=time)live.delete(route);
  }
  function scheduleExpiry(){
    if(expiryTimer!==null){clearTimeout(expiryTimer);expiryTimer=null;}
    if(destroyed||live.size===0)return;
    const next=Math.min(...[...live.values()].map(x=>x.expires));
    expiryTimer=setTimeout(()=>{
      expiryTimer=null;expireVisuals();decorate();scheduleExpiry();
    },Math.max(1,Math.min(30001,next-now()+1)));
  }
  function decorate(){
    if(destroyed)return;
    expireVisuals();
    for(const card of root.querySelectorAll(".nox-pack01__tile")){
      const preset=map.get(card.dataset.routeId);
      if(!preset)continue;
      card.dataset.cinemaDomain=preset.domain;
      card.dataset.cinemaMaterial=preset.material;
      card.style.setProperty("--cinema-delay",preset.delay);
      card.style.setProperty("--cinema-cycle",preset.cycle);
      // Native route capability remains the authority to display live state.
      if(!["CONNECTED","VERIFIED"].includes(card.dataset.state)){
        card.removeAttribute("data-cinema-live");continue;
      }
      const last=live.get(card.dataset.routeId);
      if(last)card.dataset.cinemaLive=last.state;
      else card.removeAttribute("data-cinema-live");
    }
  }

  // In-page calls cannot confer native authentication; use only a host-owned
  // subscription that validated the producer, session, receipt and route ownership.
  function applyNativeEvent(_untrustedEvent){return false;}
  function receiveVerifiedNativePacket(packet){
    if(destroyed)return false;
    const event=admitNativeVisualEvent(packet,catalog,{now:now()});
    if(!event||!known.has(event.routeId))return false;
    const last=lastSequenceByRun.get(event.runId);
    if(last!==undefined&&event.sequence<=last)return false;
    if(lastSequenceByRun.size>=64&&!lastSequenceByRun.has(event.runId))
      lastSequenceByRun.delete(lastSequenceByRun.keys().next().value);
    lastSequenceByRun.set(event.runId,event.sequence);
    lastIds.set(event.routeId,event.eventId);
    live.set(event.routeId,event);
    decorate();scheduleExpiry();return true;
  }
  if(subscribeVerifiedNative!==null){
    try{
      unsubscribe=subscribeVerifiedNative(receiveVerifiedNativePacket);
      if(typeof unsubscribe!=="function")throw Error("NOX_NATIVE_UNSUBSCRIBE_REQUIRED");
    }catch(err){if(typeof unsubscribe==="function")unsubscribe();
      document.removeEventListener("visibilitychange",onVisibility);
      if(motion?.removeEventListener)motion.removeEventListener("change",onReduced);
      if(viewport)viewport.disconnect();
      if(expiryTimer!==null){clearTimeout(expiryTimer);expiryTimer=null;}
      live.clear();lastIds.clear();lastSequenceByRun.clear();
      root.removeAttribute("data-cinema-ready");
      root.removeAttribute("data-cinema-mode");
      root.removeAttribute("data-cinema-paused");
      throw err;
    }
  }

  function setMode(value){
    if(destroyed||!MODES.includes(value))return false;
    mode=value;onReduced();return true;
  }

  function snapshot(){
    return Object.freeze({routes:50,mode:root.dataset.cinemaMode,
      visualEvents:live.size,hostAcceptance:"UNVERIFIED_BY_VISUAL_LAYER"});
  }

  function destroy(){
    if(destroyed)return;
    destroyed=true;
    document.removeEventListener("visibilitychange",onVisibility);
    if(motion?.removeEventListener)motion.removeEventListener("change",onReduced);
    if(viewport)viewport.disconnect();
    for(const card of root.querySelectorAll(".nox-pack01__tile")){
      card.removeAttribute("data-cinema-domain");
      card.removeAttribute("data-cinema-material");
      card.removeAttribute("data-cinema-live");
      card.style.removeProperty("--cinema-delay");
      card.style.removeProperty("--cinema-cycle");
    }
    root.removeAttribute("data-cinema-ready");
    root.removeAttribute("data-cinema-mode");
    root.removeAttribute("data-cinema-paused");
    if(expiryTimer!==null){clearTimeout(expiryTimer);expiryTimer=null;}
    if(unsubscribe){unsubscribe();unsubscribe=null;}
    live.clear();lastIds.clear();lastSequenceByRun.clear();
  }
  return Object.freeze({decorate,applyNativeEvent,setMode,snapshot,destroy,
    nativeSubscriptionActive:()=>unsubscribe!==null});
}
