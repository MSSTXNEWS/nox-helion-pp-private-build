'use strict';
// Executes the original WebView JavaScript with an inert DOM/host fixture.
// No browser, Windows host, downloads, installer or model weights are run.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const test = require('node:test');
const source = fs.readFileSync(path.join(__dirname, '../P03.ModelCenter.Wow/ui.js'), 'utf8');
function boot() {
  const nodes = new Map();
  function node() { return {children: [], value: '', checked: false, style: {setProperty() {}},
    classList: {add() {}, toggle() {}}, append(...items) {this.children.push(...items);},
    replaceChildren(...items) {this.children = items;}, setAttribute() {}, removeAttribute() {},
    addEventListener() {}, focus() {}}; }
  const document = {getElementById(id) {if (!nodes.has(id)) nodes.set(id, node()); return nodes.get(id);},
    createElement: node, querySelectorAll: () => [], addEventListener() {}};
  const context = vm.createContext({document, window: {}, URL, setTimeout: () => 1, clearTimeout() {}});
  vm.runInContext(source + '\nglobalThis.api = {state, processMessage, currentJob, hardwareCompatibility};', context);
  return {...context.api, nodes};
}
const id = '11111111-1111-1111-1111-111111111111';
const models = [{id: 'deepseek-r1', name: 'DeepSeek'}, {id: 'qwen3', name: 'Qwen'}];
function snapshot(api, job, extra = {}) {api.processMessage({type: 'p03.snapshot.v1', models,
  activeJob: job, capabilities: {stop: true, retry: true}, ...extra});}
function job(state = 'Queued') {return {jobId: id, modelId: 'deepseek-r1', modelTag: 'deepseek-r1', state};}
function event(api, phase, extra = {}) {api.processMessage({type: 'p03.event.v1', event:
  {jobId: id, modelTag: 'deepseek-r1', phase, status: phase, ...extra}});}

