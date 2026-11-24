'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
async function probe(file,mode,broken){
 const root={AbortController,TextDecoder,TextEncoder,setTimeout,clearTimeout};
 vm.runInNewContext(fs.readFileSync(file,'utf8'),root);
 const s={conversation_id:'conv',exchange_id:'ex2'},s3={conversation_id:'conv',exchange_id:'ex3'};
 let client,reads=0,deltas=0,cancels=0,stopped,gets=0,acks=0;
 const posts=[],valid=[];
 const stop=()=>{stopped=client.stop(s)};
 const wire=new TextEncoder().encode('id: stable-2\nevent: delta\ndata: stop\n\n');
 client=root.NOXB1StreamReconnect.createClient({
 transport:{post:async scope=>{
 posts.push(scope.exchange_id);
 if(scope.exchange_id==='ex3')return {ok:true,body:new ReadableStream({start(c){c.enqueue(new TextEncoder().encode('id: stable-3\nevent: delta\ndata: valid\n\n'));c.close()}})};
 const inner=new ReadableStream({start(c){if(mode==='delta')c.enqueue(wire)},cancel(){cancels++}});
 return {ok:true,body:{getReader(){const r=inner.getReader();if(mode==='read')queueMicrotask(stop);return {
 read(){reads++;return r.read().then(part=>mode==='delta'?{done:part.done,get value(){queueMicrotask(stop);return part.value}}:part)},
 cancel(){return r.cancel()}
 }}}};},readback:async()=>{gets++;return null},ack:async()=>{acks++}},
 host:{readCommitted:async()=>null},bridge:{acceptTerminal:async()=>null},
 ui:{onDelta:async(scope,t,signal,id)=>{if(scope.exchange_id==='ex2'){assert.equal(signal.aborted,true);deltas++}else valid.push([t,id])},upsertTerminal:async()=>null},timeoutMs:2000});
 assert.equal(await client.begin(s),'STOPPED');
 assert.equal(stopped,true);assert.equal(cancels,1);
 assert.equal(reads,mode==='read'?(broken?1:0):1);
 assert.equal(deltas,mode==='delta'&&broken?1:0);
 await assert.rejects(client.begin(s),{code:'HOLD_STREAM_NO_REPOST'});
 await assert.rejects(client.reconnect(s));assert.equal(gets,1);assert.equal(acks,0);
 assert.equal(await client.begin(s3),'STREAM_ENDED_READBACK_REQUIRED');
 assert.deepEqual(posts,['ex2','ex3']);assert.deepEqual(valid,[['valid','stable-3']]);
 console.log((broken?'REPRODUCED R77':'PASS R79'),mode,{reads,deltas,cancels,posts,gets,acks});
}
(async()=>{for(const mode of ['read','delta']){await probe(path.join(__dirname,'../b1-r77/b1_browser_bundle.js'),mode,true);await probe(path.join(__dirname,'b1_browser_bundle.js'),mode,false)}console.log('4/4 differential fixtures; actual ReadableStream; synthetic transport; native_accepted=false')})().catch(e=>{console.error(e);process.exitCode=1});
