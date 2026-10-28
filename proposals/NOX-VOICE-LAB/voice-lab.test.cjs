/* NOX V16 P02 Voice Lab: actual client module regression; no network or microphone.
 * Run: node --test proposals/NOX-VOICE-LAB/voice-lab.test.cjs
 * Covers STOP=discard, explicit send, late permission and lifecycle races.
 */
'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const voice = require('./voice-lab.js');

function stage({ pendingPermission = false } = {}) {
  class Element {
    constructor(tag) {
      this.tag = tag; this.nodeType = 1; this.children = [];
      this.textContent = ''; this.value = ''; this.disabled = false;
      this.hidden = false; this.style = {};
    }
    append(...children) { this.children.push(...children); }
    replaceChildren(...children) { this.children = [...children]; }
    setAttribute() {}
    remove() { this.removed = true; }
  }
  const handlers = new Map();
  global.document = {
    hidden: false,
    createElement: tag => new Element(tag),
    addEventListener: (event, cb) => handlers.set(event, cb),
    removeEventListener: event => handlers.delete(event)
  };
  const stream = () => {
    const track = { stopped: false, stop() { this.stopped = true; } };
    return { track, getTracks() { return [track]; } };
  };
  const feeds = [];
  let resolvePermission;
  global.navigator = {
    mediaDevices: { getUserMedia: () => pendingPermission
      ? new Promise(resolve => { resolvePermission = resolve; })
      : Promise.resolve(stream()) }
  };
  class Recorder {
    static instances = [];
    static isTypeSupported() { return true; }
    constructor(media, options = {}) {
      this.stream = media; this.mimeType = options.mimeType || 'audio/webm';
      this.state = 'inactive'; Recorder.instances.push(this);
    }
    start() { this.state = 'recording'; }
    stop() {
      assert.equal(this.state, 'recording');
      this.state = 'inactive';
      queueMicrotask(() => {
        this.ondataavailable?.({ data: new Blob(['recorded-voice']) });
        this.onstop?.();
      });
    }
  }
  global.MediaRecorder = Recorder;
  const root = new Element('div');
  const bridge = { dispatch: async () => ({}), onAudio: async data => { feeds.push(data); } };
  const app = voice.mount(root, bridge);
  const walk = node => [node, ...node.children.flatMap(walk)];
  const button = text => walk(root).find(x => x.tag === 'button' && x.textContent === text);
  const capture = button('Записать 30 секунд');
  const stop = button('STOP');
  const settle = () => new Promise(resolve => setImmediate(resolve));
  return { app, root, handlers, capture, stop, feeds, Recorder, stream, settle,
    selectors: () => walk(root).filter(x => x.tag === 'select'),
    permit: () => { assert.ok(resolvePermission); const s = stream(); resolvePermission(s); return s; } };
}

test('STOP revokes microphone and never forwards captured audio', async () => {
  const s = stage();
  s.capture.onclick(); await s.settle();
  const active = s.Recorder.instances[0];
  assert.equal(active.state, 'recording');
  s.stop.onclick(); await s.settle();
  assert.equal(active.stream.track.stopped, true);
  assert.equal(s.feeds.length, 0);
  s.app.destroy();
});

test('explicit Record->Send delivers one approved audio blob, no duplicate send', async () => {
  const s = stage();
  s.capture.onclick(); await s.settle();
  assert.equal(s.capture.textContent, 'Отправить аудио');
  s.capture.onclick(); await s.settle();
  assert.equal(s.feeds.length, 1);
  assert.ok(s.feeds[0].audio instanceof Blob);
  assert.equal(s.feeds[0].mode, 'translate');
  assert.equal(s.feeds[0].direction, 'ru-es');
  assert.equal(s.Recorder.instances[0].stream.track.stopped, true);
  s.app.destroy();
  assert.equal(s.feeds.length, 1);
});

test('hidden tab cancels recorder before final dataavailable', async () => {
  const s = stage();
  s.capture.onclick(); await s.settle();
  global.document.hidden = true;
  s.handlers.get('visibilitychange')();
  await s.settle();
  assert.equal(s.feeds.length, 0);
  assert.equal(s.Recorder.instances[0].stream.track.stopped, true);
  s.app.destroy();
});

test('STOP before getUserMedia resolves closes late stream without dispatch', async () => {
  const s = stage({pendingPermission:true});
  s.capture.onclick(); await Promise.resolve();
  s.stop.onclick();
  const late = s.permit(); await s.settle();
  assert.equal(late.track.stopped, true);
  assert.equal(s.Recorder.instances.length, 0);
  assert.equal(s.feeds.length, 0);
  s.app.destroy();
});

test('destroy before microphone permission resolves must not leak acquired tracks', async () => {
  const s = stage({pendingPermission:true});
  s.capture.onclick(); await Promise.resolve();
  s.app.destroy();
  const late = s.permit(); await s.settle();
  assert.equal(late.track.stopped, true);
  assert.equal(s.feeds.length, 0);
});

test('destroy during recording discards data on delayed onstop', async () => {
  const s = stage();
  s.capture.onclick(); await s.settle();
  s.app.destroy(); await s.settle();
  assert.equal(s.feeds.length, 0);
  assert.equal(s.Recorder.instances[0].stream.track.stopped, true);
});

test('switching translation/MAESTRO cancels the previous audio epoch', async () => {
  const s = stage();
  s.capture.onclick(); await s.settle();
  const modes = s.selectors()[0];
  modes.value = 'maestro'; modes.onchange(); await s.settle();
  assert.equal(s.feeds.length, 0);
  assert.equal(s.Recorder.instances[0].stream.track.stopped, true);
  s.app.destroy();
});

test('spontaneous media recorder stop is discard, not implicit consent', async () => {
  const s = stage();
  s.capture.onclick(); await s.settle();
  const current = s.Recorder.instances[0];
  current.stop(); await s.settle();
  assert.equal(s.feeds.length, 0);
  s.app.destroy();
});
