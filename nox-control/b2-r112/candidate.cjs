'use strict';
const {checkReportedVerdicts}=require('./verdict_consistency.cjs');
const pin=x=>typeof x==='string'&&/^[a-f0-9]{64}$/.test(x);
const pair=x=>Array.isArray(x)&&x.length===2&&x.every(pin)&&x[0]!==x[1];
function checkReviewRolePins(result){
 const checked=checkReportedVerdicts(result);
 if(checked?.status!=='MATCHED_FROZEN_ORDERED_OFFLINE')return checked;
 const d=checked.reported_review_diagnostics;
 if(pin(d.rubric_sha256)&&pair(d.readback_sha256)&&pair(d.submission_sha256)&&
    d.submission_sha256.every(s=>s!==d.rubric_sha256&&!d.readback_sha256.includes(s)))return checked;
 return {status:'HOLD_REPORTED_REVIEW_ROLE_PIN',quality_sample:null,metrics:null,
 native_accepted:false,authentication_verified:false,training_admitted:false,
 ack_allowed:false,next_post_allowed:false,reported_review_diagnostics:null};
}
module.exports={checkReviewRolePins};
