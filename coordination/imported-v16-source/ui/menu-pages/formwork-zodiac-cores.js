/* NOX HELION · FORMWORK ZODIAC (MIT) adapted constellation lines.
 * Visualizes the *existing* 8 CoreID nodes; no duplicate controls, routes,
 * telemetry or continuous animation. Source: shellcat-com/formwork-zodiac.
 */
(function(){
 'use strict';
 function boot(){
  const d=document,w=window,section=d.querySelector('.core-section'),cores=d.querySelector('#cores');
  if(!section||!cores||section.dataset.noxZodiac==='1')return;
  section.dataset.noxZodiac='1';
  const ns='http://www.w3.org/2000/svg';
  const svg=d.createElementNS(ns,'svg');
  svg.classList.add('nox-zodiac-lines');
  svg.setAttribute('aria-hidden','true');
  svg.setAttribute('focusable','false');
  section.insertBefore(svg,cores);
  const make=(tag,attrs)=>{
   const v=d.createElementNS(ns,tag);
   for(const [k,val] of Object.entries(attrs))v.setAttribute(k,String(val));
   svg.append(v);return v;
  };
  let active=true,observer=null;
  function draw(){
   if(!active)return;
   const parent=section.getBoundingClientRect();
   const width=Math.max(1,Math.ceil(parent.width));
   const height=Math.max(1,Math.ceil(parent.height));
   svg.setAttribute('viewBox',`0 0 ${width} ${height}`);
   svg.replaceChildren();
   const nodes=[...cores.querySelectorAll('button.core')].slice(0,8);
   if(nodes.length!==8){section.dataset.noxZodiac='unavailable';return;}
   const centers=nodes.map(button=>{
    const rect=button.getBoundingClientRect();
    return {x:Math.round(rect.left-parent.left+rect.width/2),y:Math.round(rect.top-parent.top+rect.height/2)};
   });
   const path=centers.map((p,i)=>`${i===0?'M':'L'}${p.x} ${p.y}`).join(' ');
   make('path',{d:path,fill:'none',stroke:'#87d6ec','stroke-width':1,'stroke-opacity':.27});
   for(const p of centers){
    make('circle',{cx:p.x,cy:p.y,r:3.2,fill:'#e9c59d','fill-opacity':.42});
   }
   section.dataset.noxZodiac='active';
  }
  if(w.ResizeObserver){observer=new w.ResizeObserver(draw);observer.observe(cores);}
  w.addEventListener('resize',draw,{passive:true});
  w.addEventListener('pagehide',()=>{active=false;observer?.disconnect();w.removeEventListener('resize',draw);},{once:true});
  draw();
 }
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});
 else boot();
})();
