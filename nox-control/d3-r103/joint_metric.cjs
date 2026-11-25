'use strict';
// Source-only joint adapter. Host verification is a construction-time dependency,
// never an input flag. The staged package has no authenticated host implementation.
const {createHash}=require('node:crypto');
const {classifyFinalizedCompletion}=require('./b4_r72_final_disposition_metric_fence.cjs');
const sha=s=>createHash('sha256').update(s,'utf8').digest('hex');
const hold=reason=>({status:reason,quality_sample:null,metrics:null,native_accepted:false,training_admitted:false,ack_allowed:false,next_post_allowed:false});
const need=x=>{if(!x)throw new Error('HOLD_JOINT_BINDING');};
const keys=['conversation_id','physical_dialog_id','s03_dialog_id','session_id','served_sha256','server_sha256','owner_admission_receipt_sha256','turn','exchange_id','request_id','attempt_id','event_id','turn_id','user_message_id','assistant_message_id','observation_id','browser_sha256','terminal_receipt_sha256'];
function pinned(p){
 need(Array.isArray(p)&&p.length===2&&typeof p[0]==='string'&&sha(p[0])===p[1]);
 const d=JSON.parse(p[0]);need(d&&typeof d==='object'&&!Array.isArray(d));return d;
}
function makeJointReview(verifyHostEvidence){
 return function review(rawPacket){
  try{
   need(typeof rawPacket==='string');
   const q=JSON.parse(rawPacket), r=q.review, p=r.dialog_provenance;
   need(r.route==='REVIEW_DATA_ONLY'&&r.native_accepted===false&&r.training_admitted===false&&r.ack_allowed===false&&r.next_post_allowed===false&&r.retry_allowed===false);
   need(p.disposition_status==='MATCHED_OFFLINE'&&p.authentication_verified===false&&Array.isArray(p.finalized_observation_pairs)&&p.finalized_observation_pairs.length===2);
   need(Array.isArray(q.turns)&&q.turns.length===2);
   const seen=new Set(),ids=new Set(), staged=[];
   for(let i=0;i<2;i++){
    const t=q.turns[i], o=pinned(t.observation), a=pinned(t.reservation), d=pinned(t.disposition), link=p.finalized_observation_pairs[i];
    for(const [name,pair] of [['observation',t.observation],['reservation',t.reservation],['disposition',t.disposition]]){
     need(link[name+'_sha256']===pair[1]&&!seen.has(pair[1]));seen.add(pair[1]);
    }
    need(o.schema==='nox.browser.projection-readback.v1'&&o.turn===i+2&&o.state==='TERMINAL_VISIBLE'&&o.visible_row_count===1&&o.ack_state==='NOT_SENT');
    need(a.schema==='nox.browser.ack-reservation-readback.v1'&&a.state==='RESERVED_NOT_SENT');
    need(d.schema==='nox.browser.projection-disposition.v1'&&d.state==='FINALIZED'&&d.dom_recheck==='MATCHED'&&d.stop_recheck==='CLEAR');
    for(const k of keys)need(o[k]!==undefined&&o[k]===a[k]&&o[k]===d[k]);
    need(a.observation_sha256===t.observation[1]&&d.observation_sha256===t.observation[1]&&d.reservation_sha256===t.reservation[1]&&d.reservation_id===a.reservation_id);
    for(const id of [o.observation_id,a.reservation_id,d.disposition_id]){need(typeof id==='string'&&/^[A-Za-z0-9._:-]{1,128}$/.test(id)&&!ids.has(id));ids.add(id);}
    const proof={...t.proof};
    for(const k of ['conversation_id','exchange_id','served_sha256','observation_id','terminal_receipt_sha256','browser_sha256','physical_dialog_id','s03_dialog_id','session_id','request_id','attempt_id','event_id','turn_id','assistant_message_id','turn'])need(proof[k]===o[k]);
    need(proof.answer_sha256===o.visible_text_sha256&&proof.observation_sha256===t.observation[1]&&proof.reservation_receipt_id===a.reservation_id);
    need(proof.reservation_sha256===t.reservation[1]&&proof.disposition_sha256===t.disposition[1]);
    // This is derived only after the trusted host validates all original bytes,
    // the R101 result and the independently retained timing/DOM/S03 proofs.
    delete proof.verified;staged.push({sample:t.sample,proof,dispositionId:d.disposition_id,link});
   }
   if(typeof verifyHostEvidence!=='function'||verifyHostEvidence(rawPacket)!==true)return hold('HOLD_HOST_AUTHENTICATION');
   const metrics=[];
   for(const x of staged){
    const proof={...x.proof,verified:true};
    const final={...proof,receipt_id:x.dispositionId,state:'ACK_RESERVED_AFTER_DOM_RECHECK'};
    const metric=classifyFinalizedCompletion(x.sample,proof,final);
    if(metric.status!=='VERIFIED_COMPLETION_SAMPLE')return hold(metric.status);
    metrics.push({...metric,...x.link,turn:proof.turn});
   }
   // Even an injected fixture verifier cannot produce production samples.
   return {...hold('MATCHED_JOINT_OFFLINE'),fixture_metrics:metrics,quality_candidate_sha256:sha(JSON.stringify(r.quality_sample??null)),host_provider_required:true};
  }catch(_){return hold('HOLD_JOINT_BINDING');}
 };
}
module.exports={makeJointReview};
