import assert from 'node:assert/strict';
import {test} from 'node:test';
import {projectFeeds} from './E05SpaceReadOnlyProjection.mjs';
const now=Date.parse('2026-10-28T18:40:00Z');
const good={id:'brent', provider:'licensed-market', license_status:'APPROVED',
  license_receipt_sha256:'a'.repeat(64), status:'LIVE', parsed_by_owner:true,
  value:80.5, source_at_utc:'2026-10-28T18:39:00Z',
  fetched_at_utc:'2026-10-28T18:39:30Z', ttl_ms:60000};
const denied={...good,license_status:'DENIED',license_receipt_sha256:null,
  provider:'unapproved',value:999};

test('R14 unlicensed duplicate after licensed cannot make Brent HOLD',()=>{
  const cards=projectFeeds([good,denied],now);
  assert.equal(cards.length,1);
  assert.deepEqual([cards[0].id,cards[0].stage,cards[0].value],
    ['brent','SOURCE_DATED',80.5]);
});
test('R14 unlicensed duplicate before licensed cannot make Brent HOLD',()=>{
  const cards=projectFeeds([denied,good],now);
  assert.equal(cards.length,1);
  assert.equal(cards[0].stage,'SOURCE_DATED');
  assert.equal(cards[0].value,80.5);
});
test('R14 malformed provider on APPROVED receipt is not a trusted quote',()=>{
  const invalid={...good,provider:'  ',value:999};
  const cards=projectFeeds([invalid,good],now);
  assert.equal(cards.length,1);
  assert.equal(cards[0].stage,'SOURCE_DATED');
  assert.equal(cards[0].value,80.5);
});
test('R14 approved-but-invalid-provider padding cannot consume 16 slots',()=>{
  const fake={...good,id:'weather',provider:' ',value:20};
  const cards=projectFeeds([...Array(16).fill(fake),good],now);
  assert.equal(cards[0].id,'brent');
  assert.equal(cards[0].value,80.5);
});
test('R14 two approved conflicting quotes remain HOLD, rejected third irrelevant',()=>{
  const cards=projectFeeds([good,denied,{...good,value:81}],now);
  assert.equal(cards.length,1);
  assert.equal(cards[0].stage,'HOLD_DUPLICATE_FEED');
  assert.equal(cards[0].value,null);
});
test('R14 sole unlicensed market remains explicit DISABLED',()=>{
  const cards=projectFeeds([denied],now);
  assert.equal(cards.length,1);
  assert.equal(cards[0].stage,'DISABLED');
  assert.equal(cards[0].value,null);
});
