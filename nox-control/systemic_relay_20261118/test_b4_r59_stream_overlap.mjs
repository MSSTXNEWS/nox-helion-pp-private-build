// R59: deterministic overlap and native EOF distinction on pinned R61.
// No network/GLM/S03; the gate deliberately withholds remaining native frames.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import vm from 'node:vm';
import {performance} from 'node:perf_hooks';
import {measureSseResponse} from './b4_sse_latency_probe.mjs';
const sha=x=>createHash('sha256').update(x).digest('hex');
const candidate=readFileSync(process.argv[2],'utf8');
assert.equal(sha(candidate),'9cd1cd1ab96a01b295418b59d53669b742d804520af15e3da648716b02427ef3');
const id='a'.repeat(32),model='GLM-5.3-Flash',prior='fixture-exchange-1';
const rows=[{role:'user',content:'prior question',exchange_id:prior},{role:'assistant',content:'prior answer',exchange_id:prior}];
const priorSnapshot=JSON.stringify(rows);
let posts=1, browserPosts=1, stops=0, active;
const loc=new URL('http://fixture.invalid/nox-web-v29/pc/resonance.html');
const json=x=>new Response(JSON.stringify(x));
const encode=x=>new TextEncoder().encode(JSON.stringify(x)+'\n');
const window={NOX_NATIVE_OWNER:true,dispatchEvent(){},fetch:async(path,init)=>{
 const url=new URL(String(path),loc);
 if(url.pathname==='/api/nox/stop'){stops++;return json({status:'STOP_REQUESTED',stream_cancellation_signalled:true});}
 if(url.pathname==='/api/ui/memory/dialogs/history')return json({status:'READY',dialog_id:id,messages:rows});
 assert.equal(url.pathname,'/api/nox/chat/stream');
 const data=JSON.parse(init.body);assert.equal(data.dialog_id,id);
 const turn=++posts,ex='fixture-exchange-'+turn;
 assert.equal(active.turn,turn);
 const a=active, first='Привет ',last='мир '+turn+' ¿sí?';
 a.answer=first+last;
 let controller;
 const stream=new ReadableStream({
   start(c){
     controller=c;
     c.enqueue(encode({type:'preparing',stream_mode:'NATIVE_TOKEN_STREAM',dialog_id:id}));
     c.enqueue(encode({type:'start',model,dialog_id:id}));
     c.enqueue(encode({type:'delta',text:first,dialog_id:id}));
   },
   cancel(){a.nativeCanceled=true;}
 });
 a.releaseRest=()=>{
   assert.equal(a.restSent,false);a.restSent=true;
   controller.enqueue(encode({type:'delta',text:last,dialog_id:id}));
   rows.push({role:'user',content:data.message,exchange_id:ex},{role:'assistant',content:a.answer,exchange_id:ex});
   controller.enqueue(encode({type:'done',saved:true,s03_integrated:true,dialog_id:id,exchange_id:ex}));
   a.nativeDoneSent=true;
   // No close: deliberately distinguish terminal frame from physical EOF.
 };
 a.closeNative=()=>{if(!a.nativeCanceled){controller.close();a.nativeEof=true;}};
 return new Response(stream);
}};
vm.runInNewContext(candidate,{window,location:loc,URL,Request,Response,ReadableStream,TextEncoder,TextDecoder,AbortController,Intl,performance,CustomEvent:class{constructor(type,options){this.type=type;this.detail=options.detail;}},setTimeout,clearTimeout,requestAnimationFrame:f=>setTimeout(f,0)},{timeout:1000});
const result=[];
for(const turn of [2,3]){
 const a=active={turn,restSent:false,nativeDoneSent:false,nativeCanceled:false,nativeEof:false};
 const start=performance.now();browserPosts++;
 const response=await window.fetch('/api/nox/chat',{method:'POST',body:JSON.stringify({dialog_id:id,request_id:'fixture-'+turn,message:'Вопрос '+turn})});
 const reader=response.clone().body.getReader();
 const measuring=measureSseResponse(response,{protocol:'nox-browser',expectedDialogId:id,startedAt:start});
 // Catch immediately to avoid unhandled rejection while the independent reader is active.
 measuring.catch(()=>{});
 let pending='', firstSeen=null;
 const timer=setTimeout(()=>{console.error('B4_R59_TIMEOUT waiting for first token or browser EOF');process.exit(1);},5000);
 const decoder=new TextDecoder();
 try {
  for(;;){
   const {value,done}=await reader.read();if(done)break;
   pending+=decoder.decode(value,{stream:true});
   let k;while((k=pending.indexOf('\n\n'))>=0){
    const block=pending.slice(0,k);pending=pending.slice(k+2);
    if(!block.startsWith('data: '))continue;
    const event=JSON.parse(block.slice(6));
    if(event.type==='token'&&typeof event.t==='string'&&event.t.trim()&&firstSeen===null){
      firstSeen=performance.now()-start;
      assert.equal(a.restSent,false);assert.equal(a.nativeDoneSent,false);
      assert.equal(a.nativeEof,false);a.releaseRest();
    }
   }
  }
  const proof=await measuring;
  assert(firstSeen!==null);assert.equal(proof.visible_text_sha256,sha(a.answer));
  assert.equal(proof.exchange_id,'fixture-exchange-'+turn);
  assert.equal(a.nativeDoneSent,true);assert.equal(a.nativeEof,false);
  // R61 currently cancels its native reader at DONE, without observing EOF.
  assert.equal(a.nativeCanceled,true,'expected known R61 EOF distinction; repin if bridge fixed');
  assert.equal(proof.native_verified,false);
  result.push({turn,first_browser_token_ms:firstSeen,browser_ttft_ms:proof.ttft_ms,browser_completion_ms:proof.completion_ms,first_before_remaining_native_frames:true,native_done_sent:true,native_eof_observed:false,native_reader_canceled:true,native_acceptance:'HOLD'});
 }finally{clearTimeout(timer);a.closeNative();reader.releaseLock();}
}
assert.equal(posts,3);assert.equal(browserPosts,3);assert.equal(stops,0);
assert.equal(JSON.stringify(rows.slice(0,2)),priorSnapshot);assert.equal(rows.length,6);
console.log('B4_R59_OVERLAP_WITNESS '+JSON.stringify({turns:result,newBrowserPosts:2,newMockNativePosts:2,priorUnchanged:true,physical_glm_measured:false,native_accepted:false,canonical_s03_verified:false}));
