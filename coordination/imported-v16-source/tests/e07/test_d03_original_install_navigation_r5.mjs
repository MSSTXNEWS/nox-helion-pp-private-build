// D03 R5: node --test tests/e07/test_d03_original_install_navigation_r5.mjs
// Execute the original staged handler. No fake native consent/EXIT/NO-LOSS proof.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
const source=readFileSync(new URL('../../coordination/express/stage_original_five_primary.py',import.meta.url),'utf8');
const builder=readFileSync(new URL('../../coordination/e06/build_onehost_installer.ps1',import.meta.url),'utf8');
function probe(mode,clicks=1){
 const guard=source.indexOf("let originalInstallDelegated=false;");
 const start=source.indexOf("nav.addEventListener('click',event=>{");
 assert.ok(guard>=0&&guard<start);
 const end=source.indexOf("\n// Read-only original A1",start);
 assert.ok(start>=0&&end>start);
 let cb,invoked=0,navInvoked=0,active=false,prevented=false;
 const state={textContent:''};
 const owner={tagName:'BUTTON',isConnected:true,disabled:false,getClientRects(){return [1]},
  focus(){if(mode==='focus-throws')throw Error('disposed native owner focus');doc.activeElement=owner},
  click(){invoked++;if(mode==='owner-throws')throw Error('owner aborted after dispatch');}};
 const primary={getClientRects(){return [1]},closest(){return primary},
  getAttribute(k){return k==='data-nox-primary'?'INSTALL':null}};
 const navControl={click(){navInvoked++;if(mode==='nav-throws')throw Error('disposed original route');active=true;}};
 const doc={activeElement:null,querySelectorAll(sel){
   if(sel==='.nav button[data-screen="control"]')return [navControl];
   if(sel==='button#pc-install')return [owner];return [];},
  getElementById(id){return id==='control'?{classList:{contains:k=>k==='active'&&active}}:null}};
 const nav={contains(){return true},addEventListener(type,fn){assert.equal(type,'click');cb=fn;}};
 Function('nav','state','document','originalPrimaryButtons','verifiedOriginalPrimaryDock',
   'originalInstallTransportPresent','originalNavigationAllowed','visibleOriginalOwnerTarget',
   'findOriginalControl','findOriginalScreen',source.slice(guard,end))(
   nav,state,doc,[primary],()=>true,()=>true,()=>true,()=>true,()=>null,()=>null);
 for(let i=0;i<clicks;i++)
   assert.doesNotThrow(()=>cb({target:primary,isTrusted:true,preventDefault(){prevented=true;}}));
 assert.equal(navInvoked,1);assert.equal(prevented,true);
 return {invoked,state:state.textContent,navInvoked};
}
test('INSTALL original navigation throws: no owner action and visible HOLD',()=>{
 const r=probe('nav-throws');assert.equal(r.invoked,0);assert.match(r.state,/HOLD/);
});
test('INSTALL original focus throws: no owner action and visible HOLD',()=>{
 const r=probe('focus-throws');assert.equal(r.invoked,0);assert.match(r.state,/HOLD/);
});
test('INSTALL healthy original route still executes only one original owner click',()=>{
 const r=probe('ok');assert.equal(r.invoked,1);assert.match(r.state,/не подтверждён/);
});
test('INSTALL repeated trusted shortcut cannot launch duplicate original owner action',()=>{
 const r=probe('ok',2);
 assert.equal(r.invoked,1);assert.equal(r.navInvoked,1);assert.match(r.state,/HOLD/);
});
test('INSTALL original owner may partially dispatch before throwing: no retry',()=>{
 const r=probe('owner-throws',2);
 assert.equal(r.invoked,1);assert.equal(r.navInvoked,1);assert.match(r.state,/HOLD/);
});
test('one exact original source pin in Windows builder',()=>{
 const bytes=Buffer.from(source,'utf8');
 const hash=createHash('sha1').update(Buffer.from('blob '+bytes.length+String.fromCharCode(0))).update(bytes).digest('hex');
 assert.ok(builder.includes("@{path=$primaryOwner;sha='"+hash+"'}"));
});
