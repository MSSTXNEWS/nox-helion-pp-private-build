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
import {settingsAutostartOwnerAdmission,AUTOSTART_UIA_IDS,createAutostartOwnerFlow,nativeAutostartDenialCode} from '../onehost-menu-bindings.mjs';
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

test('D06 native SETTINGS owner refusal: reviewed codes only, no paths or false readback',async()=>{
 const routeId='system.autostart';
 const hold=errorCode=>({routeId,state:'HOLD',errorCode,result:null});
 const refusal=hold('NOX_AUTOSTART_FOREIGN_ENTRY_HOLD');
 assert.equal(nativeAutostartDenialCode(refusal),'NOX_AUTOSTART_FOREIGN_ENTRY_HOLD');
 await assert.rejects(createAutostartOwnerFlow(async()=>refusal).request({enabled:true}),
   {message:'NOX_AUTOSTART_FOREIGN_ENTRY_HOLD'});
 await assert.rejects(createAutostartOwnerFlow(async()=>hold('NATIVE_CONSENT_DENIED')).request({}),
   {message:'NATIVE_CONSENT_DENIED'});
 await assert.rejects(createAutostartOwnerFlow(async()=>hold('SECRET_PATH_NOT_FOR_RENDERER')).request({enabled:false}),
   {message:'NOX_AUTOSTART_WRITE_UNVERIFIED'});
 await assert.rejects(createAutostartOwnerFlow(async()=>({...refusal,routeId:'models.catalog'})).request({}),
   {message:'NOX_AUTOSTART_READ_UNVERIFIED'});
 await assert.rejects(createAutostartOwnerFlow(async()=>({...refusal,state:'COMPLETED'})).request({enabled:true}),
   {message:'NOX_AUTOSTART_WRITE_UNVERIFIED'});
 const written={routeId,state:'COMPLETED',errorCode:null,result:{enabled:true,readOnly:false}};
 await assert.rejects(createAutostartOwnerFlow(async(_,payload)=>
   Object.keys(payload).length?written:hold('NOX_AUTOSTART_HKCU_UNAVAILABLE')).request({enabled:true}),
   {message:'NOX_AUTOSTART_HKCU_UNAVAILABLE'});
 const readback={routeId,state:'COMPLETED',errorCode:null,result:{enabled:true,readOnly:true}};
 const request=async(_,payload)=>Object.keys(payload).length?written:readback;
 assert.equal((await createAutostartOwnerFlow(request).request({enabled:true})).result.enabled,true);
 assert.equal((await createAutostartOwnerFlow(request).request({})).result.readOnly,true);
});

test('D06 separate SETTINGS surfaces serialize one native owner HKCU consent/readback chain',async()=>{
 let release;const gate=new Promise(resolve=>{release=resolve;});
 let writes=0,saved=false;
 const nativeRequest=async(route,payload)=>{
   assert.equal(route,'system.autostart');
   if(Object.keys(payload).length===0)return {routeId:route,state:'COMPLETED',errorCode:null,
     result:{enabled:saved,readOnly:true}};
   writes+=1;
   await gate;
   saved=payload.enabled;
   return {routeId:route,state:'COMPLETED',errorCode:null,
     result:{enabled:saved,readOnly:false}};
 };
 const first=createAutostartOwnerFlow(nativeRequest);
 const second=createAutostartOwnerFlow(nativeRequest);
 const current=first.request({enabled:true});
 const competing=second.request({enabled:false}).then(()=>null,e=>e.message);
 assert.equal(await competing,'NOX_AUTOSTART_OWNER_IN_FLIGHT');
 assert.equal(writes,1,'foreign surface must never dispatch second HKCU action');
 release();
 const result=await current;
 assert.equal(result.result.enabled,true);
 const after=await second.request({enabled:false});
 assert.equal(after.result.enabled,false,'lock must release after verified readback');
 assert.equal(writes,2);
});
