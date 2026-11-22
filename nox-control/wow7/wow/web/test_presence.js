// node --test web/test_presence.js
const test = require('node:test'), assert = require('node:assert');
const P = require('./presence.js');

test('moodToVisual: спокойный циан, тревога янтарь/дрожь', () => {
  const calm = P.moodToVisual({ p: 0.8, a: -0.2, d: 0.3 }, {});
  assert.ok(calm.rgb[0] < 160 && calm.rgb[2] > 200, 'циан');
  assert.equal(calm.jitter, 0);
  const fear = P.moodToVisual({ p: -0.5, a: 0.6, d: -0.4 }, { vanish: 0.9 });
  assert.ok(fear.rgb[0] > 200, 'тёплый');
  assert.ok(fear.jitter > 0.8);
  assert.ok(fear.period < calm.period, 'возбуждение дышит чаще');
  const d = P.moodToVisual(null, null); assert.equal(d.fear, 0);
  const wild = P.moodToVisual({ p: 99, a: -99, d: 99 }, {}); assert.ok(wild.period <= 6.5 && wild.glow <= 1);
});

test('stateBadge', () => {
  assert.equal(P.stateBadge('speaking', 'доволен'), 'ГОВОРИТ · ДОВОЛЕН');
  assert.equal(P.stateBadge('???'), 'ПОКОЙ');
});

test('poller: состояние -> outbox -> ack; ошибка -> backoff', async () => {
  const calls = [], states = [], msgs = [], errs = [], delays = [];
  let fail = false;
  const fetch = async (url, init) => {
    calls.push((init && init.method || 'GET') + ' ' + url);
    if (fail) return { ok: false, status: 502, json: async () => ({}) };
    if (url.endsWith('/state')) return { ok: true, json: async () => ({ mood: { p: 0 }, outbox: 2 }) };
    if (url.endsWith('/outbox')) return { ok: true, json: async () => ({ messages: [{ id: 'm1', text: 'a' }, { id: 'm2', text: 'b' }] }) };
    return { ok: true, json: async () => ({ ok: true }) };
  };
  let next; const setTimeout_ = (fn, ms) => { delays.push(ms); next = fn; return 1; };
  const p = P.createPoller({ fetch, base: '/presence', poll: 1000, setTimeout: setTimeout_, clearTimeout() {}, onState: (s) => states.push(s), onMessage: (m) => { msgs.push(m.id); if (m.id === 'm1') throw new Error('ui'); }, onError: (e, n) => errs.push(n) });
  p.start(); await new Promise((r) => setImmediate(r)); await new Promise((r) => setImmediate(r));
  assert.deepEqual(msgs, ['m1', 'm2']);
  assert.ok(calls.includes('POST /presence/ack'));
  assert.equal(delays[0], 1000);
  fail = true; next(); await new Promise((r) => setImmediate(r)); await new Promise((r) => setImmediate(r));
  assert.deepEqual(errs, [1]); assert.equal(delays[1], 2000);
  next(); await new Promise((r) => setImmediate(r)); await new Promise((r) => setImmediate(r));
  assert.equal(delays[2], 4000);
  p.stop();
});

test('mount без DOM возвращает null', () => { assert.equal(P.mount(null, {}), null); });

test('mount на заглушке DOM: кадры рисуются, теги и состояния работают', async () => {
  const noop = new Proxy(function () {}, { get: (t, k) => (k === 'addColorStop' ? () => {} : noop), apply: () => noop });
  const mk = () => { const kids = [], el = { style: { setProperty() {} }, children: kids, classList: { add() {} }, setAttribute() {}, getAttribute() {}, addEventListener() {}, appendChild(c) { kids.push(c); return c; }, remove() {},
    querySelector(s) { return s === 'canvas' ? cv : el; }, getBoundingClientRect: () => ({ left: 0, top: 0, width: 160, height: 160 }), set innerHTML(v) {}, set textContent(v) { kids.length = 0; this._t = v; } }; return el; };
  const cv = Object.assign(mk(), { getContext: () => new Proxy({ createRadialGradient: () => ({ addColorStop() {} }) }, { get: (t, k) => (k in t ? t[k] : () => {}), set: () => true }) });
  const events = [], frames = [];
  global.window = { matchMedia: () => ({ matches: false }), dispatchEvent: (e) => events.push(e.type), addEventListener() {}, removeEventListener() {}, MutationObserver: undefined };
  global.CustomEvent = function (t, o) { this.type = t; this.detail = o && o.detail; };
  global.document = { hidden: false, body: mk(), createElement: () => mk(), getElementById: () => null, querySelector: () => null };
  global.performance = { now: () => 1000 };
  global.requestAnimationFrame = (fn) => { frames.push(fn); return frames.length; };
  global.cancelAnimationFrame = () => {};
  global.fetch = undefined;
  const h = P.mount(null, { base: false, autoBind: false });
  assert.ok(h);
  for (const s of P.STATES) { h.setState(s); h.setLevel(0.5); h.setMood({ p: -0.6, a: 0.7, d: -0.2, label: 'встревожен' }, { vanish: 0.95 }); h.nudge(); for (let t = 1000; t < 9000; t += 500) { const f = frames.shift(); f && f(t); } }
  h.setTags([{ id: 't1', text: 'баланс Vast', importance: 0.9 }]);
  assert.ok(events.includes('nox:presence-state'));
  h.destroy();
  delete global.window; delete global.document; delete global.performance; delete global.requestAnimationFrame; delete global.cancelAnimationFrame;
});
