'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const {createScopedAdmission}=require('./b4_r66_scoped_admission.cjs');
const {createAdmissionBudget}=require('./b4_r63_admission_budget.cjs');
const {createPreverifierFence}=require('./b4_r64_preverifier_fence.cjs');
const b1=path.resolve(process.argv[2]),b3=path.resolve(process.argv[3]);
const {createWireGuard}=require(path.join(b1,'b1-r74/wire_guard.cjs'));
const {createScopedTransport}=require(path.join(b1,'b1-r76/scoped_transport.cjs'));
const {check:checkScope}=require(b3);
const root={AbortController,TextDecoder,TextEncoder,setTimeout,clearTimeout};
vm.runInNewContext(fs.readFileSync(path.join(b1,'b1-r75/b1_browser_bundle.js'),'utf8'),root);
const {createClient}=root.NOXB1StreamReconnect;
const h=n=>n.toString(16).padStart(64,'0');
const contract={wire:'named-delta-stable-server-id-v1',route:'logical-route',served_sha256:h(21),server_sha256:h(22)};
const physical={route:'/fixture/model',model_id:'fixture',dialog_id:'physical-dialog',weights_manifest_sha256:h(11),tokenizer_manifest_sha256:h(12),bridge_sha256:'c44b5aa2ef3d45246276a24bbcfad30bf76533fc2e08089eb91b442002643dc7',original_checkpoint_sha256:h(13),owner_admission_receipt_sha256:h(14),process:{boot_id:'boot',pid:42,start_ticks:123},turn_request_ids:['req2','req3'],window_start_ms:100,window_end_ms:200};
const mapping={...structuredClone(physical),schema:'NOX_B3_ROUTE_BINDING_V1',wire:contract.wire,symbolic_route:contract.route,served_sha256:contract.served_sha256,server_sha256:contract.server_sha256,conversation_id:'conv',exchange_bindings:[{turn:2,request_id:'req2',exchange_id:'ex2'},{turn:3,request_id:'req3',exchange_id:'ex3'}]};
const s2={conversation_id:'conv',exchange_id:'ex2'},s3={conversation_id:'conv',exchange_id:'ex3'};
function fixture({pre=0,read=0,auth=0,approved=true,foreign=false}={}){
 let t=0;const counts={read:0,auth:0,post:0,ack:0,get:0},events=[];
 const c=createScopedAdmission({createClient,createScopedTransport,createWireGuard,createPreverifierFence,createAdmissionBudget,checkScope,contract,limitMs:5,deadlineMs:1000,now:()=>t,
  readBinding:async(pin,s)=>{counts.read++;t+=read;const m=structuredClone(mapping);if(foreign)m.exchange_bindings[0].exchange_id='foreign';return {physical:structuredClone(physical),mapping:m,expectedTurn:s.exchange_id==='ex3'?3:2};},
  authenticateBinding:async()=>{counts.auth++;t+=auth;return approved;},
  transport:{post:async s=>{counts.post++;const bytes=new TextEncoder().encode('id: stable-'+s.exchange_id+'\nevent: delta\ndata: Привет hola\n\n');return {ok:true,body:new ReadableStream({start(c){c.enqueue(bytes);c.close();}})};},readback:async()=>{counts.get++;return null;},ack:async()=>{counts.ack++;}},
  clientOptions:{host:{readCommitted:async()=>{t+=pre;return null;}},bridge:{acceptTerminal:async()=>null},ui:{onDelta:async(s,text,signal,id)=>{events.push([s.exchange_id,text,id]);return true;},upsertTerminal:async()=>null},timeoutMs:3000}});
 return {c,counts,events};
}
async function hold(f,stage,want){
 await assert.rejects(f.c.begin(s2));await assert.rejects(f.c.begin(s2),{code:'HOLD_B4_R66_NO_REPOST'});
 assert.deepEqual([f.counts.read,f.counts.auth,f.counts.post],want);
 assert.equal(f.c.report(s2).transport_invoked,false);
 if(stage)assert.equal(f.c.report(s2).reason,stage);
 assert.deepEqual(f.events,[]);assert.equal(f.counts.ack,0);
}
(async()=>{
 let f=fixture({pre:1,read:1,auth:1});assert.equal(await f.c.begin(s2),'STREAM_ENDED_READBACK_REQUIRED');assert.equal(await f.c.begin(s3),'STREAM_ENDED_READBACK_REQUIRED');assert.equal(f.counts.post,2);assert.equal(f.counts.auth,2);assert.deepEqual(f.events,[['ex2','Привет hola','stable-ex2'],['ex3','Привет hola','stable-ex3']]);assert.equal(f.c.report(s2).transport_elapsed_ms,3);assert.equal(f.c.report(s3).transport_elapsed_ms,3);assert.equal(f.counts.ack,0);await assert.rejects(f.c.begin(s2),{code:'HOLD_B4_R66_NO_REPOST'});console.log('PASS actual R76/R64/R75 distinct turns2/3, one POST each, EOF not ACK');
 await hold(fixture({pre:5}),'HOLD_B4_R64_EXPIRED_VERIFIER',[0,0,0]);console.log('PASS expired preflight skips binding and auth');
 await hold(fixture({pre:1,read:4}),'HOLD_B4_R66_EXPIRED_AUTH',[1,0,0]);console.log('PASS exact cumulative deadline skips expensive authentication');
 await hold(fixture({pre:1,read:5}),'HOLD_B4_R66_EXPIRED_AUTH',[1,0,0]);console.log('PASS late binding skips expensive authentication');
 await hold(fixture({pre:1,read:1,auth:3}),null,[1,1,0]);console.log('PASS late auth result blocked by final R64/R63 fence');
 await hold(fixture({approved:false}),null,[1,1,0]);console.log('PASS false authentication no POST');
 await hold(fixture({foreign:true}),null,[1,0,0]);console.log('PASS foreign mapping no auth or POST');
 console.log('7/7 SOURCE PASS; synthetic monotonic clock and transport, no native acceptance');
})().catch(e=>{console.error(e);process.exitCode=1;});
