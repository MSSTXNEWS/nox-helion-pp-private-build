// B4 R61: actual R71 client + R64 bridge, synthetic native backend only.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import vm from 'node:vm';
import {performance} from 'node:perf_hooks';
const [p1,p3]=process.argv.slice(2);
const b1=readFileSync(p1,'utf8'),b3=readFileSync(p3,'utf8');
const sha=s=>createHash('sha256').update(s).digest('hex');
assert.equal(sha(b1),'7b3175d0ad9195520896732dfcff39f23bfcfa76410c08b3118e142629ff86c1');
assert.equal(sha(b3),'c44b5aa2ef3d45246276a24bbcfad30bf76533fc2e08089eb91b442002643dc7');
const id='a'.repeat(32), model='GLM-5.3-Flash';
const encode=x=>new TextEncoder().encode(JSON.stringify(x)+'\n');
const json=x=>new Response(JSON.stringify(x));
const loc=new URL('http://fixture.invalid/nox-web-v29/pc/resonance.html');
async function attempt(turn){
 const rows=[{role:'user',content:'prior question',exchange_id:'prior'},{role:'assistant',content:'prior answer',exchange_id:'prior'}];
 const snapshot=JSON.stringify(rows);
 let browserPosts=0,nativePosts=0,stops=0,visible=[],gets=0,acks=0,terminal=0,cancels=0,stopAt=null,tokenAt=null,stopResult;
 let resolveStop;
 const stopObserved=new Promise(r=>resolveStop=r);
 const start=performance.now();
 const window={NOX_NATIVE_OWNER:true,dispatchEvent(e){
  if(e.type==='nox:native-phase'&&e.detail.phase==='speaking'&&tokenAt===null)tokenAt=performance.now()-start;
  if(e.type==='nox:native-stop-result'){stopResult=e.detail;resolveStop();}
 },fetch:async(path,init)=>{
  const url=new URL(String(path),loc);
  if(url.pathname==='/api/nox/stop'){stops++;stopAt=performance.now()-start;return json({status:'STOP_REQUESTED',stream_cancellation_signalled:true});}
  if(url.pathname==='/api/ui/memory/dialogs/history')return json({status:'READY',dialog_id:id,messages:rows});
  assert.equal(url.pathname,'/api/nox/chat/stream');
  nativePosts++;assert.equal(JSON.parse(init.body).dialog_id,id);
  return new Response(new ReadableStream({start(c){
   c.enqueue(encode({type:'preparing',stream_mode:'NATIVE_TOKEN_STREAM',dialog_id:id}));
   c.enqueue(encode({type:'start',model,dialog_id:id}));
   c.enqueue(encode({type:'delta',text:'Привет мир ¿sí?',dialog_id:id}));
   // Deliberately withhold terminal; an incompatible UI must not be mistaken for success.
  },cancel(){cancels++;}}));
 }};
 vm.runInNewContext(b3,{window,location:loc,URL,Request,Response,ReadableStream,TextEncoder,TextDecoder,AbortController,Intl,performance,CustomEvent:class{constructor(type,options){this.type=type;this.detail=options.detail;}},setTimeout,clearTimeout,requestAnimationFrame:f=>setTimeout(f,0)},{timeout:1000});
 const ctx={AbortController,TextDecoder,TextEncoder,setTimeout,clearTimeout};
 vm.runInNewContext(b1,ctx,{timeout:1000});
 const client=ctx.NOXB1StreamReconnect.createClient({
  transport:{post:async(s,signal)=>{browserPosts++;return window.fetch('/api/nox/chat',{method:'POST',signal,body:JSON.stringify({dialog_id:id,request_id:'fixture-'+turn,message:'Вопрос '+turn})});},readback:async()=>{gets++},ack:async()=>{acks++}},
  host:{readCommitted:async()=>null},bridge:{acceptTerminal:async()=>{terminal++}},
  ui:{onDelta:async(s,d)=>visible.push(d),upsertTerminal:async()=>{terminal++}}
 });
 const scope={conversation_id:id,exchange_id:'fixture-turn-'+turn};
 let outcome,repeat,timer;
 const bounded=p=>Promise.race([p,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('fixture timeout')),5000)})]).finally(()=>clearTimeout(timer));
 try{outcome=await bounded(client.begin(scope))}catch(e){outcome=e.code||e.message}
 const holdAt=performance.now()-start;
 assert.equal(outcome,'HOLD_STREAM_WIRE_DELTA_ID_REQUIRED');
 await bounded(stopObserved);
 try{await client.begin(scope)}catch(e){repeat=e.code}
 assert.equal(repeat,'HOLD_STREAM_NO_REPOST');
 assert.equal(browserPosts,1);assert.equal(nativePosts,1);assert.equal(stops,1);
 assert.equal(visible.length,0);assert.equal(gets,0);assert.equal(acks,0);assert.equal(terminal,0);
 assert.equal(stopResult.transport_outcome,'signal_accepted');
 assert.equal(stopResult.gpu_stop_verified,false);
 assert.equal(stopResult.stop_admission_outcome,'HTTP_200_ADMITTED');
 assert(tokenAt!==null&&stopAt>=tokenAt&&holdAt>=tokenAt);
 assert.equal(JSON.stringify(rows),snapshot);
 return {fixture_attempt:turn,bridge_first_token_ms:tokenAt,ui_hold_ms:holdAt,mock_stop_ms:stopAt,browser_posts:browserPosts,mock_native_posts:nativePosts,mock_stop_posts:stops,native_reader_cancels:cancels,visible_tokens:visible.length,repeat,outcome,prior_unchanged:true,physical_glm_measured:false,native_accepted:false};
}
console.log('B4_R61_WIRE_CANCEL_STOP '+JSON.stringify({attempts:[await attempt(2),await attempt(3)],independent_fixtures:true,canonical_s03_verified:false}));
