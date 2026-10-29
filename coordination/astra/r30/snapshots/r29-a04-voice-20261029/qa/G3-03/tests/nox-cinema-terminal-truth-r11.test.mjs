/* NOX V16 G3-03 R11 — independent UI-only RED regression.
 * Owner: G3-03 QA. Tested against the exact PR #162 E01 source.
 * This is not an installed Windows EXE test; do not edit E01/E05 product code here.
 * A terminal visual indication must follow a coherent, verified native envelope.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import {visualEvent, attachCinemaToNativeEvents} from '../../../proposals/NOX-CINEMA-FX/nox-cinema-events.mjs';
import {gravitationalSample} from '../candidates/nox-cinema.mjs';

const NOW = Date.parse('2026-10-28T13:00:00.000Z');
const good = Object.freeze({
  schema: 'NOX-INSTALLER-EVENT-v3', run_id: 'NOX_R11',
  event_id: 'NOX_R11_01', event_sequence: 1,
  event_type: 'task.completed', task_id: 'V16_26_3_R11',
  package_id: 'P04', action_id: 'training.eval',
  timestamp_utc: new Date(NOW).toISOString(), state: 'COMPLETED',
  source: 'P04.QLoRA', message: '', numerator: 1,
  denominator: 1, evidence_verified: true
});

// GREEN controls: denying contradictory events must not break real, valid ones.
test('coherent verified completion may show decorative success', () => {
  assert.equal(visualEvent({...good}, NOW)?.state, 'success');
});
test('real in-progress training may show a decorative training state', () => {
  assert.equal(visualEvent({...good, event_type: 'task.progress',
    state: 'RUNNING'}, NOW)?.state, 'training');
});

// RED cases: these are source defects, not proof of installed-runtime impact.
test('a task.completed envelope with FAILED native state must not show success', () => {
  assert.equal(visualEvent({...good, state: 'FAILED'}, NOW), null);
});
test('a task.failed envelope with COMPLETED native state must not show error', () => {
  assert.equal(visualEvent({...good, event_type: 'task.failed'}, NOW), null);
});
test('a completion without verified evidence must not assert visual success', () => {
  assert.equal(visualEvent({...good, evidence_verified: false}, NOW), null);
});
test('late in-progress event must not reverse terminal success within same RunID', () => {
  const states = []; let emit;
  const unsubscribe = attachCinemaToNativeEvents(
    {setState: state => states.push(state)},
    callback => {emit = callback; return () => {};},
    {now: () => NOW}
  );
  emit({...good, event_sequence: 2, event_id: 'NOX_R11_DONE'});
  emit({...good, event_sequence: 3, event_id: 'NOX_R11_LATE',
    event_type: 'task.progress', state: 'RUNNING'});
  unsubscribe();
  assert.deepEqual(states, ['success']);
});
test('finite but overflowing particle inputs cannot produce NaN/Infinity SVG', () => {
  const input = {started: 0, duration: 1000, surfaceRadius: 1e308,
    reach: 1e308, angle: 0.3, swirl: 4, brightness: 0.6,
    rotation: 3};
  let result;
  try {result = gravitationalSample(input, 500);} catch {return;}
  assert.ok(Number.isFinite(result.x) && Number.isFinite(result.y),
    'reject such geometry or return finite positions');
});
