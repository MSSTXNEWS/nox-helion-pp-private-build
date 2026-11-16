'use strict';
// Local behavior fixtures only; no native requests, user history, or model generation.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const crypto = require('node:crypto');

const source = fs.readFileSync(path.join(__dirname, 'nox-v24-chat-markdown-final.js'), 'utf8');
const marker = '  /* ---- cursor-reactive light (one layer, rAF, skipped in ECO/STOP/reduced) ---- */';
const begin = source.indexOf('  function md(text) {');
const end = source.indexOf(marker);
assert.ok(begin > 0 && end > begin);

function runtime() {
  let now = 0;
  const timers = [], calls = [], writes = [];
  const window = {};
  const context = vm.createContext({window, WeakMap, performance: {now: () => now},
    setTimeout(fn, delay) { timers.push({fn, at: now + delay}); return timers.length; }});
  vm.runInContext(source.slice(begin, end) + '\nglobalThis.render = renderSafeMarkdown;', context);
  function node() {
    let text = '', html = '';
    return {isConnected: true,
      get textContent() { return text; },
      set textContent(value) { text = String(value); html = ''; },
      get innerHTML() { return html; },
      set innerHTML(value) { html = value; writes.push(value); },
      querySelectorAll() { return []; }};
  }
  function ready(html = '<p>sanitized</p>') {
    window.marked = {parse(text, options) { calls.push(['parse', text, options]); return '<raw>' + text; }};
    window.DOMPurify = {sanitize(value, options) { calls.push(['sanitize', value, options]); return html; }};
  }
  function tick(at) {
    const item = timers.shift();
    assert.ok(item, 'a bounded scheduled attempt must exist');
    now = at === undefined ? item.at : at;
    item.fn();
  }
  return {render: context.render, node, window, ready, calls, timers, writes, tick};
}

const tests = [
  ['all unrelated V24 behavior remains the exact verified preimage', () => {
    const helperStart = source.indexOf('  // Final formatting owns only its original message node');
    assert.ok(helperStart > begin && helperStart < end);
    let original = source.slice(0, helperStart) + source.slice(end);
    original = original.replace("      renderSafeMarkdown(b, text || '');",
      "      const h = md(text || ''); if (h !== null) { b.innerHTML = h; highlight(b); } else b.textContent = text;");
    original = original.replace(
      "        if (result && done.status === 'done' && !controller.signal.aborted) renderSafeMarkdown(out.body, result);\n        else if (!result) out.body.textContent = done.status === 'STOP_FLAG' ? '— STOP активен —' : '—';",
      "        const h = result && md(result); if (h) { out.body.innerHTML = h; highlight(out.body); } else if (!result) out.body.textContent = done.status === 'STOP_FLAG' ? '— STOP активен —' : '—';");
    assert.equal(crypto.createHash('sha256').update(original).digest('hex'),
      '3427be9e0a497ad0dd120daaa5007f0daa32f3c97271a10ee3b5f1567abcdd8a');
  }],
  ['only a string returned by the sanitizer reaches the HTML sink', () => {
    const r = runtime(), n = r.node(), raw = '<img src=x onerror=alert(1)> **text**';
    r.ready('<p>clean text</p>'); r.render(n, raw);
    assert.deepEqual(r.writes, ['<p>clean text</p>']);
    assert.equal(r.calls[0][0], 'parse'); assert.equal(r.calls[0][1], raw);
    assert.equal(r.calls[1][0], 'sanitize'); assert.equal(r.calls[1][1], '<raw>' + raw);
    assert.equal(r.calls[1][2].USE_PROFILES.html, true); assert.equal(r.timers.length, 0);
  }],
  ['late libraries format the same live node without any request or awaited cleanup', () => {
    const r = runtime(), n = r.node();
    assert.equal(r.render(n, '### late'), undefined);
    assert.equal(n.textContent, '### late'); assert.equal(r.writes.length, 0);
    r.ready('<h3>late</h3>'); r.tick();
    assert.equal(n.innerHTML, '<h3>late</h3>'); assert.equal(r.timers.length, 0);
  }],
  ['missing, throwing, and non-string renderers remain literal and bounded', () => {
    for (const fault of ['missing', 'throw', 'object']) {
      const r = runtime(), n = r.node();
      if (fault !== 'missing') {
        r.ready(fault === 'object' ? {unsafe: '<script>bad</script>'} : 'unused');
        if (fault === 'throw') r.window.DOMPurify.sanitize = () => { throw Error('fixture'); };
      }
      r.render(n, '**literal**'); let checks = 0;
      while (r.timers.length) { r.tick(); checks++; assert.ok(checks <= 4); }
      assert.equal(checks, 4); assert.equal(n.textContent, '**literal**');
      assert.deepEqual(r.writes, []);
    }
  }],
  ['detached or subsequently edited nodes are never overwritten by delayed formatting', () => {
    for (const detached of [true, false]) {
      const r = runtime(), n = r.node(); r.render(n, '**old**');
      if (detached) n.isConnected = false; else n.textContent = 'new independent content';
      r.ready(); r.tick(); assert.deepEqual(r.writes, []); assert.equal(r.timers.length, 0);
      assert.equal(n.textContent, detached ? '**old**' : 'new independent content');
    }
  }],
  ['a newer message ticket invalidates an older scheduled callback', () => {
    const r = runtime(), n = r.node();
    r.render(n, '**old**'); r.render(n, '**new**'); r.ready('<p>new</p>');
    r.tick(); assert.deepEqual(r.writes, []);
    r.tick(); assert.deepEqual(r.writes, ['<p>new</p>']);
    assert.equal(r.calls[0][1], '**new**');
  }],
  ['a suspended tab cannot resume formatting after the two-second deadline', () => {
    const r = runtime(), n = r.node(); r.render(n, '**late**'); r.ready(); r.tick(2500);
    assert.deepEqual(r.writes, []); assert.equal(r.timers.length, 0);
  }],
  ['history can prepare a detached node, while deferred work requires its attachment', () => {
    const r = runtime(), n = r.node(); n.isConnected = false;
    r.ready('<p>history</p>'); r.render(n, '**history**');
    assert.equal(n.innerHTML, '<p>history</p>'); assert.equal(r.timers.length, 0);
  }]
];

for (const [name, test] of tests) { test(); process.stdout.write('PASS ' + name + '\n'); }
process.stdout.write(`${tests.length} local tests passed; native final-DOM acceptance remains separate.\n`);
