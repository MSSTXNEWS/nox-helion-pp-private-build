import assert from 'node:assert/strict';
import {test} from 'node:test';
import {projectFeeds} from './E05SpaceReadOnlyProjection.mjs';

const NOW=Date.parse('2026-10-28T03:45:00Z');
const receipt='a'.repeat(64);
const live={id:'brent', provider:'licensed-host', license_status:'APPROVED',
  license_receipt_sha256:receipt, status:'LIVE',
  source_at_utc:'2026-10-28T03:44:00Z', fetched_at_utc:'2026-10-28T03:44:50Z',
  ttl_ms:60000, parsed_by_owner:true, value:78};
const refused={...live,id:'weather',provider:'unlicensed-host',
  license_status:'DENIED',license_receipt_sha256:null};

test('R13 sixteen rejected known feeds cannot hide a licensed market price',()=>{
  const cards=projectFeeds([...Array(16).fill(refused),live],NOW);
  assert.equal(cards.length,16);
  assert.equal(cards[0].id,'brent');
  assert.equal(cards[0].stage,'SOURCE_DATED');
  assert.equal(cards[0].value,78);
});

test('R13 rejected source remains clearly disabled when no licensed source exists',()=>{
  const cards=projectFeeds([refused],NOW);
  assert.equal(cards.length,1);
  assert.equal(cards[0].id,'weather');
  assert.equal(cards[0].stage,'DISABLED');
  assert.equal(cards[0].value,null);
});

test('R13 duplicate licensed quotes remain quarantined despite rejected padding',()=>{
  const cards=projectFeeds([...Array(16).fill(refused),live,{...live,value:89}],NOW);
  assert.equal(cards[0].id,'brent');
  assert.equal(cards[0].stage,'HOLD_DUPLICATE_FEED');
  assert.equal(cards[0].value,null);
});

test('R13 licensed feed ordering stays stable and still obeys display cap',()=>{
  const weather={...live,id:'weather',value:22};
  const items=[weather,live,...Array(16).fill(refused)];
  const cards=projectFeeds(items,NOW);
  assert.equal(cards[0].id,'weather');
  assert.equal(cards[1].id,'brent');
  assert.equal(cards.length,16);
});
