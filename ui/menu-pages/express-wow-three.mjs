/* WOW donor #22: original local Three.js, lazy loaded only for MAX rendering.
 * No external CDN, no duplicate app, no privileged bridge or navigation changes. */
(function(){
 'use strict';
 const d=document,w=window;
 function boot(){
  const stage=d.querySelector('.universe'),body=d.body;
  if(!stage||!body||stage.dataset.wowThreeMounted)return;
  stage.dataset.wowThreeMounted='1';
  const reduce=w.matchMedia?.('(prefers-reduced-motion: reduce)');
  const saveData=!!w.navigator?.connection?.saveData;
  const canStart=()=>body.dataset.fx==='MAX' && !reduce?.matches && !saveData && d.visibilityState!=='hidden';
  let instance=null,pending=null,disposed=false;
  const canvas=d.createElement('canvas');
  canvas.className='nox-wow-three';canvas.hidden=true;canvas.setAttribute('aria-hidden','true');
  stage.insertBefore(canvas,stage.firstChild);
  function loadEngine(){
   if(w.THREE)return Promise.resolve(w.THREE);
   if(pending)return pending;
   pending=new Promise((resolve,reject)=>{
    const script=d.createElement('script');
    script.src=new URL('./three.min.js',import.meta.url).href;
    script.async=true;
    script.onload=()=>w.THREE?resolve(w.THREE):reject(new Error('Three.js did not register'));
    script.onerror=()=>reject(new Error('local Three.js asset unavailable'));
    d.head.appendChild(script);
   });
   return pending;
  }
  async function sync(){
   if(disposed)return;
   if(!canStart()){instance?.sync();canvas.hidden=true;return;}
   if(instance){instance.sync();return;}
   try{
    const THREE=await loadEngine();
    if(disposed||!canStart())return;
    const mod=await import('./nox-wow-scene.js');
    if(disposed||!canStart())return;
    instance=mod.mountNoxWow(canvas,THREE,w);
    if(!instance){canvas.hidden=true;stage.dataset.wowThreeState='fallback';}
    else stage.dataset.wowThreeState='active';
   }catch{
    canvas.hidden=true;
    stage.dataset.wowThreeState='fallback'; /* Keep original V3/AURUM atmosphere. */
   }
  }
  let mo=null;
  if(w.MutationObserver){
   mo=new w.MutationObserver(sync);
   mo.observe(body,{attributes:true,attributeFilter:['data-fx']});
  }
  function dispose(){
   disposed=true;mo?.disconnect();instance?.dispose();
   d.removeEventListener('visibilitychange',sync);
   reduce?.removeEventListener?.('change',sync);
   w.removeEventListener('pagehide',dispose);
  }
  reduce?.addEventListener?.('change',sync);
  d.addEventListener('visibilitychange',sync);
  w.addEventListener('pagehide',dispose,{once:true});
  sync();
 }
 if(d.readyState==='loading')d.addEventListener('DOMContentLoaded',boot,{once:true});
 else boot();
})();
