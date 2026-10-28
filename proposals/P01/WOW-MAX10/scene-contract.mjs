/* E01 WOW MAX10: T01 original 9 orbs, T02 8 distinct CoreID,
   T03 exact 8 MENU + 5 function controls, T04 preserve original nodes,
   T05 secondary WOW must never replace D02 HOME. */
import {validateScene} from "../../NOX-CINEMA-FX/nox-cinema.mjs";
const ID=/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const MODES=new Set(["ECO","BALANCED","MAX","REDUCED"]);
const inside=(root,node)=>!!node&&node.nodeType===1&&root.contains(node);
function checkEntries(root,items,expected,kind){
  if(!Array.isArray(items)||items.length!==expected)throw Error(kind+"_COUNT");
  const ids=new Set(),elements=new Set();
  for(const x of items){
    if(!ID.test(x?.id)||!ID.test(x?.routeId)||
       !inside(root,x?.element)||ids.has(x.id)||elements.has(x.element))
      throw Error(kind+"_IDENTITY_OR_DOM");
    ids.add(x.id);elements.add(x.element);
  }
  return elements;
}
export function validateOwnerP01(spec){
  const {root,orbs,menu,buttons,secondary,hostPort}=spec||{};
  if(!root||root.nodeType!==1||typeof root.contains!=="function"||
     !root.ownerDocument?.addEventListener)throw Error("ORIGINAL_ROOT_REQUIRED");
  validateScene(orbs);
  if(orbs.some(x=>!inside(root,x.element)))throw Error("ORIGINAL_NINE_ORBS_REQUIRED");
  const m=checkEntries(root,menu,8,"EIGHT_MENU");
  const b=checkEntries(root,buttons,5,"FIVE_BUTTONS");
  const nodes=[...orbs.map(x=>x.element),...m,...b];
  if(new Set(nodes).size!==nodes.length)throw Error("ORIGINAL_NODES_COLLIDE");
  if(secondary!=null&&(!inside(root,secondary)||
     secondary.dataset?.noxWowSlot!=="secondary"||
     secondary.closest?.('[data-nox-page="home"]')))
    throw Error("SECONDARY_WOW_CANNOT_REPLACE_HOME");
  if(typeof hostPort?.isAvailable!=="function"||
     typeof hostPort?.invokeRoute!=="function"||
     typeof hostPort?.subscribeNative!=="function")
    throw Error("E06_NATIVE_PORT_REQUIRED");
  return Object.freeze({helion:1,cores:8,menu:8,buttons:5,
    wow51to200:secondary!=null,existingNodesPreserved:true});
}
export function shortcutRoute(e,{homeActive=false,searchRoute,fullscreenRoute,escapeRoute}={}){
  if(!e||homeActive||e.defaultPrevented||e.isComposing||e.altKey)return null;
  const key=String(e.key||"").toLowerCase();
  const mod=e.ctrlKey===true||e.metaKey===true;
  if(mod&&key==="k"&&ID.test(searchRoute))return searchRoute;
  if(!mod&&key==="f11"&&ID.test(fullscreenRoute))return fullscreenRoute;
  if(!mod&&key==="escape"&&ID.test(escapeRoute))return escapeRoute;
  return null;
}
export function validateMode(mode){return MODES.has(mode);}
