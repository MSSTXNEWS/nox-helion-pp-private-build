'use strict';
const assert=require('node:assert/strict');
const old=require('../b1-r63/b1_client_stream_reconnect_harness.js');
const fixed=require('./b1_client_stream_reconnect_harness.js');
const scope={conversation_id:'d',exchange_id:'t2'};
const tick=()=>new Promise(r=>setImmediate(r));
async function run(api,mode){
 let client,posts=0,bodyReads=0,acquires=0,cancels=0,deltas=0,acks=0,readbacks=0;
 const body={cancel(){cancels++;return Promise.resolve()},getReader(){acquires++;return {read:async()=>({done:true}),cancel(){cancels++;return Promise.resolve()}}}};
 const response={
  get body(){bodyReads++;if(mode==='body-stop')client.stop(scope);return body},
  get ok(){if(mode==='status-stop')client.stop(scope);if(mode==='throw')throw Error('bad status');return true}
 };
 if(mode==='reader-stop')Object.defineProperty(body,'getReader',{get(){client.stop(scope);return ()=>{acquires++;return {read:async()=>({done:true}),cancel(){cancels++;}}}}});
 let release,entered;
 const enteredPromise=new Promise(r=>entered=r);
 const late=new Promise(r=>release=r);
 client=api.createClient({transport:{post(){posts++;entered();return mode==='late'?late:response},readback(){readbacks++;return {}},ack(){acks++;return true}},host:{readCommitted:async()=>null},bridge:{acceptTerminal:async()=>({})},ui:{onDelta(){deltas++},upsertTerminal(){}},timeoutMs:2000});
 const p=client.begin(scope);
 if(mode==='late'){await enteredPromise;assert.equal(client.stop(scope),true);assert.equal(await p,'STOPPED');release(response);await tick();}
 let result;try{result=await p}catch(e){result=e.code;}
 await assert.rejects(client.begin(scope),{code:'HOLD_STREAM_NO_REPOST'});
 return {result,posts,bodyReads,acquires,cancels,deltas,acks,readbacks};
}
(async()=>{
 const baseline=await run(old,'status-stop');
 assert.equal(baseline.result,'STOPPED');assert.equal(baseline.acquires,1);
 console.log('REPRO R63 acquires reader after synchronous STOP');
 let count=0;
 for(const mode of ['status-stop','body-stop','reader-stop','throw','late','normal']){
  const r=await run(fixed,mode);
  assert.deepEqual(r,{result:mode==='normal'?'STREAM_ENDED_READBACK_REQUIRED':mode==='throw'?'HOLD_STREAM_POST_RESPONSE':'STOPPED',posts:1,bodyReads:1,acquires:mode==='normal'?1:0,cancels:mode==='normal'?0:1,deltas:0,acks:0,readbacks:0},mode);
  count++;console.log('PASS',mode,JSON.stringify(r));
 }
 console.log('B1_R65_SOURCE '+count+'/6 PASS; NATIVE_ACCEPTED=false');
})().catch(e=>{console.error(e);process.exitCode=1});
