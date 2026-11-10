// D03: execute the original R11 delegated INSTALL owner-target admission (not fake IPC).
import {readFileSync} from 'node:fs';
import {strict as assert} from 'node:assert';
import {test} from 'node:test';
const source=readFileSync(new URL('../../coordination/express/stage_original_five_primary.py',import.meta.url),'utf8');
const start=source.indexOf('function visibleOriginalOwnerTarget(button){');
const end=source.indexOf("nav.addEventListener('click'",start);
assert.ok(start>=0&&end>start,'production owner-target function required');
const admission=new Function('document','window','button',source.slice(start,end)+';return visibleOriginalOwnerTarget(button)');
function admit(change={}){
 const rect={left:20,top:30,right:140,bottom:90,width:120,height:60};
 const button={tagName:'BUTTON',isConnected:true,disabled:false,
  getClientRects(){return [{}]},closest(){return null},
  matches(s){return s===':disabled'&&!!this.inheritedDisabled},
  getAttribute(k){return k==='aria-disabled'&&this.ariaDisabled?'true':null},
  getBoundingClientRect(){return rect},contains(){return false},...change};
 const document={documentElement:{clientWidth:320,clientHeight:240},
  elementFromPoint(){return change.occluded?{}:button}};
 const window={getComputedStyle(){return {display:'block',visibility:'visible',pointerEvents:'auto',opacity:'1'}}};
 return admission(document,window,button);
}
test('original enabled INSTALL owner target is accepted',()=>assert.equal(admit(),true));
test('inherited disabled fieldset blocks delegated owner click',()=>assert.equal(admit({inheritedDisabled:true}),false));
test('ARIA-disabled owner blocks delegated click',()=>assert.equal(admit({ariaDisabled:true}),false));
test('native disabled blocks delegated click',()=>assert.equal(admit({disabled:true}),false));
test('inert ancestor blocks delegated click',()=>assert.equal(admit({closest(){return {}}}),false));
test('occluded owner target blocks click',()=>assert.equal(admit({occluded:true}),false));
test('hidden owner target blocks click',()=>assert.equal(admit({getClientRects(){return []}}),false));
