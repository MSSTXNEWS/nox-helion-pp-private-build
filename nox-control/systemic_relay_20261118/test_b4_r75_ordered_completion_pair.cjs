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
const {classifyOrderedCompletionPair:ordered}=require('./b4_r75_ordered_completion_pair.cjs');
let count=0;
function times(x,begin){for(const y of [x.trusted.sample,x.trusted.proof]){y.begin_ms=begin;y.first_visible_ms=begin+10;y.eof_ms=begin+50;}x.trusted.proof.dom_commit_ms=begin+70;}
function clock(x,value){x.trusted.sample.clock_id=x.trusted.proof.clock_id=value;}
function hold(t){const r=ordered(t,q(t));assert.equal(r.status,'HOLD_COMPLETION_PAIR');assert.deepEqual(r.samples,[]);assert.equal(r.native_accepted,false);count++;}
for(const start of [0,100,160,170,200,1000000]){
 const t=setup();times(t[1],start);clock(t[1],'other-origin');
 assert.equal(joint(t,q(t)).status,'VERIFIED_COMPLETION_PAIR');
 hold(t);
}
for(const start of [0,100,169]){const t=setup();times(t[1],start);hold(t);}
for(const start of [170,200,1000000]){
 const t=setup();times(t[1],start);const r=ordered(t,q(t));
 assert.deepEqual(r,joint(t,q(t)));assert.equal(r.status,'VERIFIED_COMPLETION_PAIR');
 assert.deepEqual(r.samples.map(x=>[x.ttft_ms,x.stream_eof_ms,x.completion_ms]),[[10,50,70],[10,50,70]]);
 assert.equal(r.native_accepted,false);count++;
}
let t=setup();t[1].trusted.authentication_verified=false;hold(t);
t=setup();t[1].trusted.sample.clock_id='other-origin';hold(t);
t=setup();t[1].trusted.sample.outcome='STOPPED';hold(t);
console.log('B4 R75 clock domain synthetic PASS '+count+'; 6/6 R74 cross-clock admissions now HOLD; NATIVE_ACCEPTED=false');
