/* V21: verified existing GSAP vendor used for gentle independent CoreID motion.
   Explicit disable on reduced motion / ECO / hidden document.
   Uses approved standalone portrait assets, never cuts faces from HOME artwork. */
(()=>{'use strict';
 const init=()=>{
  if(document.body.dataset.page!=='index'||!document.body.classList.contains('nox-owner-cinema'))return;
  const base='./assets/nox-owner-approved/';
  const ids=['kv','am','la','ev','kw'];
  document.querySelectorAll('.nox-owner-persona').forEach((b,i)=>{
   if(ids[i])b.style.setProperty('--nox-persona-image','url("'+base+'nox-owner-persona-'+ids[i]+'.webp")');
  });
  const links=[...document.querySelectorAll('.nox-owner-core')];
  const prefersReduce=matchMedia('(prefers-reduced-motion: reduce)');
  const scheduler=window.gsap,owner=window.NOX_OWNER_HOME_V20;
  const motions=[];
  const offsets=[[-10,6],[8,-7],[-5,4],[11,-4],[-8,6],[7,-5],[-4,-6],[9,5]];
  const shouldMove=()=>!document.hidden&&!prefersReduce.matches&&document.body.dataset.noxOwnerLayout!=='PBR'&&!document.body.classList.contains('nox-eco')&&document.querySelector('[data-mode="ECO"][aria-pressed="true"]')===null;
  if(scheduler&&typeof scheduler.to==='function'){
   links.forEach((el,i)=>{
    const [dx,dy]=offsets[i];const t=scheduler.to(el,{x:dx,y:dy,duration:11+(i%4)*3,repeat:-1,yoyo:true,ease:'sine.inOut',paused:true,delay:-(i*1.65)});
    motions.push(t);
   });
  }
  const sync=()=>{const active=shouldMove();motions.forEach(t=>active?t.resume():t.pause());};
  sync();document.addEventListener('visibilitychange',sync);
  if(prefersReduce.addEventListener)prefersReduce.addEventListener('change',sync);
  new MutationObserver(sync).observe(document.body,{attributes:true,attributeFilter:['data-nox-owner-layout','class']});
  const modeButtons=document.getElementById('homeModes');
  if(modeButtons)modeButtons.addEventListener('click',()=>requestAnimationFrame(sync));
  const state=Object.freeze({motionEngine:scheduler&&typeof scheduler.to==='function'?'gsap-vendor':'static-fallback',
   portraits:ids.length,kind:'existing-D02-plus-approved-art',gpuAcceptance:'HOLD'});
  window.NOX_OWNER_FIDELITY_V21=state;
 };
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();