'use strict';
const assert=require('node:assert/strict');
const {test}=require('node:test');
const before=require('../b1-r65/b1_client_stream_reconnect_harness.js');
const after=require('./b1_client_stream_reconnect_harness.js');
const scope={conversation_id:'existing-dialog',exchange_id:'turn-2'};
function setup(lib,makeParts){
  const counters={post:0,read:0,cancel:0,ack:0,delta:[]};
  let client;
  const parts=makeParts(()=>client.stop(scope));
  const reader={read:async()=>{counters.read++;return parts.shift()??{done:true};},
    cancel:()=>{counters.cancel++;}};
  client=lib.createClient({transport:{post:async()=>{counters.post++;return {ok:true,body:{getReader:()=>reader}};},readback:async()=>null,ack:async()=>{counters.ack++;}},
    host:{readCommitted:async()=>null},bridge:{acceptTerminal:async()=>null},
    ui:{onDelta:async(s,d)=>counters.delta.push(d),upsertTerminal:async()=>true}});
  return {client,counters};
}
const chunk=(x,id=x)=>new TextEncoder().encode('event: delta\nid: '+id+'\ndata: '+x+'\n\n');
function changing(){
  let n=0;
  return [{get done(){return ++n!==1;},value:chunk('a')},{done:false,value:chunk('b')},{done:true}];
}
test('R65 reproduces premature EOF; R68 preserves both chunks',async()=>{
  const old=setup(before,changing);await old.client.begin(scope);
  assert.deepEqual(old.counters.delta,['a']);
  const next=setup(after,changing);
  assert.equal(await next.client.begin(scope),'STREAM_ENDED_READBACK_REQUIRED');
  assert.deepEqual(next.counters.delta,['a','b']);
  assert.equal(next.counters.read,3);
  await assert.rejects(next.client.begin(scope),{code:'HOLD_STREAM_NO_REPOST'});
  assert.equal(next.counters.post,1);assert.equal(next.counters.ack,0);
});
test('STOP from done getter never reads value or emits a delta',async()=>{
  let valueReads=0;
  const next=setup(after,stop=>[{get done(){stop();return false;},get value(){valueReads++;return chunk('late');}}]);
  assert.equal(await next.client.begin(scope),'STOPPED');
  assert.equal(valueReads,0);assert.equal(next.counters.cancel,1);
  assert.deepEqual(next.counters.delta,[]);assert.equal(next.counters.post,1);assert.equal(next.counters.ack,0);
});
test('STOP from value getter cannot emit or repost',async()=>{
  const next=setup(after,stop=>[{done:false,get value(){stop();return chunk('late');}}]);
  assert.equal(await next.client.begin(scope),'STOPPED');
  assert.equal(next.counters.cancel,1);assert.deepEqual(next.counters.delta,[]);
  await assert.rejects(next.client.begin(scope),{code:'HOLD_STREAM_NO_REPOST'});
  assert.equal(next.counters.post,1);assert.equal(next.counters.ack,0);
});
test('malformed done fails closed and disposes reader',async()=>{
  const next=setup(after,()=>[{done:'false',value:chunk('late')}]);
  await assert.rejects(next.client.begin(scope),{code:'HOLD_STREAM_READ_RESULT'});
  assert.equal(next.counters.cancel,1);assert.deepEqual(next.counters.delta,[]);
  assert.equal(next.counters.ack,0);
});
test('normal EOF and UTF8 split preserve exact text',async()=>{
  const full=chunk('три','ru3'),cut=full.length-4;
  const next=setup(after,()=>[{done:false,value:full.slice(0,cut)},{done:false,value:full.slice(cut)},{done:true}]);
  assert.equal(await next.client.begin(scope),'STREAM_ENDED_READBACK_REQUIRED');
  assert.deepEqual(next.counters.delta,['три']);assert.equal(next.counters.cancel,0);
});
