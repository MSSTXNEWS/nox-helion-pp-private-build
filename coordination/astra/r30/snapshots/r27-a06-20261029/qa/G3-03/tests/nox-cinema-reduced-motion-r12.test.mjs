/* NOX V16 · G3-03 · R12 · independent UI-only RED regression.
 * Load the exact current E01 mount source; replace imports ONLY inside a local
 * test evaluator so the media-query/profile logic executes with instrumented
 * dependencies. This is not proof of Windows/WebView2 runtime or approved art.
 * Owner: G3-03 QA. Never edit E01 source here.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';

const OWNER_PATH = new URL('../../../proposals/P01/WOW-MAX10/mount-p01.mjs', import.meta.url);

function probe(startReduced = false) {
  const source = readFileSync(OWNER_PATH, 'utf8');
  const gitBlob = createHash('sha1')
    .update('blob ' + Buffer.byteLength(source, 'utf8') + '\0')
    .update(source, 'utf8').digest('hex');
  const bare = source.replace(/^import[^\n]*\n/gm, '')
    .replace('export function mountP01Owner', 'function mountP01Owner');
  assert.match(bare, /function mountP01Owner\(/, 'exact E01 source not found');
  let reduced = startReduced, onMotion = null, fxMode = null;
  const fxModes = [];
  const media = {
    get matches() { return reduced; },
    addEventListener(type, fn) { if (type === 'change') onMotion = fn; },
    removeEventListener() { onMotion = null; }
  };
  const doc = {
    defaultView: { matchMedia: () => media },
    addEventListener() {}, removeEventListener() {}
  };
  const root = {nodeType: 1, ownerDocument: doc, contains: () => true};
  const orbs = Array.from({length: 9}, (_, i) =>
    ({id: i ? 'CORE' + i : 'HELION', element: {nodeType: 1}}));
  const fx = {
    setProfile(next) { fxMode = next; fxModes.push(next); return true; },
    snapshot() { return {profile: fxMode}; }, destroy() {}
  };
  const dependencies = {
    validateOwnerP01: () => ({helion: 1, cores: 8}),
    validateMode: next => ['ECO', 'BALANCED', 'MAX', 'REDUCED'].includes(next),
    createP01RouteDispatcher: () => ({
      close() {}, isPending() { return false; },
      async invoke() { return {ok: false}; }
    }),
    installNoxCinemaFX({profile}) {
      fxMode = profile; fxModes.push(profile); return fx;
    },
    createD02NativeVisualBus: () => ({
      subscribe() { return () => {}; },
      snapshot() { return {}; }, destroy() {}
    }),
    mountUnifiedCinema() { throw Error('secondary not used in this test'); },
    reviewWowScopes() {}, nativeVisualApproval() {},
    shortcutRoute() { return null; }
  };
  // This sandbox exercises the real file's entire mountP01Owner function while
  // replacing only imported host/DOM collaborators with controlled test doubles.
  const factory = new Function('deps',
    'const {' + Object.keys(dependencies).join(',') + '}=deps;\n'
    + bare + '\nreturn mountP01Owner;');
  const scene = factory(dependencies)({
    root, orbs, menu: [], buttons: [], hostPort: {},
    mode: 'BALANCED', homeActive: () => true
  });
  return {
    gitBlob, scene, fxModes,
    get fxMode() { return fxMode; },
    changeReduced(next) {
      reduced = next;
      onMotion?.({matches: next});
    }
  };
}

test('GREEN: ordinary BALANCED mode remains active with motion allowed', () => {
  const t = probe(false);
  try { assert.equal(t.fxMode, 'BALANCED'); }
  finally { t.scene.destroy(); }
});

test('GREEN: user MAX setting propagates when motion is allowed', () => {
  const t = probe(false);
  try {
    assert.equal(t.scene.setMode('MAX'), true);
    assert.equal(t.fxMode, 'MAX');
  } finally { t.scene.destroy(); }
});

test('RED: initial OS Reduced Motion must prevent FX animation immediately', () => {
  const t = probe(true);
  try { assert.equal(t.fxMode, 'REDUCED'); }
  finally { t.scene.destroy(); }
});

test('RED: changing OS preference to Reduced Motion must stop FX profile', () => {
  const t = probe(false);
  try {
    t.changeReduced(true);
    assert.equal(t.fxMode, 'REDUCED');
  } finally { t.scene.destroy(); }
});

test('RED: selecting MAX while OS Reduced Motion is active must stay reduced', () => {
  const t = probe(true);
  try {
    assert.equal(t.scene.setMode('MAX'), true);
    assert.equal(t.fxMode, 'REDUCED');
  } finally { t.scene.destroy(); }
});
