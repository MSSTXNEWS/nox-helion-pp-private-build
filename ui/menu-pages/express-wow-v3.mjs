/* NOX HELION EXPRESS WOW V3: optional deterministic starfield and volumetric accents.
   DOM-only decoration. It never invokes OneHost, launches actions or invents telemetry. */
(function(){
 'use strict';
 function boot(){
  const d=document,w=window,stage=d.querySelector('.universe'),body=d.body;
  if(!stage||!body||stage.dataset.wowV3==='1')return;
  stage.dataset.wowV3='1';
  const reduce=w.matchMedia?.('(prefers-reduced-motion: reduce)');
  const dataSaver=!!navigator.connection?.saveData;
  const canvas=d.createElement('canvas');
  canvas.className='wow-v3-field';canvas.setAttribute('aria-hidden','true');
  stage.insertBefore(canvas,stage.firstChild);
  const disc=d.createElement('div');disc.className='wow-v3-accretion';disc.setAttribute('aria-hidden','true');
  stage.insertBefore(disc,canvas.nextSibling);
  for(const orb of stage.querySelectorAll('.planet')){
   if(orb.querySelector('.wow-v3-crust'))continue;
   const crust=d.createElement('span');crust.className='wow-v3-crust';crust.setAttribute('aria-hidden','true');orb.insertBefore(crust,orb.firstChild);
  }
  const planets=Array.from(stage.querySelectorAll('button.planet'));
  planets.forEach((planet,index)=>{
   planet.addEventListener('keydown',ev=>{
    if(ev.altKey||ev.ctrlKey||ev.metaKey||ev.shiftKey)return;
    let next=index;
    if(ev.key==='ArrowRight'||ev.key==='ArrowDown')next=(index+1)%planets.length;
    else if(ev.key==='ArrowLeft'||ev.key==='ArrowUp')next=(index+planets.length-1)%planets.length;
    else if(ev.key==='Home')next=0;
    else if(ev.key==='End')next=planets.length-1;
    else return;
    ev.preventDefault();planets[next]?.focus();
   });
  });
  let ctx=null;
  try{ctx=canvas.getContext('2d',{alpha:true});}catch{}
  if(!ctx)return;
  let width=0,height=0,dpr=1,raf=0,last=0,disposed=false,frameIndex=0;
  const stars=[];
  let seed=0x4e4f5821;
  function rnd(){seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/4294967296;}
  for(let i=0;i<112;i++)stars.push({x:rnd(),y:rnd(),size:.45+rnd()*1.65,phase:rnd()*6.28318,speed:.28+rnd()*.72,warm:rnd()>.56});
  function active(){return !disposed&&!dataSaver&&!reduce?.matches&&body.dataset.fx!=='ECO'&&d.visibilityState!=='hidden'&&width>520;}
  function resize(){
   if(disposed)return;
   const r=stage.getBoundingClientRect();width=Math.max(1,Math.round(r.width));height=Math.max(1,Math.round(r.height));
   dpr=Math.min(w.devicePixelRatio||1,1.5);
   const pw=Math.round(width*dpr),ph=Math.round(height*dpr);
   if(canvas.width!==pw||canvas.height!==ph){canvas.width=pw;canvas.height=ph;}
   ctx.setTransform(dpr,0,0,dpr,0,0);paint(0);resume();
  }
  function paint(t){
   ctx.clearRect(0,0,width,height);
   const max=body.dataset.fx==='MAX';
   const count=active()?(max?112:65):22;
   for(let i=0;i<count;i++){
    const star=stars[i],phase=t*.0003*star.speed+star.phase;
    const drift=active()?Math.sin(phase)*.015:0;
    const x=(star.x+drift)*width,y=(star.y+Math.cos(phase)*.005)*height;
    const a=active()?(max?.48:.36)+.28*Math.sin(phase)**2:.26;
    ctx.beginPath();ctx.fillStyle=star.warm?'rgba(255,210,157,'+a+')':'rgba(161,219,244,'+a+')';
    ctx.arc(x,y,star.size*(max?1.15:1),0,Math.PI*2);ctx.fill();
   }
   if(!active())return;
   const cx=width*.5,cy=height*.49;
   const radians=t*.00013;
   ctx.save();ctx.translate(cx,cy);ctx.rotate(-.26);
   ctx.beginPath();ctx.ellipse(0,0,width*.355,height*.28,0,0,Math.PI*2);
   ctx.strokeStyle=max?'rgba(245,185,124,.14)':'rgba(245,185,124,.08)';
   ctx.lineWidth=1.1;ctx.stroke();
   const x=Math.cos(radians)*width*.355,y=Math.sin(radians)*height*.28;
   const g=ctx.createRadialGradient(x,y,0,x,y,max?17:10);
   g.addColorStop(0,'rgba(255,226,174,.75)');g.addColorStop(1,'rgba(255,226,174,0)');
   ctx.fillStyle=g;ctx.beginPath();ctx.arc(x,y,max?17:10,0,Math.PI*2);ctx.fill();ctx.restore();
  }
  function tick(t){
   raf=0;if(!active())return;
   const ms=body.dataset.fx==='MAX'?33:50;
   if(t-last>=ms){last=t;frameIndex++;paint(t);}
   raf=w.requestAnimationFrame(tick);
  }
  function resume(){
   if(raf){w.cancelAnimationFrame(raf);raf=0;}
   if(disposed)return;
   if(active()&&typeof w.requestAnimationFrame==='function')raf=w.requestAnimationFrame(tick);
   else paint(0);
  }
  let observer=null;
  if(typeof MutationObserver!=='undefined'){
   observer=new MutationObserver(resume);
   observer.observe(body,{attributes:true,attributeFilter:['data-fx']});
  }
  const onVisibility=()=>resume();
  d.addEventListener('visibilitychange',onVisibility);
  w.addEventListener('resize',resize,{passive:true});
  reduce?.addEventListener?.('change',resume);
  function dispose(){
   disposed=true;
   if(raf)w.cancelAnimationFrame(raf);
   observer?.disconnect();d.removeEventListener('visibilitychange',onVisibility);
   w.removeEventListener('resize',resize);reduce?.removeEventListener?.('change',resume);
  }
  w.addEventListener('pagehide',dispose,{once:true});
  resize();
 }
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});
 else boot();
})();
