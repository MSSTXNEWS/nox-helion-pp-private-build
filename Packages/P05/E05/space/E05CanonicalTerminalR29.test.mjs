import {test} from 'node:test';
import assert from 'node:assert/strict';
import {EVENT_SCHEMA,projectCanonicalEvents} from './E05SpaceReadOnlyProjection.mjs';
// Contracts/events.v3.json blob 5204e668ab39e4bf4955ff7b405279628b5bbef2:
// model.stopped belongs to P04; numerator and denominator are required.
const now=Date.parse('2026-10-29T02:00:00Z'),run='R29-A05';
const event=(type='model.stopped',pkg='P04')=>({schema:EVENT_SCHEMA,run_id:run,
 event_id:'terminal-1',task_id:'P04-STOP',action_id:'stop',package_id:pkg,
 event_type:type,state:type==='model.stopped'?'STOPPED':'ERROR',
 timestamp_utc:'2026-10-29T01:59:59Z',source:pkg+'.Worker',message:'Native terminal',
 numerator:null,denominator:null,evidence_verified:true});
const project=e=>projectCanonicalEvents([e],run,now);
test('schema P04 STOP and generic owner failures still project',()=>{
 assert.deepEqual(project(event()),{state:'STOPPED',errors:0});
 for(const owner of ['P01','P02','P03','P04','P05','E06','E07'])
  assert.deepEqual(project(event('task.failed',owner)),{state:'ERROR',errors:1});
});
test('non-P04 model.stopped cannot impersonate trainer STOP',()=>{
 for(const owner of ['P01','P02','P03','P05','E06','E07'])
  assert.deepEqual(project(event('model.stopped',owner)),{state:'HOLD_MALFORMED_TERMINAL',errors:null});
});
test('missing required counters or impossible counter pair is quarantined',()=>{
 for(const counters of [{numerator:undefined,denominator:undefined},{numerator:null,denominator:4},
  {numerator:4,denominator:null},{numerator:1.5,denominator:4},{numerator:5,denominator:4},
  {numerator:0,denominator:0},{numerator:-1,denominator:4},{numerator:'1',denominator:4},
  {numerator:1,denominator:Number.MAX_SAFE_INTEGER+1}])
  assert.equal(project({...event(),...counters}).state,'HOLD_MALFORMED_TERMINAL');
});
test('known bounded progress on STOP remains observed progress, never completion',()=>{
 for(const numerator of [0,2,4]) assert.deepEqual(project({...event(),numerator,denominator:4}),{state:'STOPPED',errors:0});
});
test('same event identity with changed counter receipt is collision',()=>{
 const a={...event(),numerator:1,denominator:4};const b={...a,numerator:2};
 assert.deepEqual(projectCanonicalEvents([a,b],run,now),{state:'HOLD_EVENT_ID_COLLISION',errors:null});
 assert.deepEqual(projectCanonicalEvents([a,{...a}],run,now),{state:'STOPPED',errors:0});
});
test('canonical identity lengths cannot exceed schema128',()=>{
 for(const key of ['run_id','event_id','task_id','action_id']) {
  const e={...event(),[key]:'x'.repeat(129)};
  assert.equal(projectCanonicalEvents([e],e.run_id,now).state,'HOLD_MALFORMED_TERMINAL');
 }
});
