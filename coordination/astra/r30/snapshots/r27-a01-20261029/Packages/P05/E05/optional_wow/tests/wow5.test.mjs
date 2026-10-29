import test from 'node:test';
import assert from 'node:assert/strict';
import {
  applyCoreRingEvidence, applyStreamEvent, applyActionAck,
  applyFeedFreshness, setWow5Enabled, resetTransientSignals
} from '../assets/nox-wow5.mjs';

const now = Date.parse('2026-10-28T12:00:00Z');
const fresh = (kind, fields={}) => ({
  source:'events.v3', runId:'noxtest-8',
  timestamp:'2026-10-28T11:59:59Z', kind, ...fields
});
const el = () => ({ dataset:{}, style:{
  entries:{}, setProperty(k,v){this.entries[k]=v}, removeProperty(k){delete this.entries[k]}
}});

test('1. confirmed ring uses receipt and percent, not timer', () => {
  const e=el(); const ev=fresh('core.progress',{coreId:'core-1',state:'VERIFIED',receiptId:'sha256:example',percent:47});
  assert.equal(applyCoreRingEvidence(e,ev,now),true);
  assert.equal(e.dataset.noxWowRing,'verified');
  assert.equal(e.style.entries['--nox-wow-verified-level'],'0.47');
});
test('1. stale or unverifiable ring is unknown',()=>{
  const e=el();
  assert.equal(applyCoreRingEvidence(e,fresh('core.progress',{coreId:'core-1',state:'VERIFIED',percent:100}),now),false);
  assert.equal(e.dataset.noxWowRing,'unknown');
  assert.equal(applyCoreRingEvidence(e,{...fresh('core.progress',{coreId:'core-1',state:'VERIFIED',receiptId:'a',percent:100}),timestamp:'2026-10-27T11:59:59Z'},now),false);
});
test('3. tokens activate stream, completion deactivates',()=>{
  const e=el();
  assert.equal(applyStreamEvent(e,fresh('chat.token',{streamId:'S1'}),now),true);
  assert.equal(e.dataset.noxWowStream,'active');
  assert.equal(applyStreamEvent(e,fresh('chat.completed',{streamId:'S1'}),now),true);
  assert.equal(e.dataset.noxWowStream,'idle');
});
test('3. untrusted or stale token does not animate',()=>{
  const e=el();
  assert.equal(applyStreamEvent(e,{...fresh('chat.token',{streamId:'S1'}),source:'foreign-page'},now),false);
  assert.equal(e.dataset.noxWowStream,'unknown');
});
test('4. only confirmed acknowledgements produce success',()=>{
  const e=el();
  assert.equal(applyActionAck(e,fresh('action.ack',{actionId:'A',confirmed:false}),now),false);
  assert.equal(e.dataset.noxWowAck,'unknown');
  assert.equal(applyActionAck(e,fresh('action.ack',{actionId:'A',confirmed:true}),now),true);
  assert.equal(e.dataset.noxWowAck,'success');
  assert.equal(applyActionAck(e,fresh('action.error',{actionId:'A',confirmed:true}),now),true);
  assert.equal(e.dataset.noxWowAck,'error');
});
test('5. source timestamp determines fresh/stale/cache/offline',()=>{
  const e=el();
  const p={provider:'configured',sourceTimestamp:'2026-10-28T11:59:50Z',maxAgeMs:60000,status:'LIVE'};
  assert.equal(applyFeedFreshness(e,p,now),'fresh');
  assert.equal(applyFeedFreshness(e,{...p,status:'CACHE'},now),'cached');
  assert.equal(applyFeedFreshness(e,{...p,sourceTimestamp:'2026-10-28T11:50:00Z'},now),'stale');
  assert.equal(applyFeedFreshness(e,{...p,status:'OFFLINE'},now),'offline');
  assert.equal(applyFeedFreshness(e,{...p,sourceTimestamp:null},now),'unknown');
});
test('all five enhancements are opt in; safe transient reset',()=>{
  const root=el(), stream=el(), ack=el();
  setWow5Enabled(root,true); assert.equal(root.dataset.noxWow5,'on');
  setWow5Enabled(root,false); assert.equal(root.dataset.noxWow5,'off');
  stream.dataset.noxWowStream='active';ack.dataset.noxWowAck='success';
  resetTransientSignals({stream,ack});
  assert.equal(stream.dataset.noxWowStream,'unknown');
  assert.equal(ack.dataset.noxWowAck,'unknown');
});
