'use strict';
// Existing R111/R110 release callsite, not an authenticator or native timing source.
const {makeReportedReview}=require('../b2-r110/reported_review.cjs');
const pin=x=>typeof x==='string'&&/^[a-f0-9]{64}$/.test(x);
const hold=status=>({status,quality_sample:null,metrics:null,native_accepted:false,
 authentication_verified:false,training_admitted:false,ack_allowed:false,next_post_allowed:false,
 reported_review_diagnostics:null,offline_browser_timing:null});
function makeTimingEvidenceReview(readDetachedEvidence){
 return (bytes,packet)=>{
  try {
   let inconsistent=false;
   const provider=typeof readDetachedEvidence==='function'?key=>{
    const evidence=readDetachedEvidence(key);
    if(!evidence)return evidence;
    const turns=evidence.host?.turns;
    if(Array.isArray(turns)&&turns.length===2){
     for(const row of turns){
      const p=row?.trusted?.proof, pins=row?.trusted?.pins;
      if(!['observation_sha256','reservation_sha256','disposition_sha256'].every(k=>pin(pins?.[k])&&p?.[k]===pins[k])){
       inconsistent=true;return null;
      }
     }
    }
    return evidence;
   }:undefined;
   const result=makeReportedReview(provider)(bytes,packet);
   if(inconsistent)return hold('HOLD_TIMING_PROOF_PIN');
   if(result.status!=='MATCHED_FROZEN_ORDERED_OFFLINE')return {...result,offline_browser_timing:null};
   if(!Array.isArray(result.offline_metrics)||result.offline_metrics.length!==2)
    return hold('HOLD_TIMING_PROJECTION');
   // The immutable packet was already bound to host proof/sample by R108.
   // Project only those validated packet timestamps; never re-read provider getters.
   const rows=JSON.parse(packet).turns;
   if(!Array.isArray(rows)||rows.length!==2)return hold('HOLD_TIMING_PROJECTION');
   const bound=rows.map(row=>({clock_id:row.proof.clock_id,begin_ms:row.sample.begin_ms,
    first_visible_ms:row.sample.first_visible_ms,eof_ms:row.sample.eof_ms,dom_commit_ms:row.proof.dom_commit_ms}));
   if(result.offline_metrics.some((s,i)=>{const b=bound[i];return s.turn!==i+2||
    ![b.begin_ms,b.first_visible_ms,b.eof_ms,b.dom_commit_ms].every(Number.isFinite)||
    b.first_visible_ms-b.begin_ms!==s.ttft_ms||b.eof_ms-b.begin_ms!==s.stream_eof_ms||
    b.dom_commit_ms-b.begin_ms!==s.completion_ms;}))return hold('HOLD_TIMING_PROJECTION');
   const samples=result.offline_metrics.map((s,i)=>({turn:s.turn,...bound[i],
    first_visible_delay_ms:s.ttft_ms,stream_eof_delay_ms:s.stream_eof_ms,dom_completion_delay_ms:s.completion_ms,
    observation_sha256:s.observation_sha256,reservation_sha256:s.reservation_sha256,disposition_sha256:s.disposition_sha256}));
   return {...result,offline_browser_timing:{
    status:'OFFLINE_BROWSER_TIMING_ONLY',packet_sha256:result.reported_review_diagnostics.packet_sha256,
    frozen_payload_sha256:result.reported_review_diagnostics.frozen_payload_sha256,
    samples,model_ttft_ms:null,model_tokens_per_second:null,native_accepted:false}};
  }catch{return hold('HOLD_TIMING_RELEASE_INVALID');}
 };
}
module.exports={makeTimingEvidenceReview};
