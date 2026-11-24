'use strict';
const assert=require('node:assert/strict');
const old=require('../b1-r73/wire_guard.cjs').createWireGuard;
const fixed=require('./wire_guard.cjs').createWireGuard;
const pin={wire:'named-delta-stable-server-id-v1',route:'current-route',served_sha256:'a'.repeat(64),server_sha256:'b'.repeat(64)};
const scope=n=>({conversation_id:'existing',exchange_id:'turn-'+n});
function fixture(make,verifyWire,deadlineMs=20){const posts=[];return {guard:make({transport:{post:(s,signal)=>{posts.push({s,signal});return s.exchange_id;},readback:()=>null,ack:()=>null},verifyWire,contract:pin,deadlineMs}),posts};}
function hung(){let child,aborts=0;return {verify:(_p,_s,signal)=>{child=signal;return new Promise((_,reject)=>signal.addEventListener('abort',()=>{aborts++;reject(signal.reason);},{once:true}));},signal:()=>child,aborts:()=>aborts};}
(async()=>{
 const p=new AbortController(),a=hung(),x=fixture(old,a.verify);await assert.rejects(x.guard.post(scope(2),p.signal),{code:'HOLD_B1_WIRE_TIMEOUT'});assert.equal(a.signal(),p.signal);assert.equal(a.aborts(),0);assert.equal(x.posts.length,0);p.abort();
 const q=new AbortController(),b=hung(),y=fixture(fixed,b.verify);await assert.rejects(y.guard.post(scope(2),q.signal),{code:'HOLD_B1_WIRE_TIMEOUT'});assert.notEqual(b.signal(),q.signal);assert.equal(b.signal().aborted,true);assert.equal(b.aborts(),1);assert.equal(q.signal.aborted,false);assert.equal(y.posts.length,0);await assert.rejects(y.guard.post(scope(2),q.signal),{code:'HOLD_B1_WIRE_NO_REPOST'});
 const r=new AbortController(),c=hung(),z=fixture(fixed,c.verify,1000);const pending=z.guard.post(scope(2),r.signal);await Promise.resolve();r.abort();await assert.rejects(pending,{code:'HOLD_B1_WIRE_STOPPED'});assert.equal(c.aborts(),1);assert.equal(z.posts.length,0);
 const t=new AbortController(),children=[],w=fixture(fixed,(_p,_s,signal)=>{children.push(signal);return true;},1000);assert.equal(await w.guard.post(scope(2),t.signal),'turn-2');assert.equal(await w.guard.post(scope(3),t.signal),'turn-3');assert.equal(w.posts.length,2);assert.ok(w.posts.every(p=>p.signal===t.signal));assert.ok(children.every(s=>s.aborted));assert.notEqual(children[0],children[1]);assert.equal(t.signal.aborted,false);
 const u=new AbortController();let late;const j=fixture(fixed,(_p,_s,signal)=>new Promise(resolve=>{late=resolve;signal.addEventListener('abort',()=>resolve(true),{once:true});}));await assert.rejects(j.guard.post(scope(2),u.signal),{code:'HOLD_B1_WIRE_TIMEOUT'});late(true);await Promise.resolve();assert.equal(j.posts.length,0);
 console.log('5/5 PASS: R73 leaves verifier live on timeout; R74 aborts child only, STOP, two turns, late result fenced');
})().catch(e=>{console.error(e);process.exitCode=1;});
