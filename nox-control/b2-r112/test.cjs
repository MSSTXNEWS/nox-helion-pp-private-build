'use strict';
const a=require('node:assert/strict');
const old=require('./verdict_consistency.cjs').checkReportedVerdicts;
const check=require('./candidate.cjs').checkReviewRolePins;
const make=()=>({status:'MATCHED_FROZEN_ORDERED_OFFLINE',quality_sample:null,metrics:null,native_accepted:false,authentication_verified:false,training_admitted:false,ack_allowed:false,next_post_allowed:false,offline_metrics:[1,2],reported_review_diagnostics:{status:'REPORTED_UNVERIFIED_DATA_ONLY',decisions_bound:4,disagreements:[],reported_incorrect:[],reported_uncertain:[],rubric_sha256:'1'.repeat(64),readback_sha256:['2'.repeat(64),'3'.repeat(64)],submission_sha256:['4'.repeat(64),'5'.repeat(64)]}});
let oldAccepts=0,newHolds=0;
for(let i=0;i<2;i++)for(let j=0;j<3;j++){
 const r=make(),d=r.reported_review_diagnostics;
 d.submission_sha256[i]=[d.rubric_sha256,...d.readback_sha256][j];
 a.equal(old(r),r);oldAccepts++;
 const out=check(r);a.equal(out.status,'HOLD_REPORTED_REVIEW_ROLE_PIN');a.equal(out.reported_review_diagnostics,null);a.equal(out.offline_metrics,undefined);
 for(const k of ['native_accepted','authentication_verified','training_admitted','ack_allowed','next_post_allowed'])a.equal(out[k],false);
 newHolds++;
}
const good=make();a.equal(check(good),good);
const bad=make();bad.reported_review_diagnostics.disagreements=[2];a.equal(check(bad).status,'HOLD_REPORTED_VERDICT_INCONSISTENT');
const missing={status:'HOLD_RELEASE_PROVIDER'};a.equal(check(missing),missing);
console.log(JSON.stringify({scope:'exact R112 projection with synthetic R110 output only',old_accepts:oldAccepts,new_holds:newHolds,controls:3,native_accepted:false}));
