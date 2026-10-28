/* NOX CINEMA 01/50. Display-only material/event controller for trusted local WebView2.
 * Owns no actual AI/GPU/network functionality, never fabricates sensor progress.
 * Does not touch original D02 HOME, approved art, Persona or native bridge.
 */
const MODES=Object.freeze(["eco","balanced","max","reduced"]);
const STATES=Object.freeze(["running","streaming","training","downloading","completed","paused","error","offline"]);
const NATIVE_SOURCE="NOX_EVENT_V3_VERIFIED";
const RE=/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;

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

export function validateLiveVisualEvent(event,knownRoutes){
  if(!event||event.source!==NATIVE_SOURCE||event.evidenceVerified!==true||
     !RE.test(event.eventId||"")||!RE.test(event.runId||"")||
     !knownRoutes.has(event.routeId)||!STATES.includes(event.state))
    return false;
  if(event.progress!==undefined){
    const p=event.progress;
    if(!p||!Number.isInteger(p.numerator)||!Number.isInteger(p.denominator)||
       p.denominator<1||p.numerator<0||p.numerator>p.denominator)return false;
  }
  return true;
}

export function mountCinematic(root,catalog){
  if(typeof document==="undefined"||!root||root.nodeType!==1||
     !root.classList.contains("nox-pack01")||root.closest('[data-nox-page="home"]')||
     root.dataset.noxPage==="home")throw Error("NOX_CINEMA_SECONDARY_ONLY");
  if(!Array.isArray(catalog?.actions)||catalog.actions.length!==50)throw Error("NOX_CINEMA_50_REQUIRED");
  const actions=catalog.actions,known=new Set(actions.map(x=>x.routeId));
  if(known.size!==50)throw Error("NOX_CINEMA_DUPLICATE_ROUTES");
  const map=new Map(actions.map((a,i)=>[a.routeId,visualPreset(a,i)]));
  const live=new Map();
  const lastIds=new Map();
  let mode="balanced",destroyed=false,paused=false,visible=true;
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

  function decorate(){
    if(destroyed)return;
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

  function applyNativeEvent(event){
    if(destroyed||!validateLiveVisualEvent(event,known))return false;
    const last=lastIds.get(event.routeId);
    if(last===event.eventId)return false;
    lastIds.set(event.routeId,event.eventId);
    live.set(event.routeId,{state:event.state,runId:event.runId,progress:event.progress||null});
    decorate();
    return true;
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
    live.clear();lastIds.clear();
  }
  return Object.freeze({decorate,applyNativeEvent,setMode,snapshot,destroy});
}
