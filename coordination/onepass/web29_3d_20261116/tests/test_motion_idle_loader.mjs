import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync(new URL('../site/nox-motion-idle-loader.js', import.meta.url), 'utf8');

class Target {
  constructor() { this.events = new Map(); }
  addEventListener(name, fn) {
    const a = this.events.get(name) || []; a.push(fn); this.events.set(name, a);
  }
  removeEventListener(name, fn) { this.events.set(name, (this.events.get(name) || []).filter(f => f !== fn)); }
  dispatchEvent(evt) { for (const f of [...(this.events.get(evt.type) || [])]) f(evt); }
  emit(name, detail = {}) { this.dispatchEvent({type: name, detail}); }
}

function harness({reduced = false, ready = 'complete', existing = false, origin = 'https://nox.test', nativeOwner = false} = {}) {
  const window = new Target(), document = new Target(), media = new Target();
  let idleId = 0, timeoutId = 0;
  const pending = new Map(), fallbacks = new Map(), injected = [], idleOptions = [];
  media.matches = reduced;
  document.hidden = false;
  document.readyState = ready;
  document.documentElement = {dataset: {typing:'false'}};
  document.body = {dataset: {trainingActive:'false'}};
  document.activeElement = {closest:()=>false};
  document.currentScript = {src: 'https://nox.test/nox-motion-idle-loader.js'};
  document.createElement = () => Object.assign(new Target(), {dataset: {}, remove() {this.removed = true;}});
  document.head = {appendChild: el => injected.push(el)};
  window.NoxWorkspace = {settings: {mode:'BALANCED', motion:'system'}};
  if (nativeOwner) window.NOX_NATIVE_OWNER = true;
  if (existing) window.Motion = {animate() {}};
  window.requestIdleCallback = (fn,opts) => { const id = ++idleId; idleOptions.push(opts); pending.set(id,fn); return id; };
  window.cancelIdleCallback = id => pending.delete(id);
  const setTimeout = fn => {const id = ++timeoutId;fallbacks.set(id,fn);return id;};
  const clearTimeout = id => fallbacks.delete(id);
  const sandbox = {window, document, location: {origin}, matchMedia:()=>media, URL,
    requestIdleCallback:window.requestIdleCallback, cancelIdleCallback:window.cancelIdleCallback,
    setTimeout,clearTimeout};
  vm.runInNewContext(source, sandbox, {filename:'nox-motion-idle-loader.js'});
  const flush = () => {const jobs = [...pending.values()];pending.clear(); for (const fn of jobs)fn();};
  const diag = () => window.NoxMotionIdleLoader?.diagnostics();
  return {window, document, media, pending, injected, idleOptions, flush, diag};
}

