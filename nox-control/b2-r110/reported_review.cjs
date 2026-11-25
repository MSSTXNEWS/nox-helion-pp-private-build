'use strict';
// Diagnostic output only. No reviewer authentication, model instruction or native authority.
const {createHash}=require('node:crypto');
const {makeFrozenOrderedReview}=require('../a3-r109-r80/joint_frozen.cjs');
const hash=b=>createHash('sha256').update(b).digest('hex');
const pin=x=>typeof x==='string'&&/^[a-f0-9]{64}$/.test(x);
const pair=x=>Array.isArray(x)&&x.length===2&&x.every(pin)&&x[0]!==x[1];
const turns=x=>Array.isArray(x)&&x.every(n=>n===2||n===3)&&new Set(x).size===x.length;
const hold=status=>({status,quality_sample:null,metrics:null,native_accepted:false,
 authentication_verified:false,training_admitted:false,ack_allowed:false,next_post_allowed:false,
 reported_review_diagnostics:null});
function makeReportedReview(readDetachedEvidence){
 const review=makeFrozenOrderedReview(readDetachedEvidence);
 return (bytes,packet)=>{
  try {
   if(!Buffer.isBuffer(bytes)||!bytes.length||bytes.length>8*1024*1024||
      typeof packet!=='string'||Buffer.byteLength(packet)>4*1024*1024)return hold('HOLD_REVIEW_INPUT');
   const raw=Buffer.from(bytes);
   const result=review(raw,packet);
   if(result.status!=='MATCHED_FROZEN_ORDERED_OFFLINE')return {...result,reported_review_diagnostics:null};
   const doc=JSON.parse(packet), s=doc.review?.quality_sample?.review_summary;
   if(!s||s.schema!=='NOX_B2_EXISTING_DIALOG_REVIEW_V1'||s.decisions_bound!==4||
      s.reviewer_identity_verified!==false||s.quality_grade!=='NOT_INDEPENDENTLY_VERIFIED'||
      !pin(s.rubric_sha256)||!pair(s.readback_sha256)||!pair(s.submission_sha256)||
      ![s.disagreements,s.reported_incorrect,s.reported_uncertain].every(turns))
     return hold('HOLD_REPORTED_REVIEW_SUMMARY');
   const summary=s.reported_incorrect.length?'INCORRECT_REPORTED_UNVERIFIED':
      (s.disagreements.length||s.reported_uncertain.length)?'ADJUDICATION_REQUIRED':
      'TWO_REVIEWER_CONSENSUS_REPORTED_UNVERIFIED';
   if(s.review_summary!==summary)return hold('HOLD_REPORTED_REVIEW_SUMMARY');
   return {...result,reported_review_diagnostics:{
     status:'REPORTED_UNVERIFIED_DATA_ONLY',packet_sha256:hash(Buffer.from(packet,'utf8')),
     frozen_payload_sha256:hash(raw),rubric_sha256:s.rubric_sha256,
     readback_sha256:s.readback_sha256,submission_sha256:s.submission_sha256,
     decisions_bound:4,summary,disagreements:s.disagreements,
     reported_incorrect:s.reported_incorrect,reported_uncertain:s.reported_uncertain,
     reviewer_identity_verified:false,quality_grade:'NOT_INDEPENDENTLY_VERIFIED',
     model_instruction:false,training_admitted:false,native_accepted:false}};
  } catch {return hold('HOLD_REPORTED_REVIEW_INVALID');}
 };
}
module.exports={makeReportedReview};
