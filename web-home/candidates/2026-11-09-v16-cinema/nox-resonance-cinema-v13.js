/* NOX Resonance — core-origin signal fronts. No external API or fake telemetry.
   Each pulse is a soundless visual response. Existing chat href remains genuine. */
(()=>{"use strict";
 const stage=document.querySelector(".helion-stage");
 if(!stage||document.body.dataset.page!=="index")return;
 const reduced=matchMedia("(prefers-reduced-motion: reduce)");
 const canvas=document.createElement("canvas");
 canvas.id="noxResonanceWaveCanvas";canvas.setAttribute("aria-hidden","true");
 stage.appendChild(canvas);
 const c=canvas.getContext("2d",{alpha:true});
 const link=document.querySelector("#noxCoreEntry");
 let width=0,height=0,ratio=1,last=0,frames=0,fronts=0,interactive=0,boostUntil=0;
 const particles=Array.from({length:41},(_,i)=>({angle:(i*2.399963229728653)%6.283,size:.7+(i%4)*.17,phase:i*.77}));
 function resize(){
  const a=stage.getBoundingClientRect(),nw=Math.max(1,Math.round(a.width)),nh=Math.max(1,Math.round(Math.min(a.height,innerWidth<=1100?510:1800)));
  const mobile=nw<=1100,cy=mobile?Math.min(260,nh*.5):nh*.465;
  const radius=Math.min(nw*(nw<=700?.28:mobile?.225:.15),nh*.225,mobile?125:210);
  // Anchor the dialog plaque to the photographed core's lower silhouette, never its corona.
  const titleY=Math.max(0,Math.min(mobile?nh-72:nh-106,cy+radius+(nw<=700?18:22)));
  stage.style.setProperty("--nox-resonance-label-top",Math.round(titleY)+"px");
  if(nw===width&&nh===height)return;
  width=nw;height=nh;ratio=Math.min(devicePixelRatio||1,1.6);
  canvas.width=Math.round(width*ratio);canvas.height=Math.round(height*ratio);
 }
 function front(t){
  if(!c)return;
  c.setTransform(ratio,0,0,ratio,0,0);
  c.clearRect(0,0,width,height);
  const cx=width*.5, cy=width<=1100?Math.min(260,height*.50):height*.465;
  const radius=Math.min(width*(width<=700?.28:width<=1100?.225:.15),height*.225,width<=1100?125:210);
  const burst=t<boostUntil, gold=document.documentElement.dataset.noxColor!=="amethyst";
  c.save();c.globalCompositeOperation="screen";
  // A controlled solar rim shimmer, not a floating wireframe orbit around the interface.
  // Three separated arcs, all within 1.10 radii; no large elliptical outlines.
  if(!reduced.matches){
   for(let j=0;j<3;j++){
    const startAngle=t*.008+j*2.094+Math.sin(t*.11+j)*.12;
    const sweep=.16+.05*Math.sin(t*.09+j);
    const alpha=(burst?.22:.095)*(j===0?1:.65);
    c.beginPath();c.ellipse(cx,cy,radius*(1.035+j*.014),radius*(1.035+j*.014),0,startAngle,startAngle+sweep);
    c.strokeStyle=gold?"rgba(236,175,98,"+alpha+")":"rgba(185,165,220,"+alpha+")";
    c.lineWidth=j===0?.9:.55;c.shadowBlur=burst?12:5;
    c.shadowColor=gold?"#f4b66f":"#baa6d8";c.stroke();fronts++;
   }
   // Sparse independent ash particles near the corona; never a clocklike perimeter.
   for(const p of particles){
    const depth=.25+.75*(.5+.5*Math.sin(t*.12+p.phase));
    const rr=radius*(1.08+.12*depth);
    const a=p.angle+.009*Math.sin(t*.21+p.phase);
    c.fillStyle="rgba(207,178,148,"+(.018+.035*depth).toFixed(3)+")";
    c.shadowBlur=0;c.beginPath();c.arc(cx+Math.cos(a)*rr,cy+Math.sin(a)*rr,p.size*.66,0,Math.PI*2);c.fill();
   }
  }
  c.restore();
 }
 function frame(ms){
  requestAnimationFrame(frame);
  if(document.hidden)return;
  const t=ms/1000;
  if(ms-last<(reduced.matches?1000:50))return;
  last=ms;resize();front(t);frames++;if(frames%5===0){canvas.dataset.waveFrames=String(frames);canvas.dataset.waveFronts=String(fronts);canvas.dataset.source='D02_ORIGIN';}
 }
 if(link){
  link.addEventListener("pointerenter",()=>{boostUntil=performance.now()/1000+1.6;interactive++;});
  link.addEventListener("focus",()=>{boostUntil=performance.now()/1000+1.6;interactive++;});
  link.addEventListener("pointerdown",()=>{boostUntil=performance.now()/1000+2;interactive++;});
 }
 resize();requestAnimationFrame(frame);
 window.NOX_RESONANCE_VISUAL_QA=()=>({render:"CANVAS2D_LIGHT_WAVE_OVERLAY",frames,fronts,interactive,canvasPixels:[canvas.width,canvas.height],reducedMotion:reduced.matches,link:link?.getAttribute("href"),font:link?getComputedStyle(link.querySelector(".nox-resonance-word")||link).fontFamily:null});
})();