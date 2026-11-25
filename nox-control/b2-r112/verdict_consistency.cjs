'use strict';
// Final diagnostic projection only. Run AFTER the one existing R110 call.
// A disagreement is possible only if at least one non-correct mark is present;
// incorrect+uncertain together require disagreement. Two reviewers, 3 marks.
const flags=new Set(['000','010','001','110','101','111']);
const hold=()=>({status:'HOLD_REPORTED_VERDICT_INCONSISTENT',quality_sample:null,metrics:null,
 native_accepted:false,authentication_verified:false,training_admitted:false,
 ack_allowed:false,next_post_allowed:false,reported_review_diagnostics:null});
function checkReportedVerdicts(result){
 if(result?.status!=='MATCHED_FROZEN_ORDERED_OFFLINE')return result;
 const d=result.reported_review_diagnostics;
 if(!d||d.status!=='REPORTED_UNVERIFIED_DATA_ONLY'||d.decisions_bound!==4||
    ![d.disagreements,d.reported_incorrect,d.reported_uncertain].every(a=>Array.isArray(a)&&
      a.every(n=>n===2||n===3)&&new Set(a).size===a.length))return hold();
 for(const n of [2,3]){
  const key=[d.disagreements,d.reported_incorrect,d.reported_uncertain].map(a=>a.includes(n)?'1':'0').join('');
  if(!flags.has(key))return hold();
 }
 return result;
}
module.exports={checkReportedVerdicts};
