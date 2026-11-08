import assert from 'node:assert/strict';
import {test} from 'node:test';
import {projectFeeds} from './E05SpaceReadOnlyProjection.mjs';
const now=Date.parse('2026-10-28T21:03:00Z');
const approved={id:'brent',provider:'LICENSED_A',license_status:'APPROVED',
  license_receipt_sha256:'a'.repeat(64),status:'LIVE',parsed_by_owner:true,
  value:82.5,source_at_utc:'2026-10-28T21:02:00Z',
  fetched_at_utc:'2026-10-28T21:02:20Z',ttl_ms:60000};
const card=(items)=>projectFeeds(items,now)[0];
test('R17 identical approved market feed replay is one observation, not false conflict',()=>{
  const result=projectFeeds([approved,{...approved}],now);
  assert.equal(result.length,1);
  assert.deepEqual([result[0].stage,result[0].value],['SOURCE_DATED',82.5]);
});
test('R17 identical quote with different object key order is a replay',()=>{
  const reversed=Object.fromEntries(Object.entries(approved).reverse());
  assert.deepEqual([card([approved,reversed]).stage,card([approved,reversed]).value],
    ['SOURCE_DATED',82.5]);
});
test('R17 two distinct approved price values stay HOLD',()=>{
  const out=card([approved,{...approved,value:82.6}]);
  assert.deepEqual([out.stage,out.value],['HOLD_DUPLICATE_FEED',null]);
});
test('R17 different authenticated provider stays HOLD even with same value',()=>{
  const out=card([approved,{...approved,provider:'LICENSED_B'}]);
  assert.deepEqual([out.stage,out.value],['HOLD_DUPLICATE_FEED',null]);
});
test('R17 mismatching timestamp is distinct even when value equal',()=>{
  const out=card([approved,{...approved,source_at_utc:'2026-10-28T21:01:00Z'}]);
  assert.equal(out.stage,'HOLD_DUPLICATE_FEED');
});
test('R17 duplicate licensed replay before a second distinct quote remains HOLD',()=>{
  const out=card([approved,{...approved},{...approved,value:77}]);
  assert.equal(out.stage,'HOLD_DUPLICATE_FEED');
});
test('R17 rejected duplicate does not contaminate licensed replay',()=>{
  const denied={...approved,license_status:'DENIED',provider:'SPOOF'};
  const out=projectFeeds([denied,approved,{...approved}],now);
  assert.equal(out.length,1);
  assert.deepEqual([out[0].stage,out[0].value],['SOURCE_DATED',82.5]);
});
