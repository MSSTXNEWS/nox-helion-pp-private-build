/* Final cinematic orchestration 151–200. No third renderer:
   one mount of existing WOW51-100 and WOW101-150; purely opt-in secondary stage. */
import {createCinematicCues} from "../NOX-WOW51-100/wow51-100.mjs";
import {mountDirector} from "../NOX-WOW101-150/director.mjs";
import {COMPOSITIONS,COMPOSITION_BY_ID,verifyCompositions} from "./catalog.mjs";
const M=new WeakMap();
const MODES=new Set(["MAX","BALANCED","ECO","REDUCED"]);
export function mountFinale(root,{mode="BALANCED",authorize=null,reducedMotion=false}={}){
 verifyCompositions();
 if(!root||root.nodeType!==1||root.dataset?.noxWowSlot!=="secondary"||
 (typeof root.closest==="function"&&root.closest('[data-nox-page="home"]')))throw Error("D02_HOME_LOCK");
 if(M.has(root))throw Error("FINALE_ALREADY_MOUNTED");
 if(!MODES.has(mode)||authorize!==null&&typeof authorize!=="function")throw Error("INVALID_FINALE_OPTIONS");
 const doc=root.ownerDocument;
 if(!doc||typeof doc.createElement!=="function")throw Error("APPROVED_DOCUMENT_REQUIRED");
 // These are the existing rendering implementations. No new RAF, GPU/Canvas, server or model.
 const optic=createCinematicCues(root,{mode,reducedMotion});
 let director;
 try{director=mountDirector(root,{mode,reducedMotion,authorize});}
 catch(e){optic.destroy();throw e;}
 const panel=doc.createElement("div");
 panel.className="nox-finale-optics";panel.setAttribute("aria-hidden","true");
 const label=doc.createElement("output");
 label.className="nox-finale-status";label.textContent="ДЕМО · вторичная сцена";
 label.setAttribute("aria-live","off");
 root.classList.add("nox-finale-scope");
 root.append(panel,label);
 let disposed=false,lastId=null,source=null;
 function show(id,kind){
  if(disposed)throw Error("FINALE_DISPOSED");
  const item=COMPOSITION_BY_ID.get(id);
  if(!item)throw Error("UNKNOWN_FINALE");
  if(kind==="APPROVED_INTERACTION"&&(!authorize||authorize(item)!==true))throw Error("HOST_APPROVAL_REQUIRED");
  // Only offline purely artistic optics are used; IDs 81–90 are excluded.
  optic.preview(item.opticalId);
  // The composition is already host-authorized above; use the existing director preview path
  // to avoid a second, conflicting authorization callback for its internal 101–150 ID.
  director.preview(item.directorId);
  panel.dataset.scene=String(item.id);
  panel.dataset.tone=item.tone;
  panel.dataset.depth=String(item.depth);
  panel.dataset.mode=director.current().mode;
  label.textContent=(kind==="DEMO"?"ДЕМО · ":"ПОДТВЕРЖДЕНО · ")+item.id+" · "+item.title;
  lastId=id;source=kind;return item;
 }
 const api=Object.freeze({
  preview(id){return show(id,"DEMO");},
  activate(id){return show(id,"APPROVED_INTERACTION");},
  setMode(next){if(disposed)throw Error("FINALE_DISPOSED");if(!MODES.has(next))throw Error("INVALID_MODE");optic.setMode(next);director.setMode(next);panel.dataset.mode=director.current().mode;},
  setReducedMotion(v){if(disposed)throw Error("FINALE_DISPOSED");optic.setReducedMotion(v);director.setReducedMotion(v);panel.dataset.mode=director.current().mode;},
  current(){return Object.freeze({id:lastId,source,mode:director.current().mode,directorId:director.current().id,opticId:lastId===null?null:COMPOSITION_BY_ID.get(lastId).opticalId});},
  destroy(){if(disposed)return;disposed=true;director.destroy();optic.destroy();panel.remove();label.remove();root.classList.remove("nox-finale-scope");M.delete(root);}
 });
 M.set(root,api);return api;
}
