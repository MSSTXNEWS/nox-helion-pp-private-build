/* NOX Cinematic Director · WOW 101–150 · isolated secondary-scene layer.
   Preserves D02 HOME, original 8 CoreID and all existing PR30/31 effects.
   No extra engine/LLM/DB/network, no privileged commands, no invented telemetry. */
import {SHOTS,BY_ID,validateShots} from "./catalog.mjs";
const MODES=Object.freeze({ECO:{speed:.7,amplitude:.32},BALANCED:{speed:1,amplitude:1},MAX:{speed:1.1,amplitude:1.24},REDUCED:{speed:0,amplitude:0}});
const installed=new WeakMap();
export function choreography(shot,mode="BALANCED"){
 if(!shot||BY_ID.get(shot.id)!==shot||!Object.hasOwn(MODES,mode))throw Error("INVALID_SHOT_OR_MODE");
 const p=MODES[mode],v=shot.distance*p.amplitude,a=shot.angle*p.amplitude,z=1+(shot.depth-1)*p.amplitude;
 const move=(x,y,scale,rot)=>"translate3d("+x.toFixed(2)+"px,"+y.toFixed(2)+"px,0) scale("+scale.toFixed(4)+") rotate("+rot.toFixed(2)+"deg)";
 const cam=[
  {offset:0,transform:move(-v/2,-v/3,z*.98,a/7),opacity:.45},
  {offset:.27,transform:move(v/4,-v/5,z*1.013,-a/13),opacity:.86},
  {offset:.71,transform:move(-v/7,v/8,z*1.006,a/27),opacity:.94},
  {offset:1,transform:move(0,0,1,0),opacity:1}];
 const light=[
  {offset:0,transform:move(v/2,0,.89,0),opacity:.03},
  {offset:.45,transform:move(-v/4,0,1.07,0),opacity:shot.heat},
  {offset:1,transform:move(0,0,1,0),opacity:.08}];
 const haze=[
  {offset:0,transform:move(-v/1.4,v/3,1,0),opacity:.03},
  {offset:.55,transform:move(v/3,-v/4,1.015,0),opacity:.08+shot.heat/3},
  {offset:1,transform:move(0,0,1,0),opacity:.08}];
 return {cam,light,haze,duration:Math.round(shot.duration*p.speed)};
}
export function mountDirector(root,{mode="BALANCED",authorize=null,reducedMotion=false}={}){
 validateShots();
 if(!root||root.nodeType!==1||root.dataset?.noxWowSlot!=="secondary"||
   (typeof root.closest==="function"&&root.closest('[data-nox-page="home"]')))throw Error("D02_HOME_LOCK");
 if(installed.has(root))throw Error("ALREADY_MOUNTED");
 if(!Object.hasOwn(MODES,mode))throw Error("INVALID_PROFILE");
 if(authorize!==null&&typeof authorize!=="function")throw Error("BAD_AUTHORIZE");
 const doc=root.ownerDocument;
 if(!doc||typeof doc.createElement!=="function")throw Error("APPROVED_DOCUMENT_REQUIRED");
 const stage=doc.createElement("div");stage.className="nox-d101-stage";stage.setAttribute("aria-hidden","true");
 const cam=doc.createElement("div"),light=doc.createElement("div"),haze=doc.createElement("div");
 cam.className="nox-d101-camera";light.className="nox-d101-light";haze.className="nox-d101-haze";stage.append(cam,light,haze);
 const label=doc.createElement("output");label.className="nox-d101-label";label.textContent="ДЕМО · только вторичный экран";label.setAttribute("aria-live","off");
 root.append(stage,label);root.classList.add("nox-d101-slot");
 let done=false,activeId=null,source=null,profile=mode,reduced=reducedMotion===true,animations=[];
 const motionMedia=doc.defaultView?.matchMedia?.("(prefers-reduced-motion: reduce)")||null;
 const effective=()=>reduced||motionMedia?.matches?"REDUCED":profile;
 const cancel=()=>{for(const a of animations)a.cancel?.();animations=[]};
 function motionChange(){stage.dataset.mode=effective();if(effective()==="REDUCED")cancel()}
 function visibility(){if(doc.hidden){for(const a of animations)a.pause?.()}else{for(const a of animations)a.play?.()}}
 motionMedia?.addEventListener?.("change",motionChange);doc.addEventListener?.("visibilitychange",visibility);motionChange();
 function show(id,provenance){
  if(done)throw Error("DIRECTOR_DISPOSED");
  const shot=BY_ID.get(id);if(!shot)throw Error("UNKNOWN_SHOT");
  if(provenance==="APPROVED_INTERACTION"&&(!authorize||authorize(shot)!==true))throw Error("HOST_APPROVAL_REQUIRED");
  cancel();activeId=id;source=provenance;stage.dataset.shot=String(id);stage.dataset.family=shot.family;stage.dataset.source=provenance;
  stage.dataset.mode=effective();label.textContent=(provenance==="DEMO"?"ДЕМО · ":"ПОДТВЕРЖДЕНО · ")+id+" · "+shot.name;
  if(effective()!=="REDUCED"&&!doc.hidden){
   const frames=choreography(shot,effective());
   for(const [element,seq] of [[cam,frames.cam],[light,frames.light],[haze,frames.haze]])
    if(typeof element.animate==="function")animations.push(element.animate(seq,{duration:frames.duration,easing:"cubic-bezier(.22,.61,.36,1)",iterations:1,fill:"both"}));
  }
  return shot;
 }
 const api=Object.freeze({preview(id){return show(id,"DEMO")},activate(id){return show(id,"APPROVED_INTERACTION")},
  setMode(v){if(done)throw Error("DIRECTOR_DISPOSED");if(!Object.hasOwn(MODES,v))throw Error("INVALID_PROFILE");profile=v;motionChange()},
  setReducedMotion(v){if(done)throw Error("DIRECTOR_DISPOSED");reduced=v===true;motionChange()},
  current(){return {id:activeId,source,mode:effective(),runningAnimations:animations.length}},
  destroy(){if(done)return;done=true;cancel();motionMedia?.removeEventListener?.("change",motionChange);doc.removeEventListener?.("visibilitychange",visibility);stage.remove();label.remove();root.classList.remove("nox-d101-slot");installed.delete(root)}
 });installed.set(root,api);return api;
}
