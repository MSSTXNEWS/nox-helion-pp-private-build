/* Local protocol fixtures; no native/browser performance acceptance is claimed. */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const crypto = require('node:crypto');
const ROOT = 'coordination/onepass/';
const OLD = fs.readFileSync(ROOT + 'nox-v135-resonance-owner-bridge.js', 'utf8');
const SOURCE = fs.readFileSync(ROOT + 'nox-v135-resonance-owner-bridge-coalesced.js', 'utf8');
const ID = 'abcd1234abcd1234abcd1234abcd1234';
const PROMPT = 'Public coalescing protocol fixture';
const EXCHANGE = 'coalescing-exchange-01';
const encoder = new TextEncoder();
const tick = () => new Promise(resolve => setImmediate(resolve));

function clock(mode = 'held') {
  let serial = 0, peakFrames = 0, peakTimers = 0, requests = 0;
  const frames = new Map(), timers = new Map(), callbacks = [], real = new Map();
  const request = callback => {
    const id = ++serial; requests++; frames.set(id, callback); callbacks.push(callback);
    peakFrames = Math.max(peakFrames, frames.size);
    if (mode === 'real') real.set(id, setTimeout(() => {
      real.delete(id); if (frames.delete(id)) callback(performance.now());
    }, 2));
    return id;
  };
  const cancel = id => {
    frames.delete(id); clearTimeout(real.get(id)); real.delete(id);
  };
  const timer = (callback, milliseconds) => {
    const id = ++serial; timers.set(id, callback); callbacks.push(callback);
    peakTimers = Math.max(peakTimers, timers.size);
    if (mode !== 'held') real.set(id, setTimeout(() => {
      real.delete(id); if (timers.delete(id)) callback();
    }, milliseconds));
    return id;
  };
  const clear = id => {
    timers.delete(id); clearTimeout(real.get(id)); real.delete(id);
  };
  return {api: {requestAnimationFrame: request, cancelAnimationFrame: cancel,
      setTimeout: timer, clearTimeout: clear},
    flushFrame() {for (const [id, callback] of [...frames]) {cancel(id); callback(performance.now());}},
    flushLate() {for (const callback of [...callbacks]) callback(performance.now());},
    stats: () => ({frames: frames.size, timers: timers.size, peakFrames, peakTimers, requests}),
    close() {for (const id of frames.keys()) cancel(id); for (const id of timers.keys()) clear(id);}
  };
}

function fixture({answer = 'first second third', mode = 'held', legacy = false,
                  historyMismatch = false, onHistory, onPhase, source = SOURCE} = {}) {
  const schedule = clock(mode), trace = [], calls = [];
  let controller, upstreamSignal, nativeReads = 0, opened = false;
  let openResolve;
  const ready = new Promise(resolve => {openResolve = resolve;});
  const window = {NOX_NATIVE_OWNER: true, dispatchEvent(event) {
    trace.push({type: 'phase', phase: event.detail.phase}); onPhase?.(event);
  }};
  window.fetch = async (path, options = {}) => {
    const url = new URL(String(path), 'https://nox.local'); calls.push(url.pathname);
    if (url.pathname === '/api/nox/chat/stream') {
      assert.equal(options.credentials, 'same-origin');
      const payload = JSON.parse(options.body);
      assert.equal(payload.message, PROMPT); assert.equal(payload.dialog_id, ID);
      assert.deepEqual(payload.history, []);
      upstreamSignal = options.signal;
      const stream = new ReadableStream({start(value) {controller = value; opened = true; openResolve();}});
      const getReader = stream.getReader.bind(stream);
      stream.getReader = () => {
        const reader = getReader();
        return {read() {nativeReads++; return reader.read();}, cancel() {return reader.cancel();}};
      };
      upstreamSignal.addEventListener('abort', () => {
        try {controller.error(Error('fixture abort'));} catch {}
      }, {once: true});
      return new Response(stream, {headers: {'content-type': 'application/x-ndjson'}});
    }
    if (url.pathname === '/api/ui/memory/dialogs/history') {
      trace.push({type: 'history'}); await onHistory?.();
      return Response.json({status: 'READY', dialog_id: ID, messages: [
        {role: 'user', content: PROMPT, exchange_id: EXCHANGE},
        {role: 'assistant', content: answer, exchange_id: historyMismatch ? 'foreign-exchange' : EXCHANGE}
      ]});
    }
    throw Error('unexpected fixture route');
  };
  const location = {pathname: '/nox-web-v29/pc/resonance.html',
    href: 'https://nox.local/nox-web-v29/pc/resonance.html', origin: 'https://nox.local'};
  const context = {window, location, URL, Request, Response, ReadableStream,
    TextEncoder, TextDecoder, AbortController, performance, console, ...schedule.api,
    CustomEvent: class {constructor(type, init) {this.type = type; this.detail = init.detail;}}};
  if (legacy) context.Intl = {};
  vm.runInNewContext(source, context);
  const abort = new AbortController();
  const response = window.fetch('/api/nox/chat', {method: 'POST', signal: abort.signal,
    body: JSON.stringify({message: PROMPT, dialog_id: ID, request_id: 'fixture-01'})});
  const push = (...frames) => controller.enqueue(encoder.encode(frames.map(row => JSON.stringify(row) + '\n').join('')));
  const headers = () => push({type: 'preparing', stream_mode: 'NATIVE_TOKEN_STREAM'}, {type: 'start'});
  const delta = text => push({type: 'delta', text});
  const finish = (extra = []) => {
    push({type: 'done', saved: true, s03_integrated: true, dialog_id: ID, exchange_id: EXCHANGE}, ...extra);
    controller.close();
  };
  return {schedule, trace, calls, abort, response, ready, push, headers, delta, finish,
    closeNative: () => controller.close(),
    reads: () => nativeReads, signal: () => upstreamSignal, opened: () => opened};
}

