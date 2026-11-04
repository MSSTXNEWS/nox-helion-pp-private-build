import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

// F01: prove original native EXPRESS owner changes reach precisely one Windows
// E06 push build, without a duplicate PR build or a wildcard CI storm.
const source = readFileSync(new URL('../../.github/workflows/nox-v16-e06-d02-onehost.yml', import.meta.url), 'utf8');
function eventPaths(text, eventName) {
  let current = '';
  let paths = false;
  const selected = [];
  for (const line of text.split(/\r?\n/)) {
    const header = line.match(/^  (push|pull_request|workflow_dispatch):\s*$/);
    if (header) { current = header[1]; paths = false; continue; }
    if (current !== eventName) continue;
    if (/^    paths:\s*$/.test(line)) { paths = true; continue; }
    if (paths && /^    [a-z_]+:/.test(line)) { paths = false; continue; }
    if (paths) {
      const item = line.match(/^      - (.+?)\s*$/);
      if (item) selected.push(item[1].replace(/^['"]|['"]$/g, ''));
    }
  }
  return selected;
}
test('F01 exact native source change triggers one E06 push (not duplicate PR) and no wildcard storm', () => {
  const push = eventPaths(source, 'push');
  const pull = eventPaths(source, 'pull_request');
  for (const path of ['ui/nox-r11-wow.mjs', 'ui/firstboot-truth.mjs']) {
    assert.equal(push.filter(p => p === path).length, 1, path + ' must trigger exactly once');
    assert.equal(pull.includes(path), false, path + ' must not double-trigger PR build');
  }
  assert.equal(push.includes('coordination/e06/**'), true, 'existing stage pins kept');
  assert.equal(push.includes('.github/workflows/nox-v16-e06-d02-onehost.yml'), true, 'workflow change must trigger one run');
  assert.equal(push.some(p => p === '**' || p === '**/*' || p === 'ui/**'), false, 'no unbounded watch');
  assert.match(source, /group: nox-e06-onehost-/);
  assert.match(source, /cancel-in-progress: false/);
});
