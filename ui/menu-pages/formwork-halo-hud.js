/* NOX · FORMWORK HALO HUD adaptation
 * Upstream: shellcat-com/formwork-halo (MIT, source signature: deterministic
 * polar radar, orbit dial, seeded blips). Original HUD mechanics adapted to
 * existing HELION .universe, no dummy telemetry, no extra runtime or backend.
 */
(function(){
 'use strict';
 function boot(){
  const d=document,w=window,stage=d.querySelector('.universe'),body=d.body;
  if(!stage||!body||stage.dataset.noxHaloHud==='1')return;
  stage.dataset.noxHaloHud='1';
  const canvas=d.createElement('canvas');canvas.className='nox-halo-radar';
  canvas.setAttribute('aria-hidden','true');stage.insertBefore(canvas,stage.firstChild);
  let ctx;try{ctx=canvas.getContext('2d',{alpha:true});}catch{}
  if(!ctx){canvas.remove();stage.dataset.noxHaloHud='fallback';return;}
  const reduce=w.matchMedia?.('(prefers-reduced-motion: reduce)');
  const saveData=!!w.navigator?.connection?.saveData;
  let width=0,height=0,last=0,raf=0,stopped=false,observer=null,ro=null;
  const tau=Math.PI*2;
  // HALO-style reproducible blips; decoration only, never labelled as sensors.
  let seed=0x4de8ff;
  const rand=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/4294967296;};
  const blips=Array.from({length:7},(_,i)=>({a:rand()*tau,r:.29+rand()*.62,warm:i===2}));
  function active(){return !stopped&&!saveData&&!reduce?.matches&&body.dataset.fx!=='ECO'&&d.visibilityState!=='hidden';}
  function fit(){
   const r=stage.getBoundingClientRect(),pw=Math.max(1,Math.floor(r.width)),ph=Math.max(1,Math.floor(r.height));
   const ratio=Math.min(w.devicePixelRatio||1,1.5);
   if(canvas.width!==Math.floor(pw*ratio)||canvas.height!==Math.floor(ph*ratio)){
    canvas.width=Math.floor(pw*ratio);canvas.height=Math.floor(ph*ratio);
   }
   width=pw;height=ph;ctx.setTransform(ratio,0,0,ratio,0,0);
  }
  function draw(ms){
   if(!width||!height)return;
   ctx.clearRect(0,0,width,height);
   const cx=width*.5,cy=height*.49,rad=Math.min(width*.40,height*.44);
   const motion=active();
   const angle=motion?ms*.00025:-.45;
   ctx.save();ctx.translate(cx,cy);ctx.rotate(-.28);ctx.scale(1,.65);
   for(const scale of [.57,.76,1]){
    ctx.beginPath();ctx.arc(0,0,rad*scale,0,tau);
    ctx.strokeStyle='rgba(127,221,238,.12)';ctx.lineWidth=1;ctx.stroke();
   }
   for(let i=0;i<72;i++){
    const a=i*tau/72;
    const r0=rad*(i%6===0?.94:.97);
    ctx.beginPath();ctx.moveTo(Math.cos(a)*r0,Math.sin(a)*r0);
    ctx.lineTo(Math.cos(a)*rad,Math.sin(a)*rad);
    ctx.strokeStyle='rgba(251,209,158,.28)';ctx.stroke();
   }
   if(motion){
    const gradient=ctx.createRadialGradient(0,0,0,0,0,rad);
    gradient.addColorStop(0,'rgba(104,207,231,0)');
    gradient.addColorStop(.75,'rgba(104,207,231,.018)');
    gradient.addColorStop(1,'rgba(104,207,231,.08)');
    ctx.fillStyle=gradient;
    ctx.beginPath();ctx.moveTo(0,0);ctx.arc(0,0,rad,angle-.36,angle);ctx.closePath();ctx.fill();
    ctx.beginPath();ctx.moveTo(0,0);ctx.lineTo(Math.cos(angle)*rad,Math.sin(angle)*rad);
    ctx.strokeStyle='rgba(148,228,248,.34)';ctx.lineWidth=1.5;ctx.stroke();
   }
   for(const b of blips){
    const x=Math.cos(b.a)*rad*b.r,y=Math.sin(b.a)*rad*b.r;
    ctx.beginPath();ctx.arc(x,y,b.warm?2.3:1.4,0,tau);
    ctx.fillStyle=b.warm?'rgba(249,187,122,.68)':'rgba(145,225,242,.52)';ctx.fill();
   }
   ctx.restore();
  }
  function frame(ms){
   raf=0;if(!active())return;
   if(ms-last >= (body.dataset.fx==='MAX'?32:66)){last=ms;draw(ms);}
   raf=w.requestAnimationFrame(frame);
  }
  function sync(){
   if(raf){w.cancelAnimationFrame(raf);raf=0;}
   if(stopped)return;
   fit();canvas.hidden=body.dataset.fx==='ECO';
   draw(0);
   if(active())raf=w.requestAnimationFrame(frame);
  }
  function dispose(){
   stopped=true;
   if(raf)w.cancelAnimationFrame(raf);
   observer?.disconnect();ro?.disconnect();
   d.removeEventListener('visibilitychange',sync);
   w.removeEventListener('resize',sync);
   w.removeEventListener('pagehide',dispose);
   reduce?.removeEventListener?.('change',sync);
   canvas.remove();
  }
  if(w.MutationObserver){
   observer=new w.MutationObserver(sync);
   observer.observe(body,{attributes:true,attributeFilter:['data-fx']});
  }
  if(w.ResizeObserver){ro=new w.ResizeObserver(sync);ro.observe(stage);}
  d.addEventListener('visibilitychange',sync);
  w.addEventListener('resize',sync,{passive:true});
  w.addEventListener('pagehide',dispose,{once:true});
  reduce?.addEventListener?.('change',sync);
  sync();
 }
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});
 else boot();
})();
