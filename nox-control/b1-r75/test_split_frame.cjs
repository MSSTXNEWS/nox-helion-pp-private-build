'use strict';
// Exact R71 donor and R75 asset. Synthetic read-only host + POST fixture only.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
function load(rel){const root={AbortController,TextDecoder,TextEncoder,setTimeout,clearTimeout};vm.runInNewContext(fs.readFileSync(path.join(__dirname,rel),'utf8'),root);return root.NOXB1StreamReconnect.createClient;}
function frame(n,id='stable-2',char='x'){const head='id: '+id+'\nevent: delta\ndata: ';const room=n-Buffer.byteLength(head);const size=Buffer.byteLength(char);return head+char.repeat(Math.floor(room/size))+'x'.repeat(room%size);}
async function scenario(make,parts,turn=2){
 let posts=0,cancels=0,events=[],acks=0;
 const client=make({transport:{post:async()=>{posts++;let i=0;return {ok:true,body:new ReadableStream({pull(c){if(i<parts.length)c.enqueue(Buffer.from(parts[i++]));else c.close();},cancel(){cancels++;}},{highWaterMark:0})};},readback:async()=>null,ack:async()=>{acks++;}},host:{readCommitted:async()=>null},bridge:{acceptTerminal:async()=>null},ui:{onDelta:async(s,t,signal,id)=>events.push({id,t,exchange:s.exchange_id}),upsertTerminal:async()=>null},timeoutMs:5000});
 const scope={conversation_id:'existing',exchange_id:'turn-'+turn};
 let status;try{status=await client.begin(scope)}catch(e){status=e.code}
 await assert.rejects(client.begin(scope),{code:'HOLD_STREAM_NO_REPOST'});
 return {status,posts,cancels,events,acks};
}
(async()=>{
 const a=load('../b1-r71/b1_browser_bundle.js'),b=load('./b1_browser_bundle.js');
 const f=frame(65536),over=frame(65537),f3=frame(65536,'stable-3','я');
 const good='STREAM_ENDED_READBACK_REQUIRED',bad='HOLD_STREAM_FRAME_TOO_LARGE';
 const cases=[['baseline split',a,[f+'\n','\n'],bad],['exact split',b,[f+'\n','\n'],good],['exact one read',b,[f+'\n\n'],good],['oversized split',b,[over+'\n','\n'],bad],['oversized completed',b,[over+'\n\n'],bad],['partial EOF',b,[f+'\n'],'HOLD_STREAM_TRUNCATED_SSE'],['third turn',b,[f3,'\n','\n'],good]];
 for(const [name,make,parts,want] of cases){const x=await scenario(make,parts,name==='third turn'?3:2);assert.equal(x.status,want,name);assert.equal(x.posts,1);assert.equal(x.acks,0);assert.equal(x.events.length,want===good?1:0);if(want===good){assert.equal(x.cancels,0);const expected=name==='third turn'?f3:f;assert.equal(x.events[0].t,expected.split('data: ')[1]);assert.equal(x.events[0].id,name==='third turn'?'stable-3':'stable-2');}else assert.equal(x.cancels,1);console.log('PASS '+name);}
 console.log('7/7 PASS: exact wire frame boundary, no duplicate POST, no terminal ACK; mock host only.');
})().catch(e=>{console.error(e);process.exitCode=1;});
