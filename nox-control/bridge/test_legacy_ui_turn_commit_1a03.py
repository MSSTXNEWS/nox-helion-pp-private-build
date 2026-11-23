#!/usr/bin/env python3
"""RELAY35 1A03: exercise the actual embedded legacy browser with fake SSE.

Source-only browser behavior regression. No server/model/S03 contact and no
claim of a native two-turn acceptance.
"""
import ast
from pathlib import Path
import subprocess
import unittest


NODE = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
(async () => {
  const html = fs.readFileSync(0, 'utf8');
  const found = html.match(/<script>([\s\S]*?)<\/script>/);
  assert(found, 'legacy browser script exists');
  const node = () => ({
    value: '', textContent: '', disabled: false, children: [],
    appendChild(child) { this.children.push(child); },
    remove() { this.removed = true; },
    focus() { this.focused = true; }
  });
  const ids = new Map();
  const get = id => {
    if (!ids.has(id)) ids.set(id, node());
    return ids.get(id);
  };
  const document = {
    getElementById: get,
    querySelector: selector => {
      assert.equal(selector, '#f button');
      return get('submit');
    },
    createElement: () => node()
  };
  const seen = [];
  let requests = 0;
  const frame = obj => 'data: ' + JSON.stringify(obj) + '\n\n';
  const response = objects => ({
    ok: true,
    body: { getReader() {
      let once = false;
      return { async read() {
        if (once) return { done: true };
        once = true;
        return {
          done: false,
          value: new TextEncoder().encode(objects.map(frame).join(''))
        };
      } };
    } }
  });
  let unblock = null;
  const fetch = async (url, options) => {
    if (url === '/feedback') return { ok: true };
    assert.equal(url, '/v1/chat/stream');
    seen.push(JSON.parse(options.body).messages);
    requests += 1;
    if (requests === 1) return response([
      { type: 'token', text: 'partial' },
      { type: 'error', text: 'upstream fault' }
    ]);
    if (requests === 2) return response([
      { type: 'token', text: 'Полный ответ ✅' },
      { type: 'done', generation_complete: true,
        memory_write_receipt: {
          status: 'WRITE_RETURNED_UNVERIFIED',
          s03_readback_verified: false
        } }
    ]);
    if (requests === 3) return response([
      { type: 'token', text: 'not final' },
      { type: 'done', generation_complete: true,
        memory_write_receipt: { status: 'WRITE_RETURNED_UNVERIFIED' } },
      { type: 'error', text: 'late transport fault' }
    ]);
    if (requests >= 5) return response([
      { type: 'token', text: 'Continued ✅' },
      { type: 'done', generation_complete: true,
        memory_write_receipt: { status: 'WRITE_RETURNED_UNVERIFIED',
                                s03_readback_verified: false } }
    ]);
    return new Promise(resolve => { unblock = resolve; });
  };
  const context = vm.createContext({ document, fetch, TextDecoder, console });
  vm.runInContext(found[1], context);
  const send = get('f').onsubmit;
  const submit = async text => {
    get('i').value = text;
    await send({ preventDefault() {} });
  };
  await submit('FAILED_ORIGINAL');
  assert.equal(vm.runInContext('hist.length', context), 0);
  assert.equal(get('submit').disabled, false);
  await submit('SUCCESS_NEXT');
  assert.deepEqual(seen[1], [{ role: 'user', content: 'SUCCESS_NEXT' }],
    'failed turn is not replayed to model');
  assert.equal(vm.runInContext('hist.length', context), 2);
  assert(get('log').children.some(
    entry => entry.textContent.includes('чтение S03 не подтверждено')),
    'unverified memory must be visibly identified');
  await submit('LATE_ERROR');
  assert.equal(vm.runInContext('hist.length', context), 2,
    'a late SSE error cannot commit a chat turn');
  get('i').value = 'SLOW_REQUEST';
  const waiting = send({ preventDefault() {} });
  get('i').value = 'CONCURRENT_REQUEST';
  await send({ preventDefault() {} });
  assert.equal(requests, 4, 'second submission must not race live request');
  assert.equal(get('submit').disabled, true);
  unblock(response([{ type: 'error', text: 'hold' }]));
  await waiting;
  assert.equal(get('submit').disabled, false);
  assert.equal(vm.runInContext('hist.length', context), 2);
  for (let i = 0; i < 5; i++) await submit('LONG_DIALOGUE_' + i);
  assert.equal(vm.runInContext('hist.length', context), 12);
  assert.equal(seen[8].length, 11,
    'legacy UI must send every previously completed turn, not slice to six');
  assert.equal(seen[8][0].content, 'SUCCESS_NEXT');
  assert.equal(seen[8][10].content, 'LONG_DIALOGUE_4');
  console.log('legacy browser history/SSE admission: PASS');
})().catch(error => { console.error(error); process.exitCode = 1; });
"""


class LegacyTurnCommitTest(unittest.TestCase):
    def test_failed_sse_not_replayed_and_s03_truth_visible(self):
        source = Path(__file__).with_name("nox_bridge.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        ui = next(
            stmt.value for stmt in tree.body
            if isinstance(stmt, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "UI" for t in stmt.targets)
        )
        html = ast.literal_eval(ui)
        result = subprocess.run(
            ["node", "-e", NODE],
            input=html,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(
            result.returncode, 0,
            f"Node browser fixture failed\nstdout={result.stdout}\nstderr={result.stderr}",
        )
        self.assertIn("PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
