import test from 'node:test';
import assert from 'node:assert/strict';
import {createP01RouteDispatcher as create} from './route-dispatch.mjs';
import {nativeVisualApproval as visual} from './p01-visual-approval.mjs';
const host = (more={}) => ({isAvailable:()=>true,invokeRoute:async ({routeId})=>({ok:true,routeId,receiptId:'host-ack-1'}),...more});
test('E01-01: ordinary menu route invokes existing host once',async()=>{
 let calls=0;const d=create(host({invokeRoute:async ({routeId})=>{calls++;return {ok:true,routeId,receiptId:'r1'};}}));
 assert.equal((await d.invoke('menu.chat')).ok,true);assert.equal(calls,1);
});
test('E01-02: privileged update needs native consent',async()=>{
 let calls=0;const d=create(host({invokeRoute:async()=>{calls++;return {ok:true};}}));
 assert.equal((await d.invoke('system.update')).reason,'NATIVE_CONSENT_REQUIRED');assert.equal(calls,0);
});
test('E01-03: authorized native update sends ACK',async()=>{
 const d=create(host({authorizeSensitive:async req=>req.routeId==='system.update'}));
 assert.equal((await d.invoke('system.update')).ok,true);
});
test('E01-04: denied user confirmation never calls host action',async()=>{
 let calls=0;const d=create(host({authorizeSensitive:async()=>false,invokeRoute:async()=>{calls++;}}));
 assert.equal((await d.invoke('system.backup')).reason,'NATIVE_CONSENT_DENIED');assert.equal(calls,0);
});
test('E01-05: wrong ACK is not success',async()=>{
 const d=create(host({invokeRoute:async()=>({ok:true,routeId:'other',receiptId:'r1'})}));
 assert.equal((await d.invoke('models.pull')).reason,'ACK_MISSING');
});
test('E01-06: duplicate click during consent stays pending',async()=>{
 let finish;const gate=new Promise(resolve=>finish=resolve);
 const d=create(host({authorizeSensitive:()=>gate}));const first=d.invoke('sip.call');
 assert.equal((await d.invoke('sip.call')).reason,'PENDING');finish(true);assert.equal((await first).ok,true);
});
test('E01-07: revoked capability after consent fails closed',async()=>{
 let n=0;const d=create(host({isAvailable:()=>++n===1,authorizeSensitive:async()=>true}));
 assert.equal((await d.invoke('phone.dial')).reason,'NATIVE_CAPABILITY_HOLD');
});
test('E01-08: close while awaiting user authorization cancels action',async()=>{
 let finish;const gate=new Promise(resolve=>finish=resolve);
 const d=create(host({authorizeSensitive:()=>gate}));const req=d.invoke('system.restart');d.close();finish(true);
 assert.equal((await req).reason,'NATIVE_CONSENT_DENIED');
});
test('E01-09: host capability exception never reports success',async()=>{
 const d=create(host({isAvailable:()=>{throw Error('offline');}}));
 assert.equal((await d.invoke('menu.chat')).reason,'CAPABILITY_CHECK_FAILED');
});
test('E01-10: WOW 101–200 needs distinct native visual approval',()=>{
 const p=host({isAvailable:()=>true});assert.equal(visual(p,'shot',{id:101}),false);
 assert.equal(visual({...p,authorizeVisual:()=>true},'shot',{id:101}),true);
 assert.equal(visual({...p,authorizeVisual:async()=>true},'composition',{id:200}),false);
});