async function collector(response) {
  const reader = (await response).body.getReader(), decoder = new TextDecoder(), events = [];
  const next = async () => {
    const part = await reader.read();
    if (part.done) return null;
    const raw = decoder.decode(part.value);
    assert(raw.startsWith('data: ') && raw.endsWith('\n\n'));
    const row = JSON.parse(raw.slice(6).trim()); events.push(row); return row;
  };
  const all = async () => {while (await next() !== null) {} return events;};
  return {reader, events, next, all};
}
const tokens = events => events.filter(row => row.type === 'token');
const joined = events => tokens(events).map(row => row.t).join('');

test('frozen source and all non-SSE protocol/route functions remain byte identical', () => {
  assert.equal(crypto.createHash('sha256').update(OLD).digest('hex'),
    '8781126ee4fccce89ea43c9b7852b67af627874e8a6580931ff379ced8261237');
  const begin = '  function sseChat(data,signal) {', end = '  const responseJSONStream=';
  const helper = '  // NOX_OWNER_COALESCED_STREAM_V1:';
  assert.equal(SOURCE.slice(0, SOURCE.indexOf(helper)), OLD.slice(0, OLD.indexOf(begin)));
  assert.equal(SOURCE.slice(SOURCE.indexOf(end)), OLD.slice(OLD.indexOf(end)));
  for (const fragment of [
    "const segmenter=canSegment?new Intl.Segmenter(undefined,{granularity:'grapheme'}):null;",
    "const glyphs=Array.from(segmenter.segment(trailing),part=>part.segment);",
    "trailing=glyphs.pop()||'';",
    "if(!accepted(receipt,id))throw Error('HOLD_S03_COMMIT_RECEIPT');",
    'await checkHistory(id,data.message,answer,receipt.exchange_id,nativeSignal);'
  ]) assert(SOURCE.includes(fragment) && OLD.includes(fragment));
});

test('two genuinely separated upstream arrivals produce proper prefixes before native done', {timeout: 2000}, async () => {
  const f = fixture({answer: 'first second third', mode: 'real'});
  try {
    const c = await collector(f.response); await f.ready; f.headers(); f.delta('first ');
    assert.equal((await c.next()).type, 'meta');
    const first = await c.next(); assert.equal(first.type, 'token'); assert.equal(first.t, 'first');
    assert(!f.calls.includes('/api/ui/memory/dialogs/history'));
    f.delta('second '); const second = await c.next();
    assert.equal(second.type, 'token'); assert.equal(second.t, ' second');
    assert('first second third'.startsWith(joined(c.events))); assert(joined(c.events).length < 18);
    f.delta('third'); f.finish(); await c.all();
    assert.equal(joined(c.events), 'first second third'); assert.equal(c.events.at(-1).type, 'done');
    assert.equal(f.calls.filter(path => path === '/api/nox/chat/stream').length, 1);
  } finally {f.schedule.close();}
});

