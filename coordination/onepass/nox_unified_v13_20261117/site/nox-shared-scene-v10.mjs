/* Lazy boot of the original scene. No renderer or network prerequisite for chat. */
let scheduled=null,started=false,disposed=false;
function cancel(){if(scheduled!==null){if(window.cancelIdleCallback)cancelIdleCallback(scheduled);else clearTimeout(scheduled);scheduled=null;}}
function mount(){scheduled=null;if(started||disposed||document.hidden)return;started=true;import('./nox-eclipse-backdrop.mjs').catch(()=>{document.documentElement.dataset.noxSceneLoad='HOLD';});}
function arm(){if(!started&&!disposed&&!document.hidden&&scheduled===null)scheduled=window.requestIdleCallback?requestIdleCallback(mount,{timeout:2500}):setTimeout(mount,800);}
document.addEventListener('visibilitychange',()=>{if(document.hidden)cancel();else arm();});
window.addEventListener('pagehide',e=>{cancel();if(!e.persisted)disposed=true;});
window.addEventListener('pageshow',arm);
if(document.readyState==='complete')arm();else window.addEventListener('load',arm,{once:true});
