import assert from 'node:assert/strict';
import {test} from 'node:test';
import {projectFeeds} from './E05SpaceReadOnlyProjection.mjs';

const now=Date.parse('2026-10-28T23:00:00Z');
const quote={id:'brent',run_id:'E05-R19',provider:'LICENSED_PROVIDER',
  license_status:'APPROVED',license_receipt_sha256:'a'.repeat(64),
  status:'LIVE',parsed_by_owner:true,value:81.25,
  source_at_utc:'2026-10-28T22:58:00Z',
  fetched_at_utc:'2026-10-28T22:59:00Z',ttl_ms:120000,
  quote_currency:'USD',unit:'bbl'};
const single=feeds=>{
  const cards=projectFeeds(feeds,now);
  assert.equal(cards.length,1);
  return cards[0];
};

test('R19 same provider, source epoch and price re-polled at a new time is one observation',()=>{
  const card=single([quote,{...quote,fetched_at_utc:'2026-10-28T22:59:30Z'}]);
  assert.deepEqual([card.stage,card.value],['SOURCE_DATED',81.25]);
});

test('R19 native CACHE to LIVE handoff does not manufacture independent price source',()=>{
  const card=single([{...quote,status:'CACHE',ttl_ms:60000},
    {...quote,status:'LIVE',fetched_at_utc:'2026-10-28T22:59:30Z'}]);
  assert.deepEqual([card.stage,card.value],['SOURCE_DATED',81.25]);
});

test('R19 daily ECB quote with same owner date is not a second observation after refresh',()=>{
  const fx={...quote,id:'eur-usd',observation_date:'2026-10-28',value:1.16,
    source_at_utc:'2026-10-28T14:00:00Z',quote_currency:'USD',unit:'EUR'};
  const card=single([fx,{...fx,fetched_at_utc:'2026-10-28T22:59:20Z',
    source_at_utc:'2026-10-28T15:00:00Z'}]);
  assert.deepEqual([card.stage,card.value,card.observedKind],
    ['SOURCE_DATED',1.16,'ECB_OBSERVATION_DATE']);
});

test('R19 conflicting price from same provider at same epoch remains HOLD',()=>{
  const card=single([quote,{...quote,value:81.26,
    fetched_at_utc:'2026-10-28T22:59:30Z'}]);
  assert.deepEqual([card.stage,card.value],['HOLD_DUPLICATE_FEED',null]);
});

test('R19 changed provider, source timestamp or licensing receipt remain independent',()=>{
  for (const change of [
    {provider:'ANOTHER_PROVIDER'},
    {source_at_utc:'2026-10-28T22:57:00Z'},
    {license_receipt_sha256:'b'.repeat(64)},
    {quote_currency:'EUR'},
  ]) assert.equal(single([quote,{...quote,...change}]).stage,'HOLD_DUPLICATE_FEED');
});

test('R19 unbounded irrelevant provider metadata is not part of quote identity',()=>{
  const metadata={self:null};metadata.self=metadata;
  const card=single([quote,{...quote,metadata,
    fetched_at_utc:'2026-10-28T22:59:30Z'}]);
  assert.deepEqual([card.stage,card.value],['SOURCE_DATED',81.25]);
});

test('R19 previous R18 lesson: stale or unparsed quote cannot veto trusted one',()=>{
  const card=single([{...quote,status:'OFFLINE_CACHE',value:100},
    {...quote,parsed_by_owner:false,value:99},quote]);
  assert.deepEqual([card.stage,card.value],['SOURCE_DATED',81.25]);
});
