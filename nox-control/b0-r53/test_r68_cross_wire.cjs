'use strict';
// Real Python encoder and real B1 stream parser, synthetic transport only.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const {spawnSync}=require('node:child_process');
const [encoder,asset]=process.argv.slice(2);
const root={AbortController,TextDecoder,TextEncoder,setTimeout,clearTimeout};
vm.runInNewContext(fs.readFileSync(asset,'utf8'),root);
const make=root.NOXB1StreamReconnect.createClient;
function encode(frame){
  const r=spawnSync('python3',['-B','-c','import sys,json,runpy; f=runpy.run_path(sys.argv[1]); sys.stdout.buffer.write(f["encode_native_delta"](json.load(sys.stdin)))',encoder],{input:JSON.stringify(frame),maxBuffer:1024*1024});
  if(r.error)throw r.error;
  return r;
}
const d=(event_id,text)=>({type:'delta',event_id,text});
function wire(f){const r=encode(f);assert.equal(r.status,0,r.stderr.toString());return r.stdout;}
async function scenario(clientState,parts,turn,expected,status='STREAM_ENDED_READBACK_REQUIRED'){
  const {client,transport,events}=clientState;
  transport.parts=parts;
  const scope={conversation_id:'existing',exchange_id:'turn-'+turn};
  const before=events.length,posts=transport.posts;
  let actual;try{actual=await client.begin(scope)}catch(e){actual=e.code}
  assert.equal(actual,status);
  await assert.rejects(client.begin(scope),{code:'HOLD_STREAM_NO_REPOST'});
  assert.equal(transport.posts,posts+1);assert.equal(transport.acks,0);
  assert.deepEqual(events.slice(before),expected.map(f=>({id:f.event_id,t:f.text,exchange:scope.exchange_id})));
}
function setup(){
  const transport={parts:[],posts:0,acks:0,cancels:0,
    async post(){this.posts++;const parts=this.parts.slice();let i=0;const self=this;return {ok:true,body:new ReadableStream({pull(c){if(i<parts.length)c.enqueue(parts[i++]);else c.close();},cancel(){self.cancels++;}},{highWaterMark:0})};},
    async readback(){return null},async ack(){this.acks++}};
  const events=[];
  const client=make({transport,host:{readCommitted:async()=>null},bridge:{acceptTerminal:async()=>null},ui:{onDelta:async(s,t,signal,id)=>events.push({id,t,exchange:s.exchange_id}),upsertTerminal:async()=>null},timeoutMs:5000});
  return {transport,events,client};
}
(async()=>{
 const s=setup(),f=d('stable-2:1','  Привет 🌞\n\n¡Hola!  \n'),g=d('stable-2:2','');
 const stream=Buffer.concat([wire(f),wire(g)]);
 await scenario(s,Array.from(stream,b=>Uint8Array.of(b)),2,[f,g]);
 console.log('PASS turn2 byte-split UTF8, multiline, empty delta');
 const prefix=Buffer.byteLength('id: stable-3\nevent: delta\ndata: ');
 const room=65536-prefix;
 const h=d('stable-3','я'.repeat(Math.floor(room/2))+'x'.repeat(room%2));
 const b=wire(h);assert.equal(b.length,65538);
 await scenario(s,[b.subarray(0,b.length-1),b.subarray(b.length-1)],3,[h]);
 console.log('PASS same client turn3 exact frame budget, split separator, no repost');
 const big=encode(d('stable-3',h.text+'x'));assert.notEqual(big.status,0);assert.equal(big.stdout.length,0);assert.match(big.stderr.toString(),/HOLD_PROXY_FRAME_BUDGET/);
 console.log('PASS oversize fails at Python boundary');
 const legacy=encode({type:'token',t:'legacy'});assert.notEqual(legacy.status,0);assert.equal(legacy.stdout.length,0);
 await scenario(setup(),[Buffer.from('data: {"type":"token","t":"legacy"}\n\n')],2,[],'HOLD_STREAM_WIRE_DELTA_ID_REQUIRED');
 console.log('PASS legacy rejected by both sides');
 const truncated=wire(f).subarray(0,-1);
 await scenario(setup(),[truncated],2,[],'HOLD_STREAM_TRUNCATED_SSE');
 console.log('PASS truncated EOF, no ACK or repost');
 console.log('5/5 CROSS_LANGUAGE_SOURCE_ONLY; NATIVE_ACCEPTED=false');
})().catch(e=>{console.error(e);process.exitCode=1});
