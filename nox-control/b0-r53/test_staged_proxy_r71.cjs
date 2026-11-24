'use strict';
// Extracted exact B0 iterator -> real B1 parser; synthetic owner and transport.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const {spawnSync}=require('node:child_process');
const dir=process.argv[2],root={AbortController,TextDecoder,TextEncoder,setTimeout,clearTimeout};
vm.runInNewContext(fs.readFileSync(path.join(dir,'b1_browser_bundle.js'),'utf8'),root);
const frames=[{type:'delta',event_id:'existing:2:1',text:'Привет 🌞\n¡Hola!  '},{type:'delta',event_id:'existing:3:1',text:'  Продолжаем\n\nSí'}];
function produce(frame){
  const r=spawnSync('python3',['-B','-c',[
    'import json,sys',
    'from b0_proxy_stream_iter import ProxyDeltaBody',
    'def source():',
    '    try: yield json.load(sys.stdin)',
    '    finally: print("CLOSED",file=sys.stderr)',
    'body=ProxyDeltaBody(source())',
    'try:',
    '    for data in body: sys.stdout.buffer.write(data)',
    'finally: body.close()'
  ].join('\n')],{cwd:dir,input:JSON.stringify(frame)});
  assert.equal(r.status,0,r.stderr.toString());
  assert.equal(r.stderr.toString().trim(),'CLOSED');
  return r.stdout;
}
(async()=>{
  let parts=[],posts=0,acks=0,events=[];
  const transport={async post(){posts++;let i=0;const chunks=parts.slice();return {ok:true,body:new ReadableStream({pull(c){if(i<chunks.length)c.enqueue(chunks[i++]);else c.close();}},{highWaterMark:0})};},async readback(){return null},async ack(){acks++}};
  const client=root.NOXB1StreamReconnect.createClient({transport,host:{readCommitted:async()=>null},bridge:{acceptTerminal:async()=>null},ui:{onDelta:async(s,t,signal,id)=>events.push({id,t,exchange:s.exchange_id}),upsertTerminal:async()=>null},timeoutMs:5000});
  for(let i=0;i<2;i++){
    const f=frames[i],scope={conversation_id:'existing',exchange_id:'turn-'+(i+2)};
    parts=Array.from(produce(f),b=>Uint8Array.of(b));
    assert.equal(await client.begin(scope),'STREAM_ENDED_READBACK_REQUIRED');
    await assert.rejects(client.begin(scope),{code:'HOLD_STREAM_NO_REPOST'});
    assert.deepEqual(events[i],{id:f.event_id,t:f.text,exchange:scope.exchange_id});
  }
  assert.equal(posts,2);assert.equal(acks,0);
  console.log('STAGED_PROXY turns=2 posts=2 acks=0 native_accepted=false');
})().catch(e=>{console.error(e);process.exitCode=1});
