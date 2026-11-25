'use strict';
// Actual loopback HTTP, pinned proxy iterator and browser parser; no native authority.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const {spawn}=require('node:child_process'),{once}=require('node:events');
const {createInterface}=require('node:readline');
const path=require('node:path');
const dir=process.argv[2];
const root={AbortController,TextDecoder,TextEncoder,setTimeout,clearTimeout};
vm.runInNewContext(fs.readFileSync(path.join(dir,'b1_browser_bundle.js'),'utf8'),root);
const child=spawn('python3',['-B',path.join(dir,'fixture.py')],{stdio:['ignore','pipe','inherit']});
const lines=createInterface({input:child.stdout});
let posts=0,acks=0,terminal=0;
const events=[];
(async()=>{
  const [port]=await once(lines,'line');
  assert.match(port,/^\d+$/);
  const base='http://127.0.0.1:'+port;
  const transport={
    async post(s,signal){posts++;return fetch(base+(s.exchange_id==='turn-2'?'/fault':'/clean'),{method:'POST',signal});},
    async readback(){return null},
    async ack(){acks++}
  };
  const client=root.NOXB1StreamReconnect.createClient({
    transport,host:{readCommitted:async()=>null},
    bridge:{acceptTerminal:async()=>{terminal++;return null}},
    ui:{onDelta:async(s,t,signal,id)=>{
      events.push({exchange:s.exchange_id,id,t});
      if(s.exchange_id==='turn-2'){const r=await fetch(base+'/release');assert.equal(r.ok,true);await r.json();}
    },upsertTerminal:async()=>{terminal++;return null}},
    timeoutMs:15000
  });
  const s2={conversation_id:'existing',exchange_id:'turn-2'};
  await assert.rejects(client.begin(s2),{code:'HOLD_STREAM_POST_OR_READ'});
  await assert.rejects(client.begin(s2),{code:'HOLD_STREAM_NO_REPOST'});
  assert.deepEqual(events,[{exchange:'turn-2',id:'existing:2:1',t:'Привет 🌞\n¡Hola!'}]);
  // Independent synthetic later exchange only; not authorization to advance a live dialogue.
  const s3={conversation_id:'existing',exchange_id:'turn-3'};
  assert.equal(await client.begin(s3),'STREAM_ENDED_READBACK_REQUIRED');
  await assert.rejects(client.begin(s3),{code:'HOLD_STREAM_NO_REPOST'});
  assert.deepEqual(events[1],{exchange:'turn-3',id:'existing:3:1',t:'  Continuamos\nSí  '});
  const r=await fetch(base+'/counts');
  assert.deepEqual(await r.json(),{posts:2,closed:2,faults:1,clean:1});
  assert.equal(posts,2);assert.equal(acks,0);assert.equal(terminal,0);
  console.log('R75 actual HTTP partial fault HOLD; independent clean EOF readback required; posts=2 closed=2 faults=1 clean=1 ack=0 terminal=0 native_accepted=false');
})().catch(e=>{console.error(e);process.exitCode=1}).finally(()=>{lines.close();child.kill();});
