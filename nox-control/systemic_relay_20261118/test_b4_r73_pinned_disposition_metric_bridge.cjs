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
const turns=[fixture(2),fixture(3)];
const quality={route:'REVIEW_DATA_ONLY',native_accepted:false,training_admitted:false,next_post_allowed:false,retry_allowed:false,ack_allowed:false,dialog_provenance:{disposition_status:'MATCHED_OFFLINE',authentication_verified:false,finalized_observation_pairs:turns.map(x=>x.pins)}};
let count=0;
function reject(receipts,q,t){const a=gate(receipts,q,t);assert.equal(a.status,'HOLD_PINNED_DISPOSITION');assert.equal(a.completion_ms,null);assert.equal(a.ttft_ms,null);assert.equal(a.native_accepted,false);count++;}
for(const x of turns){
 const {receipts,trusted,o,r,f,pins}=x;
 assert.equal(old(trusted.sample,trusted.proof,JSON.parse(receipts.disposition)).status,'HOLD_FINAL_DISPOSITION');
 const ok=gate(receipts,quality,trusted);assert.equal(ok.status,'VERIFIED_COMPLETION_SAMPLE');assert.equal(ok.ttft_ms,10);assert.equal(ok.completion_ms,70);assert.equal(ok.stream_eof_ms,50);assert.equal(ok.disposition_sha256,pins.disposition_sha256);assert.equal(ok.native_accepted,false);count++;
 reject(receipts,quality,undefined);
 reject(receipts,quality,{...trusted,authentication_verified:false});
 reject(receipts,quality,{...trusted,proof:{...trusted.proof,verified:false}});
 reject({...receipts,reservation:turns[trusted.proof.turn===2?1:0].receipts.reservation},quality,trusted);
 reject(receipts,quality,{...trusted,proof:{...trusted.proof,server_sha256:digest(99)}});
 reject(receipts,quality,{...trusted,proof:{...trusted.proof,user_message_id:'foreign'}});
 reject(receipts,quality,{...trusted,proof:{...trusted.proof,answer_sha256:digest(99),dom_sha256:digest(99)}});
 reject(receipts,quality,{...trusted,sample:{...trusted.sample,outcome:'STOPPED'}});
 reject(receipts,{...quality,dialog_provenance:{...quality.dialog_provenance,finalized_observation_pairs:[pins,pins]}},trusted);
 reject(receipts,{...quality,dialog_provenance:{...quality.dialog_provenance,finalized_observation_pairs:[...quality.dialog_provenance.finalized_observation_pairs].reverse()}},trusted);
 // Rehash altered bytes and even update the independent quality digest fixture:
 // wrong states, same-id reservation substitution, wrong scope, and duplicate keys.
 for(const [oo,rr,ff] of [[o,{...r,state:'SENDING'},f],[o,r,{...f,stop_recheck:'STOP'}],[o,r,{...f,dom_recheck:'REJECTED'}],[o,r,{...f,state:'PENDING'}],[o,{...r,server_sha256:digest(9)},f],[o,r,{...f,disposition_id:r.reservation_id}]]){
  const altered=pair(oo,rr,ff);const q={...quality,dialog_provenance:{...quality.dialog_provenance,finalized_observation_pairs:turns.map((y,i)=>i===trusted.proof.turn-2?altered.pins:y.pins)}};
  reject(altered.receipts,q,{...trusted,pins:altered.pins});
 }
 const dup=Buffer.from(receipts.disposition.toString().replace('"state":"FINALIZED"','"state":"PENDING","state":"FINALIZED"'));
 const p2={...pins,disposition_sha256:hash(dup)};
 reject({...receipts,disposition:dup},{...quality,dialog_provenance:{...quality.dialog_provenance,finalized_observation_pairs:turns.map((y,i)=>i===trusted.proof.turn-2?p2:y.pins)}},{...trusted,pins:p2});
 // Same reservation ID but different detached bytes: reserialized reservation must not
 // match the prior final's reservation SHA or the independent quality evidence.
 const res2=Buffer.from(JSON.stringify(JSON.parse(receipts.reservation),null,2));
 reject({...receipts,reservation:res2},quality,{...trusted,pins:{...pins,reservation_sha256:hash(res2)}});
}
console.log('B4 R73 R101 pinned bridge synthetic PASS '+count+'; NATIVE_ACCEPTED=false');
