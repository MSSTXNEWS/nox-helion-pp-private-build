/* E01 WOW MAX10: T01 original 9 orbs, T02 8 distinct CoreID,
   T03 eight EXPRESS MENU tiles + five controls; ten legacy submenu worlds optional, T04 preserve original nodes,
   T05 secondary WOW must never replace D02 HOME. */
import {validateScene} from "../../NOX-CINEMA-FX/nox-cinema.mjs";
const ID=/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const MODES=new Set(["ECO","BALANCED","MAX","REDUCED"]);
const APPROVED_MENU_TILES=Object.freeze(["work","intelligence","knowledge","creative","people","development","world","system"]);
const OWNER_MENU_WORLDS=Object.freeze(["work","intelligence","knowledge","learning","entertainment","people","creative","business","world","pc"]);
// 10 logical worlds are mapped to 8 existing approved physical tiles.
export const LOGICAL_MENU_PARENTS=Object.freeze({
 work:"work",intelligence:"intelligence",knowledge:"knowledge",
 learning:"development",entertainment:"creative",people:"people",
 creative:"creative",business:"work",world:"world",pc:"system"
});
const validId=x=>typeof x==="string"&&ID.test(x);
const inside=(root,node)=>!!node&&node.nodeType===1&&root.contains(node);
function checkEntries(root,items,expected,kind){
  if(!Array.isArray(items)||items.length!==expected)throw Error(kind+"_COUNT");
  const ids=new Set(),routes=new Set(),elements=new Set();
  for(const x of items){
    if(!validId(x?.id)||!validId(x?.routeId)||
       !inside(root,x?.element)||ids.has(x.id)||routes.has(x.routeId)||
       elements.has(x.element))
      throw Error(kind+"_IDENTITY_OR_DOM");
    ids.add(x.id);routes.add(x.routeId);elements.add(x.element);
  }
  return {elements,routes};
}
export function validateOwnerP01(spec){
  const {root,orbs,menu,logicalMenu: optionalWorlds,buttons,secondary,hostPort}=spec||{};
  // EXPRESS has eight required MENU directions; legacy worlds are optional.
  const logicalMenu=optionalWorlds??[];
  if(!root||root.nodeType!==1||typeof root.contains!=="function"||
     !root.ownerDocument?.addEventListener)throw Error("ORIGINAL_ROOT_REQUIRED");
  validateScene(orbs);
  if(orbs.some(x=>!inside(root,x.element)))throw Error("ORIGINAL_NINE_ORBS_REQUIRED");
  // Eight approved visual tiles are immutable; ten old navigation worlds
  // remain real submenu DOM nodes, not two invented top-level graphics.
  const m=checkEntries(root,menu,8,"EIGHT_MENU_TILES");
  if(menu.some((entry,index)=>entry.id!==APPROVED_MENU_TILES[index]))
    throw Error("EIGHT_MENU_OWNER_TILE_IDENTITY_HOLD");
  const l=checkEntries(root,logicalMenu,logicalMenu.length===0?0:10,"TEN_LOGICAL_ROUTES");
  if(logicalMenu.some((entry,index)=>entry.id!==OWNER_MENU_WORLDS[index] ||
      entry.parentTileId!==LOGICAL_MENU_PARENTS[entry.id]))
    throw Error("TEN_LOGICAL_MENU_PARENT_OR_WORLD_HOLD");
  const b=checkEntries(root,buttons,5,"FIVE_BUTTONS");
  const allRoutes=[...m.routes,...l.routes,...b.routes];
  if(new Set(allRoutes).size!==allRoutes.length)
    throw Error("MENU_BUTTON_ROUTE_COLLIDE");
  const nodes=[...orbs.map(x=>x.element),...m.elements,...l.elements,...b.elements];
  if(new Set(nodes).size!==nodes.length)throw Error("ORIGINAL_NODES_COLLIDE");
  if(secondary!=null&&(!inside(root,secondary)||
     secondary.dataset?.noxWowSlot!=="secondary"||
     secondary.closest?.('[data-nox-page="home"]')))
    throw Error("SECONDARY_WOW_CANNOT_REPLACE_HOME");
  if(typeof hostPort?.isAvailable!=="function"||
     typeof hostPort?.invokeRoute!=="function"||
     typeof hostPort?.subscribeNative!=="function")
    throw Error("E06_NATIVE_PORT_REQUIRED");
  return Object.freeze({helion:1,cores:8,menuTiles:8,logicalMenuRoutes:logicalMenu.length,buttons:5,
    wow51to200:secondary!=null,existingNodesPreserved:true});
}
export function shortcutRoute(e,{homeActive=false,searchRoute,fullscreenRoute,escapeRoute}={}){
  if(!e||e.defaultPrevented||e.isComposing||e.altKey||e.repeat||
     e.isTrusted===false)return null;
  const key=String(e.key||"").toLowerCase();
  const mod=e.ctrlKey===true||e.metaKey===true;
  const edit=Boolean(e.target?.isContentEditable ||
    /^(INPUT|TEXTAREA|SELECT)$/i.test(e.target?.tagName||"") ||
    e.target?.closest?.('[contenteditable="true"],[role="textbox"]'));
  if(mod&&key==="k"&&!homeActive&&!e.shiftKey&&!edit&&
     !(e.ctrlKey===true&&e.metaKey===true)&&validId(searchRoute))
    return searchRoute;
  // HOME keeps the approved native fullscreen/escape controls; only palette is hidden.
  if(!mod&&!e.shiftKey&&key==="f11"&&validId(fullscreenRoute))
    return fullscreenRoute;
  if(!mod&&!e.shiftKey&&!edit&&key==="escape"&&validId(escapeRoute))
    return escapeRoute;
  return null;
}
export function validateMode(mode){return MODES.has(mode);}
