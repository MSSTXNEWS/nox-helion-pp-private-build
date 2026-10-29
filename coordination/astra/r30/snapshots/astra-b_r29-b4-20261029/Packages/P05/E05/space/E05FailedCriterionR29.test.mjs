import {test} from 'node:test';
import assert from 'node:assert/strict';
import {projectReadiness,LOCKED_BASELINE} from './E05SpaceReadOnlyProjection.mjs';
const now=Date.parse('2026-10-29T01:00:00Z'), h='a'.repeat(64), run='R29-A05';
const input=()=>({run_id:run,source_commit:LOCKED_BASELINE,at_utc:'2026-10-29T01:00:00Z',native_attestation:'E06_OWNER_VERIFIED',overall:87.5,
 bars:[1,2,3,4,5].map(i=>({executor:i,stage:'CRITERIA_VERIFIED',percent:i===2?50:100,total_tasks:2,manifest_sha256:h,receipt_sha256:h,
 task_ledger:[{task_id:`P0${i}-A`,weight:50,status:'COMPONENT_VERIFIED',receipt_sha256:h},
 {task_id:`P0${i}-B`,weight:50,status:i===2?'FAILED':'COMPONENT_VERIFIED',...(i===2?{}:{receipt_sha256:h})}]}))
 .concat([{executor:6,stage:'HOLD',percent:null},{executor:7,stage:'NOT_RUN',percent:null}])});
test('failed criterion remains in fixed denominator as zero credit',()=>{
 const r=projectReadiness(input(),run,now);assert.equal(r.bars[1].percent,50);assert.equal(r.overall,87.5);
});
test('failed criterion cannot smuggle a success receipt or inflate completion',()=>{
 for(const mutate of [r=>r.bars[1].task_ledger[1].receipt_sha256=h,r=>r.bars[1].percent=100]){
  const r=input();mutate(r);const out=projectReadiness(r,run,now);assert.equal(out.bars[1].percent,null);assert.equal(out.overall,null);
 }
});
test('all failed criteria yield measured zero, not unknown denominator',()=>{
 const r=input();for(const b of r.bars.slice(0,5)){b.percent=0;for(const t of b.task_ledger){t.status='FAILED';delete t.receipt_sha256;}}r.overall=0;
 assert.equal(projectReadiness(r,run,now).overall,0);
});