for (const [phase, expected] of [['completed', 'Completed'], ['failed', 'Failed'], ['cancelled', 'Cancelled']]) {
  test('background selected-model switch preserves ' + phase, () => {
    const api = boot(); snapshot(api, job('Running')); api.state.activeId = 'qwen3';
    event(api, phase); assert.equal(api.state.activeJob.state, expected);
    api.state.activeId = 'deepseek-r1'; assert.equal(api.currentJob().state, expected);
  });
}
test('started advances Queued to Running even while another model is selected', () => {
  const api = boot(); snapshot(api, job()); api.state.activeId = 'qwen3'; event(api, 'started');
  assert.equal(api.state.activeJob.state, 'Running');
});
test('started cannot undo STOP or a terminal result', () => {
  for (const state of ['Cancelling', 'Completed', 'Failed', 'Cancelled']) {
    const api = boot(); snapshot(api, job(state)); event(api, 'started');
    assert.equal(api.state.activeJob.state, state);
  }
});
test('another job or model cannot finish active transfer', () => {
  const api = boot(); snapshot(api, job('Running'));
  event(api, 'completed', {jobId: '22222222-2222-2222-2222-222222222222'});
  event(api, 'completed', {modelTag: 'qwen3'});
  assert.equal(api.state.activeJob.state, 'Running');
});
test('invalid snapshot cannot replace models or clear existing consent', () => {
  const api = boot(); snapshot(api, job('Running')); api.nodes.get('licenseAck').checked = true;
  const original = api.state.models;
  snapshot(api, {...job(), jobId: 'invalid'}, {models: [{id: 'qwen3', name: 'replacement'}]});
  assert.equal(api.state.models, original); assert.equal(api.state.activeId, 'deepseek-r1');
  assert.equal(api.nodes.get('licenseAck').checked, true);
});
test('invalid progress snapshot admission is atomic', () => {
  const api = boot(); snapshot(api, job('Running')); const original = api.state.models;
  snapshot(api, {...job(), completedBytes: 200, totalBytes: 100}, {models: [{id: 'qwen3', name: 'replacement'}]});
  assert.equal(api.state.models, original); assert.equal(api.state.activeJob.state, 'Running');
});
test('unknown-total progress preserves real transferred bytes without inventing percent', () => {
  const api = boot(); snapshot(api, job('Running'));
  event(api, 'progress', {completedBytes: 4096, totalBytes: null});
  assert.equal(api.state.activeJob.completedBytes, 4096);
  assert.equal(api.state.activeJob.totalBytes, null);
  assert.equal(api.nodes.get('transfer').textContent, '4 КБ / Н/Д');
  assert.equal(api.nodes.get('orbitLabel').textContent, 'Running');
});
test('unknown-total events cannot regress known byte counters', () => {
  const api = boot(); snapshot(api, {...job('Running'), completedBytes: 4096, totalBytes: 8192});
  event(api, 'progress', {completedBytes: 6144});
  assert.equal(api.state.activeJob.completedBytes, 6144);
  assert.equal(api.state.activeJob.totalBytes, 8192);
  event(api, 'progress', {completedBytes: 2048});
  assert.equal(api.state.activeJob.completedBytes, 6144);
  event(api, 'progress', {completedBytes: 16384});
  assert.equal(api.state.activeJob.completedBytes, 6144);
});
test('zero-total update keeps bytes visible and denominator unknown', () => {
  const api = boot(); snapshot(api, job('Running'));
  event(api, 'progress', {completedBytes: 1024, totalBytes: 0});
  assert.equal(api.state.activeJob.completedBytes, 1024);
  assert.equal(api.nodes.get('transfer').textContent, '1 КБ / Н/Д');
});
test('fractional and unsafe byte counts are not presented as measured progress', () => {
  for (const amount of [0.5, Number.MAX_SAFE_INTEGER + 1]) {
    const api = boot(); snapshot(api, {...job('Running'), completedBytes: amount, totalBytes: amount});
    assert.equal(api.state.activeJob.completedBytes, null);
    assert.equal(api.state.activeJob.totalBytes, null);
    event(api, 'progress', {completedBytes: amount, totalBytes: amount});
    assert.equal(api.state.activeJob.completedBytes, null);
  }
});
function reviewedModel(extra = {}) {return {id: 'deepseek-r1', name: 'DeepSeek', artifactVerified: true,
  exactTag: 'deepseek-r1:1.5b', immutableRevision: 'reviewed-revision', license: 'reviewed-license',
  licenseEvidenceUrl: 'https://example.invalid/license', artifactBytes: 1024, sha256: 'a'.repeat(64),
  manifestSha256: 'b'.repeat(64), compatibilityReviewed: true, recommendedRamGiB: 8, ...extra};}
test('reviewed RAM-only model uses actual available RAM', () => {
  const api = boot(); api.state.hardware = {ramFreeGiB: 16, vramFreeGiB: null};
  assert.equal(api.hardwareCompatibility(reviewedModel()), true);
  api.state.hardware.ramFreeGiB = 4;
  assert.equal(api.hardwareCompatibility(reviewedModel()), false);
});
test('RAM-only compatibility stays unknown for missing or invalid RAM reading', () => {
  const api = boot(); for (const ramFreeGiB of [null, undefined, NaN, -1, '16']) {
    api.state.hardware = {ramFreeGiB, vramFreeGiB: 24};
    assert.equal(api.hardwareCompatibility(reviewedModel()), null);
  }
});
test('positive GPU requirement cannot be bypassed by abundant system RAM', () => {
  const api = boot(), model = reviewedModel({requiredVramGiB: 8});
  api.state.hardware = {ramFreeGiB: 128, vramFreeGiB: 4};
  assert.equal(api.hardwareCompatibility(model), false);
  api.state.hardware.vramFreeGiB = null; assert.equal(api.hardwareCompatibility(model), null);
  api.state.hardware.vramFreeGiB = 12; assert.equal(api.hardwareCompatibility(model), true);
});
test('unreviewed memory requirement never produces compatible status', () => {
  const api = boot(); api.state.hardware = {ramFreeGiB: 128, vramFreeGiB: 24};
  assert.equal(api.hardwareCompatibility(reviewedModel({artifactVerified: false})), null);
});
