import assert from 'node:assert/strict';
import {test} from 'node:test';
import {projectFeeds} from './E05SpaceReadOnlyProjection.mjs';
const now=Date.parse('2026-10-28T03:45:00Z');
const base={id:'weather',provider:'approved',license_status:'APPROVED',license_receipt_sha256:'a'.repeat(64),status:'LIVE',source_at_utc:'2026-10-28T03:44:00Z',fetched_at_utc:'2026-10-28T03:44:50Z',ttl_ms:60000,parsed_by_owner:true,value:14};
test('R12 filter before capping',()=>{
  const padding=Array(16).fill({id:'unapproved'});
  assert.equal(projectFeeds([...padding,base],now)[0]?.id,'weather');
  assert.equal(projectFeeds([...padding,{...base,id:'bitcoin',license_status:'UNKNOWN',value:90000}],now)[0]?.value,null);
});
test('R12 duplicate market quarantine still scans full batch',()=>{
  const arr=[...Array(16).fill({id:'unknown'}),{...base,id:'brent',value:78},{...base,id:'brent',value:80}];
  assert.equal(projectFeeds(arr,now)[0]?.stage,'HOLD_DUPLICATE_FEED');
});
test('R12 bounded known feed display',()=>{
  assert.equal(projectFeeds(Array(18).fill({...base,id:'nox-news'}),now).length,16);
  assert.equal(projectFeeds(Array(4097).fill(base),now).length,0);
});
