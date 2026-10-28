/* NOX V16: ACTUAL owner-approved nine-sphere D02 runtime mount.
 * Uses the exact E01 owner renderer (pinned Git blob). Never creates a ninth CoreID, routes,
 * numerical training progress, new event bus, model process or storage.
 * Fail-closed if the original R13 core identity/geometry differs.
 */
import {installNoxCinemaFX} from '../canonical/nox-cinema.mjs';

export const CANONICAL_CORES=Object.freeze([
  'CONSCIOUSNESS','PERSONA','ATLAS','VOICE','REFLECTION','CORE','NEXUS','FORGE'
]);
let mounted=null,observer=null,bodyObserver=null;

export function mountApprovedHome(doc=document){
  if(mounted)return mounted;
  const home=doc.getElementById('home');
  const stage=home?.querySelector('.nox-orbit-stage');
  if(!home||!stage||!home.classList.contains('screen'))
    throw Error('D02_HOME_APPROVED_ORBIT_STAGE_REQUIRED');
  const central=stage.querySelector('.nox-eclipse');
  const items=[...stage.querySelectorAll('.nox-orbit-core')];
  const ids=items.map(e=>e.dataset.coreId);
  if(!central||items.length!==8||ids.some((v,i)=>v!==CANONICAL_CORES[i])||
      stage.querySelectorAll('.nox-eclipse').length!==1 ||
      new Set(ids).size!==8 ||
      [...items,central].some(e=>e.getAttribute('data-nox-verified-fx')==='active'))
    throw Error('D02_EXACT_HELION_PLUS_EIGHT_CORE_LOCK');
  const orbs=[{id:'HELION',element:central},...items.map((element,i)=>({id:CANONICAL_CORES[i],element}))];
  const view=doc.defaultView;
  if(!view)throw Error('D02_WINDOW_REQUIRED');
  function chosenMode(){
    if(view.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches)return 'REDUCED';
    const body=doc.body;
    return body.classList.contains('nox-wow-eco')?'ECO':
      body.classList.contains('nox-wow-max')?'MAX':'BALANCED';
  }
  // Existing approved PR30 source owns the visual physics of these exact nine
  // elements. No trusted events are supplied until the native bridge is attested.
  const scene=installNoxCinemaFX({root:stage,orbs,profile:chosenMode()});
  try{
    const sync=()=>{scene.setVisible(home.classList.contains('active'));
      scene.setProfile(chosenMode());};
    observer=new view.MutationObserver(sync);
    observer.observe(home,{attributes:true,attributeFilter:['class']});
    bodyObserver=new view.MutationObserver(sync);
    bodyObserver.observe(doc.body,{attributes:true,attributeFilter:['class']});
    for(const element of [central,...items])element.dataset.noxVerifiedFx='active';
    sync();
    mounted=Object.freeze({
      snapshot:()=>({...scene.snapshot(),kind:'decorative-d02',backendAccepted:false,source:'E01_OWNER_PINNED'}),
      setProfile:mode=>scene.setProfile(mode),
      destroy(){observer?.disconnect();bodyObserver?.disconnect();observer=null;bodyObserver=null;
        for(const element of [central,...items])delete element.dataset.noxVerifiedFx;
        scene.destroy();mounted=null;}
    });
    return mounted;
  }catch(error){observer?.disconnect();bodyObserver?.disconnect();scene.destroy();throw error;}
}
function boot(){
  try{mountApprovedHome(document)}
  catch(error){
    // Local interface should remain usable even if a visual integration is held.
    // Never overwrite a user-visible project success status or fabricate telemetry.
    const h=document.getElementById('home');
    if(h)h.dataset.noxCinemaFx='hold';
    console.warn('NOX D02 CINEMA FX HOLD',error?.message||'UNKNOWN');
  }
}
if(typeof document!=='undefined'){
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});
  else boot();
}