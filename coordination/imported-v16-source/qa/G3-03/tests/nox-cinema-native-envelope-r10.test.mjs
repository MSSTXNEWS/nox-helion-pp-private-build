/*
 * NOX V16 G3-03 R10 / UI-only native event envelope contract.
 * Independent QA: RED tests against the currently staged E01 visual adapter.
 * Do not modify E01 source or map a source fixture to accepted Windows EXE.
 */
import test from "node:test";
import assert from "node:assert/strict";
import {visualEvent} from "../../../proposals/NOX-CINEMA-FX/nox-cinema-events.mjs";

const NOW = Date.parse("2026-10-28T12:00:00.000Z");
const envelope = Object.freeze({
  schema: "NOX-INSTALLER-EVENT-v3",
  run_id: "RUN_R10",
  event_id: "EVENT_R10",
  event_sequence: 1,
  event_type: "task.completed",
  task_id: "G3_03_R10_08",
  package_id: "P04",
  action_id: "training.eval",
  timestamp_utc: new Date(NOW).toISOString(),
  state: "COMPLETED",
  source: "P04.QLoRA",
  message: "",
  numerator: 1,
  denominator: 1,
  evidence_verified: true
});

test("valid full v3 completion yields cosmetic success (not product acceptance)", () => {
  assert.equal(visualEvent({...envelope}, NOW)?.state, "success");
});

test("missing required native envelope fields never render visual success", () => {
  for(const key of [
    "task_id", "source", "message", "numerator", "denominator",
    "evidence_verified"
  ]) {
    const ev = {...envelope};
    delete ev[key];
    assert.equal(visualEvent(ev, NOW), null, key + " must be required");
  }
});

test("invalid v3 field types and bounds never render visual success", () => {
  const cases = [
    {message: 99},
    {source: 3},
    {task_id: ""},
    {numerator: -1},
    {denominator: "one"},
    {evidence_verified: "yes"}
  ];
  for(const bad of cases) {
    assert.equal(visualEvent({...envelope,...bad}, NOW), null,
      JSON.stringify(bad) + " must be rejected before UI state change");
  }
});

test("non-RFC3339 UTC timestamps cannot trigger visual success", () => {
  assert.equal(visualEvent({...envelope,
    timestamp_utc: "2026-10-28 12:00:00"}, NOW), null);
});
