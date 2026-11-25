'use strict';
const assert=require('node:assert/strict');
const {createHash}=require('node:crypto');
const {classifyPinnedCompletion:gate}=require('./b4_r73_pinned_disposition_metric_bridge.cjs');
const {classifyFinalizedCompletion:old}=require('./b4_r72_final_disposition_metric_fence.cjs');
const hash=b=>createHash('sha256').update(b).digest('hex');
const digest=n=>hash('fixture-'+n);
const bytes=o=>Buffer.from(JSON.stringify(o));
const pair=(o,r,f)=>{const observation=bytes(o),observation_sha256=hash(observation);const reservation=bytes({...r,observation_sha256}),reservation_sha256=hash(reservation);const disposition=bytes({...f,observation_sha256,reservation_sha256}),disposition_sha256=hash(disposition);return {receipts:{observation,reservation,disposition},pins:{observation_sha256,reservation_sha256,disposition_sha256}};};
function fixture(turn){
 const scope={conversation_id:'conv',physical_dialog_id:'physical',s03_dialog_id:'s03',session_id:'session',served_sha256:digest(1),server_sha256:digest(2),owner_admission_receipt_sha256:digest(3)};
 const common={...scope,turn,exchange_id:'ex'+turn,request_id:'req'+turn,attempt_id:'attempt'+turn,event_id:'event'+turn,turn_id:'turn'+turn,user_message_id:'user'+turn,assistant_message_id:'msg'+turn,observation_id:'obs'+turn,browser_sha256:digest(4),terminal_receipt_sha256:digest(turn+10)};
 const answer_sha256=hash(turn===2?'30 евро 🐾':'Quedan 90 euros 🐾');
 const o={...common,schema:'nox.browser.projection-readback.v1',visible_text_sha256:answer_sha256,visible_row_count:1,state:'TERMINAL_VISIBLE',ack_state:'NOT_SENT'};
 const r={...common,schema:'nox.browser.ack-reservation-readback.v1',reservation_id:'res'+turn,state:'RESERVED_NOT_SENT'};
 const f={...common,schema:'nox.browser.projection-disposition.v1',disposition_id:'final'+turn,reservation_id:r.reservation_id,state:'FINALIZED',dom_recheck:'MATCHED',stop_recheck:'CLEAR'};
 const p=pair(o,r,f);
 const sample={...scope,exchange_id:common.exchange_id,clock_id:'clock',terminal_event_id:'terminal'+turn,begin_ms:100,first_visible_ms:110,eof_ms:150,outcome:'STREAM_ENDED_READBACK_REQUIRED'};
 const proof={...sample,...common,verified:true,dom_receipt_id:'dom'+turn,canonical_receipt_id:'canonical'+turn,dom_sha256:answer_sha256,answer_sha256,dom_commit_ms:170,observation_sha256:p.pins.observation_sha256,reservation_receipt_id:r.reservation_id};
 return {...p,o,r,f,trusted:{authentication_verified:true,sample,proof,pins:p.pins}};
}
const {classifyCompletionPair:joint}=require('./b4_r74_completion_pair.cjs');
function setup(){
 const a=fixture(2),b=fixture(3);
 for(const x of [b.trusted.sample,b.trusted.proof]){x.begin_ms+=100;x.first_visible_ms+=100;x.eof_ms+=100;}
 b.trusted.proof.dom_commit_ms+=100;
 return [a,b];
}
function q(t){return {route:'REVIEW_DATA_ONLY',native_accepted:false,training_admitted:false,next_post_allowed:false,retry_allowed:false,ack_allowed:false,dialog_provenance:{disposition_status:'MATCHED_OFFLINE',authentication_verified:false,finalized_observation_pairs:t.map(x=>x.trusted.pins)}};}
function repin(x){
 const p=pair(x.o,x.r,x.f);
 Object.assign(x,p);Object.assign(x.trusted,{pins:p.pins});x.trusted.proof.observation_sha256=p.pins.observation_sha256;
}
function setId(x,kind,v){
 const p=x.trusted.proof;
 if(kind===0){for(const y of [x.o,x.r,x.f,p])y.observation_id=v;}
 if(kind===1){x.r.reservation_id=x.f.reservation_id=p.reservation_receipt_id=v;}
 if(kind===2)x.f.disposition_id=v;
 if(kind===3)p.dom_receipt_id=v;
 if(kind===4)p.canonical_receipt_id=v;
 repin(x);
}
function allIds(x){return [x.o.observation_id,x.r.reservation_id,x.f.disposition_id,x.trusted.proof.dom_receipt_id,x.trusted.proof.canonical_receipt_id];}
let cases=0;
function hold(t){const a=joint(t,q(t));assert.equal(a.status,'HOLD_COMPLETION_PAIR');assert.deepEqual(a.samples,[]);assert.equal(a.native_accepted,false);cases++;}
let t=setup();const pass=joint(t,q(t));assert.equal(pass.status,'VERIFIED_COMPLETION_PAIR');assert.equal(pass.samples.length,2);assert.deepEqual(pass.samples.map(s=>[s.ttft_ms,s.stream_eof_ms,s.completion_ms]),[[10,50,70],[10,50,70]]);assert.equal(pass.native_accepted,false);cases++;
for(let i=0;i<5;i++)for(let j=0;j<5;j++){
 t=setup();setId(t[1],j,allIds(t[0])[i]);const quality=q(t);
 // Baseline accepts both individually even though one receipt identity is reused.
 for(const x of t)assert.equal(gate(x.receipts,quality,x.trusted).status,'VERIFIED_COMPLETION_SAMPLE');
 hold(t);
}
t=setup();hold(t.slice().reverse());
t=setup();t[1].trusted.authentication_verified=false;hold(t);
t=setup();t[1].trusted.sample.outcome='STOPPED';hold(t);
t=setup();t[1].trusted.sample.begin_ms=160;t[1].trusted.proof.begin_ms=160;hold(t);
t=setup();for(const x of [t[1].o,t[1].r,t[1].f,t[1].trusted.sample,t[1].trusted.proof])x.conversation_id='other';repin(t[1]);hold(t);
t=setup();for(const x of [t[1].o,t[1].r,t[1].f,t[1].trusted.proof])x.request_id=t[0].o.request_id;repin(t[1]);hold(t);
t=setup();for(const x of [t[1].o,t[1].r,t[1].f,t[1].trusted.proof])x.terminal_receipt_sha256=t[0].o.terminal_receipt_sha256;repin(t[1]);hold(t);
console.log('B4 R74 paired completion synthetic PASS '+cases+'; cross-turn receipt collisions 25/25; NATIVE_ACCEPTED=false');
