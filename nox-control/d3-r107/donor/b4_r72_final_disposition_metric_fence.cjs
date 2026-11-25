'use strict';
const {classifyCompletion}=require('./b4_r70_completion_metric_fence.cjs');
function classifyFinalizedCompletion(sample,proof,disposition){
 const hold=reason=>Object.freeze({status:reason,ttft_ms:null,completion_ms:null,stream_eof_ms:null,recovery_ms:null,native_accepted:false});
 const id=v=>typeof v==='string'&&/^[A-Za-z0-9._:-]{1,128}$/.test(v);
 const sha=v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
 const base=classifyCompletion(sample,proof);
 if(base.status!=='VERIFIED_COMPLETION_SAMPLE')return base;
 // Contract for separately authenticated owner disposition, not an authenticator.
 // Retaining pre-ACK bytes is only PENDING, including if the later DOM recheck fails.
 if(!disposition||disposition.verified!==true||disposition.state!=='ACK_RESERVED_AFTER_DOM_RECHECK')return hold('HOLD_FINAL_DISPOSITION');
 if(!id(disposition.receipt_id)||[proof.dom_receipt_id,proof.canonical_receipt_id,proof.observation_id,proof.reservation_receipt_id].includes(disposition.receipt_id))return hold('HOLD_FINAL_RECEIPT');
 for(const k of ['conversation_id','exchange_id','clock_id','terminal_event_id','served_sha256','dom_receipt_id','canonical_receipt_id','observation_id','observation_sha256','terminal_receipt_sha256','browser_sha256','physical_dialog_id','s03_dialog_id','session_id','request_id','attempt_id','event_id','turn_id','assistant_message_id','answer_sha256','reservation_receipt_id']){
   if(!(k.endsWith('sha256')?sha(proof[k]):id(proof[k]))||proof[k]!==disposition[k])return hold('HOLD_FINAL_BINDING');
 }
 if(![2,3].includes(proof.turn)||proof.turn!==disposition.turn)return hold('HOLD_FINAL_BINDING');
 return base;
}
module.exports={classifyFinalizedCompletion};
