/* E01 C2: preserve original D02 and canonical 8+5 navigation. */
import {validateScene} from "../../NOX-CINEMA-FX/nox-cinema.mjs";
const ID=/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const MODES=new Set(["ECO","BALANCED","MAX","REDUCED"]);
const inside=(root,node)=>!!node&&node.nodeType===1&&root.contains(node);
function checkEntries(root,items,count,kind){
  if(!Array.isArray(items)||items.length!==count)throw Error(kind+"_COUNT");
  const ids=new Set(),routes=new Set(),elements=new Set();
  for(const item of items){
    if(typeof item?.id!=="string"||!ID.test(item.id)||
       typeof item?.routeId!=="string"||!ID.test(item.routeId)||
       !inside(root,item.element)||typeof item.element.addEventListener!=="function"||
       ids.has(item.id)||routes.has(item.routeId)||elements.has(item.element))
      throw Error(kind+"_IDENTITY_OR_DOM");
    ids.add(item.id);routes.add(item.routeId);elements.add(item.element);
  }
  return elements;
}
export function validateOwnerP01(spec){
  const {root,orbs,menu,buttons,secondary,hostPort}=spec||{};
  if(!root||root.nodeType!==1||typeof root.contains!=="function"||
     !root.ownerDocument||typeof root.ownerDocument.addEventListener!=="function")
    throw Error("ORIGINAL_ROOT_REQUIRED");
  validateScene(orbs);
  if(orbs.some(x=>!inside(root,x.element)||x.element===root))
    throw Error("ORIGINAL_NINE_ORBS_REQUIRED");
  const menus=checkEntries(root,menu,8,"EIGHT_MENU");
  const actions=checkEntries(root,buttons,5,"FIVE_BUTTONS");
  const nodes=[...orbs.map(x=>x.element),...menus,...actions];
  if(new Set(nodes).size!==nodes.length)throw Error("ORIGINAL_NODES_COLLIDE");
  if(secondary!=null){
    if(!inside(root,secondary)||secondary===root||
       secondary.dataset?.noxWowSlot!=="secondary"||
       secondary.closest?.('[data-nox-page="home"]')||
       nodes.includes(secondary)||
       orbs.some(x=>x.element.contains?.(secondary)))
      throw Error("SECONDARY_WOW_CANNOT_REPLACE_HOME");
  }
  if(typeof hostPort?.isAvailable!=="function"||
     typeof hostPort?.invokeRoute!=="function"||
     typeof hostPort?.subscribeNative!=="function")
    throw Error("E06_NATIVE_PORT_REQUIRED");
  return Object.freeze({helion:1,cores:8,menu:8,buttons:5,
    wow51to200:secondary!=null,existingNodesPreserved:true});
}
export function shortcutRoute(e,{homeActive=false,searchRoute,fullscreenRoute,escapeRoute}={}){
  if(!e||e.defaultPrevented||e.isComposing||e.altKey)return null;
  const key=String(e.key||"").toLowerCase();
  const modifier=e.ctrlKey===true||e.metaKey===true;
  const shift=e.shiftKey===true;
  if(!homeActive&&modifier&&!shift&&key==="k"&&ID.test(searchRoute))return searchRoute;
  if(!modifier&&!shift&&key==="f11"&&ID.test(fullscreenRoute))return fullscreenRoute;
  if(!modifier&&!shift&&key==="escape"&&ID.test(escapeRoute))return escapeRoute;
  return null;
}
export function validateMode(mode){return typeof mode==="string"&&MODES.has(mode);}
