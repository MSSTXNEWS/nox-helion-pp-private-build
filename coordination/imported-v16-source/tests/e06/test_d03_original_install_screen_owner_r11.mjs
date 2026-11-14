/** D03: execute original INSTALL owner admission, no fake native ACK or E07. */
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const source=readFileSync(new URL('../../coordination/express/stage_original_five_primary.py',import.meta.url),'utf8');
const a=source.indexOf('function ariaSuppressed(el){');
const b=source.indexOf('function verifiedOriginalPrimaryDock(){',a);
const c=source.indexOf('function visibleOriginalOwnerTarget(button){');
const e=source.indexOf('// Availability is NOT',c);
assert.ok(a>=0&&b>a&&c>=0&&e>c,'approved production INSTALL owner must exist');
const admission=new Function('document','window','button',source.slice(a,b)+'\n'+source.slice(c,e)+'\nreturn visibleOriginalOwnerTarget(button)');
function probe({moved=false,duplicate=false,inactive=false,other=false,disabled=false}={}){
 const rect={left:30,top:20,right:150,bottom:90,width:120,height:70};
 const button={tagName:'BUTTON',isConnected:true,disabled,parentElement:null,
  getAttribute(k){return k==='id'&&!other?'pc-install':null;},
  getClientRects(){return [{}]},matches(){return false;},closest(){return null;},
  getBoundingClientRect(){return rect;},contains(){return false;}};
 const screen={classList:{contains(k){return k==='active'&&!inactive;}},
  contains(x){return x===button&&!moved;}};
 const doc={documentElement:{clientWidth:400,clientHeight:400},
  querySelectorAll(k){return k==='[id="control"]'?(duplicate?[screen,screen]:[screen]):[];},
  getElementById(k){return k==='control'?screen:null;},elementFromPoint(){return button;}};
 const win={getComputedStyle(){return {display:'block',visibility:'visible',pointerEvents:'auto',opacity:'1'};}};
 return admission(doc,win,button);
}
test('admit visible original INSTALL inside unique active CONTROL, native owner remains separate',()=>assert.equal(probe(),true));
test('reject moved same-id INSTALL',()=>assert.equal(probe({moved:true}),false));
test('reject duplicate native CONTROL root',()=>assert.equal(probe({duplicate:true}),false));
test('reject inactive native CONTROL root',()=>assert.equal(probe({inactive:true}),false));
test('preserve non-INSTALL original owner behavior',()=>assert.equal(probe({other:true}),true));
test('reject disabled owner target',()=>assert.equal(probe({disabled:true}),false));
