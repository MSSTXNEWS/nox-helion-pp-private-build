'use strict';
// Offline-only release callsite. A separately authorized provider must supply
// BOTH detached hashes and R108 host evidence. Never use the producer hash
// as an admission pin and never turn a consistency result into native authority.
const {createHash}=require('node:crypto');
const {checkFrozenPayload}=require('./frozen/b3_r80_frozen_byte_ingress.cjs');
const {makeOfflinePairReview}=require('../b2-r108/atomic_ordered_quality.cjs');
const hash=x=>createHash('sha256').update(x).digest('hex');
const hold=status=>({status,quality_sample:null,metrics:null,native_accepted:false,
 authentication_verified:false,training_admitted:false,ack_allowed:false,next_post_allowed:false});
function makeFrozenOrderedReview(readDetachedEvidence){
 return (bytes,packet)=>{
  try{
   if(!Buffer.isBuffer(bytes)||!bytes.length||bytes.length>8*1024*1024||
      typeof packet!=='string'||Buffer.byteLength(packet)>4*1024*1024)return hold('HOLD_RELEASE_INPUT');
   if(typeof readDetachedEvidence!=='function')return hold('HOLD_RELEASE_PROVIDER');
   const raw=Buffer.from(bytes), packetPin=hash(Buffer.from(packet,'utf8'));
   const detached=readDetachedEvidence(packetPin);
   if(!detached||detached.packet_sha256!==packetPin||!detached.host)return hold('HOLD_RELEASE_DETACHED');
   const frozen=checkFrozenPayload(raw,detached.payload_sha256);
   if(frozen.status!=='CONSISTENT_PHYSICAL_RETAINED_PAIR_ONLY'||frozen.consistent!==true)return hold('HOLD_RELEASE_FROZEN');
   const [physical,pair]=JSON.parse(raw.toString('utf8'));
   const candidate=JSON.parse(packet), provenance=candidate.review?.dialog_provenance;
   const physicalPins=physical.receipts.receipt_index.map(x=>x.sha256);
   if(!Array.isArray(provenance?.physical_readback_sha256)||
      JSON.stringify(physicalPins)!==JSON.stringify(provenance.physical_readback_sha256)||
      !Array.isArray(candidate.turns)||candidate.turns.length!==2)return hold('HOLD_RELEASE_PHYSICAL');
   for(let i=0;i<2;i++){
    const t=physical.turns[i], p=pair.turns[i], row=candidate.turns[i];
    const o=JSON.parse(row.observation[0]), r=JSON.parse(row.reservation[0]), d=JSON.parse(row.disposition[0]);
    const link=t.link, proof=row.proof;
    const expected={turn:i+2,conversation_id:link.conversation_id,exchange_id:link.exchange_id,
      physical_dialog_id:link.physical_dialog_id,request_id:link.request_id,attempt_id:link.attempt_id,
      s03_dialog_id:link.s03_dialog_id,session_id:link.s03_session_id,event_id:link.s03_event_id,
      turn_id:link.s03_turn_id,user_message_id:link.user_message_id,assistant_message_id:link.assistant_message_id,
      served_sha256:t.wire.served_sha256,server_sha256:t.wire.server_sha256,
      owner_admission_receipt_sha256:t.physical.owner_admission_receipt_sha256};
    if(Object.entries(expected).some(([k,v])=>o[k]!==v)||
       o.visible_text_sha256!==p.answer_sha256||proof.answer_sha256!==p.answer_sha256||
       o.ack_state!=='NOT_SENT'||r.state!=='RESERVED_NOT_SENT'||d.state!=='FINALIZED'||
       d.dom_recheck!=='MATCHED'||d.stop_recheck!=='CLEAR')return hold('HOLD_RELEASE_DISPOSITION');
   }
   const result=makeOfflinePairReview(pin=>pin===packetPin?detached.host:null)(packet);
   if(result.status!=='MATCHED_PAIR_OFFLINE')return hold(result.status);
   return {...hold('MATCHED_FROZEN_ORDERED_OFFLINE'),offline_metrics:result.offline_metrics,host_provider_required:true};
  }catch{return hold('HOLD_RELEASE_INVALID');}
 };
}
module.exports={makeFrozenOrderedReview};