test('idle load: exactly one same-origin decorative script, never a native request', () => {
  const h = harness();
  assert.equal(h.diag().queued, true);
  h.flush();
  assert.equal(h.injected.length,1);
  assert.equal(h.injected[0].src, 'https://nox.test/vendor/fx/motion.js');
  assert.equal(h.injected[0].async,true);
  h.injected[0].emit('load');
  assert.equal(h.diag().loaded,true);
  h.window.emit('nox-settings');h.flush();
  assert.equal(h.injected.length,1);
});
test('chat blocks loading before first token', () => {
  const h = harness();
  h.window.emit('nox-chat-activity',{active:true});h.flush();
  assert.equal(h.diag().queued,false);
  assert.equal(h.injected.length,0);
  h.window.emit('nox-chat-activity',{active:false});h.flush();
  assert.equal(h.injected.length,1);
});
test('voice ending cannot override a running chat', () => {
  const h = harness();
  h.window.emit('nox-chat-activity',{active:true});
  h.window.emit('nox-voice-activity',{active:true});
  h.window.emit('nox-voice-activity',{active:false});h.flush();
  assert.equal(h.injected.length,0);
  h.window.emit('nox-chat-activity',{active:false});h.flush();
  assert.equal(h.injected.length,1);
});
test('reduced-motion OS setting prevents optional library request', () => {
  const h = harness({reduced:true});h.flush();
  assert.equal(h.injected.length,0);
  h.media.matches = false;h.media.emit('change');h.flush();
  assert.equal(h.injected.length,1);
});
test('explicit reduced motion and ECO block loading', () => {
  const h = harness();h.window.NoxWorkspace.settings.motion = 'reduce';
  h.window.emit('nox-settings');h.flush();assert.equal(h.injected.length,0);
  h.window.NoxWorkspace.settings.motion = 'system';h.window.NoxWorkspace.settings.mode='ECO';
  h.window.emit('nox-settings');h.flush();assert.equal(h.injected.length,0);
  h.window.NoxWorkspace.settings.mode='MAX';
  h.window.emit('nox-settings');h.flush();assert.equal(h.injected.length,1);
});
test('page hiding and STOP cancel idle callbacks; next chat idle is explicit', () => {
  const h = harness();h.document.hidden=true;h.document.emit('visibilitychange');h.flush();
  assert.equal(h.injected.length,0);
  h.document.hidden=false;h.document.emit('visibilitychange');
  h.window.emit('nox-stop-requested');h.flush();assert.equal(h.injected.length,0);
  h.window.emit('nox-chat-activity',{active:false});h.flush();
  assert.equal(h.injected.length,0);
  h.window.emit('nox-chat-activity',{active:true});
  h.window.emit('nox-chat-activity',{active:false});h.flush();
  assert.equal(h.injected.length,1);
});
test('load gate waits for existing page load event and never delays it', () => {
  const h = harness({ready:'loading'});
  assert.equal(h.pending.size,0);h.window.emit('load');assert.equal(h.pending.size,1);
});
test('already loaded Motion is reused, not loaded again', () => {
  const h = harness({existing:true});h.flush();assert.equal(h.injected.length,0);
  assert.equal(h.diag().loaded,true);
});
test('same-origin is mandatory', () => {
  const h = harness({origin:'https://other.host'});
  assert.equal(h.window.NoxMotionIdleLoader,undefined);
});
test('back-forward cache restoration can resume optional decoration', () => {
  const h = harness();h.window.dispatchEvent({type:'pagehide',persisted:true});h.flush();
  assert.equal(h.injected.length,0);
  h.window.dispatchEvent({type:'pageshow',persisted:true});h.flush();assert.equal(h.injected.length,1);
});

test('native owner fail-closed until known idle runtime (not timer alone)', () => {
  const h = harness({nativeOwner:true});
  assert.equal(h.diag().runtimeKnown,false);h.flush();assert.equal(h.injected.length,0);
  h.window.emit('nox-runtime-observed',{known:false,busy:false});h.flush();assert.equal(h.injected.length,0);
  h.window.emit('nox-runtime-observed',{known:true,busy:false});h.flush();assert.equal(h.injected.length,1);
});
test('native busy runtime blocks idle fetch before token events', () => {
  const h=harness();h.window.emit('nox-runtime-observed',{known:true,busy:true});h.flush();
  assert.equal(h.injected.length,0);h.window.emit('nox-runtime-observed',{known:true,busy:false});
  h.flush();assert.equal(h.injected.length,1);
});
test('media playback does not race with optional Motion download', () => {
  const h=harness();h.window.emit('nox-media-activity',{active:true});h.flush();assert.equal(h.injected.length,0);
  h.window.emit('nox-media-activity',{active:false});h.flush();assert.equal(h.injected.length,1);
});
test('typing and training-state idle gate is independent of the chat event', () => {
  const h=harness();h.document.documentElement.dataset.typing='true';
  h.window.emit('nox-typing');h.flush();assert.equal(h.injected.length,0);
  h.document.documentElement.dataset.typing='false';h.document.body.dataset.trainingActive='true';
  h.window.emit('nox-typing');h.flush();assert.equal(h.injected.length,0);
  h.document.body.dataset.trainingActive='false';h.window.emit('nox-training-activity');h.flush();
  assert.equal(h.injected.length,1);
});
test('requestIdleCallback no forced timeout under continuous token rendering', () => {
  const h=harness();assert.equal(h.idleOptions.length,1);assert.equal(h.idleOptions[0],undefined);
  h.window.emit('nox-chat-activity',{active:true});h.flush();assert.equal(h.injected.length,0);
});
test('reduced-motion CSS wins against original contrast and live shorthand', () => {
  const css=fs.readFileSync(new URL('../site/nox-cinematic-accessibility-3d.css', import.meta.url),'utf8');
  assert.match(css,/html:root:root:root:root body:is/);
  assert.match(css,/@media \(prefers-reduced-motion: reduce\)/);
  assert.doesNotMatch(css,/not\(\[data-theme="contrast"\]\)/);
});

