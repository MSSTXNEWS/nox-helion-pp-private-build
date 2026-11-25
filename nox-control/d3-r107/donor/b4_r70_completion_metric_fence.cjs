'use strict';
// Classifies already independently verified evidence; never authenticates it or authorizes ACK/deploy.
function classifyCompletion(sample, proof) {
  const hold=reason=>Object.freeze({status:reason,ttft_ms:null,completion_ms:null,stream_eof_ms:null,recovery_ms:null,native_accepted:false});
  const id=v=>typeof v==='string'&&/^[A-Za-z0-9._:-]{1,128}$/.test(v);
  const sha=v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
  const num=v=>typeof v==='number'&&Number.isFinite(v)&&v>=0;
  if(!sample||!id(sample.conversation_id)||!id(sample.exchange_id)||!id(sample.clock_id)||!id(sample.terminal_event_id)||!sha(sample.served_sha256))return hold('HOLD_SCOPE');
  if(!num(sample.begin_ms))return hold('HOLD_CLOCK');
  if(!proof||proof.verified!==true||!id(proof.dom_receipt_id)||!id(proof.canonical_receipt_id)||proof.dom_receipt_id===proof.canonical_receipt_id)return hold('HOLD_PROVENANCE');
  for(const k of ['conversation_id','exchange_id','clock_id','terminal_event_id','served_sha256'])if(sample[k]!==proof[k])return hold('HOLD_SCOPE');
  if(!sha(proof.dom_sha256)||!sha(proof.answer_sha256)||proof.dom_sha256!==proof.answer_sha256)return hold('HOLD_CANONICAL_TEXT');
  if(!num(proof.dom_commit_ms)||proof.dom_commit_ms<sample.begin_ms)return hold('HOLD_CLOCK');
  if(sample.outcome==='STOPPED'){
    if(!num(sample.stop_ms)||sample.stop_ms<sample.begin_ms||proof.dom_commit_ms<sample.stop_ms)return hold('HOLD_CLOCK');
    return Object.freeze({...hold('RECOVERED_AFTER_STOP'),recovery_ms:proof.dom_commit_ms-sample.stop_ms});
  }
  if(sample.outcome!=='STREAM_ENDED_READBACK_REQUIRED')return hold('HOLD_STREAM');
  if(!num(sample.first_visible_ms)||!num(sample.eof_ms)||sample.first_visible_ms<sample.begin_ms||sample.eof_ms<sample.first_visible_ms||proof.dom_commit_ms<sample.eof_ms)return hold('HOLD_CLOCK');
  return Object.freeze({status:'VERIFIED_COMPLETION_SAMPLE',ttft_ms:sample.first_visible_ms-sample.begin_ms,completion_ms:proof.dom_commit_ms-sample.begin_ms,stream_eof_ms:sample.eof_ms-sample.begin_ms,recovery_ms:null,native_accepted:false});
}
module.exports={classifyCompletion};
