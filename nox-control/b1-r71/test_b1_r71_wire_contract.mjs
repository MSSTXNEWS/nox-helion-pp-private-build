// Exact R70 vs R71 and B3 R64 wire contract; no network or live S03.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import vm from 'node:vm';
const [oldPath,newPath,b3Path]=process.argv.slice(2);
const old=readFileSync(oldPath,'utf8'),candidate=readFileSync(newPath,'utf8'),b3=readFileSync(b3Path,'utf8');
const sha=s=>createHash('sha256').update(s).digest('hex');
assert.equal(sha(old),'50735b78dbc8538a4b3b32adec90426e9ff626e69d0a4725cba74798ecb12b72');
assert.equal(sha(b3),'c44b5aa2ef3d45246276a24bbcfad30bf76533fc2e08089eb91b442002643dc7');
assert(b3.includes("controller.enqueue(enc.encode('data: '+JSON.stringify(payload)+'\\n\\n'))"));
assert(b3.includes("event({type:'token',t:parts[index]})"));
function make(src){
 const ctx={AbortController,TextDecoder,TextEncoder,setTimeout,clearTimeout};
 vm.runInNewContext(src,ctx,{timeout:1000});
 return ctx.NOXB1StreamReconnect;
}
const scope=turn=>({conversation_id:'fixture-dialog',exchange_id:'fixture-turn-'+turn});
const envelope=t=>'data: '+JSON.stringify({type:'token',t})+'\n\n';
async function probe(src,turn,frames){
 let posts=0,acks=0,gets=0,cancels=0,visible=[];
 const client=make(src).createClient({
  transport:{post:async()=>{posts++;let i=0;return new Response(new ReadableStream({
   pull(c){if(i<frames.length)c.enqueue(new TextEncoder().encode(frames[i++]));else c.close();},
   cancel(){cancels++}
  }))},readback:async()=>{gets++},ack:async()=>{acks++}},
  host:{readCommitted:async()=>null},bridge:{acceptTerminal:async()=>{}},
  ui:{onDelta:async(s,d,signal,id)=>{assert.equal(signal.aborted,false);visible.push([s.exchange_id,d,id])},upsertTerminal:async()=>{}}
 });
 let outcome,repeat;
 try{outcome=await client.begin(scope(turn))}catch(e){outcome=e.code}
 try{await client.begin(scope(turn))}catch(e){repeat=e.code}
 assert.equal(posts,1);assert.equal(gets,0);assert.equal(acks,0);
 assert.equal(repeat,'HOLD_STREAM_NO_REPOST');
 return {outcome,visible,cancels};
}
for(const turn of [2,3]){
 const text='Привет '+turn+' ¿sí?';
 const frames=[envelope(text),'data: '+JSON.stringify({type:'done',status:'done'})+'\n\n'];
 const before=await probe(old,turn,frames);
 assert.equal(before.outcome,'STREAM_ENDED_READBACK_REQUIRED');assert.deepEqual(before.visible,[]);
 const after=await probe(candidate,turn,frames);
 assert.equal(after.outcome,'HOLD_STREAM_WIRE_DELTA_ID_REQUIRED');assert.deepEqual(after.visible,[]);
 const canonical=await probe(candidate,turn,[': heartbeat\n\n','event: delta\nid: event-'+turn+'-1\ndata: '+text+'\n\n']);
 assert.equal(canonical.outcome,'STREAM_ENDED_READBACK_REQUIRED');
 assert.deepEqual(canonical.visible,[[scope(turn).exchange_id,text,'event-'+turn+'-1']]);
 console.log('B1_R71_TURN_'+turn+' PASS '+JSON.stringify({before,after,canonical}));
}
console.log('B1_R71_WIRE_CONTRACT 6/6 PASS; candidate SHA256 '+sha(candidate)+'; synthetic wire fixture; NATIVE_ACCEPTED=false');
