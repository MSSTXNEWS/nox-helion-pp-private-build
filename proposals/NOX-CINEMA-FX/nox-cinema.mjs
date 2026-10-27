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
  return true;
}
export function profileFor(mode,reduced){
  if(!profileSet.has(mode))throw new Error("NOX_FX_INVALID_PROFILE");
  return PROFILES[reduced?"REDUCED":mode];
}
// Burst outward, slow near the apex, and return to the point of emergence.
// It is a designed visual cue, not a claim of astronomical simulation.
export function gravitationalSample(p,timeMs){
  if(!p||!Number.isFinite(timeMs)||!Number.isFinite(p.started)||!Number.isFinite(p.duration)||
     p.duration<=0)throw new Error("NOX_FX_INVALID_PARTICLE");
  const t=clamp((timeMs-p.started)/p.duration,0,1);
  const arc=Math.sin(Math.PI*t);
  const radius=p.surfaceRadius+arc*p.reach;
  const sideways=p.swirl*arc*Math.cos(Math.PI*t);
  const angle=p.angle;
  const x=100+Math.cos(angle)*radius-Math.sin(angle)*sideways;
  const y=100+Math.sin(angle)*radius+Math.cos(angle)*sideways;
  const opacity=(t<=0||t>=1)?0:clamp(Math.pow(arc,.6)*p.brightness,0,1);
  return {x,y,opacity,angle:t*320+p.rotation,done:t>=1,t,radius};
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
  const time=clock||(()=>win.performance.now());
  const motion=typeof win.matchMedia==="function"?
    win.matchMedia("(prefers-reduced-motion: reduce)"):null;
  let preference=!!motion?.matches;
  let mode=profile;
  let disposed=false,active=true,raf=0,lastFrame=0,frameCount=0;
  let state="idle",stateRunId=null,emissions=0,particleCount=0;
  let ownerRoot=false;
  const decorated=[];
  const particles=[];
  const each=orbs.map((entry,index)=>{
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
    element.classList.add("nox-cinema-orb");
    element.dataset.noxState="idle";
    element.appendChild(layers);
    decorated.push({element,cls:"nox-cinema-orb"});
    const shape={id:entry.id,element,layers,svg,index,
      nextBurst:time()+4500+random()*18000};
    return shape;
  });
  function decorate(items,cls){
    if(!Array.isArray(items))throw new Error("NOX_FX_DECORATION_LIST");
    for(const e of items){
      if(!e||e.nodeType!==1||!root.contains(e))continue;
      // Buttons and panels remain original controls. Only cosmetic classes added.
      e.classList.add(cls);decorated.push({element:e,cls});
    }
  }
  decorate(controls,"nox-cinema-control");
  decorate(panels,"nox-cinema-panel");
  root.classList.add("nox-cinema-scope");ownerRoot=true;
  root.dataset.noxMode=profile.toLowerCase();
  root.dataset.noxFxVisible="true";
  root.dataset.noxState=state;
  function clearParticles(){
    for(const p of particles){p.node.remove();}
    particles.length=0;particleCount=0;
  }
  function nextDelay(policy){return policy.minimumBurstMs+
    random()*(policy.maximumBurstMs-policy.minimumBurstMs);}
  function makeParticle(orb,now){
    const angle=2*Math.PI*random();
    const size=clamp(.65+random()*1.85,.6,2.5);
    const node=svgElement(doc,"path",{d:"M "+(-size)+" 0 L 0 "+(-size*.42)+
      " L "+size+" 0 L 0 "+(size*.42)+" Z",
      fill:random()<.23?"#323032":"#c57244",
      opacity:"0"});
    orb.svg.appendChild(node);
    const p={node,started:now,duration:2200+random()*1900,
      surfaceRadius:86+random()*6,reach:(orb.index===0?16:8)+random()*(orb.index===0?29:20),
      angle,swirl:(random()-.5)*17,brightness:.48+random()*.42,
      rotation:random()*360};
    particles.push(p);particleCount++;emissions++;
  }
  function loop(now){
    raf=0;
    if(disposed||!active||doc.hidden)return;
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
      if(orb.index!==0 && random()>.38)continue;
      const count=orb.index===0?2:1;
      for(let i=0;i<count&&particleCount<policy.maxParticles;i++)makeParticle(orb,now);
    }
  }
  function wake(){
    if(!disposed&&active&&!doc.hidden&&!preference&&!raf){
      lastFrame=0;raf=win.requestAnimationFrame(loop);
    }
  }
  function sleep(){
    if(raf){win.cancelAnimationFrame(raf);raf=0;}
    clearParticles();
  }
  function onVisibility(){root.dataset.noxFxVisible=doc.hidden?"false":"true";if(doc.hidden)sleep();else wake();}
  doc.addEventListener("visibilitychange",onVisibility);
  const onMotion=e=>{preference=!!e.matches;if(preference)sleep();else wake();};
  if(motion){
    if(typeof motion.addEventListener==="function")
      motion.addEventListener("change",onMotion);
    else if(typeof motion.addListener==="function")motion.addListener(onMotion);
  }
  const observer=typeof win.IntersectionObserver==="function"?
    new win.IntersectionObserver(items=>{
      active=items.some(x=>x.isIntersecting);
      root.dataset.noxFxVisible=active?"true":"false";
      if(active)wake();else sleep();
    },{threshold:.001}):null;
  if(observer)observer.observe(root);
  function applyState(next,runId=null,coreId=null){
    if(!stateSet.has(next)||(runId!==null && (!pattern.test(runId))))
      return false;
    if(coreId!==null){
      const orb=each.find(x=>x.id===coreId);
      if(!orb)return false;
      orb.element.dataset.noxState=next;
    }else{
      state=next;stateRunId=runId;
      root.dataset.noxState=next;
      each[0].element.dataset.noxState=next;
    }
    return true;
  }
  // No document-wide listeners; subscribe to the existing validated event source only.
  let unsubscribe=null;
  if(hostEvents){
    const un=hostEvents.subscribe(event=>{
      if(!event||typeof event!=="object"||event.trusted!==true ||
         typeof event.state!=="string")return;
      // No fabricated training progress: CSS data-state is just a host-attested state.
      applyState(event.state,event.runId||null,event.coreId||null);
    });
    if(typeof un!=="function")throw new Error("NOX_FX_SUBSCRIBE_REQUIRES_CLEANUP");
    unsubscribe=un;
  }
  mounted.set(root,true);wake();
  return Object.freeze({
    setProfile(next){
      if(!profileSet.has(next))return false;
      mode=next;root.dataset.noxMode=next.toLowerCase();
      if(next==="REDUCED")sleep();else wake();return true;
    },
    setState:applyState,
    setVisible(value){active=value===true;root.dataset.noxFxVisible=active?"true":"false";
      if(active)wake();else sleep();},
    snapshot(){return Object.freeze({profile:preference?"REDUCED":mode,
      active:!doc.hidden&&active&&!disposed,coreCount:CORE_COUNT,
      particles:particleCount,emitted:emissions,frames:frameCount,
      state,stateRunId,telemetry:"HOST_ONLY"});},
    destroy(){
      if(disposed)return;disposed=true;sleep();
      doc.removeEventListener("visibilitychange",onVisibility);
      if(motion){
        if(typeof motion.removeEventListener==="function")
          motion.removeEventListener("change",onMotion);
        else if(typeof motion.removeListener==="function")motion.removeListener(onMotion);
      }
      if(observer)observer.disconnect();
      if(unsubscribe)unsubscribe();
      for(const orb of each){orb.layers.remove();delete orb.element.dataset.noxState;}
      for(const item of decorated)item.element.classList.remove(item.cls);
      if(ownerRoot){root.classList.remove("nox-cinema-scope");
        delete root.dataset.noxMode;delete root.dataset.noxState;
        delete root.dataset.noxFxVisible;}
      mounted.delete(root);
    }
  });
}
