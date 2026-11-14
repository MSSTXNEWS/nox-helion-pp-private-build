// D03: original R11 INSTALL must not dispatch a privileged native owner action
// from a renderer with no real WebView2 transport. SOURCE_ONLY; WPF/NSIS E07 required.
import {readFileSync} from 'node:fs';
import {strict as assert} from 'node:assert';
import {test} from 'node:test';
const source=readFileSync(new URL('../../coordination/express/stage_original_five_primary.py',import.meta.url),'utf8');
const start=source.indexOf('function originalInstallTransportPresent(){');
const end=source.indexOf("\n\nnav.addEventListener('click',",start);
assert.ok(start>=0 && end>start,'original INSTALL native source gate required');
const fn=new Function('window',source.slice(start,end)+';return originalInstallTransportPresent;');
const bridge={chrome:{webview:{postMessage(){}}}};
test('callable original WebView2 transport is eligible, never considered receipt',()=>assert.equal(fn(bridge)(),true));
test('INSTALL without native host cannot be delegated',()=>{
 for(const host of [{},{chrome:null},{chrome:{}},{chrome:{webview:null}},
                    {chrome:{webview:{postMessage:'spoof'}}}])
  assert.equal(fn(host)(),false);
});
test('broken native host accessor fails closed',()=>{
 const host={};Object.defineProperty(host,'chrome',{get(){throw Error('unavailable');}});
 assert.equal(fn(host)(),false);
});
test('original owner delegated click remains bound behind the new native precondition',()=>{
 const guard=source.indexOf("if(name==='INSTALL'&&!originalInstallTransportPresent())");
 const dispatch=source.indexOf('invokeMatches[0].click()');
 assert.ok(guard>0&&dispatch>guard);
 assert.equal(source.split('invokeMatches[0].click()').length-1,1);
});
