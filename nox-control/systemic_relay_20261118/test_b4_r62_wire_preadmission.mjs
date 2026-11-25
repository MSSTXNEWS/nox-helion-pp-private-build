// B4 R62: exact R71/R72/R64 source composition, negative-only mock transport.
// No native credentials, routes, POST, acceptance or synthetic wire identifiers.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {performance} from 'node:perf_hooks';
const [p1,p2,p3]=process.argv.slice(2);
const [b1,b2,b3]=[p1,p2,p3].map(p=>readFileSync(p,'utf8'));
const loc=new URL('http://fixture.invalid/nox-web-v29/pc/resonance.html');
const contract={wire:'named-delta-stable-server-id-v1',route:'fixture-route',served_sha256:'a'.repeat(64),server_sha256:'b'.repeat(64)};
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function attempt(mode,turn){
 const scope={conversation_id:'a'.repeat(32),exchange_id:'fixture-turn-'+turn};
 const counts={browser_posts:0,native_posts:0,stop_posts:0,readback:0,ack:0,delta:0,terminal:0,verify:0};
 const window={NOX_NATIVE_OWNER:true,dispatchEvent(){},fetch:async(path)=>{
   const url=new URL(String(path),loc);
   if(url.pathname==='/api/nox/stop')counts.stop_posts++;
   else if(url.pathname==='/api/nox/chat/stream')counts.native_posts++;
   throw Error('unexpected mock native request '+url.pathname);
 }};
 vm.runInNewContext(b3,{window,location:loc,URL,Request,Response,ReadableStream,TextEncoder,TextDecoder,AbortController,Intl,performance,CustomEvent:class{},setTimeout,clearTimeout,requestAnimationFrame:f=>setTimeout(f,0)},{timeout:1000});
 const ctx={AbortController,TextDecoder,TextEncoder,setTimeout,clearTimeout};
 vm.runInNewContext(b1,ctx,{timeout:1000});
 vm.runInNewContext(b2,ctx,{timeout:1000});
 let entered,release,guardError;
 const entry=new Promise(r=>entered=r);
 const guarded=ctx.NOXB1WireGuard.createWireGuard({
   contract,deadlineMs:mode==='deadline'?20:1000,
   verifyWire(pin,s,signal){
     counts.verify++;assert.equal(s.exchange_id,scope.exchange_id);assert.equal(pin.wire,contract.wire);
     entered();
     if(mode==='denied')return false;
     if(mode==='untrusted')return {verified:true};
     return new Promise(r=>release=r);
   },
   transport:{post(s,signal){counts.browser_posts++;return window.fetch('/api/nox/chat',{method:'POST',signal,body:JSON.stringify({dialog_id:s.conversation_id,request_id:s.exchange_id,message:'fixture only'})});},
   readback(){counts.readback++;},ack(){counts.ack++;}}
 });
 const client=ctx.NOXB1StreamReconnect.createClient({
   transport:{...guarded,post:async(...args)=>{try{return await guarded.post(...args)}catch(e){guardError=e.code;throw e;}}},
   host:{readCommitted:async()=>null},bridge:{acceptTerminal:async()=>{counts.terminal++;}},
   ui:{onDelta:async()=>{counts.delta++;},upsertTerminal:async()=>{counts.terminal++;}},timeoutMs:3000
 });
 const start=performance.now();
 const pending=client.begin(scope).then(x=>x,e=>e.code);
 if(mode==='stop'){await entry;assert.equal(client.stop(scope),true);}
 const outcome=await pending,holdMs=performance.now()-start;
 // Resolve an uncooperative verifier after STOP/deadline, not before.
 if(release)release(true);
 await sleep(30);
 assert.equal(outcome,mode==='stop'?'STOPPED':'HOLD_STREAM_POST_OR_READ');
 assert.equal(guardError,mode==='stop'?'HOLD_B1_WIRE_STOPPED':mode==='deadline'?'HOLD_B1_WIRE_TIMEOUT':'HOLD_B1_WIRE_UNVERIFIED');
 await assert.rejects(client.begin(scope),e=>e.code==='HOLD_STREAM_NO_REPOST');
 assert.deepEqual(counts,{browser_posts:0,native_posts:0,stop_posts:0,readback:0,ack:0,delta:0,terminal:0,verify:1});
 return {mode,fixture_attempt:turn,outcome,guardError,pre_admission_hold_ms:holdMs,...counts,physical_glm_measured:false,native_accepted:false};
}
const results=[];
for(const [i,mode] of ['denied','untrusted','stop','deadline'].entries())results.push(await attempt(mode,i%2+2));
console.log('B4_R62_PREADMISSION '+JSON.stringify({results,source_only:true,compatible_wire_proven:false,canonical_s03_verified:false}));
