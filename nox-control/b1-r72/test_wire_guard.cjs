'use strict';
const {createWireGuard}=require('./wire_guard.cjs');
async function runTests(make){
 const eq=(a,b)=>{if(a!==b)throw Error("expected "+b+" got "+a);};
 const rejected=async(p,code)=>{try{await p;}catch(e){eq(e.code,code);return;}throw Error("expected rejection "+code);};
 function ctl(){const listeners=new Set();let aborted=false;const signal={get aborted(){return aborted;},addEventListener(_,f){listeners.add(f);},removeEventListener(_,f){listeners.delete(f);}};return {signal,abort(){aborted=true;for(const f of [...listeners])f();},listeners};}
 const contract={wire:"named-delta-stable-server-id-v1",route:"current-route",served_sha256:"a".repeat(64),server_sha256:"b".repeat(64)};
 const scope=n=>({conversation_id:"existing",exchange_id:"turn-"+n});
 function fixture(verifyWire,opts={}){const calls={post:0,get:0,ack:0};const guard=make({transport:{post(s){calls.post++;return s.exchange_id;},readback(){calls.get++;return "GET";},ack(){calls.ack++;}},verifyWire,contract,deadlineMs:100,...opts});return {guard,calls};}
 let count=0;
 {let legacy=false;try{fixture(()=>true,{contract:{...contract,wire:"legacy-json-token"}});}catch(e){eq(e.code,"HOLD_B1_WIRE_PROFILE");legacy=true;}eq(legacy,true);count++;}
 {const {guard,calls}=fixture(()=>false);await rejected(guard.post(scope(2),ctl().signal),"HOLD_B1_WIRE_UNVERIFIED");eq(calls.post,0);await rejected(guard.post(scope(2),ctl().signal),"HOLD_B1_WIRE_NO_REPOST");eq(calls.post,0);count++;}
 {let release;const {guard,calls}=fixture(()=>new Promise(r=>release=r));const c=ctl(),p=guard.post(scope(2),c.signal);await Promise.resolve();c.abort();await rejected(p,"HOLD_B1_WIRE_STOPPED");release(true);await Promise.resolve();eq(calls.post,0);eq(c.listeners.size,0);count++;}
 {let release;const {guard,calls}=fixture(()=>new Promise(r=>release=r),{deadlineMs:2});const c=ctl();await rejected(guard.post(scope(2),c.signal),"HOLD_B1_WIRE_TIMEOUT");release(true);await Promise.resolve();eq(calls.post,0);eq(c.listeners.size,0);count++;}
 {let release;const {guard,calls}=fixture(()=>new Promise(r=>release=r));const p=guard.post(scope(2),ctl().signal);await Promise.resolve();await rejected(guard.post(scope(2),ctl().signal),"HOLD_B1_WIRE_NO_REPOST");release(true);eq(await p,"turn-2");eq(calls.post,1);count++;}
 {const {guard,calls}=fixture((pin,s)=>Object.isFrozen(pin)&&Object.isFrozen(s)&&pin.route==="current-route");eq(await guard.post(scope(2),ctl().signal),"turn-2");eq(await guard.post(scope(3),ctl().signal),"turn-3");eq(calls.post,2);eq(guard.readback(scope(2)),"GET");eq(calls.get,1);eq(calls.ack,0);count++;}
 {const {guard,calls}=fixture(()=>({verified:true}));await rejected(guard.post(scope(2),ctl().signal),"HOLD_B1_WIRE_UNVERIFIED");eq(calls.post,0);count++;}
 {const {guard,calls}=fixture(()=>{throw Error("unavailable");});await rejected(guard.post(scope(2),ctl().signal),"HOLD_B1_WIRE_UNVERIFIED");eq(calls.post,0);count++;}
 return count;
}
runTests(createWireGuard).then(n=>console.log(n+'/8 PASS'),e=>{console.error(e);process.exitCode=1;});
