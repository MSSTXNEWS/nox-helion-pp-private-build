import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const src=readFileSync(new URL('./menu.js',import.meta.url),'utf8');
test('original SETTINGS routes to owner-verified HKCU, never direct registry access',()=>{
 assert.match(src,/if\(id==='settings'\)\{nativeSettings\(label\);return;\}/);
 assert.match(src,/createAutostartOwnerFlow\(\(route,payload\)=>client\.request\(route,payload\)\)/);
 assert.match(src,/settingsAutostartOwnerAdmission\(b,issued,event\)/);
 assert.match(src,/b\.id=AUTOSTART_UIA_IDS\[kind\]/);
 assert.match(src,/b\.dataset\.nativeRoute='system\.autostart'/);
 assert.doesNotMatch(src,/reg\s+add|window\.localStorage\.setItem\(['"]autostart/);
});
import {settingsAutostartOwnerAdmission,AUTOSTART_UIA_IDS} from '../onehost-menu-bindings.mjs';
function d06Fixture({kind='on',ariaHidden=null,ariaDisabled=null,type='button',
  role=null,trusted=true,occluded=false,duplicate=false,disabled=false}={}){
  const [key,value]={read:['',''],on:['enabled','true'],off:['enabled','false']}[kind];
  const parent={parentElement:null,hidden:false,inert:false,disabled:false,
    getAttribute(n){return n==='aria-hidden'?ariaHidden:n==='aria-disabled'?ariaDisabled:null;}};
  const button={id:AUTOSTART_UIA_IDS[kind],tagName:'BUTTON',isConnected:true,hidden:false,inert:false,disabled,
    dataset:{nativeRoute:'system.autostart',nativeKey:key,nativeValue:value},parentElement:parent,
    getAttribute(n){return n==='type'?type:n==='role'?role:null;},
    hasAttribute(n){return n==='role'&&role!==null;},
    getBoundingClientRect(){return {left:20,right:120,top:20,bottom:60};},contains(){return false;}};
  button.ownerDocument={defaultView:{innerWidth:1280,innerHeight:720,
    getComputedStyle(){return {display:'block',visibility:'visible',pointerEvents:'auto',opacity:'1'};}},
    querySelectorAll(){return duplicate?[button,button]:[button];},elementFromPoint(){return occluded?{}:button;}};
  return settingsAutostartOwnerAdmission(button,new WeakSet([button]),{isTrusted:trusted,type:'click'});
}
test('D06 native SETTINGS UIA owner rejects ARIA aliases and form side effects',()=>{
  for(const kind of ['read','on','off'])assert.equal(d06Fixture({kind}),true,kind);
  for(const variant of [
    {ariaHidden:'TRUE'},{ariaHidden:' TrUe '},{ariaDisabled:'TRUE'},
    {ariaDisabled:' true '},{type:'submit'},{type:'reset'},
    {role:'link'},{trusted:false},{occluded:true},{duplicate:true},{disabled:true}
  ])assert.equal(d06Fixture(variant),false,JSON.stringify(variant));
});