test('native chat interrupts in-flight decorative fetch without stale completion', () => {
  const h=harness({nativeOwner:true});
  h.window.emit('nox-runtime-observed',{known:true,busy:false});
  h.flush();
  assert.equal(h.diag().inFlight,true);
  const old=h.injected[0];
  h.window.emit('nox-chat-activity',{active:true});
  assert.equal(old.removed,true);
  assert.equal(h.diag().started,false);
  assert.equal(h.diag().inFlight,false);
  old.emit('load');old.emit('error');
  assert.equal(h.diag().loaded,false);
  assert.equal(h.diag().failed,false);
  h.window.emit('nox-chat-activity',{active:false});
  h.flush();
  assert.equal(h.injected.length,2);
  assert.equal(h.diag().attempts,2);
  h.injected[1].emit('load');
  assert.equal(h.diag().loaded,true);
});

test('quiet runtime/settings notifications never cancel already admitted download', () => {
  const h=harness({nativeOwner:true});
  h.window.emit('nox-runtime-observed',{known:true,busy:false});
  h.flush();
  const old=h.injected[0];
  h.window.emit('nox-settings');
  h.window.emit('nox-runtime-observed',{known:true,busy:false});
  assert.equal(old.removed,undefined);
  assert.equal(h.diag().inFlight,true);
  assert.equal(h.diag().attempts,1);
  old.emit('load');
  assert.equal(h.diag().loaded,true);
  assert.equal(h.diag().inFlight,false);
});

test('STOP and pagehide abort only decorative in-flight work; BFCache resume is safe', () => {
  const h=harness();
  h.flush();
  const first=h.injected[0];
  h.window.emit('nox-stop-requested');
  assert.equal(first.removed,true);
  assert.equal(h.diag().inFlight,false);
  h.window.emit('nox-chat-activity',{active:false});
  h.flush();
  assert.equal(h.injected.length,1);
  h.window.emit('nox-chat-activity',{active:true});
  h.window.emit('nox-chat-activity',{active:false});
  h.flush();
  const second=h.injected[1];
  h.window.dispatchEvent({type:'pagehide',persisted:true});
  assert.equal(second.removed,true);
  h.window.dispatchEvent({type:'pageshow',persisted:true});
  h.flush();
  assert.equal(h.injected.length,3);
  h.injected[2].emit('load');
  assert.equal(h.diag().loaded,true);
});

test('STOP suppresses trailing aborted inactivity and duplicate active events', () => {
  const h=harness({nativeOwner:true});
  h.window.emit('nox-runtime-observed',{known:true,busy:false});
  h.flush();
  assert.equal(h.injected.length,1);
  h.window.emit('nox-chat-activity',{active:true});
  h.window.emit('nox-stop-requested');
  h.window.emit('nox-chat-activity',{active:true}); // duplicated active in old abort
  h.window.emit('nox-chat-activity',{active:false}); // finally after abort
  h.flush();
  assert.equal(h.injected.length,1);
  assert.equal(h.diag().stopped,true);
  h.window.emit('nox-chat-activity',{active:true}); // genuinely new request
  assert.equal(h.diag().stopped,false);
  h.window.emit('nox-chat-activity',{active:false});
  h.flush();
  assert.equal(h.injected.length,2);
});


test('BFCache resume cannot clear a prior chat STOP or fetch Motion during the aborted generation', () => {
  const h = harness({nativeOwner: true});
  h.window.emit('nox-runtime-observed', {known: true, busy: false});
  h.window.emit('nox-stop-requested');
  h.window.dispatchEvent({type: 'pagehide', persisted: true});
  h.window.dispatchEvent({type: 'pageshow', persisted: true});
  h.flush();
  assert.equal(h.diag().stopped, true, 'return from BFCache is not owner permission to clear STOP');
  assert.equal(h.injected.length, 0, 'no decorative network request after STOP');
  h.window.emit('nox-chat-activity', {active: false}); // delayed old stream completion
  h.flush();
  assert.equal(h.injected.length, 0);
  h.window.emit('nox-chat-activity', {active: true}); // genuinely new stream
  h.window.emit('nox-chat-activity', {active: false});
  h.flush();
  assert.equal(h.injected.length, 1, 'new user request may safely resume optional visuals');
  assert.equal(h.diag().stopped, false);
});
