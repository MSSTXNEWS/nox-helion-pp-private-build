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
vm.runInNewContext(fs.readFileSync(path.join(b1,'b1-r79/b1_browser_bundle.js'),'utf8'),root);
const {createClient}=root.NOXB1StreamReconnect;
const h=n=>n.toString(16).padStart(64,'0');
const contract={wire:'named-delta-stable-server-id-v1',route:'logical-route',served_sha256:h(21),server_sha256:h(22)};
const physical={route:'/fixture/model',model_id:'fixture',dialog_id:'physical-dialog',weights_manifest_sha256:h(11),tokenizer_manifest_sha256:h(12),bridge_sha256:'c44b5aa2ef3d45246276a24bbcfad30bf76533fc2e08089eb91b442002643dc7',original_checkpoint_sha256:h(13),owner_admission_receipt_sha256:h(14),process:{boot_id:'boot',pid:42,start_ticks:123},turn_request_ids:['req2','req3'],window_start_ms:100,window_end_ms:200};
const mapping={...structuredClone(physical),schema:'NOX_B3_ROUTE_BINDING_V1',wire:contract.wire,symbolic_route:contract.route,served_sha256:contract.served_sha256,server_sha256:contract.server_sha256,conversation_id:'conv',exchange_bindings:[{turn:2,request_id:'req2',exchange_id:'ex2'},{turn:3,request_id:'req3',exchange_id:'ex3'}]};
const s2={conversation_id:'conv',exchange_id:'ex2'},s3={conversation_id:'conv',exchange_id:'ex3'};
const {createHardAdmissionDeadline}=require('./b4_r68_hard_admission_deadline.cjs');
async function probe(mode,hard){
 const posts=[],timings=new Map();let reads=0,late=0,cancels=0,acks=0,stopped;
 const create=hard?createHardAdmissionDeadline:createScopedAdmission;
 let client;
 const stop=()=>{stopped=client.stop(s2)};
 client=create({createClient,createScopedTransport,createWireGuard,createPreverifierFence,createAdmissionBudget,checkScope,contract,limitMs:1000,deadlineMs:1000,
  readBinding:async(pin,s)=>({physical:structuredClone(physical),mapping:structuredClone(mapping),expectedTurn:s.exchange_id==='ex3'?3:2}),authenticateBinding:async()=>true,
  transport:{post:async s=>{
   posts.push(s.exchange_id);const m={post:performance.now(),first:null,eof:null};timings.set(s.exchange_id,m);
   const bytes=new TextEncoder().encode('id: stable-'+s.exchange_id+'\nevent: delta\ndata: Привет hola\n\n');
   if(s.exchange_id==='ex3')return {ok:true,body:new ReadableStream({start(c){c.enqueue(new TextEncoder().encode('id: control-ex3\nevent: heartbeat\ndata: ping\n\n'));c.enqueue(bytes);setTimeout(()=>{m.eof=performance.now();c.close()},60)}})};
   const inner=new ReadableStream({start(c){if(mode==='delta')c.enqueue(bytes)},cancel(){cancels++}});
   return {ok:true,body:{getReader(){const r=inner.getReader();if(mode==='read')queueMicrotask(stop);return {read(){reads++;return r.read().then(part=>mode==='delta'?{done:part.done,get value(){queueMicrotask(stop);return part.value}}:part)},cancel(){return r.cancel()}}}}};
  },readback:async()=>null,ack:async()=>{acks++}},
  clientOptions:{host:{readCommitted:async()=>null},bridge:{acceptTerminal:async()=>null},ui:{onDelta:async(s,t,signal,id)=>{const m=timings.get(s.exchange_id);if(s.exchange_id==='ex2')late++;assert.equal(signal.aborted,false);assert.equal(id,'stable-'+s.exchange_id);m.first=performance.now();return true;},upsertTerminal:async()=>null},timeoutMs:3000}});
 const start=performance.now();assert.equal(await client.begin(s2),'STOPPED');const stoppedMs=performance.now()-start;
 assert.equal(stopped,true);assert.equal(cancels,1);assert.equal(reads,mode==='read'?0:1);assert.equal(late,0);assert.equal(timings.get('ex2').first,null);assert.equal(timings.get('ex2').eof,null);assert.equal(client.report(s2).transport_invoked,true);
 await assert.rejects(client.begin(s2));assert.deepEqual(posts,['ex2']);
 const begin=performance.now();assert.equal(await client.begin(s3),'STREAM_ENDED_READBACK_REQUIRED');const end=performance.now(),m=timings.get('ex3');
 assert.ok(m.post>=begin&&m.first>=m.post&&m.eof>m.first&&end>=m.eof);assert.deepEqual(posts,['ex2','ex3']);assert.equal(acks,0);
 console.log(JSON.stringify({mode,hard,fixture_only:true,stopped_ms:stoppedMs,stopped_ttft_ms:null,stopped_completion_ms:null,late_projection:late,reads,cancels,posts,acks,turn3_ttft_ms:m.first-begin,turn3_completion_ms:end-begin,eof_to_completion_ms:end-m.eof}));
}
(async()=>{for(const hard of [false,true])for(const mode of ['read','delta'])await probe(mode,hard);console.log('4/4 R79 + R66/R68 joint STOP/timing fixtures; native_accepted=false')})().catch(e=>{console.error(e);process.exitCode=1});
