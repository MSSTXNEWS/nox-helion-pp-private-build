/* NOX V16 W2.03 R20: approved Cinema FX must re-arm rare gravitational
 * ejecta after REDUCED -> active, not leave the original nine orb timers at
 * Infinity. Real owner module, deterministic fake DOM/clock. SOURCE ONLY.
 * Run: node --test qa/G3-03/tests/nox-cinema-reduced-resume-ejecta-r20.test.mjs
 * No EXE, network, new renderer, asset replacement, or native event mocks.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import {installNoxCinemaFX} from '../../../proposals/NOX-CINEMA-FX/nox-cinema.mjs';

const IDS = ['HELION', 'CONSCIOUSNESS', 'PERSONA', 'ATLAS', 'VOICE',
  'REFLECTION', 'CORE', 'NEXUS', 'FORGE'];

function fixture() {
  let time = 1000, nextId = 0;
  const pending = new Map();
  const view = {
    requestAnimationFrame(fn) { const id = ++nextId; pending.set(id, fn); return id; },
    cancelAnimationFrame(id) { pending.delete(id); },
    matchMedia() { return {matches: false, addEventListener() {}, removeEventListener() {}}; }
  };
  class Element {
    constructor(doc) {
      this.nodeType = 1; this.ownerDocument = doc; this.children = [];
      this.parent = null; this.dataset = {}; this.attributes = {};
      const classes = new Set();
      this.classList = {contains: x => classes.has(x), add: x => classes.add(x),
        remove: x => classes.delete(x)};
    }
    appendChild(child) { child.parent = this; this.children.push(child); return child; }
    remove() {
      if (this.parent) this.parent.children = this.parent.children.filter(x => x !== this);
      this.parent = null;
    }
    contains(child) { return child === this || this.children.some(x => x.contains(child)); }
    querySelector() { return null; }
    setAttribute(k, v) { this.attributes[k] = String(v); }
  }
  const doc = {defaultView: view, hidden: false,
    addEventListener() {}, removeEventListener() {},
    createElement() { return new Element(doc); },
    createElementNS() { return new Element(doc); }};
  const root = new Element(doc);
  const orbs = IDS.map(id => ({id, element: root.appendChild(new Element(doc))}));
  const fx = installNoxCinemaFX({root, orbs, profile: 'BALANCED',
    random: () => 0, clock: () => time});
  function tick(now) {
    time = now;
    const frame = [...pending.values()]; pending.clear();
    for (const fn of frame) fn(now);
  }
  return {fx, tick, root, orbs};
}

for (const {mode, early, late} of [
  {mode: 'BALANCED', early: 17000, late: 40000},
  {mode: 'ECO', early: 35000, late: 55000},
  {mode: 'MAX', early: 16000, late: 28000}
]) {
  test('R20-EJECTA-' + mode + ': REDUCED -> ' + mode + ' restores finite rare bursts', () => {
    const {fx, tick, orbs} = fixture();
    try {
      assert.deepEqual(orbs.map(o => o.id), IDS, 'original HELION + 8 CoreID preserved');
      tick(10000);
      const before = fx.snapshot().emitted;
      assert.ok(before > 0, 'initial approved cinematic ejecta must be real');
      assert.equal(fx.setProfile('REDUCED'), true);
      assert.equal(fx.snapshot().active, false);
      assert.equal(fx.setProfile(mode), true);
      tick(early);
      assert.equal(fx.snapshot().emitted, before,
        mode + ' must not fire a premature burst immediately after resume');
      tick(late);
      assert.ok(fx.snapshot().emitted > before,
        'RED: ' + mode + ' remains permanently quiet after REDUCED (deadline Infinity)');
    } finally { fx.destroy(); }
  });
}
