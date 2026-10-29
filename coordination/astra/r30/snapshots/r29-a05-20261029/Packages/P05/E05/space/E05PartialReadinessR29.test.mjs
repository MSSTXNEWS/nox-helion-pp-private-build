import {test} from 'node:test';
import assert from 'node:assert/strict';
import {projectReadiness,LOCKED_BASELINE} from './E05SpaceReadOnlyProjection.mjs';
const now=Date.parse('2026-10-29T01:00:00Z'), hash='a'.repeat(64), run='R29-A05';
const bar=i=>({executor:i,stage:'CRITERIA_VERIFIED',percent:100,total_tasks:1,
  task_ledger:[{task_id:`P0${i}-A`,weight:100,status:'COMPONENT_VERIFIED',receipt_sha256:hash}],manifest_sha256:hash,receipt_sha256:hash});
const input=()=>({run_id:run,source_commit:LOCKED_BASELINE,at_utc:'2026-10-29T01:00:00Z',native_attestation:'E06_OWNER_VERIFIED',overall:100,
  bars:[1,2,3,4,5].map(bar).concat([{executor:6,stage:'HOLD',percent:null},{executor:7,stage:'NOT_RUN',percent:null}])});
test('one unknown owner denominator preserves other four independently verified bars',()=>{
  for(let unknown=0;unknown<5;unknown++){
    const r=input();delete r.bars[unknown].task_ledger;
    const out=projectReadiness(r,run,now);
    assert.deepEqual(out.bars.slice(0,5).map(b=>b.percent),[0,1,2,3,4].map(i=>i===unknown?null:100));
    assert.equal(out.overall,null);assert.equal(out.reason,'LANE_OWNER_SEAL_MISSING');
  }
});
test('unsealed lane percent never contributes to overall or its own bar',()=>{
  const r=input();r.bars[1].receipt_sha256=null;r.bars[3].percent=10;
  const out=projectReadiness(r,run,now);
  assert.deepEqual(out.bars.slice(0,5).map(b=>b.percent),[100,null,100,null,100]);assert.equal(out.overall,null);
});
test('global TaskID collision quarantines all partial progress',()=>{
  const r=input();r.bars[1].task_ledger=null;r.bars[4].task_ledger[0].task_id='P01-A';
  const out=projectReadiness(r,run,now);assert.equal(out.reason,'CROSS_LANE_TASK_COLLISION');
  assert.ok(out.bars.slice(0,5).every(b=>b.percent===null));
});
test('foreign run never leaks partially verified bars',()=>{
 assert.ok(projectReadiness(input(),'OTHER',now).bars.every(b=>b.percent===null));
});
