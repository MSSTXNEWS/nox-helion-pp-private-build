import test from "node:test";import assert from "node:assert/strict";
import {validateOwnerP01,shortcutRoute,validateMode} from "./scene-contract.mjs";
const node=()=>({nodeType:1,inside:true,addEventListener(){},contains(){return false}});
function make(){
 const root={nodeType:1,ownerDocument:{addEventListener(){}},contains:n=>n?.nodeType===1&&n.inside===true&&n!==root};
 const orbs=["HELION",...Array.from({length:8},(_,i)=>"CORE"+(i+1))].map(id=>({id,element:node()}));
 const entries=(n,p)=>Array.from({length:n},(_,i)=>({id:p+i,routeId:p+"."+i,element:node()}));
 const tiles=["work","intelligence","knowledge","creative","people","development","world","system"];
 const worlds=["work","intelligence","knowledge","learning","entertainment","people","creative","business","world","pc"];
 return {root,orbs,menu:tiles.map((id,i)=>({id,routeId:"menu.tile."+(i+1),element:node()})),
   logicalMenu:worlds.map((id,i)=>({id,parentTileId:tiles[i%8],routeId:"menu.world."+(i+1),element:node()})),buttons:entries(5,"button"),
   hostPort:{isAvailable(){},invokeRoute(){},subscribeNative(){}},secondary:null};
}
test("C2.01 nine untouched original elements",()=>assert.equal(validateOwnerP01(make()).cores,8));
test("C2.02 reject duplicate CoreID",()=>{const x=make();x.orbs[2].id=x.orbs[1].id;assert.throws(()=>validateOwnerP01(x));});
test("C2.03 reject orb reusing root",()=>{const x=make();x.orbs[0].element=x.root;assert.throws(()=>validateOwnerP01(x));});
test("C2.04 reject duplicate MENU route",()=>{const x=make();x.menu[1].routeId=x.menu[0].routeId;assert.throws(()=>validateOwnerP01(x));});
test("C2.05 reject duplicate button route",()=>{const x=make();x.buttons[2].routeId=x.buttons[0].routeId;assert.throws(()=>validateOwnerP01(x));});
test("C2.06 reject a foreign detached button",()=>{const x=make();x.buttons[2].element={nodeType:1};assert.throws(()=>validateOwnerP01(x));});
test("C2.07 permit legitimate secondary only",()=>{const x=make();x.secondary=node();x.secondary.dataset={noxWowSlot:"secondary"};assert.equal(validateOwnerP01(x).wow51to200,true);});
test("C2.08 reject WOW on HOME",()=>{const x=make();x.secondary=node();x.secondary.dataset={noxWowSlot:"secondary"};x.secondary.closest=()=>x.root;assert.throws(()=>validateOwnerP01(x));});
test("C2.09 Ctrl+K disabled on HOME; F11 still available",()=>{
 const opts={homeActive:true,searchRoute:"ui.search",fullscreenRoute:"ui.fullscreen"};
 assert.equal(shortcutRoute({key:"k",ctrlKey:true},opts),null);
 assert.equal(shortcutRoute({key:"F11"},opts),"ui.fullscreen");
});
test("C2.10 reduced mode and shortcut filtering",()=>{
 assert.equal(validateMode("REDUCED"),true);assert.equal(validateMode("BAD"),false);
 assert.equal(shortcutRoute({key:"k",ctrlKey:true,shiftKey:true},{searchRoute:"ui.search"}),null);
 assert.equal(shortcutRoute({key:"k",ctrlKey:true,isComposing:true},{searchRoute:"ui.search"}),null);
});
