/* NOX HELION: BLACK MONOLITH SKY · interactive scene recovery
 * Design references: owner-approved HOME 2026-10-19, canonical HOME 2026-11-07.
 * No model/IPC/storage changes. WebGL master remains original nox-home.mjs.
 * Canvas2D runs only when original WebGL cannot produce frames. */
(()=>{"use strict";
 const stage=document.querySelector(".helion-stage"),root=document.documentElement;
 if(!stage||document.body.dataset.page!=="index")return;
 const sky=document.createElement("canvas");sky.id="noxSkyLive";sky.setAttribute("aria-hidden","true");
 const citadel=document.createElement("div");citadel.className="noxCitadel";citadel.setAttribute("aria-hidden","true");
 const fallback=document.createElement("canvas");fallback.id="noxCoreFallback";fallback.setAttribute("aria-hidden","true");
 stage.prepend(citadel);stage.prepend(sky);stage.appendChild(fallback);
 const chat=document.createElement("a");chat.id="noxCoreEntry";chat.href="chat.html";chat.setAttribute("aria-label","Резонанс — перейти в настоящий чат NOX");chat.innerHTML="<span>✦ РЕЗОНАНС</span><small>ВОЙТИ В ЧАТ</small>";stage.appendChild(chat);
 const ctx=sky.getContext("2d",{alpha:true}),fg=fallback.getContext("2d",{alpha:true});
 const reduced=matchMedia("(prefers-reduced-motion:reduce)");
 const rng=(function(){let seed=0x20261109;return()=>((seed=Math.imul(seed,1664525)+1013904223|0)>>>0)/4294967296})();
 const stars=Array.from({length:225},()=>({x:rng(),y:rng(),r:.30+rng()*1.05,d:.18+rng()*.83,seed:rng()*Math.PI*2,wave:.5+rng()*.6}));
 let w=1,h=1,scale=1,frames=0,painted=0,last=0,hidden=false,reason="initializing";
 const c=document.getElementById("noxEclipseCanvas");
 function fit(){
  const b=stage.getBoundingClientRect();w=Math.max(1,Math.round(b.width));h=Math.max(1,Math.round(Math.min(b.height,innerWidth<=1100?510:1200)));
  scale=Math.min(devicePixelRatio||1,1.4);
  for(const x of [sky,fallback]){x.width=Math.round(w*scale);x.height=Math.round(h*scale);}
 }
 function palette(){
  const name=root.dataset.noxColor||"gold";
  return {"classic":"#f1c27a","gold":"#f1c27a","copper":"#ce9572","glacier":"#adcddd","ion":"#84d1c6","amethyst":"#bfa5df"}[name]||"#f1c27a";
 }
 function strokeGlow(ctx,color,blur){ctx.strokeStyle=color;ctx.shadowColor=color;ctx.shadowBlur=blur;}
 function paintSky(t){
  if(!ctx)return;ctx.setTransform(scale,0,0,scale,0,0);ctx.clearRect(0,0,w,h);
  const tint=root.dataset.noxSkin||"helion";const p={"helion":"#b7b9c9","obsidian":"#d9dbe5","reactor":"#9ec8eb","liquid":"#b9d1d6","aurora":"#acd9ce"}[tint]||"#cbd4da";
  for(const s of stars){
   const x=((s.x*w+t*s.d*.004)%w),y=((s.y*h-t*s.d*.001+h)%h);
   const twinkle=reduced.matches?1:.66+.34*Math.sin(t*s.wave*.23+s.seed);
   const opacity=(.10+s.d*.35)*twinkle;
   ctx.globalAlpha=opacity;ctx.fillStyle=p;ctx.beginPath();ctx.arc(x,y,s.r,0,Math.PI*2);ctx.fill();
  }ctx.globalAlpha=1;
 }
 function paintCore(t){
  if(!fg)return;
  fg.setTransform(scale,0,0,scale,0,0);fg.clearRect(0,0,w,h);
  const mobile=w<=1100,cx=w*.50,cy=mobile?260:h*.465;
  const r=Math.min(mobile?190:210,w*(mobile?(w<=700?.30:.225):.15),h*(mobile?.34:.225));
  const color=palette(),pulse=reduced.matches?1:1+.012*Math.sin(t*.69);
  const rad=r*pulse;
  ctx && void 0;
  fg.save();
  const haze=fg.createRadialGradient(cx,cy,rad*.80,cx,cy,rad*1.42);
  haze.addColorStop(0,color+"00");haze.addColorStop(.36,color+"18");haze.addColorStop(1,color+"00");
  fg.fillStyle=haze;fg.beginPath();fg.arc(cx,cy,rad*1.44,0,Math.PI*2);fg.fill();
  for(let i=0;i<150;i++){
    const a=i*Math.PI*2/150,n=Math.sin(a*19+t*.24)*.047+Math.sin(a*47-t*.19)*.035;
    const start=rad*(1.01+n*.5),len=rad*(.075+.15*Math.pow(Math.max(0,Math.sin(a*37+t*.26)),11));
    fg.beginPath();fg.moveTo(cx+Math.cos(a)*start,cy+Math.sin(a)*start);
    fg.lineTo(cx+Math.cos(a)*(start+len),cy+Math.sin(a)*(start+len));
    strokeGlow(fg,color,8);fg.globalAlpha=.065+.17*Math.pow(Math.max(0,Math.sin(a*7+t*.34)),2);fg.lineWidth=.55;fg.stroke();
  }fg.globalAlpha=1;
  // Real-time shaded obsidian disk; procedural fallback, not a copied image of the nucleus.
  const rock=fg.createRadialGradient(cx-rad*.33,cy-rad*.37,rad*.05,cx,cy,rad*1.12);
  rock.addColorStop(0,"#303037");rock.addColorStop(.24,"#101216");rock.addColorStop(.65,"#060709");rock.addColorStop(1,"#000000");
  fg.fillStyle=rock;fg.beginPath();fg.arc(cx,cy,rad*.97,0,Math.PI*2);fg.fill();
  fg.save();fg.beginPath();fg.arc(cx,cy,rad*.97,0,Math.PI*2);fg.clip();
  // Slow-moving mineral fractures, sharply restrained.
  for(let k=0;k<34;k++){
   const a=k*2.3999632+.4,rr=.12+(k%5)*.13,x=cx+Math.cos(a)*rad*rr,y=cy+Math.sin(a)*rad*rr;
   const bend=Math.sin(t*.16+k)*rad*.012;
   fg.beginPath();fg.moveTo(x,y);
   fg.quadraticCurveTo(x+rad*.12+bend,y-rad*.06,x+rad*.08,y-rad*.18);
   fg.quadraticCurveTo(x+rad*.04,y-rad*.25,x+rad*.17,y-rad*.27);
   strokeGlow(fg,k%3===0?color:"#8d623e",5);
   fg.lineWidth=k%4===0?1.25:.62;fg.globalAlpha=k%4===0?.57:.27;fg.stroke();
  }fg.restore();
  fg.globalAlpha=1;
  const rim=fg.createLinearGradient(cx-rad,cy-rad,cx+rad,cy+rad);
  rim.addColorStop(0,color+"e0");rim.addColorStop(.28,color+"52");rim.addColorStop(.56,color+"18");rim.addColorStop(.81,color+"ce");rim.addColorStop(1,color+"75");
  fg.beginPath();fg.arc(cx,cy,rad*.985,0,Math.PI*2);
  fg.strokeStyle=rim;fg.lineWidth=2.0;fg.shadowBlur=23;fg.shadowColor=color;fg.stroke();
  fg.restore();
 }
 function state(){
  const d=window.noxHomeDiagnostics?.();
  const good=!!d&&d.status==="READY"&&d.renderCount>0;
  fallback.dataset.live=String(good);
  reason=good?"ORIGINAL_D02_WEBGL":fg?"CANVAS2D_PROCEDURAL_FALLBACK":"CSS_ONLY";root.dataset.noxCoreRender=reason;
  if(good){const n=document.getElementById("sceneNotice");if(n)n.hidden=true;}
  return good;
 }
 function loop(ms){
  requestAnimationFrame(loop);
  if(document.hidden)return;
  if(reduced.matches&&painted>0)return;
  if(ms-last<50)return;last=ms;const t=ms/1000;
  fitIfNeeded();
  paintSky(t);if(!state())paintCore(t);
  frames++;painted++;
 }
 function fitIfNeeded(){const b=stage.getBoundingClientRect();if(Math.abs(b.width-w)>2||Math.abs(Math.min(b.height,innerWidth<=1100?510:1200)-h)>2)fit();}
 /* Theme illumination never replaces BLACK MONOLITH SKY as the HOME backdrop. */
 const darken=()=>{
   const s=root.dataset.noxSkin||"helion";
   const wash={helion:"#05070c",obsidian:"#03040b",reactor:"#030914",liquid:"#05070a",aurora:"#020a0c"}[s]||"#020407";
   if(stage.style.getPropertyValue("background-color")!==wash)stage.style.setProperty("background-color",wash,"important");
   if(stage.style.getPropertyValue("background-image")!=="none")stage.style.setProperty("background-image","none","important");
 };
 let pending=false;
 const scheduleDark=()=>{if(pending)return;pending=true;queueMicrotask(()=>{pending=false;darken();});};
 new MutationObserver(scheduleDark).observe(stage,{attributes:true,attributeFilter:["style"]});
 new MutationObserver(scheduleDark).observe(root,{attributes:true,attributeFilter:["data-nox-skin"]});
 darken();
 root.dataset.noxSky="BLACK_MONOLITH_SKY";
 fit();requestAnimationFrame(loop);
 addEventListener("resize",fit,{passive:true});
 reduced.addEventListener?.("change",()=>{painted=0;});
 window.NOX_HOME_RECOVERY_QA=()=>({source:"OWNER_D02_ORIGINAL_PLUS_GENUINE_FALLBACK",render:reason,frames,starCount:stars.length,webgl:window.noxHomeDiagnostics?.()||null,coreParent:c?.parentElement?.className,corePixels:[c?.width,c?.height],worlds:document.querySelectorAll(".nox-orbital-controls button").length,color:root.dataset.noxColor,skin:root.dataset.noxSkin,quality:root.dataset.noxDemoMode,reducedMotion:reduced.matches,backendStatus:"PUBLIC_PREVIEW_API_NOT_CONNECTED"});
})();
