/** NOX HUD V7 adapter: decorates original native-owner page, does not own actions or telemetry. */
import {mountNoxHoloMotion} from './nox-holo-runtime-v7.mjs';
(function(){
  'use strict';
  const doc=document,root=doc.querySelector('.shell');
  if(!root)return;
  const owner=doc.body;
  const media=window.matchMedia?.('(prefers-reduced-motion: reduce)');
  let disposed=false,scheduled=false;
  const classes=[
    ['.metrics','nox-holo-instrument'],
    ['.sidebar','nox-holo-instrument'],
    ['.details:not([hidden])','nox-holo-instrument'],
    ['.core-section','nox-holo-instrument'],
    ['#status','nox-holo-instrument'],
    ['.sun','nox-holo-core'],
    ['.sun-ring','nox-holo-rim'],
    ['.orbit','nox-holo-rim'],
    ['.core','nox-holo-node'],
    ['.planet','nox-holo-node']
  ];
  function decorate(){
    if(disposed)return;
    for(const [selector,name] of classes){
      for(const element of root.querySelectorAll(selector))element.classList.add(name);
    }
    for(const el of root.querySelectorAll('.nox-holo-node')){
      const i=Array.prototype.indexOf.call(el.parentElement?.children||[],el);
      el.style.setProperty('--nox-delay',(-Math.max(0,i%13)*.31)+'s');
    }
    // Explicit native evidence only: a styled instrument is not a source of data.
    const active=doc.querySelector('[data-nox-owner-verified="true"][data-nox-live="true"]');
    for(const indicator of root.querySelectorAll('.nox-holo-live'))indicator.dataset.live=String(Boolean(active));
    root.dataset.noxMotion=(owner.dataset.fx==='ECO'||media?.matches||doc.visibilityState==='hidden')?'off':'on';
  }
  const unmount=mountNoxHoloMotion(root,{isLive:()=>Boolean(doc.querySelector('[data-nox-owner-verified="true"][data-nox-live="true"]'))});
  const schedule=()=>{if(disposed||scheduled)return;scheduled=true;queueMicrotask(()=>{scheduled=false;decorate()})};
  const observer=new MutationObserver(records=>{
    if(records.some(r=>r.type==='childList'||(r.type==='attributes'&&r.attributeName==='hidden')))schedule();
  });
  observer.observe(root,{subtree:true,childList:true,attributes:true,attributeFilter:['hidden']});
  const modeObserver=new MutationObserver(schedule);
  modeObserver.observe(owner,{attributes:true,attributeFilter:['data-fx']});
  doc.addEventListener('visibilitychange',schedule);
  media?.addEventListener?.('change',schedule);
  window.addEventListener('pagehide',()=>{
    disposed=true;observer.disconnect();modeObserver.disconnect();
    doc.removeEventListener('visibilitychange',schedule);
    media?.removeEventListener?.('change',schedule);
    unmount();
  },{once:true});
  decorate();
})();
