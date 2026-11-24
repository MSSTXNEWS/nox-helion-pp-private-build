'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const {createScopedTransport}=require('./scoped_transport.cjs');
const {createWireGuard}=require('../b1-r74/wire_guard.cjs');
const {check:checkScope}=require(path.resolve(process.argv[2]));
const root={AbortController,TextDecoder,TextEncoder,setTimeout,clearTimeout};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../b1-r75/b1_browser_bundle.js'),'utf8'),root);
const {createClient}=root.NOXB1StreamReconnect;
const h=n=>n.toString(16).padStart(64,'0');
const contract={wire:'named-delta-stable-server-id-v1',route:'logical-route',served_sha256:h(21),server_sha256:h(22)};
const physical={route:'/fixture/model',model_id:'fixture',dialog_id:'physical-dialog',weights_manifest_sha256:h(11),tokenizer_manifest_sha256:h(12),bridge_sha256:'c44b5aa2ef3d45246276a24bbcfad30bf76533fc2e08089eb91b442002643dc7',original_checkpoint_sha256:h(13),owner_admission_receipt_sha256:h(14),process:{boot_id:'boot',pid:42,start_ticks:123},turn_request_ids:['req2','req3'],window_start_ms:100,window_end_ms:200};
const mapping={...structuredClone(physical),schema:'NOX_B3_ROUTE_BINDING_V1',wire:contract.wire,symbolic_route:contract.route,served_sha256:contract.served_sha256,server_sha256:contract.server_sha256,conversation_id:'conv',exchange_bindings:[{turn:2,request_id:'req2',exchange_id:'ex2'},{turn:3,request_id:'req3',exchange_id:'ex3'}]};
const s2={conversation_id:'conv',exchange_id:'ex2'},s3={conversation_id:'conv',exchange_id:'ex3'};
function fixture({mutate=()=>{},auth=async()=>true,deadlineMs=1000}={}){
 const posts=[],gets=[],events=[],acks=[];let authCalls=0;
 const transport=createScopedTransport({createWireGuard,checkScope,contract,deadlineMs,
   readBinding:async(pin,scope)=>{const b={physical:structuredClone(physical),mapping:structuredClone(mapping),expectedTurn:scope.exchange_id==='ex3'?3:2};mutate(b);return b;},
   authenticateBinding:async(...args)=>{authCalls++;assert.ok(Object.isFrozen(args[0].mapping.exchange_bindings));return auth(...args);},
   transport:{post:async(s)=>{posts.push(s.exchange_id);const bytes=new TextEncoder().encode('id: stable-'+s.exchange_id+'\nevent: delta\ndata: Привет hola\n\n');return {ok:true,body:new ReadableStream({start(c){c.enqueue(bytes);c.close();}})};},readback:async(s)=>{gets.push(s.exchange_id);return null;},ack:async(s)=>{acks.push(s.exchange_id);}}});
 const client=createClient({transport,host:{readCommitted:async()=>null},bridge:{acceptTerminal:async()=>null},ui:{onDelta:async(s,t,signal,id)=>events.push([s.exchange_id,t,id]),upsertTerminal:async()=>null},timeoutMs:3000});
 return {client,posts,gets,events,acks,authCalls:()=>authCalls};
}
async function noRepost(f,s){await assert.rejects(f.client.begin(s),{code:'HOLD_STREAM_NO_REPOST'});}
async function getOnly(f,s){await assert.rejects(f.client.reconnect(s));assert.deepEqual(f.gets,[s.exchange_id]);assert.deepEqual(f.acks,[]);}
(async()=>{
 let f=fixture();assert.equal(await f.client.begin(s2),'STREAM_ENDED_READBACK_REQUIRED');assert.equal(await f.client.begin(s3),'STREAM_ENDED_READBACK_REQUIRED');await noRepost(f,s2);await noRepost(f,s3);assert.deepEqual(f.posts,['ex2','ex3']);assert.deepEqual(f.events,[['ex2','Привет hola','stable-ex2'],['ex3','Привет hola','stable-ex3']]);assert.equal(f.authCalls(),2);await getOnly(f,s2);console.log('PASS actual R74 + R69 + R75 distinct turns2/3, GET-only');
 f=fixture({mutate:b=>b.mapping.exchange_bindings[0].exchange_id='foreign'});await assert.rejects(f.client.begin(s2));await noRepost(f,s2);assert.deepEqual(f.posts,[]);assert.equal(f.authCalls(),0);await getOnly(f,s2);console.log('PASS foreign exchange blocked before auth and POST');
 f=fixture({auth:async()=>false});await assert.rejects(f.client.begin(s2));await noRepost(f,s2);assert.deepEqual(f.posts,[]);assert.equal(f.authCalls(),1);console.log('PASS consistency alone cannot authorize POST');
 let entered,release,verifierSignal;const ready=new Promise(r=>entered=r);
 f=fixture({auth:async(b,p,s,signal)=>{verifierSignal=signal;entered();return new Promise(r=>release=r);}});
 const pending=f.client.begin(s2);await ready;assert.equal(f.client.stop(s2),true);assert.equal(await pending,'STOPPED');release(true);await new Promise(r=>setImmediate(r));assert.equal(verifierSignal.aborted,true);await noRepost(f,s2);await getOnly(f,s2);assert.deepEqual(f.posts,[]);assert.deepEqual(f.events,[]);console.log('PASS STOP during authentication fences late true; GET-only');
 f=fixture({deadlineMs:30,auth:async(b,p,s,signal)=>new Promise(r=>signal.addEventListener('abort',()=>r(true),{once:true}))});await assert.rejects(f.client.begin(s2));await noRepost(f,s2);assert.deepEqual(f.posts,[]);console.log('PASS verifier deadline aborts without POST');
 console.log('5/5 SOURCE PASS; authenticated provider and transport synthetic; native_accepted=false');
})().catch(e=>{console.error(e);process.exitCode=1;});
