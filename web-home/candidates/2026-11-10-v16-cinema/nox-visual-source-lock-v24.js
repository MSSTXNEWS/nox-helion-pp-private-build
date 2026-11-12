/* NOX V24 source-fidelity observer — no extra renderer, material changes or
   new animation engine. Hide the approved-image fallback ONLY after original
   D02 reports a genuine rendered WebGL frame; otherwise preserve fallback. */
(()=>{'use strict';
 const boot=()=>{
  const body=document.body;
  if(body.dataset.page!=='index'||!body.classList.contains('nox-owner-cinema')||window.NOX_VISUAL_SOURCE_LOCK_V24)return;
  // One spatial motion owner: original GSAP if actually running, otherwise
  // original CSS float. Both original visual material effects remain intact.
  body.dataset.noxMotionOwner=window.NOX_OWNER_FIDELITY_V21?.motionEngine==='gsap-vendor'
    ?'GSAP':'CSS_ORIGINAL';
  const canvas=document.getElementById('noxEclipseCanvas');
  const css=[...document.querySelectorAll('link[rel="stylesheet"]')].find(x=>x.href.includes('nox-visual-source-lock-v24.css'));
  const keepLast=()=>{if(css?.parentElement===document.head&&document.head.lastElementChild!==css)document.head.append(css)};
  if(css){
   const observer=new MutationObserver(records=>{
    if(records.some(r=>[...r.addedNodes].some(n=>n.nodeType===1&&n!==css&&(n.nodeName==='STYLE'||n.nodeName==='LINK'))))keepLast();
   });
   observer.observe(document.head,{childList:true});
   keepLast();
   setTimeout(()=>observer.disconnect(),9000);
  }
  let checks=0,probe=null;
  const check=()=>{
   const rendered=window.NOX_CINEMATIC_HEALTH?.snapshot?.()?.core?.realRendered===true;
   body.dataset.noxD02Rendered=String(rendered);
   checks++;
   if(rendered||checks>=24){clearInterval(probe);probe=null}
  };
  const start=()=>{
   if(probe)clearInterval(probe);
   checks=0;probe=setInterval(check,500);check();
  };
  canvas?.addEventListener('webglcontextlost',()=>{
   body.dataset.noxD02Rendered='false';
   if(probe){clearInterval(probe);probe=null}
  },{passive:true});
  canvas?.addEventListener('webglcontextrestored',start,{passive:true});
  start();
  window.NOX_VISUAL_SOURCE_LOCK_V24=Object.freeze({
   engine:'ORIGINAL_D02_AND_PHYSICAL_WORLDS_V7',
   originalMaterialPresets:true,oneApprovedArtworkSource:true,
   separatedArtworkBands:2,physicalGpuAcceptance:'HOLD',
   realD02Frame:()=>body.dataset.noxD02Rendered==='true'
  });
 };
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});
 else boot();
})();