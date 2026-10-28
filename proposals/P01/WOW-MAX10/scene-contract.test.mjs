import test from "node:test";
import assert from "node:assert/strict";
import {validateOwnerP01,shortcutRoute,validateMode} from "./scene-contract.mjs";
import {reviewWowScopes} from "../../NOX-WOW-UNIFIED-1-150/gate.mjs";
const node=()=>({nodeType:1,inside:true,addEventListener(){},removeEventListener(){}});
function fixture(){
 const root={nodeType:1,ownerDocument:{addEventListener(){}},
   contains(el){return el?.inside===true;}};
 const orbs=["HELION",...Array.from({length:8},(_,i)=>"fixture-core-"+(i+1))]
   .map(id=>({id,element:node()}));
 const entries=(count,prefix)=>Array.from({length:count},(_,i)=>({
   id:prefix+(i+1),routeId:prefix+".action."+(i+1),element:node()}));
 const hostPort={isAvailable:()=>true,invokeRoute:async()=>({ok:false}),
   subscribeNative:()=>()=>{}};
 return {root,orbs,menu:entries(8,"menu"),buttons:entries(5,"action"),
   secondary:null,hostPort};
}
test("T01 original 9 nodes and T02 unique 8 CoreID",()=>{
 assert.equal(validateOwnerP01(fixture()).cores,8);
 const x=fixture();x.orbs[1].id="HELION";
 assert.throws(()=>validateOwnerP01(x),/CORE_IDS/);
});
test("T03 eight MENU routes are required",()=>{
 const x=fixture();x.menu.pop();
 assert.throws(()=>validateOwnerP01(x),/EIGHT_MENU_COUNT/);
});
test("T04 five real function buttons are required",()=>{
 const x=fixture();x.buttons.pop();
 assert.throws(()=>validateOwnerP01(x),/FIVE_BUTTONS_COUNT/);
});
test("T05 no duplicate original UI DOM nodes",()=>{
 const x=fixture();x.menu[0].element=x.orbs[0].element;
 assert.throws(()=>validateOwnerP01(x),/ORIGINAL_NODES_COLLIDE/);
});
test("T06 no HOME replacement by secondary WOW",()=>{
 const x=fixture();x.secondary=node();
 x.secondary.dataset={noxWowSlot:"secondary"};
 x.secondary.closest=()=>({dataset:{noxPage:"home"}});
 assert.throws(()=>validateOwnerP01(x),/CANNOT_REPLACE_HOME/);
});
test("T07 native E06 host port mandatory",()=>{
 const x=fixture();delete x.hostPort.invokeRoute;
 assert.throws(()=>validateOwnerP01(x),/E06_NATIVE_PORT_REQUIRED/);
});
test("T08 Ctrl+K scoped outside HOME and F11/Escape native routes",()=>{
 const shortcuts={searchRoute:"ui.search",fullscreenRoute:"ui.fullscreen",escapeRoute:"ui.close"};
 assert.equal(shortcutRoute({key:"k",ctrlKey:true},shortcuts),"ui.search");
 assert.equal(shortcutRoute({key:"k",ctrlKey:true},{...shortcuts,homeActive:true}),null);
 assert.equal(shortcutRoute({key:"F11"},shortcuts),"ui.fullscreen");
 assert.equal(shortcutRoute({key:"Escape"},shortcuts),"ui.close");
});
test("T09 ECO/BALANCED/MAX/REDUCED only",()=>{
 for(const mode of ["ECO","BALANCED","MAX","REDUCED"])assert.equal(validateMode(mode),true);
 assert.equal(validateMode("SUPERFAKE"),false);
});
test("T10 one WOW 51-200 source registry, not EXE acceptance",()=>{
 const s=reviewWowScopes();
 assert.equal(s.groups.aggregate,150);
 assert.equal(s.notEquivalentToAcceptedExe,true);
});

test("T01 duplicate MENU route IDs are blocked even when labels differ",()=>{
 const x=fixture();x.menu[1].routeId=x.menu[0].routeId;
 assert.throws(()=>validateOwnerP01(x),/EIGHT_MENU_IDENTITY_OR_DOM/);
});
test("T02 a privileged button must not shadow a MENU action",()=>{
 const x=fixture();x.buttons[0].routeId=x.menu[0].routeId;
 assert.throws(()=>validateOwnerP01(x),/MENU_BUTTON_ROUTE_COLLIDE/);
});
test("T03 synthetic keyboard events cannot invoke native routes",()=>{
 const config={searchRoute:"ui.search",fullscreenRoute:"ui.fullscreen"};
 assert.equal(shortcutRoute({key:"k",ctrlKey:true,isTrusted:false},config),null);
 assert.equal(shortcutRoute({key:"F11",isTrusted:false},config),null);
});
test("T04 HOME blocks palette but retains native fullscreen and escape",()=>{
 const config={homeActive:true,searchRoute:"ui.search",
   fullscreenRoute:"ui.fullscreen",escapeRoute:"ui.close"};
 assert.equal(shortcutRoute({key:"k",ctrlKey:true},config),null);
 assert.equal(shortcutRoute({key:"F11"},config),"ui.fullscreen");
 assert.equal(shortcutRoute({key:"Escape"},config),"ui.close");
});
test("T05 editable controls and modified/repeated keys never hijack text input",()=>{
 const config={searchRoute:"ui.search",escapeRoute:"ui.close",
   fullscreenRoute:"ui.fullscreen"};
 assert.equal(shortcutRoute({key:"k",ctrlKey:true,target:{tagName:"INPUT"}},config),null);
 assert.equal(shortcutRoute({key:"Escape",target:{isContentEditable:true}},config),null);
 assert.equal(shortcutRoute({key:"k",ctrlKey:true,shiftKey:true},config),null);
 assert.equal(shortcutRoute({key:"k",ctrlKey:true,metaKey:true},config),null);
 assert.equal(shortcutRoute({key:"F11",repeat:true},config),null);
 assert.equal(shortcutRoute({key:"F11",target:{tagName:"INPUT"}},config),"ui.fullscreen");
});
