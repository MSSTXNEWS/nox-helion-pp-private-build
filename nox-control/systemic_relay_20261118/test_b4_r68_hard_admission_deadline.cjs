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
vm.runInNewContext(fs.readFileSync(path.join(b1,'b1-r77/b1_browser_bundle.js'),'utf8'),root);
const {createClient}=root.NOXB1StreamReconnect;
const h=n=>n.toString(16).padStart(64,'0');
const contract={wire:'named-delta-stable-server-id-v1',route:'logical-route',served_sha256:h(21),server_sha256:h(22)};
const physical={route:'/fixture/model',model_id:'fixture',dialog_id:'physical-dialog',weights_manifest_sha256:h(11),tokenizer_manifest_sha256:h(12),bridge_sha256:'c44b5aa2ef3d45246276a24bbcfad30bf76533fc2e08089eb91b442002643dc7',original_checkpoint_sha256:h(13),owner_admission_receipt_sha256:h(14),process:{boot_id:'boot',pid:42,start_ticks:123},turn_request_ids:['req2','req3'],window_start_ms:100,window_end_ms:200};
const mapping={...structuredClone(physical),schema:'NOX_B3_ROUTE_BINDING_V1',wire:contract.wire,symbolic_route:contract.route,served_sha256:contract.served_sha256,server_sha256:contract.server_sha256,conversation_id:'conv',exchange_bindings:[{turn:2,request_id:'req2',exchange_id:'ex2'},{turn:3,request_id:'req3',exchange_id:'ex3'}]};
const s2={conversation_id:'conv',exchange_id:'ex2'},s3={conversation_id:'conv',exchange_id:'ex3'};
const {createHardAdmissionDeadline}=require('./b4_r68_hard_admission_deadline.cjs');
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
function deferred(){let resolve;const promise=new Promise(r=>{resolve=r;});return {promise,resolve};}
function fixture({hard=true,hang='',streamMs=0}={}){
 const gate=deferred(),entered=deferred(),counts={pre:0,read:0,auth:0,post:0,cancel:0,ack:0},events=[];
 let stageSignal,postSignal;
 async function maybe(stage,signal,value){
  counts[stage]++;
  if(hang===stage){stageSignal=signal;entered.resolve();return gate.promise;}
  return value;
 }
 const create=hard?createHardAdmissionDeadline:createScopedAdmission;
 const c=create({createClient,createScopedTransport,createWireGuard,createPreverifierFence,createAdmissionBudget,checkScope,contract,limitMs:100,deadlineMs:1000,
  readBinding:(pin,s,signal)=>maybe('read',signal,{physical:structuredClone(physical),mapping:structuredClone(mapping),expectedTurn:s.exchange_id==='ex3'?3:2}),
  authenticateBinding:(binding,pin,s,signal)=>maybe('auth',signal,true),
  transport:{post:async(s,signal)=>{counts.post++;postSignal=signal;const enc=new TextEncoder();let timer;return {ok:true,body:new ReadableStream({start(ctrl){ctrl.enqueue(enc.encode('id: stable-'+s.exchange_id+'\nevent: delta\ndata: Привет hola\n\n'));if(streamMs)timer=setTimeout(()=>ctrl.close(),streamMs);else ctrl.close();},cancel(){clearTimeout(timer);counts.cancel++;}})};},readback:async()=>null,ack:async()=>{counts.ack++;}},
  clientOptions:{host:{readCommitted:(conversation,exchange,signal)=>maybe('pre',signal,null)},bridge:{acceptTerminal:async()=>null},ui:{onDelta:async(s,t)=>{events.push([s.exchange_id,t]);return true;},upsertTerminal:async()=>null},timeoutMs:3000}});
 return {c,gate,entered,counts,events,get stageSignal(){return stageSignal;},get postSignal(){return postSignal;}};
}
(async()=>{
 // Differential: R66 does not settle at its own 100ms admission limit when
 // the canonical read never resolves; stop locally before proceeding.
 let f=fixture({hard:false,hang:'pre'}),p=f.c.begin(s2);await f.entered.promise;
 assert.equal(await Promise.race([p.then(()=>false,()=>false),sleep(180).then(()=>true)]),true);
 assert.equal(f.counts.post,0);f.c.stop(s2);assert.equal(await p,'STOPPED');
 f.gate.resolve(null);console.log('PASS baseline R66 remains pending after budget');
 for(const stage of ['pre','read','auth']){
  f=fixture({hang:stage});const started=performance.now();p=f.c.begin(s2);
  const settled=assert.rejects(p,{code:'HOLD_B4_R68_ADMISSION_TIMEOUT'});
  await f.entered.promise;await settled;const ms=performance.now()-started;
  assert.ok(ms>=75&&ms<1500,'fixture deadline '+ms);
  assert.equal(f.stageSignal.aborted,true);assert.equal(f.counts.post,0);assert.equal(f.counts.ack,0);assert.deepEqual(f.events,[]);
  assert.equal(f.c.report(s2).transport_invoked,false);
  assert.equal(f.c.report(s2).reason,'HOLD_B4_R68_ADMISSION_TIMEOUT');
  // A late preflight HTTP body must still be released by R77.
  let lateCancel=0;
  f.gate.resolve(stage==='pre'?{body:{cancel(){lateCancel++;return Promise.resolve();}}}:stage==='read'?{physical,mapping,expectedTurn:2}:true);
  await sleep(10);assert.equal(f.counts.post,0);if(stage==='pre')assert.equal(lateCancel,1);
  await assert.rejects(f.c.begin(s2),{code:'HOLD_B4_R68_NO_REPOST'});
  console.log(JSON.stringify({stage,fixture_only:true,elapsed_ms:ms,post:0,late_get_cancel:lateCancel}));
 }
 f=fixture({streamMs:220});
 for(const s of [s2,s3]){
  const start=performance.now();assert.equal(await f.c.begin(s),'STREAM_ENDED_READBACK_REQUIRED');
  const elapsed=performance.now()-start;
  assert.ok(elapsed>=180);assert.equal(f.postSignal.aborted,false);
  assert.equal(f.c.report(s).transport_invoked,true);
  assert.ok(f.c.report(s).hard_admission_elapsed_ms<100);
 }
 assert.equal(f.counts.post,2);assert.equal(f.counts.cancel,0);assert.equal(f.counts.ack,0);
 assert.deepEqual(f.events,[['ex2','Привет hola'],['ex3','Привет hola']]);
 console.log('PASS deadline disarmed at actual POST; two streams longer than admission budget finish without cancellation');
 console.log('5/5 SOURCE PASS; actual Node timers, mocked provider/transport; no GLM or native acceptance');
})().catch(e=>{console.error(e);process.exitCode=1;});
