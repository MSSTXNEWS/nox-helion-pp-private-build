'use strict';
// Source-only: exact generated candidate, no real network, no native acceptance.
const assert=require('node:assert/strict');
const {readFileSync}=require('node:fs');
const {execFileSync}=require('node:child_process');
const {createHash}=require('node:crypto');
const vm=require('node:vm');
const root='coordination/onepass/';
const raw=execFileSync(process.execPath,[root+'b3_r55_cross_turn_pin.cjs','--emit'],{encoding:'utf8',maxBuffer:1024*1024});
assert(!raw.includes(String.fromCharCode(96))&&!/\\\r?$/m.test(raw)&&!raw.includes('/*'));
const source=readFileSync(root+'b3_r56_combined_candidate.js','utf8');
assert.equal(source,raw.replace(/^[ \t]+/gm,''));
const bytes=Buffer.byteLength(source);
assert(bytes<=25454);
const digest=createHash('sha256').update(source).digest('hex');
const policy=JSON.parse(readFileSync(root+'v135_owner_bridge_cap_policy.json','utf8'));
assert.equal(policy.max_bridge_bytes,25454);
assert.notEqual(digest,policy.bridge_sha256,'candidate must not impersonate admitted bridge');
const id='a'.repeat(32),other='b'.repeat(32),model='GLM-5.3-Flash';
const answer='Привет, ¿qué tal? 👩‍💻';
function fixture(src){
 const rows=new Map();let label=model,mode='ok',posts=0,stops=0,hist=0;
 const json=(x,status=200)=>new Response(JSON.stringify(x),{status});
 const loc=new URL('http://fixture.invalid/nox-web-v29/pc/resonance.html');
 const window={NOX_NATIVE_OWNER:true,fetch:async(path,init)=>{
   const url=new URL(String(path),loc);
   if(url.pathname==='/api/nox/stop'){stops++;return json({status:'STOP_REQUESTED',stream_cancellation_signalled:true});}
   if(url.pathname==='/api/ui/memory/dialogs/create')return json({dialog_id:id});
   if(url.pathname==='/api/ui/memory/dialogs/history'){
     hist++;const d=url.searchParams.get('dialog_id');
     return json({status:'READY',dialog_id:d,messages:mode==='badHistory'?[]:(rows.get(d)||[])});
   }
   assert.equal(url.pathname,'/api/nox/chat/stream');
   const data=JSON.parse(init.body);posts++;
   if(mode==='409')return json({error:'HOLD_ACTIVE_SESSION_STREAM'},409);
   const d=data.dialog_id,ex='fixture-exchange-'+posts;
   const frames=[{type:'preparing',stream_mode:'NATIVE_TOKEN_STREAM',dialog_id:d},
    {type:'start',model:label,dialog_id:mode==='foreign'?other:d},
    {type:'delta',text:answer,dialog_id:d},
    {type:'done',saved:true,s03_integrated:true,dialog_id:d,exchange_id:ex}];
   rows.set(d,[...(rows.get(d)||[]),{role:'user',content:data.message,exchange_id:ex},{role:'assistant',content:answer,exchange_id:ex}]);
   const buf=new TextEncoder().encode(frames.map(x=>JSON.stringify(x)).join('\n')+'\n');
   // Deliberately split all multi-byte characters across chunk boundaries.
   return new Response(new ReadableStream({start(c){for(let n=0;n<buf.length;n++)c.enqueue(buf.subarray(n,n+1));c.close();}}));
 }};
 vm.runInNewContext(src,{window,location:loc,URL,Request,Response,ReadableStream,TextEncoder,TextDecoder,AbortController,Intl,performance,setTimeout,clearTimeout,requestAnimationFrame:f=>setTimeout(f,0)},{timeout:1000});
 async function turn(dialog=id,sse=true){
   const body=sse?{dialog_id:dialog,request_id:'fixture-'+(posts+1),message:'Вопрос ¿sí?'}:{message:'Вопрос ¿sí?'};
   const response=await window.fetch('/api/nox/chat',{method:'POST',body:JSON.stringify(body)});
   if(!sse)return {status:response.status,body:await response.json()};
   const events=(await response.text()).split('\n\n').filter(Boolean).map(x=>JSON.parse(x.slice(6)));
   return {answer:events.filter(x=>x.type==='token').map(x=>x.t).join(''),done:events.filter(x=>x.type==='done'),errors:events.filter(x=>x.type==='error')};
 }
 return {turn,set:(m,l=model)=>{mode=m;label=l;},counts:()=>({posts,stops,hist})};
}
async function check(src){
 const f=fixture(src);
 const a=await f.turn();assert.equal(a.answer,answer);assert.equal(a.done.length,1);assert.equal(a.done[0].model_identity_verified,false);assert.equal(a.errors.length,0);
 const b=await f.turn();assert.equal(b.answer,answer);assert.equal(b.done.length,1);
 f.set('ok','Qwen');const drift=await f.turn();assert.equal(drift.answer,'');assert.equal(drift.done.length,0);assert.equal(drift.errors[0].error,'HOLD_DIALOG_MODEL_DRIFT');
 const j=await f.turn(id,false);assert.equal(j.status,503);assert.equal(j.body.error,'HOLD_DIALOG_MODEL_DRIFT');
 const independent=await f.turn(other);assert.equal(independent.answer,answer);assert.equal(independent.done.length,1);
 f.set('foreign');const foreign=await f.turn();assert.equal(foreign.answer,'');assert.equal(foreign.errors[0].error,'HOLD_NATIVE_FRAME_DIALOG_SCOPE');
 f.set('409');const oldStops=f.counts().stops;const conflict=await f.turn();assert.equal(conflict.errors[0].error,'HOLD_NATIVE_STREAM_HOLD_ACTIVE_SESSION_STREAM');assert.equal(f.counts().stops,oldStops);
 const g=fixture(src);g.set('badHistory');const bad=await g.turn();assert.equal(bad.done.length,0);assert.equal(bad.errors.length,1);g.set('ok','Qwen');const noPin=await g.turn();assert.equal(noPin.done.length,1);
 return 8;
}
(async()=>{const uncompact=await check(raw),compact=await check(source);
 console.log(JSON.stringify({task:'5A05-B3-GREEN-BASE-R55-REAL-NODE-CANDIDATE-20261124-R56',r55_real_node:true,uncompact,compact,bytes,rawBytes:Buffer.byteLength(raw),cap:25454,sha256:digest,stage_pin_matches:false,native_accepted:false}));
})().catch(e=>{console.error(e);process.exitCode=1;});
