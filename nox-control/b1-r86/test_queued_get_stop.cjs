'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
async function check(source){
 const root={};
 new Function('globalThis','AbortController','setTimeout','clearTimeout',source)(root,AbortController,setTimeout,clearTimeout);
 const calls=[];let posts=0,acks=0,projects=0;
 const c=root.NOXB1StreamReconnect.createClient({
   transport:{post(){posts++;throw Error('POST');},readback(s){calls.push(s.exchange_id);throw Error('fixture GET');},ack(){acks++;}},
   host:{readCommitted:async()=>null,verifyCanonicalText:async()=>false},
   bridge:{acceptTerminal(){throw Error('unexpected bridge');}},
   ui:{onDelta(){projects++;},upsertTerminal(){projects++;}}
 });
 const second={conversation_id:'dialog-1',exchange_id:'turn-2'},third={conversation_id:'dialog-1',exchange_id:'turn-3'};
 const p=c.reconnect(second).catch(e=>e.code);
 const stopped=await Promise.resolve().then(()=>c.stop(second));
 const state=await p;
 await Promise.resolve();const before=calls.length;
 const repost=await c.begin(second).then(x=>x.status,e=>e.code);
 const later=await c.reconnect(third).catch(e=>e.code);
 return {stopped,state,before,repost,later,calls,posts,acks,projects};
}
(async()=>{
 const baseline=await check(fs.readFileSync(path.join(__dirname,'../b1-r84/b1_browser_bundle.js'),'utf8'));
 const revised=await check(fs.readFileSync(path.join(__dirname,'b1_browser_bundle.js'),'utf8'));
 const common={stopped:true,state:'HOLD_STREAM_RECONNECT_STOPPED',repost:'HOLD_STREAM_NO_REPOST',later:'HOLD_STREAM_READBACK',posts:0,acks:0,projects:0};
 assert.deepEqual(baseline,{...common,before:1,calls:['turn-2','turn-3']});
 assert.deepEqual(revised,{...common,before:0,calls:['turn-3']});
 console.log('B1_R86 PASS '+JSON.stringify({baseline,revised,authority:'fixture',native_accepted:false}));
})().catch(e=>{console.error(e);process.exitCode=1;});
