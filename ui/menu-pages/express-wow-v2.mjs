/* NOX HELION EXPRESS / additive WOW layer. No fake telemetry, network or native authority. */
function startWow(){
 const d=document,view=window,stage=d.querySelector('.universe'),sun=d.querySelector('.sun');
 if(!stage||!sun||stage.dataset.wowEnhanced==='1')return;
 stage.dataset.wowEnhanced='1';
 const reduce=view.matchMedia?.('(prefers-reduced-motion: reduce)');
 const fine=view.matchMedia?.('(pointer: fine)');
 const safe=()=>!(reduce?.matches)&&fine?.matches&&d.body?.dataset.fx!=='ECO'&&view.innerWidth>520;
 const slots=[sun,...stage.querySelectorAll('.planet')];
 let frame=0,selected=null;
 function reset(node){node.style.setProperty(node===sun?'--sun-x':'--tilt-x','0deg');node.style.setProperty(node===sun?'--sun-y':'--tilt-y','0deg');}
 function move(ev,node){
  if(!safe())return;
  const rect=node.getBoundingClientRect();
  const nx=Math.max(-1,Math.min(1,((ev.clientX-rect.left)/rect.width-.5)*2));
  const ny=Math.max(-1,Math.min(1,((ev.clientY-rect.top)/rect.height-.5)*2));
  selected={node,nx,ny};
  if(frame)return;
  frame=view.requestAnimationFrame(()=>{
   frame=0;if(!selected)return;
   const p=selected;selected=null;
   // FX/OS motion can switch after pointermove but before this queued frame.
   if(!safe()){slots.forEach(reset);return;}
   p.node.style.setProperty(p.node===sun?'--sun-y':'--tilt-y',String((p.nx*9).toFixed(2))+'deg');
   p.node.style.setProperty(p.node===sun?'--sun-x':'--tilt-x',String((-p.ny*9).toFixed(2))+'deg');
  });
 }
 for(const slot of slots){
  slot.addEventListener('pointermove',ev=>move(ev,slot),{passive:true});
  slot.addEventListener('pointerleave',()=>reset(slot),{passive:true});
  slot.addEventListener('blur',()=>reset(slot));
 }
 // The central graphical HELION body navigates back to the world overview.
 sun.setAttribute('role','button');sun.setAttribute('tabindex','0');
 sun.setAttribute('aria-label','HELION · вернуться ко всем мирам');
 function overview(){d.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));}
 sun.addEventListener('click',overview);
 sun.addEventListener('keydown',ev=>{if(ev.key==='Enter'||ev.key===' '){ev.preventDefault();overview();}});
 const fx=d.getElementById('fx');
 fx?.setAttribute('aria-label','Переключить качество графики: BALANCED, MAX, ECO');
 function resync(){if(!safe()){
  if(frame){view.cancelAnimationFrame(frame);frame=0;}
  selected=null;slots.forEach(reset);
 }}
 fx?.addEventListener('click',resync);
 reduce?.addEventListener?.('change',resync);
 view.addEventListener('pagehide',()=>{
  if(frame){view.cancelAnimationFrame(frame);frame=0;}
  selected=null;slots.forEach(reset);
  reduce?.removeEventListener?.('change',resync);
 },{once:true});
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',startWow,{once:true});
else startWow();
