'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
async function probe(file,broken){
 const root={AbortController,TextDecoder,TextEncoder,setTimeout,clearTimeout};
 vm.runInNewContext(fs.readFileSync(file,'utf8'),root);
 const posts=[],deltas=[],gets=[],acks=[];let cancelled=0;
 const s2={conversation_id:'conv',exchange_id:'ex2'},s3={conversation_id:'conv',exchange_id:'ex3'};
 const client=root.NOXB1StreamReconnect.createClient({
 transport:{post:async s=>{posts.push(s.exchange_id);const wire=s.exchange_id==='ex2'?'id: stable-control\nevent: heartbeat\n\nevent: delta\ndata: invalid\n\n':'id: stable-3\nevent: delta\ndata: valid\n\n';return {ok:true,body:new ReadableStream({start(c){c.enqueue(new TextEncoder().encode(wire));if(s.exchange_id==='ex3'||broken)c.close();},cancel(){cancelled++;}})};},readback:async s=>{gets.push(s.exchange_id);return null;},ack:async s=>acks.push(s.exchange_id)},
 host:{readCommitted:async()=>null},bridge:{acceptTerminal:async()=>null},
 ui:{onDelta:async(s,t,signal,id)=>deltas.push([s.exchange_id,t,id]),upsertTerminal:async()=>null},timeoutMs:2000});
 if(broken){assert.equal(await client.begin(s2),'STREAM_ENDED_READBACK_REQUIRED');assert.deepEqual(deltas,[['ex2','invalid',undefined]]);return;}
 await assert.rejects(client.begin(s2),{code:'HOLD_STREAM_DELTA_EVENT_ID'});
 assert.equal(cancelled,1);assert.deepEqual(deltas,[]);
 await assert.rejects(client.begin(s2),{code:'HOLD_STREAM_NO_REPOST'});
 await assert.rejects(client.reconnect(s2));assert.deepEqual(gets,['ex2']);assert.deepEqual(acks,[]);
 assert.equal(await client.begin(s3),'STREAM_ENDED_READBACK_REQUIRED');
 assert.deepEqual(posts,['ex2','ex3']);assert.deepEqual(deltas,[['ex3','valid','stable-3']]);
 console.log('PASS missing delta ID fenced before UI, cancelled, GET-only, independent turn3');
}
(async()=>{await probe(path.join(__dirname,'../b1-r75/b1_browser_bundle.js'),true);await probe(path.join(__dirname,'b1_browser_bundle.js'),false);console.log('SOURCE PASS; synthetic transport, native_accepted=false');})().catch(e=>{console.error(e);process.exitCode=1;});
