'use strict';
const assert=require('node:assert/strict');
const old=require('../b1-r72/wire_guard.cjs').createWireGuard;
const fixed=require('./wire_guard.cjs').createWireGuard;
const pin={wire:'named-delta-stable-server-id-v1',route:'current-route',served_sha256:'a'.repeat(64),server_sha256:'b'.repeat(64)};
const scope=n=>({conversation_id:'existing',exchange_id:'turn-'+n});
const slow=()=>{const t=performance.now();while(performance.now()-t<35){}return true;};
function fixture(make,verifyWire,deadlineMs=5){let posts=0;return {guard:make({transport:{post:s=>{posts++;return s.exchange_id;},readback:()=>null,ack:()=>null},verifyWire,contract:pin,deadlineMs}),posts:()=>posts};}
(async()=>{
 const a=fixture(old,slow);assert.equal(await a.guard.post(scope(2),new AbortController().signal),'turn-2');assert.equal(a.posts(),1);
 const b=fixture(fixed,slow);await assert.rejects(b.guard.post(scope(2),new AbortController().signal),{code:'HOLD_B1_WIRE_TIMEOUT'});assert.equal(b.posts(),0);await assert.rejects(b.guard.post(scope(2),new AbortController().signal),{code:'HOLD_B1_WIRE_NO_REPOST'});
 const c=fixture(fixed,()=>true,1000);assert.equal(await c.guard.post(scope(2),new AbortController().signal),'turn-2');assert.equal(await c.guard.post(scope(3),new AbortController().signal),'turn-3');assert.equal(c.posts(),2);
 const d=new AbortController();const e=fixture(fixed,()=>{d.abort();return slow();});await assert.rejects(e.guard.post(scope(2),d.signal),{code:'HOLD_B1_WIRE_STOPPED'});assert.equal(e.posts(),0);
 console.log('4/4 PASS: R72 late POST reproduced; R73 expired POST fenced, independent turns preserved, STOP priority');
})().catch(e=>{console.error(e);process.exitCode=1;});