test('native reader advances while one visual frame is pending; burst coalesces', {timeout: 2000}, async () => {
  const answer = 'abcdef'.repeat(1000), f = fixture({answer});
  const c = await collector(f.response); await f.ready; f.headers();
  f.push(...Array.from({length: 1000}, () => ({type: 'delta', text: 'abcdef'})));
  await tick();
  assert(f.reads() >= 3, 'producer must continue reader.read without waiting for a paint');
  assert.deepEqual(f.schedule.stats(), {frames: 1, timers: 1, peakFrames: 1, peakTimers: 1, requests: 1});
  assert.equal(f.trace.filter(row => row.phase === 'speaking').length, 0);
  f.finish(); await c.all();
  assert.equal(joined(c.events), answer); assert.equal(tokens(c.events).length, 1);
  assert.equal(f.schedule.stats().frames, 0); assert.equal(f.schedule.stats().timers, 0);
  assert(f.trace.findIndex(row => row.phase === 'speaking') < f.trace.findIndex(row => row.type === 'history'));
  f.schedule.flushLate(); assert.equal(tokens(c.events).length, 1);
});

test('EOF drains immediately before S03 and done, even with suspended schedulers', {timeout: 2000}, async () => {
  const f = fixture({answer: 'native final burst'}), c = await collector(f.response);
  await f.ready; f.headers(); f.delta('native final burst'); f.finish();
  await c.all();
  assert.equal(joined(c.events), 'native final burst');
  assert.deepEqual(c.events.map(row => row.type), ['meta', 'token', 'done']);
  assert(f.trace.findIndex(row => row.phase === 'speaking') < f.trace.findIndex(row => row.type === 'history'));
  assert(f.trace.findIndex(row => row.type === 'history') < f.trace.findIndex(row => row.phase === 'idle'));
  const before = f.trace.length; f.schedule.flushLate(); assert.equal(f.trace.length, before);
});

test('hidden-tab timer fallback publishes a real prefix while rAF stays suspended', {timeout: 2000}, async () => {
  const f = fixture({answer: 'visible prefix end', mode: 'timer'});
  try {
    const c = await collector(f.response); await f.ready; f.headers(); f.delta('visible prefix ');
    await c.next(); assert.equal((await c.next()).t, 'visible prefix');
    assert.equal(f.calls.filter(path => path.endsWith('/history')).length, 0);
    f.delta('end'); f.finish(); await c.all();
    assert.equal(joined(c.events), 'visible prefix end');
  } finally {f.schedule.close();}
});

test('downstream cancel clears queued fragments and stale callbacks cannot enqueue', {timeout: 2000}, async () => {
  const f = fixture(), c = await collector(f.response);
  await f.ready; f.headers(); f.delta('still queued'); await tick();
  assert.equal((await c.next()).type, 'meta'); await c.reader.cancel(); await tick();
  assert.equal(f.signal().aborted, true); assert.equal(f.schedule.stats().frames, 0);
  assert.equal(f.schedule.stats().timers, 0); const before = f.trace.length;
  f.schedule.flushLate(); assert.equal(f.trace.length, before);
  assert.equal(f.trace.filter(row => row.phase === 'speaking').length, 0);
  assert(!f.calls.includes('/api/ui/memory/dialogs/history')); assert(!f.calls.includes('/api/nox/stop'));
});

test('AbortSignal during queued output produces only stop error, no late token/done', {timeout: 2000}, async () => {
  const f = fixture(), c = await collector(f.response);
  await f.ready; f.headers(); f.delta('queued'); await tick(); f.abort.abort(); await c.all();
  assert.equal(tokens(c.events).length, 0); assert.equal(c.events.at(-1).error, 'STREAM_STOP_REQUESTED');
  const before = f.trace.length; f.schedule.flushLate(); assert.equal(f.trace.length, before);
  assert(!c.events.some(row => row.type === 'done'));
});

test('reentrant abort from speaking phase cannot enqueue a token after cancellation', {timeout: 2000}, async () => {
  let f; f = fixture({onPhase(event) {if (event.detail.phase === 'speaking') f.abort.abort();}});
  const c = await collector(f.response); await f.ready; f.headers(); f.delta('queued'); await tick();
  f.schedule.flushFrame(); await c.all();
  assert.equal(tokens(c.events).length, 0); assert.equal(c.events.at(-1).error, 'STREAM_STOP_REQUESTED');
  assert(!f.calls.includes('/api/ui/memory/dialogs/history'));
});

