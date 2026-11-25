'use strict';
const assert=require('node:assert/strict');
const {createHash}=require('node:crypto');
const {makeJointReview}=require('./joint_metric.cjs');
const h=x=>createHash('sha256').update(x,'utf8').digest('hex');
const pair=x=>{const s=JSON.stringify(x);return [s,h(s)];};
const turns=[2,3].map(turn=>{
 const common={conversation_id:'conv',physical_dialog_id:'physical',s03_dialog_id:'s03',session_id:'session',served_sha256:h('served'),server_sha256:h('server'),owner_admission_receipt_sha256:h('owner'),turn,exchange_id:'ex'+turn,request_id:'req'+turn,attempt_id:'attempt'+turn,event_id:'event'+turn,turn_id:'turn'+turn,user_message_id:'user'+turn,assistant_message_id:'msg'+turn,observation_id:'obs'+turn,browser_sha256:h('browser'),terminal_receipt_sha256:h('terminal'+turn)};
 const answer=h(turn===2?'30 евро 🐾':'Quedan 90 euros 🐾');
 const observation=pair({...common,schema:'nox.browser.projection-readback.v1',visible_text_sha256:answer,visible_row_count:1,state:'TERMINAL_VISIBLE',ack_state:'NOT_SENT'});
 const reservation=pair({...common,observation_sha256:observation[1],schema:'nox.browser.ack-reservation-readback.v1',reservation_id:'reserve'+turn,state:'RESERVED_NOT_SENT'});
 const disposition=pair({...common,observation_sha256:observation[1],schema:'nox.browser.projection-disposition.v1',disposition_id:'final'+turn,reservation_id:'reserve'+turn,reservation_sha256:reservation[1],state:'FINALIZED',dom_recheck:'MATCHED',stop_recheck:'CLEAR'});
 const sample={conversation_id:'conv',exchange_id:'ex'+turn,clock_id:'clock',terminal_event_id:'terminal'+turn,served_sha256:common.served_sha256,begin_ms:100,first_visible_ms:110,eof_ms:150,outcome:'STREAM_ENDED_READBACK_REQUIRED'};
 const proof={...common,...sample,verified:true,dom_receipt_id:'dom'+turn,canonical_receipt_id:'canonical'+turn,dom_sha256:answer,answer_sha256:answer,dom_commit_ms:170,observation_sha256:observation[1],reservation_receipt_id:'reserve'+turn,reservation_sha256:reservation[1],disposition_sha256:disposition[1]};
 return {observation,reservation,disposition,sample,proof};
});
const links=turns.map(t=>({observation_sha256:t.observation[1],reservation_sha256:t.reservation[1],disposition_sha256:t.disposition[1]}));
const q={turns,review:{route:'REVIEW_DATA_ONLY',native_accepted:false,training_admitted:false,ack_allowed:false,next_post_allowed:false,retry_allowed:false,quality_sample:{fixture:true},dialog_provenance:{disposition_status:'MATCHED_OFFLINE',authentication_verified:false,finalized_observation_pairs:links}}};
const raw=JSON.stringify(q);
const fixtureVerifier=x=>x===raw; // synthetic exact-packet verifier; NOT host authentication
const gate=makeJointReview(fixtureVerifier);
function blocked(r){assert.equal(r.quality_sample,null);assert.equal(r.metrics,null);assert.equal(r.fixture_metrics,undefined);assert.equal(r.native_accepted,false);assert.equal(r.ack_allowed,false);}
blocked(makeJointReview()(raw));blocked(makeJointReview(()=>false)(raw));
const edits=[
 x=>x.turns[0].proof.reservation_sha256=x.turns[1].reservation[1],
 x=>x.turns[0].proof.disposition_sha256=x.turns[1].disposition[1],
 x=>x.turns[0].disposition=x.turns[1].disposition,
 x=>x.turns.reverse(),
 x=>x.turns[0].proof.answer_sha256=h('foreign'),
 x=>x.review.dialog_provenance.finalized_observation_pairs[0].reservation_sha256=x.turns[1].reservation[1],
 x=>{const t=x.turns[0],d=JSON.parse(t.disposition[0]);d.stop_recheck='STOP';t.disposition=pair(d);t.proof.disposition_sha256=t.disposition[1];x.review.dialog_provenance.finalized_observation_pairs[0].disposition_sha256=t.disposition[1];},
 x=>x.turns[1].sample.dom_commit_ms=999,
];
for(const edit of edits){const x=JSON.parse(raw);edit(x);blocked(gate(JSON.stringify(x)));}
const ok=gate(raw);assert.equal(ok.status,'MATCHED_JOINT_OFFLINE');assert.equal(ok.metrics,null);assert.equal(ok.quality_sample,null);assert.equal(ok.native_accepted,false);assert.equal(ok.fixture_metrics.length,2);for(const m of ok.fixture_metrics){assert.equal(m.completion_ms,70);assert.equal(m.ttft_ms,10);}
console.log('R103_JOINT_METRIC: 10 HOLD; 1 MATCHED_JOINT_OFFLINE; NATIVE_ACCEPTED=false; HOST_PROVIDER_BOUND=false');
