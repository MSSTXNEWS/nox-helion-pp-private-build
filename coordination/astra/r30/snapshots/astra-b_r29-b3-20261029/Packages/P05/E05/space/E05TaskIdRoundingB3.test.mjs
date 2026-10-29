import assert from 'node:assert/strict';
import * as fixed from './E05SpaceReadOnlyProjection.mjs';
const H='a'.repeat(64),run='B3-ROUNDING',at='2026-10-29T01:00:00Z',now=Date.parse(at);
function fixture(vals,reported,overall){
 const bars=vals.map((weight,i)=>({executor:i+1,stage:'CRITERIA_VERIFIED',percent:reported[i],manifest_sha256:H,receipt_sha256:H,total_tasks:weight===100?1:2,task_ledger:[{task_id:'T'+i,weight,status:'COMPONENT_VERIFIED',receipt_sha256:H},...(weight===100?[]:[{task_id:'P'+i,weight:100-weight,status:'HOLD'}])]}));
 return {run_id:run,source_commit:fixed.LOCKED_BASELINE,at_utc:at,native_attestation:'E06_OWNER_VERIFIED',bars:bars.concat([{executor:6,percent:null,stage:'HOLD'},{executor:7,percent:null,stage:'NOT_RUN'}]),overall};
}
const project=(m,f)=>m.projectReadiness(f,run,now);
const cases=[
['tiny pending truthful',fixture(Array(5).fill(99.999),Array(5).fill(99.99),99.99),r=>{assert.equal(r.overall,99.99);assert.ok(r.bars.slice(0,5).every(b=>b.percent===99.99));}],
['tiny pending forged100',fixture(Array(5).fill(99.999),Array(5).fill(100),100),r=>{assert.equal(r.overall,null);assert.ok(r.bars.slice(0,5).every(b=>b.percent!==100));}],
['overall re-rounding truthful',fixture([100,100,100,100,99.99],[100,100,100,100,99.99],99.99),r=>assert.equal(r.overall,99.99)],
['overall forged100',fixture([100,100,100,100,99.99],[100,100,100,100,99.99],100),r=>assert.equal(r.overall,null)],
['fully accepted',fixture(Array(5).fill(100),Array(5).fill(100),100),r=>{assert.equal(r.overall,100);assert.ok(r.bars.slice(0,5).every(b=>b.percent===100));}],
['ordinary weighted values',fixture([10,20,30,40,50],[10,20,30,40,50],28),r=>assert.equal(r.overall,28)],
['tiny weight lost in float sum',fixture(Array(5).fill(99.999),Array(5).fill(99.99),99.99),r=>{assert.equal(r.overall,99.99);assert.ok(r.bars.slice(0,5).every(b=>b.percent===99.99));}]
];
for(const b of cases.at(-1)[1].bars.slice(0,5)){b.task_ledger[0].weight=100;b.task_ledger[1].weight=Number.MIN_VALUE;}
for (const [name, fixture, check] of cases) {
  check(project(fixed, fixture));
  console.log('PASS', name);
}
console.log('PASS 7 B3 TaskID rounding scenarios');
