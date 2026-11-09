// D03 R5 · source-derived WebView2 bridge-lifetime regression.
// Does not claim native owner consent, process exit, file readback or E07.
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const owner=readFileSync(new URL('../../coordination/express/stage_original_five_primary.py',import.meta.url),'utf8');
const prefix='function originalInstallTransportPresent(){';
const start=owner.indexOf(prefix),end=owner.indexOf('\n\nnav.addEventListener(',start);
assert.ok(start>=0&&end>start,'original transport owner must be present');
const functionSource=owner.slice(start,end);
function check(window){return vm.runInNewContext(functionSource+'\noriginalInstallTransportPresent();',{window},{timeout:1000});}
test('D03 original INSTALL revalidates live native transport before privileged owner click',()=>{
 const checks=[...owner.matchAll(/if\(name==='INSTALL'&&!originalInstallTransportPresent\(\)\)/g)].map(x=>x.index);
 const nav=owner.indexOf('navControl.click();');
 const focus=owner.indexOf('target.focus({preventScroll:false});');
 const click=owner.indexOf('invokeMatches[0].click();');
 assert.equal(checks.length,2);
 assert.ok(checks[0]<nav && checks[1]>focus && checks[1]<click);
 assert.ok(owner.indexOf('INSTALL: связь с нативным владельцем прервана · HOLD')>focus);
 assert.ok(owner.indexOf('visibleOriginalOwnerTarget(invokeMatches[0])')<checks[1]);
 assert.equal(check({chrome:{webview:{postMessage(){}}}}),true);
 assert.equal(check({}),false);
 assert.equal(check({chrome:{webview:{get postMessage(){throw Error('disposed')}}}}),false);
 let reads=0;
 const torn={chrome:{webview:{get postMessage(){reads++;return reads===1?function alive(){}:undefined}}}};
 assert.equal(check(torn),true);
 assert.equal(check(torn),false);
 assert.equal(reads,2);
});
