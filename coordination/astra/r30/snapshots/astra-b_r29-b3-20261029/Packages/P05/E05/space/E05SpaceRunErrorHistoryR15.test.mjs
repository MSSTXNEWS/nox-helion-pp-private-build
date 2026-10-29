import assert from 'node:assert/strict';
import {test} from 'node:test';
import {projectCanonicalEvents,EVENT_SCHEMA} from './E05SpaceReadOnlyProjection.mjs';

const RUN='NOX-V16-W4-02-R15';
const NOW=Date.parse('2026-10-28T19:05:00Z');
const make=(event_id,event_type,state,timestamp_utc)=>({
  schema:EVENT_SCHEMA,run_id:RUN,event_id,task_id:'P05-STOP-01',
  event_type,package_id:event_type==='model.stopped'?'P04':'P05',action_id:'host-stop',
  timestamp_utc,state,source:'P05.Host',message:'Verified native terminal',
  numerator:null,denominator:null,evidence_verified:true
});
const oldError=make('err-old','task.failed','ERROR','2026-10-28T19:03:00Z');
const recentStop=make('stop-new','model.stopped','STOPPED','2026-10-28T19:04:58Z');

test('R15 verified old same-run failure remains in total while state ages to N_D',()=>{
  assert.deepEqual(projectCanonicalEvents([oldError],RUN,NOW),{state:'N_D',errors:1});
});
test('R15 fresh STOP does not erase older independently verified failure count',()=>{
  assert.deepEqual(projectCanonicalEvents([oldError,recentStop],RUN,NOW),{state:'STOPPED',errors:1});
});
test('R15 old identical replay is not double-counted',()=>{
  assert.deepEqual(projectCanonicalEvents([oldError,oldError,recentStop],RUN,NOW),{state:'STOPPED',errors:1});
});
test('R15 reusing stale terminal event ID for a fresh different state is HOLD',()=>{
  const collision={...recentStop,event_id:'err-old'};
  assert.deepEqual(projectCanonicalEvents([oldError,collision],RUN,NOW),
    {state:'HOLD_EVENT_ID_COLLISION',errors:null});
});
test('R15 future timestamp cannot create historical error or live success',()=>{
  const future={...oldError,timestamp_utc:'2026-10-28T19:06:00Z'};
  assert.deepEqual(projectCanonicalEvents([future],RUN,NOW),{state:'N_D',errors:0});
});
test('R15 foreign run errors do not count in active run',()=>{
  assert.deepEqual(projectCanonicalEvents([{...oldError,run_id:'OTHER'}],RUN,NOW),
    {state:'N_D',errors:0});
});
