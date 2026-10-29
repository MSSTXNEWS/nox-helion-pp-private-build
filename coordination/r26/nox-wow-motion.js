/* NOX R28 · interaction-only FX, not a sensor simulator.
   Connection state must be sent from the real API result via nox:connection. */
(function(){
"use strict";
const motion=window.matchMedia?window.matchMedia("(prefers-reduced-motion: reduce)"):null;
const reduced=()=>Boolean(motion&&motion.matches)||document.body.classList.contains("nox-eco");
const root=document.documentElement;
let pointerFrame=0, pos={x:0,y:0,sx:50,sy:50}, connected=false;
const wavePath="M0 18 L39 18 L51 17 L60 19 L68 18 L77 8 L85 29 L95 4 L105 30 L115 18 L142 18 L150 14 L158 20 L172 18 L240 18";
function createPulse(){
 const place=document.querySelector(".top .actions");
 if(!place||document.getElementById("nox-telemetry"))return;
 const node=document.createElement("div");node.id="nox-telemetry";node.dataset.connection="offline";
 node.setAttribute("aria-label","NOX: статус соединения и свежести данных");
 const mark=document.createElement("span");mark.className="pulse-label";
 const dot=document.createElement("i");dot.className="pulse-pin";dot.setAttribute("aria-hidden","true");
 const label=document.createElement("span");label.textContent="DATA PULSE";
 mark.append(dot,label);
 const svg=document.createElementNS("http://www.w3.org/2000/svg","svg");
 svg.id="nox-pulse-wave";svg.setAttribute("viewBox","0 0 240 36");svg.setAttribute("role","img");svg.setAttribute("aria-label","Декоративная линия проверки соединения, не медицинский пульс");
 const path=document.createElementNS("http://www.w3.org/2000/svg","path");path.setAttribute("d",wavePath);svg.append(path);
 const state=document.createElement("span");state.id="nox-pulse-info";state.className="pulse-info";state.textContent="СНИМОК · LIVE НЕ ПРОВЕРЕН";
 node.append(mark,svg,state);
 place.insertAdjacentElement("beforebegin",node);
}
function setConnection(data){
 const state=data&&typeof data==="object"?data:{};
 connected=state.online===true;
 const status=state.checking?"checking":connected?"online":"offline";
 for(const id of ["nox-telemetry","live-status"]){const el=document.getElementById(id);if(el)el.dataset.connection=status;}
 const label=document.getElementById("nox-pulse-info");
 if(label){
  const t=state.checkedAt&&connected?new Date(state.checkedAt).toLocaleTimeString("ru-RU"):"";
  label.textContent=connected?"API ONLINE · "+(t||"ПРОВЕРЕНО"):state.checking?"CONNECTING…":"SNAPSHOT · OFFLINE";
 }
}
document.addEventListener("nox:connection",e=>setConnection(e.detail));
function placeOrbs(){
 document.querySelectorAll(".orbit-dot").forEach((el,i)=>{
  el.style.setProperty("--orb-index",String(i));
  el.setAttribute("aria-hidden","true");
 });
}
function animatePosition(){
 pointerFrame=0;
 if(reduced())return;
 const hero=document.querySelector(".hero");
 if(hero){hero.style.setProperty("--mx",pos.x.toFixed(2)+"px");hero.style.setProperty("--my",pos.y.toFixed(2)+"px");}
 root.style.setProperty("--nox-pointer-x",pos.sx.toFixed(2)+"%");
 root.style.setProperty("--nox-pointer-y",pos.sy.toFixed(2)+"%");
}
function pointer(e){
 if(reduced()||e.pointerType==="touch")return;
 const hero=document.querySelector(".hero");
 if(!hero)return;
 const r=hero.getBoundingClientRect();
 const cx=(e.clientX-r.left)/r.width-.5,cy=(e.clientY-r.top)/r.height-.5;
 pos.x=Math.max(-30,Math.min(30,cx*44));pos.y=Math.max(-22,Math.min(22,cy*34));
 pos.sx=Math.max(0,Math.min(100,(cx+.5)*100));pos.sy=Math.max(0,Math.min(100,(cy+.5)*100));
 if(!pointerFrame)pointerFrame=requestAnimationFrame(animatePosition);
}
document.addEventListener("pointermove",pointer,{passive:true});
document.addEventListener("pointerleave",()=>{pos.x=0;pos.y=0;pos.sx=50;pos.sy=50;if(!pointerFrame)pointerFrame=requestAnimationFrame(animatePosition);});
function start(){createPulse();placeOrbs();setConnection({online:false});const hero=document.querySelector(".hero");if(hero)hero.classList.add("nox-scanning");const status=document.getElementById("live-status");if(status){const sync=()=>{const text=status.textContent||"";if(text.startsWith("API отвечает"))setConnection({online:true,checkedAt:Date.now()});else if(text.includes("Проверяю"))setConnection({checking:true});else setConnection({online:false});};const watch=new MutationObserver(sync);watch.observe(status,{childList:true,subtree:true,characterData:true});sync();}}
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",start,{once:true});else start();
})();
