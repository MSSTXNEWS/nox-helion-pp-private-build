/* Bind the original vendored liquid-glass-web engine to existing NOX controls.
   No mock renderer, no replacement D02, no changed event handlers. */
import {createLiquidGlass} from './vendor/nox-liquid-glass/liquid-glass.js';
const owned=new WeakSet();let count=0;
const reduced=matchMedia('(prefers-reduced-motion:reduce)');
function apply(){
  if(reduced.matches)return;
  for(const el of document.querySelectorAll('.nox-owner-actions button,.nox-owner-persona')){
    if(owned.has(el)||el.classList.contains('lg-host'))continue;
    try{createLiquidGlass(el,{mode:'css',refraction:18,blur:4,light:12,pointer:false,radius:8});owned.add(el);count++}
    catch(err){console.warn('NOX_GLASS_SURFACE_HOLD',err.message)}
  }
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',apply,{once:true});else apply();
const observer=new MutationObserver(()=>apply());
observer.observe(document.body,{childList:true,subtree:true});
if(reduced.addEventListener)reduced.addEventListener('change',apply);
window.NOX_GLASS_INTEGRATION=Object.freeze({engine:'vendored-liquid-glass-web',attached:()=>count,originalD02Preserved:true});
