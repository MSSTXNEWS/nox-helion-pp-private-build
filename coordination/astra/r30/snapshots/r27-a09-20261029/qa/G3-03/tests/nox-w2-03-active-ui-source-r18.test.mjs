/* NOX V16 · W2·03 · R18 · source-only independent D02/WOW UI QA.
 * Run with: node --test qa/G3-03/tests/nox-w2-03-active-ui-source-r18.test.mjs
 * No EXE, installer, network, host events, or original asset changes.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {dirname, join, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

const repo = resolve(dirname(fileURLToPath(import.meta.url)), '../../..');
const load = p => readFileSync(join(repo, p), 'utf8');
const homePath = 'integrations/wow200/runtime/home-scene.mjs';
const cssPath = 'proposals/NOX-CINEMA-FX/nox-cinema.css';
const coreIds = ['CONSCIOUSNESS', 'PERSONA', 'ATLAS', 'VOICE',
  'REFLECTION', 'CORE', 'NEXUS', 'FORGE'];

function capturedMount() {
  const code = load(homePath)
    .replace(/^import\s+\{installNoxCinemaFX\}[^\n]*\n/m, '')
    .replace(/\bexport const\b/g, 'const')
    .replace(/\bexport function\b/g, 'function') + '\nreturn mountApprovedHome;';
  // No global document: compile the exact repository's trusted UI source with
  // a no-op decorator spy; inspect the real arguments to the integration call.
  let passed;
  const scene = {setVisible: () => true, setProfile: () => true,
    snapshot: () => ({}), destroy: () => {}};
  const spy = options => {passed = options; return scene;};
  const mount = new Function('installNoxCinemaFX', 'document', code)(spy, undefined);
  const node = (extra = {}) => ({nodeType: 1, dataset: {},
    getAttribute: () => null, ...extra});
  const central = node();
  const orbs = coreIds.map(id => node({dataset: {coreId: id}}));
  const realButton = node({id: 'original-real-button'});
  const realPanel = node({id: 'original-real-panel'});
  const stage = {
    contains: el => [central, ...orbs, realButton, realPanel].includes(el),
    querySelector: s => s === '.nox-eclipse' ? central : null,
    querySelectorAll: s => s === '.nox-orbit-core' ? orbs :
      s === '.nox-eclipse' ? [central] :
      s.includes('control') || s.includes('button') ? [realButton] :
      s.includes('panel') ? [realPanel] : []
  };
  const home = {
    classList: {contains: c => c === 'screen' || c === 'active'},
    querySelector: s => s === '.nox-orbit-stage' ? stage : null,
    querySelectorAll: s => stage.querySelectorAll(s)
  };
  const view = {
    matchMedia: () => ({matches: false, addEventListener() {},
      removeEventListener() {}}),
    MutationObserver: class {observe() {} disconnect() {}}
  };
  const doc = {getElementById: id => id === 'home' ? home : null,
    body: {classList: {contains: () => false}}, defaultView: view};
  const instance = mount(doc);
  return {passed, instance, realButton, realPanel};
}

test('R18-01 approved nine D02 orbs remain the ORIGINAL nodes', () => {
  const {passed, instance} = capturedMount();
  assert.deepEqual(passed.orbs.map(x => x.id), ['HELION', ...coreIds]);
  assert.ok(instance.snapshot, 'live source must return mount controller');
  instance.destroy();
});

test('R18-02 active runtime wires existing real controls AND panels into FX', () => {
  const {passed, realButton, realPanel, instance} = capturedMount();
  assert.ok(Array.isArray(passed.controls) && passed.controls.includes(realButton),
    'UI_WIRING_HOLD: FX receives default controls=[]; verify approved DOM selectors');
  assert.ok(Array.isArray(passed.panels) && passed.panels.includes(realPanel),
    'UI_WIRING_HOLD: FX receives default panels=[]; verify approved DOM selectors');
  instance.destroy();
});

function animationDurationForEcoSecondChild(css) {
  // Source-only cascade check for the two original equal-specificity rules.
  // This does not claim browser layout, native navigation, or Windows PASS.
  const eco = [...css.matchAll(/\.nox-cinema-scope\[data-nox-fx-mode="eco"\]\s+\.nox-cinema-control\[data-nox-float="true"\]::before\s*\{\s*animation-duration:\s*([\d.]+)s\s*;?\s*\}/g)]
    .map(m => ({offset: m.index, duration: Number(m[1]), important: /!important/.test(m[0])}));
  const nth2 = [...css.matchAll(/\.nox-cinema-scope\s+\.nox-cinema-control\[data-nox-float="true"\]:nth-child\(4n\+2\)::before\s*\{\s*animation-duration:\s*([\d.]+)s\s*;/g)]
    .map(m => ({offset: m.index, duration: Number(m[1]), important: /!important/.test(m[0])}));
  assert.ok(eco.length && nth2.length, 'recheck CSS selector contract on owner changes');
  const a = eco.at(-1), b = nth2.at(-1);
  // Both have specificity (0,4,1); higher !important/order wins.
  return a.important !== b.important ? (a.important ? a.duration : b.duration) :
    (a.offset > b.offset ? a.duration : b.duration);
}

test('R18-03 ECO second floating button respects 10s minimum', () => {
  const duration = animationDurationForEcoSecondChild(load(cssPath));
  assert.ok(duration >= 10,
    'ECO_CASCADE_HOLD: second floating button <10s (' + duration + 's)');
});
