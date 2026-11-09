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
  const titleY=Math.max(0,Math.min(mobile?nh-77:nh-119,cy+radius+(nw<=700?30:mobile?35:52)));
  stage.style.setProperty("--nox-resonance-label-top",Math.round(titleY)+"px");
  if(nw===width&&nh===height)return;
  width=nw;height=nh;ratio=Math.min(devicePixelRatio||1,1.6);
  canvas.width=Math.round(width*ratio);canvas.height=Math.round(height*ratio);
 }
 function front(t){
  if(!c)return;
  c.setTransform(ratio,0,0,ratio,0,0);c.clearRect(0,0,width,height);
  const cx=width*.5,cy=width<=1100?Math.min(260,height*.50):height*.465;
  const radius=Math.min(width*(width<=700?.28:width<=1100?.225:.15),height*.225,width<=1100?125:210);
  const burst=t<boostUntil, speed=burst?.46:.17;
  const waveColor=(document.documentElement.dataset.noxColor==="amethyst"?"173,187,218":"196,190,174");
  c.save();c.globalCompositeOperation="screen";
  if(!reduced.matches){
   for(let j=0;j<2;j++){
    const phase=((t*speed+j*.51)%1),r=radius*(1.10+phase*(burst?1.10:1.40));
    const alpha=(1-phase)**2*(burst?.32:.235);
    c.strokeStyle="rgba("+waveColor+","+alpha.toFixed(3)+")";
    c.shadowColor="rgba(159,184,201,"+(alpha*.64).toFixed(3)+")";c.shadowBlur=10;
    c.lineWidth=Math.max(.4,(1.15-phase*.65));
    c.beginPath();
    for(let k=0;k<=192;k++){
     const a=Math.PI*2*k/192;
     const bend=1+.019*Math.sin(a*7+t*.16+j*1.8)+.013*Math.sin(a*13-t*.11)+.006*Math.sin(a*23+t*.08);
     const x=cx+Math.cos(a)*r*bend,y=cy+Math.sin(a)*r*bend*.82;
     if(k===0)c.moveTo(x,y);else c.lineTo(x,y);
    }
    c.stroke();fronts++;
   }
  }else{
   c.strokeStyle="rgba(177,191,206,.12)";c.lineWidth=.7;
   c.beginPath();c.ellipse(cx,cy,radius*1.22,radius*.96,0,0,Math.PI*2);c.stroke();
  }
  // Faint pulse particles floating along wavefront, no uniform clock ring of dots.
  if(!reduced.matches)for(const p of particles){
   const depth=(.25+.75*(.5+.5*Math.sin(t*.12+p.phase)));
   const rr=radius*(1.18+.42*depth);
   const a=p.angle+.013*Math.sin(t*.21+p.phase);
   c.fillStyle="rgba(171,185,202,"+(.025+.07*depth).toFixed(3)+")";
   c.shadowBlur=0;c.beginPath();
   c.arc(cx+Math.cos(a)*rr,cy+Math.sin(a)*rr*.84,p.size,0,Math.PI*2);c.fill();
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