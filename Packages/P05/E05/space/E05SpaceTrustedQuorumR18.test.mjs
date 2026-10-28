import assert from 'node:assert/strict';
import {test} from 'node:test';
import {projectFeeds} from './E05SpaceReadOnlyProjection.mjs';
const now=Date.parse('2026-10-29T00:00:00Z');
const live={id:'brent',run_id:'E05-R18',provider:'MARKET_PRO',license_status:'APPROVED',
  license_receipt_sha256:'a'.repeat(64),status:'LIVE',parsed_by_owner:true,
  value:81.25,source_at_utc:'2026-10-28T23:58:00Z',
  fetched_at_utc:'2026-10-28T23:59:00Z',ttl_ms:180000};
const one=items=>{const r=projectFeeds(items,now);assert.equal(r.length,1);return r[0];};
test('R18 approved unparsed quote cannot turn owner-parsed current Brent into HOLD',()=>{
  const r=one([{...live,parsed_by_owner:false,value:9999},live]);
  assert.deepEqual([r.stage,r.value],['SOURCE_DATED',81.25]);
});
test('R18 malformed approved timestamp cannot block a dated live quote',()=>{
  const r=one([{...live,source_at_utc:'2026-02-30T00:00:00Z'},live]);
  assert.deepEqual([r.stage,r.value],['SOURCE_DATED',81.25]);
});
test('R18 authenticated offline cache cannot block a fresh market quote',()=>{
  const r=one([{...live,status:'OFFLINE_CACHE',value:72},live]);
  assert.deepEqual([r.stage,r.value],['SOURCE_DATED',81.25]);
});
test('R18 expired TTL cannot block a freshly fetched market quote',()=>{
  const r=one([{...live,fetched_at_utc:'2026-10-28T20:00:00Z'},live]);
  assert.deepEqual([r.stage,r.value],['SOURCE_DATED',81.25]);
});
test('R18 two genuinely current distinct licensed quotes still HOLD',()=>{
  const r=one([live,{...live,value:82.1}]);
  assert.deepEqual([r.stage,r.value],['HOLD_DUPLICATE_FEED',null]);
});
test('R18 previous replay lesson remains: identical current receipt is one observation',()=>{
  const r=one([live,{...live}]);
  assert.deepEqual([r.stage,r.value],['SOURCE_DATED',81.25]);
});
test('R18 no live quote: stale cache is labelled stale, not LIVE or HOLD',()=>{
  const r=one([{...live,status:'OFFLINE_CACHE',value:72}]);
  assert.deepEqual([r.stage,r.value],['STALE_CACHE',null]);
});
test('R18 no trusted quote: two unparsed approved replays cannot invent price or HOLD',()=>{
  const r=one([{...live,parsed_by_owner:false},{...live,parsed_by_owner:false,value:82.5}]);
  assert.deepEqual([r.stage,r.value],['SOURCE_DATED',null]);
});
