'use strict';
const assert=require('node:assert/strict');
const old=require('../b1-r62/b1_client_stream_reconnect_harness.js');
const current=require('./b1_client_stream_reconnect_harness.js');
const scope={conversation_id:'existing',exchange_id:'turn2'};
const good={...scope,safe_to_ack:true,model_post:false,projection_event_id:'event2',ack_cursor:'cursor2'};
function fixture(api,make){
  const calls={post:0,get:0,ack:[],ui:[],cancel:0};
  let client;
  client=api.createClient({
    transport:{post:async()=>{calls.post++;throw Error('unexpected POST')},
      readback:async()=>{calls.get++;return {body:{cancel(){calls.cancel++}}}},
      ack:async(s,c)=>{calls.ack.push(c);return true}},
    host:{readCommitted:async()=>null},
    bridge:{acceptTerminal:async()=>make(client,calls)},
    ui:{onDelta:async()=>true,upsertTerminal:async(s,e)=>{calls.ui.push(e);return true}},
    strictAckNoReplay:true,reconnectReadTimeoutMs:1000
  });
  return {client,calls};
}
(async()=>{
  let reads=0;
  const changing=()=>({...good,get projection_event_id(){return ++reads<=2?'event2':'foreign-event'}});
  const baseline=fixture(old,changing);
  await baseline.client.reconnect(scope);
  assert.deepEqual(baseline.calls.ui,['foreign-event']);
  console.log('REPRO R62 validated one event, projected another');
  reads=0;
  const fixed=fixture(current,changing);
  const receipt=await fixed.client.reconnect(scope);
  assert.equal(reads,1);assert.equal(receipt.projection_event_id,'event2');
  assert.deepEqual(fixed.calls.ui,['event2']);assert.deepEqual(fixed.calls.ack,['cursor2']);
  assert.equal(fixed.calls.post,0);console.log('PASS single event snapshot');
  reads=0;
  const cursor=fixture(current,()=>({...good,get ack_cursor(){return ++reads===1?'cursor2':'foreign-cursor'}}));
  await cursor.client.reconnect(scope);
  assert.equal(reads,1);assert.deepEqual(cursor.calls.ack,['cursor2']);console.log('PASS single cursor snapshot');
  let first=true;
  const throwing=fixture(current,()=>first?(first=false,{...good,get ack_cursor(){throw Error('bad getter')}}):good);
  await assert.rejects(throwing.client.reconnect(scope),{code:'HOLD_STREAM_UNSAFE_WITNESS'});
  assert.equal(throwing.calls.cancel,1);assert.deepEqual(throwing.calls.ui,[]);assert.deepEqual(throwing.calls.ack,[]);
  await assert.rejects(throwing.client.begin(scope),{code:'HOLD_STREAM_NO_REPOST'});
  await throwing.client.reconnect(scope);assert.equal(throwing.calls.post,0);assert.deepEqual(throwing.calls.ack,['cursor2']);
  console.log('PASS throwing getter releases GET; readback-only recovery');
  const stopped=fixture(current,client=>({...good,get ack_cursor(){client.stop(scope);return 'cursor2'}}));
  await assert.rejects(stopped.client.reconnect(scope),{code:'HOLD_STREAM_RECONNECT_STOPPED'});
  assert.equal(stopped.calls.cancel,1);assert.deepEqual(stopped.calls.ui,[]);assert.deepEqual(stopped.calls.ack,[]);assert.equal(stopped.calls.post,0);
  console.log('PASS STOP during snapshot no projection or ACK');
  const invalid=fixture(current,()=>({...good,safe_to_ack:false}));
  await assert.rejects(invalid.client.reconnect(scope),{code:'HOLD_STREAM_UNSAFE_WITNESS'});
  assert.equal(invalid.calls.cancel,1);assert.deepEqual(invalid.calls.ui,[]);assert.deepEqual(invalid.calls.ack,[]);
  console.log('PASS invalid snapshot fails closed');
  console.log('B1_R63 5/5 PASS; NATIVE_ACCEPTED=false');
})().catch(e=>{console.error(e);process.exitCode=1});
