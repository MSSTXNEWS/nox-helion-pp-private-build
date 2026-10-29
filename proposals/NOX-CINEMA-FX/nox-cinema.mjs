/*
 * NOX HELION · CINEMA FX gravity / obsidian renderer, V16.
 * This module decorates ONLY the approved existing nine D02 sphere elements.
 * It never replaces HOME, menu, persona photos or a host feature.
 * No dependencies, network, storage, model downloads or privileged commands.
 * Cinematic ejecta is decorative. Backend/learning telemetry is NEVER fabricated.
 */
const CORE_COUNT=8;
export const STATES=Object.freeze([
  "idle","thinking","streaming","speaking","loading","training",
  "paused","stopped","success","error","offline"
]);
export const PROFILES=Object.freeze({
  ECO:Object.freeze({fps:12,maxParticles:3,minimumBurstMs:32000,maximumBurstMs:52000}),
  BALANCED:Object.freeze({fps:24,maxParticles:12,minimumBurstMs:18000,maximumBurstMs:35000}),
  MAX:Object.freeze({fps:30,maxParticles:24,minimumBurstMs:10000,maximumBurstMs:22000}),
  REDUCED:Object.freeze({fps:0,maxParticles:0,minimumBurstMs:Infinity,maximumBurstMs:Infinity})
});
const stateSet=new Set(STATES);
const profileSet=new Set(Object.keys(PROFILES));
const pattern=/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const mounted=new WeakMap();
const SVG_NS="http://www.w3.org/2000/svg";
export function clamp(value,min,max){
  if(!Number.isFinite(value))return min;
  return Math.max(min,Math.min(max,value));
}
export function validateScene(orbs){
  if(!Array.isArray(orbs)||orbs.length!==CORE_COUNT+1)
    throw new Error("NOX_FX_REQUIRES_HELION_PLUS_EIGHT_CORES");
  const ids=orbs.map(x=>x?.id);
  if(ids[0]!=="HELION"||new Set(ids).size!==CORE_COUNT+1||
     ids.slice(1).some(x=>typeof x!=="string"||!pattern.test(x)))
    throw new Error("NOX_FX_INVALID_CANONICAL_CORE_IDS");
  if(orbs.some(x=>!x?.element||x.element.nodeType!==1))
    throw new Error("NOX_FX_MISSING_ORB_ELEMENTS");
  if(new Set(orbs.map(x=>x.element)).size!==CORE_COUNT+1)
    throw new Error("NOX_FX_DUPLICATE_ORB_ELEMENTS");
  return true;
}
export function profileFor(mode,reduced){
  if(!profileSet.has(mode))throw new Error("NOX_FX_INVALID_PROFILE");
  return PROFILES[reduced?"REDUCED":mode];
}
// Burst outward, slow near the apex, and return to the point of emergence.
// It is a designed visual cue, not a claim of astronomical simulation.
export function gravitationalSample(p,timeMs){
  if(!p||!Number.isFinite(timeMs)||
     ["started","duration","surfaceRadius","reach","swirl","angle","brightness","rotation"].some(k=>!Number.isFinite(p[k]))||
     p.duration<=0||p.surfaceRadius<0||p.surfaceRadius>200||
     p.reach<0||p.reach>200||Math.abs(p.swirl)>200||
     Math.abs(p.angle)>Math.PI*20000||
     Math.abs(p.rotation)>360||p.brightness<0||p.brightness>1)
    throw new Error("NOX_FX_INVALID_PARTICLE");
  // R09: reject overflowing timestamps before DOM/SVG formatting.
  const elapsed=timeMs-p.started;
  if(!Number.isFinite(elapsed)||!Number.isFinite(elapsed/p.duration))
    throw new Error("NOX_FX_INVALID_PARTICLE");
  const t=clamp(elapsed/p.duration,0,1);
  const arc=Math.sin(Math.PI*t);
  const radius=p.surfaceRadius+arc*p.reach;
  const sideways=p.swirl*arc*Math.cos(Math.PI*t);
  const angle=p.angle;
  const x=100+Math.cos(angle)*radius-Math.sin(angle)*sideways;
  const y=100+Math.sin(angle)*radius+Math.cos(angle)*sideways;
  const opacity=(t<=0||t>=1)?0:clamp(Math.pow(arc,.6)*p.brightness,0,1);
  const visualAngle=t*320+p.rotation;
  if(![x,y,radius,sideways,opacity,visualAngle].every(Number.isFinite))
    throw new Error("NOX_FX_INVALID_PARTICLE");
  return {x,y,opacity,angle:visualAngle,done:t>=1,t,radius};
}
function svgElement(doc,name,attributes={}){
  const el=doc.createElementNS(SVG_NS,name);
  for(const [key,value] of Object.entries(attributes))el.setAttribute(key,String(value));
  return el;
}
function layer(doc,cls){
  const e=doc.createElement("div");e.className=cls;
  return e;
}
export function installNoxCinemaFX({root,orbs,controls=[],panels=[],profile="BALANCED",
  hostEvents=null,random=Math.random,clock=null}={}){
  validateScene(orbs);
  if(!root||root.nodeType!==1)throw new Error("NOX_FX_TRUSTED_ROOT_REQUIRED");
  if(mounted.has(root))throw new Error("NOX_FX_ALREADY_MOUNTED");
  if(root.classList.contains("nox-cinema-scope")||
     ["noxFxMode","noxFxState","noxFxVisible"].some(k=>Object.prototype.hasOwnProperty.call(root.dataset,k))||
     orbs.some(x=>Object.prototype.hasOwnProperty.call(x.element.dataset,"noxFxState")))
    throw new Error("NOX_FX_OWNERSHIP_COLLISION");
  if(!profileSet.has(profile)||typeof random!=="function")
    throw new Error("NOX_FX_INVALID_OPTIONS");
  const doc=root.ownerDocument;
  const win=doc.defaultView;
  if(!win||typeof win.requestAnimationFrame!=="function")
    throw new Error("NOX_FX_ANIMATION_HOST_REQUIRED");
  if(hostEvents && (typeof hostEvents.subscribe!=="function"))
    throw new Error("NOX_FX_INVALID_EVENT_SOURCE");
  if(orbs.some(x=>!root.contains(x.element)||x.element.querySelector(".nox-cinema-orb__layers")))
    throw new Error("NOX_FX_ORB_OUTSIDE_HOST_OR_ALREADY_DECORATED");
  if(!Array.isArray(controls)||!Array.isArray(panels)||
     [...controls,...panels].some(e=>!e||e.nodeType!==1||!root.contains(e)))
    throw new Error("NOX_FX_INVALID_DECORATION_PREFLIGHT");
  // R08-01/02: fail closed before creating any decorative DOM.
  if(clock!==null&&typeof clock!=="function")throw new Error("NOX_FX_INVALID_CLOCK");
  const time=clock||(()=>win.performance.now());
  let initialNow;
  try{initialNow=time();}catch(_){throw new Error("NOX_FX_INVALID_CLOCK");}
  if(!Number.isFinite(initialNow)||initialNow<0)throw new Error("NOX_FX_INVALID_CLOCK");
  const motion=typeof win.matchMedia==="function"?
    win.matchMedia("(prefers-reduced-motion: reduce)"):null;
  let preference=!!motion?.matches;
  let mode=profile;
  let disposed=false,hostVisible=true,intersectVisible=true,raf=null,lastFrame=0,frameCount=0;
  let state="idle",stateRunId=null,emissions=0,particleCount=0;
  let ownerRoot=false;
  const decorated=[];
  const particles=[];
  function unitRandom(){let v;try{v=random();}catch(_){return .5;}
    return typeof v==="number"&&Number.isFinite(v)&&v>=0&&v<1?v:.5;}
  // R08-03..05: decorator transaction preserving original D02 nodes.
  const each=[];
  function undoOwnedDom(){
    for(const orb of each){
      try{orb.layers.remove();}catch(_){}
      delete orb.element.dataset.noxFxState;
    }
    for(const item of decorated){
      if(item.added)try{item.element.classList.remove(item.cls);}catch(_){}
    }
    if(ownerRoot){
      try{root.classList.remove("nox-cinema-scope");}catch(_){}
      delete root.dataset.noxFxMode;
      delete root.dataset.noxFxState;
      delete root.dataset.noxFxVisible;
      ownerRoot=false;
    }
  }
  function constructOrbs(){
    orbs.forEach((entry,index)=>{
      const element=entry.element;
      if(!root.contains(element)||element.querySelector(".nox-cinema-orb__layers"))
        throw new Error("NOX_FX_DUPLICATE_OR_OUTSIDE_ORB");
      const layers=layer(doc,"nox-cinema-orb__layers");
      for(const name of ["lava","filaments","crust","corona","rim"])
        layers.appendChild(layer(doc,"nox-cinema-orb__"+name));
      const svg=svgElement(doc,"svg",{
        class:"nox-cinema-orb__ejecta",viewBox:"0 0 200 200",
        "aria-hidden":"true",focusable:"false"
      });
      layers.appendChild(svg);
      const added=!element.classList.contains("nox-cinema-orb");
      const shape={id:entry.id,element,layers,svg,index,
        nextBurst:initialNow+4500+unitRandom()*18000};
      each.push(shape);
      decorated.push({element,cls:"nox-cinema-orb",added});
      if(added)element.classList.add("nox-cinema-orb");
      element.dataset.noxFxState="idle";
      element.appendChild(layers);
    });
  }
  function decorate(items,cls){
    if(!Array.isArray(items))throw new Error("NOX_FX_DECORATION_LIST");
    for(const e of items){
      if(!e||e.nodeType!==1||!root.contains(e))continue;
      // Buttons and panels remain original controls. Only cosmetic classes added.
      const added=!e.classList.contains(cls);
      if(added)e.classList.add(cls);
      decorated.push({element:e,cls,added});
    }
  }
  try{
    constructOrbs();
    decorate(controls,"nox-cinema-control");
    decorate(panels,"nox-cinema-panel");
    root.classList.add("nox-cinema-scope");ownerRoot=true;
    root.dataset.noxFxMode=(preference?"REDUCED":mode).toLowerCase();
    root.dataset.noxFxVisible="true";
    root.dataset.noxFxState=state;
  }catch(error){undoOwnedDom();throw error;}
  function clearParticles(){
    for(const p of particles){p.node.remove();}
    particles.length=0;particleCount=0;
  }
  function nextDelay(policy){return policy.minimumBurstMs+
    unitRandom()*(policy.maximumBurstMs-policy.minimumBurstMs);}
  function makeParticle(orb,now){
    const angle=2*Math.PI*unitRandom();
    const size=clamp(.65+unitRandom()*1.85,.6,2.5);
    const node=svgElement(doc,"path",{d:"M "+(-size)+" 0 L 0 "+(-size*.42)+
      " L "+size+" 0 L 0 "+(size*.42)+" Z",
      fill:unitRandom()<.23?"#323032":"#c57244",
      opacity:"0"});
    orb.svg.appendChild(node);
    const p={node,started:now,duration:2200+unitRandom()*1900,
      surfaceRadius:86+unitRandom()*6,reach:(orb.index===0?16:8)+unitRandom()*(orb.index===0?29:20),
      angle,swirl:(unitRandom()-.5)*17,brightness:.48+unitRandom()*.42,
      rotation:unitRandom()*360};
    particles.push(p);particleCount++;emissions++;
  }
  function loop(now){
    raf=null;
    // Browser clocks may be malformed; fail closed without emitting SVG NaN.
    if(!Number.isFinite(now)||now<0){sleep();return;}
    if(disposed||!hostVisible||!intersectVisible||doc.hidden)return;
    const policy=profileFor(mode,preference);
    if(policy.fps===0){clearParticles();return;}
    raf=win.requestAnimationFrame(loop);
    if(now-lastFrame<1000/policy.fps)return;
    lastFrame=now;frameCount++;
    for(let i=particles.length-1;i>=0;i--){
      const p=particles[i],position=gravitationalSample(p,now);
      if(position.done){p.node.remove();particles.splice(i,1);particleCount--;continue;}
      p.node.setAttribute("transform","translate("+position.x.toFixed(2)+" "+
        position.y.toFixed(2)+") rotate("+(position.angle|0)+")");
      p.node.setAttribute("opacity",position.opacity.toFixed(2));
    }
    for(const orb of each){
      if(now<orb.nextBurst)continue;
      orb.nextBurst=now+nextDelay(policy)*(orb.index===0?1:2.1);
      if(particleCount>=policy.maxParticles)continue;
      if(orb.index!==0 && unitRandom()>.38)continue;
      const count=orb.index===0?2:1;
      for(let i=0;i<count&&particleCount<policy.maxParticles;i++)makeParticle(orb,now);
    }
  }
  // G7-A R30 R08: tab, viewport and host-visibility pauses must not
  // release stale particle deadlines on the first resumed animation frame.
  // Initial mount is intentionally unchanged; validate all resumed bounds
  // before touching any live D02 timer or restarting RAF.
  let resumePending=false;
  function wake(){
    if(!disposed&&hostVisible&&intersectVisible&&!doc.hidden&&!preference&&mode!=="REDUCED"&&raf===null){
      if(resumePending){
        let now;
        try{now=time();}catch(_){return;}
        if(!Number.isFinite(now)||now<0)return;
        const policy=PROFILES[mode];
        const bounds=each.map(orb=>{
          const scale=orb.index===0?1:2.1;
          return [now+policy.minimumBurstMs*scale,
                  now+policy.maximumBurstMs*scale];
        });
        if(bounds.some(pair=>!pair.every(Number.isFinite)))return;
        each.forEach((orb,index)=>{
          const [earliest,latest]=bounds[index];
          orb.nextBurst=Number.isFinite(orb.nextBurst)
            ?Math.min(latest,Math.max(earliest,orb.nextBurst)):earliest;
        });
        resumePending=false;
      }
      lastFrame=0;raf=win.requestAnimationFrame(loop);
    }
  }
  function sleep(){
    if(raf!==null){win.cancelAnimationFrame(raf);raf=null;}
    resumePending=true;
    clearParticles();
  }
  function onVisibility(){if(disposed)return;root.dataset.noxFxVisible=(!doc.hidden&&hostVisible&&intersectVisible)?"true":"false";if(doc.hidden)sleep();else wake();}
  const onMotion=e=>{
    if(disposed)return;
    const wantsReduced=!!e?.matches;
    // G7-A R30: after an OS Reduced Motion pause, stale burst timers must
    // neither fire immediately nor remain parked outside the resumed policy.
    // Validate every new deadline before mutating any live D02 state.
    if(preference&&!wantsReduced&&mode!=="REDUCED"){
      let resumedAt;
      try{resumedAt=time();}catch(_){return;}
      if(!Number.isFinite(resumedAt)||resumedAt<0)return;
      const policy=PROFILES[mode];
      const bounds=each.map(orb=>{
        const scale=orb.index===0?1:2.1;
        return [resumedAt+policy.minimumBurstMs*scale,
                resumedAt+policy.maximumBurstMs*scale];
      });
      if(bounds.some(pair=>!pair.every(Number.isFinite)))return;
      each.forEach((orb,index)=>{
        const [earliest,latest]=bounds[index];
        orb.nextBurst=Number.isFinite(orb.nextBurst)
          ?Math.min(latest,Math.max(earliest,orb.nextBurst)):earliest;
      });
    }
    preference=wantsReduced;
    root.dataset.noxFxMode=(preference?"REDUCED":mode).toLowerCase();
    if(preference)sleep();else wake();};
  let listenerReady=false,motionReady=false,observer=null;
  // R08-06..09: handle browser registration exceptions atomically.
  try{
    doc.addEventListener("visibilitychange",onVisibility);listenerReady=true;
    if(motion){
      if(typeof motion.addEventListener==="function"){
        motion.addEventListener("change",onMotion);motionReady=true;
      }else if(typeof motion.addListener==="function"){
        motion.addListener(onMotion);motionReady=true;
      }
    }
    observer=typeof win.IntersectionObserver==="function"?
      new win.IntersectionObserver(items=>{
        if(disposed)return;
        intersectVisible=Array.isArray(items)&&items.some(x=>x?.isIntersecting===true);
        root.dataset.noxFxVisible=(!doc.hidden&&hostVisible&&intersectVisible)?"true":"false";
        if(intersectVisible)wake();else sleep();
      },{threshold:.001}):null;
    if(observer)observer.observe(root);
  }catch(error){rollbackFailedMount();throw error;}
  function applyState(next,runId=null,coreId=null){
    if(disposed)return false;
    if(!stateSet.has(next)||
       (runId!==null&&(typeof runId!=="string"||!pattern.test(runId)))||
       (coreId!==null&&(typeof coreId!=="string"||!pattern.test(coreId))))
      return false;
    if(coreId!==null){
      const orb=each.find(x=>x.id===coreId);
      if(!orb)return false;
      orb.element.dataset.noxFxState=next;
    }else{
      state=next;stateRunId=runId;
      root.dataset.noxFxState=next;
      each[0].element.dataset.noxFxState=next;
    }
    return true;
  }
  // Roll back only FX-owned nodes on malformed native subscription.
  function rollbackFailedMount(){
    // G7-A R30: a failed subscribe may leave a callback on the host bus.
    // Retire the callback before rollback touches any original D02 nodes.
    disposed=true;
    if(listenerReady)try{doc.removeEventListener("visibilitychange",onVisibility);}catch(_){}
    if(motionReady&&motion){
      try{
        if(typeof motion.removeEventListener==="function")motion.removeEventListener("change",onMotion);
        else if(typeof motion.removeListener==="function")motion.removeListener(onMotion);
      }catch(_){}
    }
    if(observer)try{observer.disconnect();}catch(_){}
    undoOwnedDom();
  }
  // No document-wide listeners; subscribe to the existing validated event source only.
  let unsubscribe=null;
  if(hostEvents){
    let un;
    try{un=hostEvents.subscribe(event=>{
      if(disposed)return;
      try{
        if(!event||typeof event!=="object"||event.trusted!==true ||
           typeof event.state!=="string")return;
        // Host event envelopes may be foreign or Proxy objects. Never let a
        // throwing accessor escape from decorative FX into the native bus.
        applyState(event.state,event.runId===undefined?null:event.runId,
          event.coreId===undefined?null:event.coreId);
      }catch(_){
        // Malformed payload: preserve the last confirmed visual state.
      }
    });}catch(error){rollbackFailedMount();throw error;}
    if(typeof un!=="function"){rollbackFailedMount();
      throw new Error("NOX_FX_SUBSCRIBE_REQUIRES_CLEANUP");}
    unsubscribe=un;
  }
  mounted.set(root,true);
  try{wake();}catch(error){
    disposed=true;
    // A failed initial RAF is not a successful subscription: release it.
    try{unsubscribe?.();}catch(_){}
    rollbackFailedMount();mounted.delete(root);throw error;
  }
  return Object.freeze({
    setProfile(next){
      if(disposed)return false;
      if(!profileSet.has(next))return false;
      // Validate the policy clock BEFORE touching live particles: a rejected
      // mode change must not partially discard the existing D02 animation.
      const newPolicy=profileFor(next,preference);
      // OS Reduced Motion caps live FX; target profile owns future burst bounds.
      const targetPolicy=PROFILES[next];
      const nextMin=targetPolicy.minimumBurstMs;
      const oldMin=PROFILES[mode].minimumBurstMs;
      // Explicit REDUCED -> active profile also needs a bounded fresh burst window.
      // Otherwise a dormant ECO deadline can exceed MAX/BALANCED's maximum.
      const faster=Number.isFinite(nextMin)&&nextMin<oldMin;
      const slower=Number.isFinite(nextMin)&&(nextMin>oldMin||oldMin===Infinity);
      let rebaseNow=null,fastBounds=null;
      if(faster||slower){
        try{rebaseNow=time();}catch(_){return false;}
        if(!Number.isFinite(rebaseNow)||rebaseNow<0||
           !Number.isFinite(rebaseNow+nextMin))return false;
        // ECO -> MAX/BALANCED must not inherit ECO's long dormant timers.
        // Validate every orbit bound before touching particles or live mode.
        if(faster){
          fastBounds=each.map(orb=>{
            const scale=orb.index===0?1:2.1;
            return [rebaseNow+targetPolicy.minimumBurstMs*scale,
                    rebaseNow+targetPolicy.maximumBurstMs*scale];
          });
          if(fastBounds.some(bounds=>!bounds.every(Number.isFinite)))return false;
        }
      }
      // Only a validated profile transition may trim the live ejecta budget.
      while(particles.length>newPolicy.maxParticles){
        const p=particles.pop();p.node.remove();
      }
      particleCount=particles.length;
      if(rebaseNow!==null)
        each.forEach((orb,index)=>{
          if(faster){
            const [earliest,latest]=fastBounds[index];
            orb.nextBurst=Math.max(earliest,Math.min(orb.nextBurst,latest));
          }else{
            orb.nextBurst=Math.max(orb.nextBurst,rebaseNow+nextMin);
          }
        });
      mode=next;root.dataset.noxFxMode=(preference?"REDUCED":mode).toLowerCase();
      if(next==="REDUCED")sleep();else wake();return true;
    },
    setState:applyState,
    setVisible(value){if(disposed||typeof value!=="boolean")return false;hostVisible=value;
      root.dataset.noxFxVisible=(!doc.hidden&&hostVisible&&intersectVisible)?"true":"false";
      if(hostVisible)wake();else sleep();return true;},
    snapshot(){return Object.freeze({profile:preference?"REDUCED":mode,
      active:!doc.hidden&&hostVisible&&intersectVisible&&!disposed&&!preference&&mode!=="REDUCED",coreCount:CORE_COUNT,
      particles:particleCount,emitted:emissions,frames:frameCount,
      state,stateRunId,telemetry:"HOST_ONLY"});},
    destroy(){
      if(disposed)return;
      disposed=true;
      try{sleep();}finally{
        try{if(unsubscribe)unsubscribe();}catch(_){/* host may throw on teardown */}
        rollbackFailedMount();
        mounted.delete(root);
      }
    }
  });
}