test('native error discards pending output and invalid terminal never performs S03', {timeout: 2000}, async () => {
  for (const bad of [{type: 'error', error: 'FIXTURE'}, {type: 'unknown'},
    {type: 'done', saved: false, s03_integrated: true, dialog_id: ID, exchange_id: EXCHANGE}]) {
    const f = fixture({answer: 'queued'}), c = await collector(f.response);
    await f.ready; f.headers(); f.delta('queued'); f.push(bad); f.closeNative(); await c.all();
    assert(!c.events.some(row => row.type === 'done'));
    assert.equal(c.events.at(-1).type, 'error'); assert(!f.calls.includes('/api/ui/memory/dialogs/history'));
    const before = f.trace.length; f.schedule.flushLate(); assert.equal(f.trace.length, before);
  }
});

test('strict NDJSON final-frame, frame-size and total-answer limits remain enforced', {timeout: 4000}, async () => {
  for (const kind of ['trailing', 'frame', 'max']) {
    const f = fixture(), c = await collector(f.response); await f.ready; f.headers();
    if (kind === 'trailing') {f.delta('text'); f.finish([{type: 'delta', text: 'extra'}]);}
    if (kind === 'frame') {f.push({type: 'delta', text: 'small', unused: 'x'.repeat(300001)}); f.closeNative();}
    if (kind === 'max') {f.delta('x'.repeat(200000)); f.delta('x'); f.closeNative();}
    await c.all(); assert(!c.events.some(row => row.type === 'done'));
    assert.match(c.events.at(-1).error, /HOLD_NATIVE_(TRAILING_FRAME_AFTER_DONE|FRAME_TOO_LARGE|DELTA)/);
    assert(!f.calls.includes('/api/ui/memory/dialogs/history'));
    const before = f.trace.length; f.schedule.flushLate(); assert.equal(f.trace.length, before);
  }
});

test('graphemes crossing native deltas retain exact content and safe prefix edges', {timeout: 2000}, async () => {
  const answer = 'prefix👨‍👩‍👧‍👦suffix e\u0301 done', split = answer.indexOf('👨') + 3;
  const f = fixture({answer}), c = await collector(f.response);
  await f.ready; f.headers(); f.delta(answer.slice(0, split)); await tick(); f.schedule.flushFrame();
  await c.next(); assert.equal((await c.next()).t, 'prefix');
  f.delta(answer.slice(split)); f.finish(); await c.all();
  assert.equal(joined(c.events), answer);
  let size = 0; const edges = new Set();
  for (const item of new Intl.Segmenter(undefined, {granularity: 'grapheme'}).segment(answer)) {
    size += item.segment.length; edges.add(size);
  }
  size = 0; for (const item of tokens(c.events)) {size += item.t.length; assert(edges.has(size));}
});

test('legacy browser without Segmenter retains whole-response fallback', {timeout: 2000}, async () => {
  const answer = 'prefix👨‍👩‍👧‍👦suffix', f = fixture({answer, legacy: true});
  const c = await collector(f.response); await f.ready; f.headers(); f.delta(answer.slice(0, 10));
  await tick(); assert.equal(f.schedule.stats().requests, 0);
  f.delta(answer.slice(10)); f.finish(); await c.all();
  assert.equal(joined(c.events), answer); assert.equal(tokens(c.events).length, 1);
  assert.equal(c.events.at(-1).history_persisted, true);
});

test('S03 mismatch or abort during readback never becomes done', {timeout: 2000}, async () => {
  for (const abortHistory of [false, true]) {
    let f; f = fixture({answer: 'exact answer', historyMismatch: !abortHistory,
      onHistory() {if (abortHistory) f.abort.abort();}});
    const c = await collector(f.response); await f.ready; f.headers(); f.delta('exact answer'); f.finish();
    await c.all(); assert.equal(joined(c.events), 'exact answer');
    assert.equal(c.events.at(-1).type, 'error'); assert(!c.events.some(row => row.type === 'done'));
    const before = f.trace.length; f.schedule.flushLate(); assert.equal(f.trace.length, before);
  }
});

test('scheduled rendering failure aborts the owned upstream and stays categorical', {timeout: 2000}, async () => {
  const f = fixture({onPhase(event) {if (event.detail.phase === 'speaking') throw Error('private fixture text');}});
  const c = await collector(f.response); await f.ready; f.headers(); f.delta('queued'); await tick();
  f.schedule.flushFrame(); await c.all();
  assert.equal(f.signal().aborted, true); assert.equal(c.events.at(-1).error, 'HOLD_NATIVE_RENDER_QUEUE');
  assert(!JSON.stringify(c.events).includes('private fixture')); assert(!c.events.some(row => row.type === 'done'));
  const before = f.trace.length; f.schedule.flushLate(); assert.equal(f.trace.length, before);
});
