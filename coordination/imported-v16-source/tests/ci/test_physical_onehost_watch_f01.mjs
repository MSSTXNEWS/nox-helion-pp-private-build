import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

// F01: changes to original FIRSTBOOT, A1 and D02 stage must reach the
// exact-source Windows Setup producer. Keep E06's own source watch disjoint:
// this file must not add coordination/e06/** and cause duplicate Windows jobs.
const source = readFileSync(new URL('../../.github/workflows/nox-express-physical-onehost.yml', import.meta.url), 'utf8');
const inputs = [
  "coordination/express/stage_original_five_primary.py",
  "ui/menu-pages/express-wow-v3.test.mjs",
  "src/nox_selfbuilder/firstboot_coordinator.py",
  "src/nox_selfbuilder/a1_native_command.py",
  "src/nox_selfbuilder/acquisition_library.py",
  "tests/ci/test_physical_onehost_watch_f01.mjs"
];
function pushPaths(yaml) {
  const all = [];
  let insidePush = false;
  let insidePaths = false;
  for (const line of yaml.split(/\r?\n/)) {
    if (/^  push:\s*$/.test(line)) { insidePush = true; continue; }
    if (insidePush && /^  [a-z_]+:\s*$/.test(line)) break;
    if (!insidePush) continue;
    if (/^    paths:\s*$/.test(line)) { insidePaths = true; continue; }
    if (insidePaths && /^    [a-z_]+:\s*$/.test(line)) { insidePaths = false; continue; }
    if (insidePaths) {
      const found = line.match(/^      - ['"]?([^'"#]+?)['"]?\s*$/);
      if (found) all.push(found[1]);
    }
  }
  return all;
}
test('F01 original D02/firstboot/owner changes reach exactly one physical push producer', () => {
  const paths = pushPaths(source);
  for (const name of inputs) {
    assert.equal(paths.filter(item => item === name).length, 1, 'missing or duplicate: '+name);
  }
});
test('F01 no broad E06 duplicate or new PR trigger, preserve immutable serialization', () => {
  const paths = pushPaths(source);
  assert.equal(paths.includes('coordination/e06/**'), false);
  assert.equal(paths.some(p => p === '**' || p === '**/*' || p === 'src/**' || p === 'ui/**'), false);
  assert.doesNotMatch(source, /^  pull_request:\s*$/m);
  assert.match(source, /group: nox-express-physical-/);
  assert.match(source, /cancel-in-progress: false/);
});
test('F01 enforce watcher before expensive source ZIP / NSIS / Windows compile', () => {
  const testInvocation = source.indexOf('node --test tests/ci/test_physical_onehost_watch_f01.mjs');
  const sourcePack = source.indexOf('express_source_snapshot_pack.py --repo');
  const nsis = source.indexOf('Official portable NSIS 3.13');
  assert.ok(testInvocation > 0 && testInvocation < sourcePack && sourcePack < nsis);
  assert.match(source, /EXPRESS_PHYSICAL_OWNER_WATCH_INPUT_HOLD/);
});
